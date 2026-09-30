"""PadMint: build your own copy of a supported Pad game on your own computer.

Run with no command for the guided path. Other commands: make, list, doctor,
tools, get, check-manifest, audit, plan, build. Game backends keep their own
validation and caching; PadMint validates inputs, runs the backend, relays
progress, and records and audits the result.
"""
import argparse
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
import urllib.parse
import uuid

from . import __version__, awake, game_file, gate, tools
from .manifest import (RUNNABLE_STATES, NeedsNewerPadMint, catalog, expand, host_id, load_manifest,
                       manifest_for, manifest_sha256, needs_build_input, on_android,
                       repository_manifest)
from .package import validate_ipa


def git(repo, *args):
    return subprocess.check_output([tools.executable("git", host_id()), "-C", str(repo), *args],
                                   text=True).strip()


def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def atomic_json(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    temporary.replace(path)


@contextlib.contextmanager
def workspace_lock(path):
    # Kernel releases the lock on exit/crash; do not delete the lock file.
    with path.open("a") as stream:
        if os.name == "nt":
            import msvcrt
            try:
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                raise ValueError("Another PadMint process is using this checkout") from None
            try:
                yield
            finally:
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            return
        import fcntl
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("Another PadMint process is using this checkout") from None
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def check_checkout(repo, revision):
    if git(repo, "rev-parse", "HEAD") != revision:
        raise ValueError("Backend HEAD does not match --revision")
    if git(repo, "status", "--porcelain", "--untracked-files=normal"):
        raise ValueError("Backend has local changes; use a clean reviewed checkout")


def selection(args, repo):
    """Return (manifest, target name, target) for the requested game and target."""
    manifest, _source = manifest_for(args.game, repo)
    name = getattr(args, "target", None) or "ios"
    target = manifest["targets"].get(name)
    if target is None:
        raise ValueError(f"{manifest['name']} does not declare a {name} target")
    if "command" not in target and "steps" not in target:
        raise ValueError(f"{manifest['name']} {name} builds are planned, not implemented")
    return manifest, name, target


def validate(args):
    repo = args.repo.expanduser().resolve()
    if not re.fullmatch(r"[0-9a-f]{40}", args.revision):
        raise ValueError("--revision must be the full reviewed Git commit (40 lowercase hex digits)")
    # Compare as paths: Git on Windows reports C:/x/y with forward slashes.
    if Path(git(repo, "rev-parse", "--show-toplevel")).resolve() != repo:
        raise ValueError("--repo must be the root of the selected backend checkout")
    check_checkout(repo, args.revision)
    manifest, _name, target = selection(args, repo)
    disc = None
    if needs_build_input(manifest):
        if getattr(args, "disc", None) is None:
            raise ValueError(f"{manifest['name']} needs --disc: your own game image is read during the build")
        disc = args.disc.expanduser().resolve()
        if not disc.is_file():
            raise ValueError("Disc image must be an existing local file")
    elif getattr(args, "disc", None) is not None:
        raise ValueError(f"{manifest['name']} does not read game files during the build; "
                         "import them in the app instead of passing --disc")
    templates = [target["command"]] if "command" in target else [step["command"] for step in target["steps"]]
    for template in templates:
        # Only the program being run must already exist; other paths may be build outputs.
        interpreters = {"bash", "sh", "zsh", "python", "python3"}
        script = template[0] if template[0].startswith("{repo}/") else (
            template[1] if len(template) > 1 and Path(template[0]).name in interpreters
            and template[1].startswith("{repo}/") else None)
        if script and not (repo / script[len("{repo}/"):]).is_file():
            raise ValueError(f"Selected checkout does not contain {script[len('{repo}/'):]}")
    if args.source_only and "source-only" not in target.get("modes", {}):
        raise ValueError(f"{manifest['name']} does not expose source-only builds through its CLI")
    if args.no_mods and "no-mods" not in target.get("options", {}):
        raise ValueError(f"{manifest['name']} does not expose mod selection through its CLI")
    return repo, disc


def command(args, repo, disc, work, output):
    _manifest, _name, target = selection(args, repo)
    values = placeholder_values(args, repo, disc, work, output)
    if "steps" in target:
        return [expand(step["command"], values) for step in target["steps"]]
    mode = "source-only" if args.source_only else "full"
    argv = expand(target["command"], values) + expand(target.get("modes", {}).get(mode, []), values)
    if args.no_mods:
        argv += expand(target["options"]["no-mods"], values)
    return argv


def run_process(argv, cwd, log_path, event_path, emit, before_spawn=None, append=False, env=None):
    """Relay new backend events; retain complete output in a private local log."""
    offset = event_path.stat().st_size if event_path.exists() else 0
    pending = b""

    def relay():
        nonlocal offset, pending
        if not event_path.exists():
            return
        if event_path.stat().st_size < offset:
            offset, pending = 0, b""
        with event_path.open("rb") as stream:
            stream.seek(offset)
            data = stream.read(65536)
            offset = stream.tell()
        pending += data
        while b"\n" in pending:
            line, pending = pending.split(b"\n", 1)
            try:
                event = json.loads(line)
                if isinstance(event, dict) and event.get("schema_version") == 1:
                    emit("backend_event", backend=event)
            except (ValueError, UnicodeError):
                emit("progress_warning", reason="Malformed backend event; see local log")
        if len(pending) > 1024 * 1024:
            pending = b""
            emit("progress_warning", reason="Oversized backend event skipped")
        return bool(data)

    def drain():
        # Keep live polls bounded, but read every remaining chunk after shutdown.
        while relay():
            pass

    def interrupt(_signum, _frame):
        raise KeyboardInterrupt

    previous = signal.signal(signal.SIGTERM, interrupt)
    process = None
    try:
        with log_path.open("ab" if append else "wb") as log:
            if before_spawn is not None:
                before_spawn()
            group = ({"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt"
                     else {"start_new_session": True})
            process = subprocess.Popen(argv, cwd=cwd, stdout=log, env=env,
                                       stderr=subprocess.STDOUT, **group)
            last_progress = time.monotonic()
            while process.poll() is None:
                relay()
                if time.monotonic() - last_progress >= 15:
                    emit("build_progress", status="running; see backend.log")
                    last_progress = time.monotonic()
                time.sleep(0.2)
            drain()
            return process.returncode, False
    except KeyboardInterrupt:
        if process is not None and os.name == "nt":
            # Stop the backend and everything it started.
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(process.pid)], capture_output=True)
            process.wait()
            drain()
        elif process is not None:
            # BlueWake's stage wrapper forwards TERM to its own child session.
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            deadline = time.monotonic() + 20
            while True:
                process.poll()
                try:
                    os.killpg(process.pid, 0)
                except ProcessLookupError:
                    break
                if time.monotonic() >= deadline:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    break
                time.sleep(0.1)
            process.wait()
            drain()
        return 130, True
    finally:
        signal.signal(signal.SIGTERM, previous)


def run_steps(steps, argvs, cwd, log_path, event_path, emit, before_each, values=None, tool_names=()):
    """Run a manifest's ordered steps; PadMint emits the stage events itself."""
    event_path.parent.mkdir(parents=True, exist_ok=True)
    code, cancelled = 0, False
    for step, argv in zip(steps, argvs):
        stage = step["stage"]
        env = backend_env((values or {}).get("jobs"), tool_names)
        if step.get("env"):
            env.update({key: expand([value], values or {})[0] for key, value in step["env"].items()})
        argv = with_python_path(argv, env)
        emit("backend_event", backend={"schema_version": 1, "event": "stage_started", "stage": stage})
        code, cancelled = run_process(argv, cwd, log_path, event_path, emit,
                                      before_spawn=before_each, append=True, env=env)
        if cancelled or code != 0:
            emit("backend_event", backend={"schema_version": 1, "stage": stage, "exit_code": code,
                                           "event": "stage_cancelled" if cancelled else "stage_failed"})
            break
        emit("backend_event", backend={"schema_version": 1, "event": "stage_completed", "stage": stage})
    return code, cancelled


def placeholder_values(args, repo, disc, work, output):
    return {"repo": str(repo), "disc": str(disc) if disc else "", "work": str(work),
            "output": str(output), "jobs": str(args.jobs), "app": app_path(args),
            "python": sys.executable}


def with_python_path(argv, env):
    """Run a `{python} -m module` step with its PYTHONPATH on sys.path itself.

    Windows PadMint ships Python's embeddable package, whose ._pth file makes
    Python ignore PYTHONPATH, so `-m` could not find a game's builder there."""
    if not env.get("PYTHONPATH") or len(argv) < 3 or argv[0] != sys.executable or argv[1] != "-m":
        return argv
    shim = ("import os, runpy, sys; "
            "sys.path[:0] = [p for p in os.environ['PYTHONPATH'].split(os.pathsep) if p]; "
            f"runpy.run_module({argv[2]!r}, run_name='__main__', alter_sys=True)")
    return [argv[0], "-c", shim, *argv[3:]]


def app_path(args):
    app = getattr(args, "app", None)
    return str(app.expanduser().resolve()) if app else ""


def backend_env(jobs, tool_names=()):
    """Environment for backend processes: PadMint's tools first on PATH, and the
    job cap for `cmake --build`. PADMINT_CACHE is a folder shared by every
    checkout of every game version, for downloads a backend can reuse after an
    update (it must still check them, as for any cache)."""
    env = tools.environment(tool_names, host_id()) if tool_names else dict(os.environ)
    if jobs:
        env.setdefault("CMAKE_BUILD_PARALLEL_LEVEL", str(jobs))
    env.setdefault("PADMINT_CACHE", str(tools.tools_root().parent / "cache"))
    # Game repositories written for PadForge (PadMint's name before 0.2.0) read
    # PADFORGE_* names; give them the same values until they read PADMINT_*.
    for key in [key for key in env if key.startswith("PADMINT_")]:
        env["PADFORGE_" + key[len("PADMINT_"):]] = env[key]
    return env


def read_game_version(repo):
    """The game's single release version (version.json at the repository root), if any."""
    try:
        data = json.loads((Path(repo) / "version.json").read_text())
    except (OSError, ValueError):
        return None
    version, build = data.get("version"), data.get("build")
    if isinstance(version, str) and version and isinstance(build, int) and build > 0:
        return {"version": version, "build": build}
    return None


def workspace_root(args, repo):
    selected = getattr(args, "workspace_root", None)
    root = selected.expanduser().resolve() if selected else (repo / "build/padmint").resolve()
    # Compare resolved paths: a home folder reached through a link (macOS /tmp,
    # a moved or synced user folder) otherwise stops every build here.
    if repo.resolve() / "build" not in root.parents:
        raise ValueError("Workspace root must be below the backend's build directory")
    return root


def forget_moved_build_settings(*folders, stream=None):
    """CMake refuses a build folder whose CMakeCache.txt was written somewhere else.
    That happens after a move: PadForge's ~/.padforge became ~/.padmint (padmint#7),
    or a player moved the folder. Those settings are only a cache, so remove them
    and CMake sets the folder up again on the next build."""
    moved = []
    for folder in folders:
        for parent, names, files in os.walk(folder):
            names[:] = [name for name in names if name not in (".git", "CMakeFiles")]
            if "CMakeCache.txt" not in files:
                continue
            cache = Path(parent) / "CMakeCache.txt"
            try:
                text = cache.read_text(errors="replace")
            except OSError:
                continue
            found = re.search(r"^CMAKE_CACHEFILE_DIR:INTERNAL=(.*)$", text, re.MULTILINE)
            if not found:
                continue
            try:
                same = os.path.samefile(found.group(1).strip(), parent)
            except OSError:  # The folder it was written in is gone: it moved.
                same = False
            if not same:
                with contextlib.suppress(OSError):
                    cache.unlink()
                    moved.append(cache)
    if moved:
        print(f"Setting up {len(moved)} build folder(s) again: they were made before PadMint's "
              "folder moved.", file=stream or sys.stdout, flush=True)
    return moved


def check_output(check, output, game_revision, disc_sha256):
    if check == "none":
        return {"check": "none"}
    if check == "ipa":
        return validate_ipa(output, None, game_revision, disc_sha256)
    return validate_ipa(output, check.split("-")[0], game_revision, disc_sha256)


def publication_gate(output):
    """Audit every personal output; personal builds are never publishable either way."""
    findings, translated = gate.check(str(output))
    return {"result": "FAIL" if findings else "PASS", "finding_count": len(findings),
            "address_named_functions": translated, "findings": sorted(set(findings))[:10],
            "label": "personal build, not publishable"}


def execute(args, repo, disc):
    manifest, target_name, target = selection(args, repo)
    # One lock per backend checkout also covers caches outside the selected work dir.
    lock_root = repo / "build/padmint"
    root = workspace_root(args, repo)
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    if subprocess.run([tools.executable("git", host_id()), "-C", str(repo), "check-ignore", "-q",
                       str(root)]).returncode:
        raise ValueError("Backend must ignore build/padmint before running")
    lock_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    with workspace_lock(lock_root / "runner.lock"):
        forget_moved_build_settings(repo, tools.tools_root().parent / "cache")
        if disc:
            print("Hashing the disc for the build record…", flush=True)
        mods = (not args.no_mods) if "no-mods" in target.get("options", {}) else "backend-default"
        identity = {"schema_version": 1, "padmint_version": __version__,
                    "game": args.game, "revision": args.revision,
                    "disc_sha256": digest(disc) if disc else None, "target": target_name,
                    "mods": mods, "source_only": args.source_only, "jobs": args.jobs}
        # Invocation controls belong to the attempt, not to reusable build inputs.
        # Keep revisions isolated until every adapter proves cross-revision invalidation.
        workspace_identity = {name: identity[name] for name in
                              ("game", "revision", "disc_sha256", "target", "mods")}
        workspace_identity["workspace_schema"] = 1
        # 16 hex digits: unique enough per checkout, and short enough that deep
        # build trees stay under Windows' 260-character path limit.
        key = hashlib.sha256(json.dumps(workspace_identity, sort_keys=True).encode()).hexdigest()[:16]
        work = root / key / "backend"
        attempt = root / key / "runs" / uuid.uuid4().hex
        attempt.mkdir(parents=True, mode=0o700)
        output = attempt / f"personal.{target.get('output', 'ipa')}"
        started = time.monotonic()
        # Other versions of the same game count too, so an update still gets an estimate.
        siblings = sorted(repo.parent.glob(f"{args.game}-*/build/padmint")) if repo.parent.name == "games" else []
        left = previous_timings([root, *siblings], args.game, target_name)
        announced = set()

        def emit(event, **fields):
            record = dict(schema_version=1, event=event,
                          build_elapsed_seconds=round(time.monotonic() - started, 2), **fields)
            with (attempt / "progress.jsonl").open("a") as stream:
                stream.write(json.dumps(record) + "\n")
            backend = fields.get("backend", {})
            counts = ""
            if "completed" in backend and "total" in backend:
                counts = f" {backend['completed']}/{backend['total']} {backend.get('unit', '')}"
            print(f"[{record['build_elapsed_seconds']}s] {event}: "
                  f"{backend.get('stage', '')} {backend.get('event', '')}{counts}".strip(), flush=True)
            stage = backend.get("stage")
            if backend.get("event") == "stage_started" and stage in left and stage not in announced:
                announced.add(stage)
                print(f"  {time_left(left[stage])} (from your last build)", flush=True)

        record = dict(identity, workspace_key=key, workspace_identity=workspace_identity,
                      manifest_sha256=manifest_sha256(manifest),
                      status="running", publication="personal-only",
                      backend_validation="not-established-by-runner")
        game_version = read_game_version(repo)
        if game_version:
            record["game_version"] = game_version
        atomic_json(attempt / "record.json", record)
        emit("build_started")
        print(f"Local log: {attempt / 'backend.log'}", flush=True)

        def recheck(phase):
            record["checkout_check"] = phase + "-failed"
            check_checkout(repo, args.revision)
            record["checkout_check"] = phase + "-passed"

        try:
            argv = command(args, repo, disc, work, output)
            events = work / "logs/progress.jsonl"
            if "steps" in target:
                code, cancelled = run_steps(target["steps"], argv, repo, attempt / "backend.log",
                                            events, emit, lambda: recheck("before-launch"),
                                            values=placeholder_values(args, repo, disc, work, output),
                                            tool_names=target.get("tools", []))
            else:
                code, cancelled = run_process(argv, repo, attempt / "backend.log", events, emit,
                                              before_spawn=lambda: recheck("before-launch"),
                                              env=backend_env(args.jobs, target.get("tools", [])))
            recheck("after-exit")
            if code == 0 and not args.source_only:
                if not output.is_file() or output.stat().st_size == 0:
                    raise ValueError("Backend exited successfully but produced no output")
                record["package_validation"] = check_output(target.get("check", "none"), output,
                                                            args.revision, identity["disc_sha256"])
                record["output_sha256"] = digest(output)
                record["output"] = output.name
                args.output_path = output
                record["publication_gate"] = publication_gate(output)
                # Kept in the build record only; the final message already tells the player the copy is theirs alone.
            recheck("before-record")
            status = "cancelled" if cancelled else "completed" if code == 0 else "failed"
        except (OSError, ValueError, subprocess.CalledProcessError) as error:
            code, status = 1, "failed"
            record["failure_type"] = type(error).__name__
            print(f"Build failed: {error}", file=sys.stderr)
        record.update(status=status, exit_code=code)
        atomic_json(attempt / "record.json", record)
        emit("build_" + status, exit_code=code)
        if status == "failed":
            space = (catalog().get(getattr(args, "game", None)) or {}).get("free_space_gb")
            print_log_tail(attempt / "backend.log", needed_gb=space)
        print(f"Build record: {attempt / 'record.json'}")
        return code if code >= 0 else 128 - code


def previous_timings(roots, game, target):
    """Seconds that were left when each stage started, in the newest completed build of this
    game and target under roots. Empty on a first build: then no estimate is shown."""
    newest = None
    for root in roots:
        for path in Path(root).glob("*/runs/*/record.json"):
            try:
                record = json.loads(path.read_text())
                changed = path.stat().st_mtime
            except (OSError, ValueError):
                continue
            if (record.get("status"), record.get("game"), record.get("target")) != ("completed", game, target):
                continue
            if newest is None or changed > newest[0]:
                newest = (changed, path.parent / "progress.jsonl")
    if newest is None:
        return {}
    starts, end = {}, None
    try:
        lines = newest[1].read_text().splitlines()
    except OSError:
        return {}
    for line in lines:
        try:
            event = json.loads(line)
        except ValueError:
            continue
        backend = event.get("backend") or {}
        if backend.get("event") == "stage_started" and backend.get("stage"):
            starts.setdefault(backend["stage"], event.get("build_elapsed_seconds", 0))
        if event.get("event") == "build_completed":
            end = event.get("build_elapsed_seconds")
    if not end:
        return {}
    return {stage: end - seconds for stage, seconds in starts.items() if end - seconds > 0}


def time_left(seconds):
    minutes = round(seconds / 60)
    if minutes < 1:
        return "less than a minute left"
    return f"about {minutes} minute{'s' if minutes != 1 else ''} left"


def print_log_tail(log, lines=15, needed_gb=None):
    """Show the end of the backend log, where the reason for a failure is."""
    try:
        # LLVM on a system with only the newer libxml2 (see tools.link_system_library)
        # warns on every run; the warning is harmless and would push the real error out.
        tail = [line for line in log.read_text(errors="replace").splitlines()
                if "no version information available" not in line][-lines:]
    except OSError:
        return
    if tail:
        print(f"Last lines of {log}:", file=sys.stderr)
        for line in tail:
            print("  " + line[-300:], file=sys.stderr)
        cause = likely_cause(tail, needed_gb)
        if cause:
            print(f"\nLikely cause: {cause}", file=sys.stderr)


NETWORK_ERRORS = re.compile(
    r"Temporary failure in name resolution|Name or service not known|nodename nor servname|"
    r"getaddrinfo failed|Could not resolve host|Connection refused|Connection reset|timed out|"
    r"Network is unreachable|No route to host|Failed to connect|URLError|HTTP Error (403|5\d\d)", re.I)
DISK_FULL = re.compile(r"No space left on device|Errno 28|ENOSPC|not enough space on the disk", re.I)
CERTIFICATES = re.compile(r"CERTIFICATE_VERIFY_FAILED|certificate verify failed|SSL certificate problem", re.I)


def likely_cause(lines, needed_gb=None):
    """A plain reading of a failed build's last lines, for the three failures players hit most
    that have a fix outside PadMint. None when nothing matches: no guessing."""
    text = "\n".join(lines)
    if DISK_FULL.search(text):
        space = f" (this build needs about {needed_gb} GB)" if needed_gb else ""
        return f"the disk filled up. Free up space{space} and run PadMint again; finished steps are kept."
    if CERTIFICATES.search(text):
        return ("a secure download failed its certificate check. Antivirus HTTPS scanning or a "
                "company network usually causes this: turn the scanning off or use another network, "
                "then run PadMint again.")
    if NETWORK_ERRORS.search(text):
        hosts = re.findall(r"https?://([A-Za-z0-9.-]+)", text)
        where = hosts[-1] if hosts else "a download server"
        return (f"a download from {where} was blocked or failed. Check your internet connection, and "
                f"whether a VPN, a firewall or an antivirus web filter blocks {where}. Then run PadMint "
                "again; finished downloads are kept.")
    return None


def latest_release(repo_url):
    """The game's latest GitHub release: tag and downloadable assets.

    Uses the release web pages, not GitHub's API: the API allows 60 unsigned
    requests an hour per network address, which shared networks run out of.
    /releases/latest redirects to the tag, and every Pad release lists its
    files in SHA256SUMS.
    """
    base = repo_url.removesuffix(".git").rstrip("/")
    with tools.open_url(f"{base}/releases/latest") as response:
        landed = response.geturl()
    if "/releases/tag/" not in landed:
        raise ValueError(f"{base} has no published release yet")
    tag = urllib.parse.unquote(landed.rsplit("/releases/tag/", 1)[1].split("?")[0].strip("/"))
    download = f"{base}/releases/download/{urllib.parse.quote(tag)}"
    try:
        with tools.open_url(f"{download}/SHA256SUMS") as response:
            listed = response.read().decode()
    except RuntimeError:
        return tag, {}
    names = [line.split(maxsplit=1)[1].lstrip("*") for line in listed.splitlines() if len(line.split()) == 2]
    assets = {name: f"{download}/{urllib.parse.quote(name)}" for name in names}
    assets["SHA256SUMS"] = f"{download}/SHA256SUMS"
    return tag, assets


def published_app(name, assets, folder):
    """Download a release asset and check it against the release's SHA256SUMS."""
    if name not in assets or "SHA256SUMS" not in assets:
        raise ValueError(f"the release has no {name} with SHA256SUMS")
    with tools.open_url(assets["SHA256SUMS"]) as response:
        sums = dict(reversed(line.split(maxsplit=1)) for line in response.read().decode().splitlines()
                    if line.strip())
    expected = sums.get(name) or sums.get("*" + name)
    if not expected:
        raise ValueError(f"SHA256SUMS does not list {name}")
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    if not path.is_file() or digest(path) != expected:
        partial = path.with_name(path.name + ".partial")
        with tools.open_url(assets[name]) as response, partial.open("wb") as handle:
            shutil.copyfileobj(response, handle)
        if digest(partial) != expected:
            partial.unlink()
            raise ValueError(f"{name} does not match the release's SHA256SUMS")
        partial.replace(path)
    return path


def physical_memory():
    """Total memory in bytes, or None when it cannot be read."""
    try:
        if os.name == "nt":
            import ctypes

            class Status(ctypes.Structure):
                _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong)] + \
                    [(name, ctypes.c_ulonglong) for name in ("total", "free", "page_total", "page_free",
                                                             "virtual_total", "virtual_free", "extended")]
            status = Status(length=ctypes.sizeof(Status))
            return status.total if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)) else None
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    except (OSError, ValueError, AttributeError):
        return None


def default_jobs(cores=None, memory=None):
    """One compile job per CPU core, at most one per 1.5 GB of memory (KartPad's largest
    translated file needs about 1 GB to compile), and at most 16."""
    cores = cores or os.cpu_count() or 4
    memory = memory if memory is not None else physical_memory()
    by_memory = int(memory / (1.5 * (1 << 30))) if memory else 4
    return max(1, min(cores, by_memory, 16))


def check_free_space(folder, needed_gb):
    """A game's catalog entry may name the free space its first build needs
    (KartPad: about 4 GB of tools plus 11 GB of build files)."""
    if not needed_gb:
        return
    existing = next(path for path in [folder, *folder.parents] if path.exists())
    free_gb = shutil.disk_usage(existing).free / (1 << 30)
    if free_gb < needed_gb:
        raise ValueError(f"PadMint needs about {needed_gb} GB free for this build, but the drive with "
                         f"{folder} has {free_gb:.1f} GB free. Free up space and run PadMint again.")


def make(game, platform_name, disc, out, ref=None, app=None, jobs=None, results=None):
    """The player's command: from their own game file to their own copy, in one step."""
    with awake.while_building():
        return _make(game, platform_name, disc, out, ref, app, jobs, results)


def _make(game, platform_name, disc, out, ref=None, app=None, jobs=None, results=None):
    entry = catalog().get(game)
    if entry is None:
        raise ValueError(f"unknown game {game}; see padmint list")
    home = tools.tools_root().parent
    source, ref, assets = release_source(game, ref)
    manifest, _source = manifest_for(game, source)
    target = manifest["targets"].get(platform_name)
    if target is None or ("command" not in target and "steps" not in target):
        raise ValueError(f"{manifest['name']} cannot be built for {platform_name} yet")
    if not needs_build_input(manifest):
        disc = None  # the game file is added in the app, not read by the build
    elif disc is None:
        raise ValueError(f"{manifest['name']} needs your own game file (--disc)")
    missing_programs = [(tool, detail) for tool in player_requirements(manifest)
                        for ok, detail in [check_program(tool)] if not ok]
    if missing_programs:
        raise ValueError(f"{manifest['name']} needs these installed first:\n"
                         + "".join(f"  {tool['name']}: {tool['note']}\n" for tool, _ in missing_programs)
                         + "Then run PadMint again.")
    missing = tools.missing_system_library(target.get("tools", []), host_id())
    if missing:
        raise ValueError(missing[1])
    accepted = game_file.check_before_tools(manifest, target, disc, host_id())
    if accepted:
        print(f"Your game file: {accepted}", flush=True)
    tools.install(target.get("tools", []), host_id())
    version = (read_game_version(source) or {}).get("version") or ref.lstrip("v")
    if target.get("published_app") and app is None:
        name = target["published_app"].format(version=version)
        print(f"Downloading the published {name}", flush=True)
        app = published_app(name, assets, home / "apps" / game)
    jobs = jobs or default_jobs()
    print(f"Building with {jobs} parallel jobs", flush=True)
    args = argparse.Namespace(game=game, repo=source, revision=git(source, "rev-parse", "HEAD"),
                              disc=disc, target=platform_name, workspace_root=None, jobs=jobs,
                              source_only=False, no_mods=False, app=app)
    code = execute(args, source, disc)
    if code != 0:
        if code != 130:
            print(f"\nThe build stopped; the lines above say why. For help, post them with your computer "
                  f"type (Windows, Mac or Linux) at {entry['repo_url']}/issues", file=sys.stderr)
        return code
    out.mkdir(parents=True, exist_ok=True)
    safe_version = re.sub(r"[^A-Za-z0-9._-]", "_", version)  # a branch name such as codex/x has a slash
    result = out / f"{manifest['name']}-v{safe_version}-{platform_name}-personal{args.output_path.suffix}"
    shutil.copyfile(args.output_path, result)
    print(f"Your {manifest['name']} for {PLATFORM_NAMES.get(platform_name, platform_name)}: {result}")
    if results is not None:
        results.append(result)
    save_game_data(args.output_path, out, manifest["name"],
                   import_label=(entry.get("game_data_import") or {}).get(platform_name))
    print("It contains game code made from your own copy: keep it to yourself.")
    return 0


def save_game_data(built, out, name, stream=None, import_label=None):
    """A backend may leave the game data folder the player imports into the app
    (files/ and sys/, as Dolphin's Extract Entire Disc makes) beside its output,
    as "<output>.data". Copy it once into the player's folder: a real copy, so
    it never shares files with PadMint's build cache."""
    stream = stream or sys.stdout
    data = Path(str(built) + ".data")
    if not data.is_dir():
        return None
    target = out / f"{name} game data"
    if target.exists():
        print(f"Your {name} game data folder is already at {target}", file=stream)
        return target
    partial = target.with_name(target.name + ".partial")
    if partial.exists():
        shutil.rmtree(tools._long(partial))
    print(f"Saving your {name} game data folder (about "
          f"{sum(p.stat().st_size for p in data.rglob('*') if p.is_file()) / (1 << 30):.1f} GB)…",
          file=stream, flush=True)
    copy_files(tools._long(data), tools._long(partial))
    partial.replace(target)
    print(f"Your {name} game data folder: {target}\n"
          f"  New to {name}? Copy it to your device and choose it with "
          f"{import_label or 'Import from Extracted Folder'}. "
          "It needs no key.", file=stream)
    return target


def copy_files(source, target):
    """Copy a folder's files (contents only) into target. Unlike copytree it never
    reads links: on an Android phone (Ubuntu in Termux) the backend's hard links
    are listed as links but cannot be read as links ("Invalid argument")."""
    for folder, _folders, files in os.walk(source):
        # No "." parts: Windows' extended-length paths (\\?\) take them literally.
        relative = os.path.relpath(folder, source)
        destination = target if relative == os.curdir else os.path.join(target, relative)
        os.makedirs(destination, exist_ok=True)
        for name in files:
            shutil.copyfile(os.path.join(folder, name), os.path.join(destination, name))


def version_tuple(text):
    match = re.search(r"\d+(?:\.\d+)*", text)
    return tuple(int(part) for part in match.group().split(".")) if match else None


def player_requirements(manifest):
    """Programs the recipe says the player installs themselves (requirements.tools with "player")."""
    return [tool for tool in manifest.get("requirements", {}).get("tools", []) if tool.get("player")]


def check_program(tool):
    """(ok, detail) for a requirements.tools entry: on PATH, and new enough if it names a minimum."""
    path = shutil.which(tool["name"])
    if path is None:
        return False, tool.get("note", "not found on PATH")
    if "version_args" not in tool:
        return True, path
    try:
        result = subprocess.run([path, *tool["version_args"]], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return False, "could not run version check"
    text = (result.stdout or result.stderr).strip().splitlines()
    detail = text[0] if text else path
    if "min_version" not in tool:
        return True, detail
    found = version_tuple(detail)
    return (found is not None and found >= version_tuple(str(tool["min_version"])),
            f"{detail} (need {tool['min_version']}+)")


def published_recipe(game):
    """(recipe, where it came from): the one the game's latest release publishes, checked
    against the release's SHA256SUMS, or PadMint's built-in copy when that can't be had."""
    entry = catalog().get(game)
    if entry is None:
        raise ValueError(f"unknown game {game}; see padmint list")
    try:
        tag, assets = latest_release(entry["repo_url"])
    except (RuntimeError, ValueError, OSError):
        why = "could not reach the release"
    else:
        name = next((n for n in assets if n.endswith("-padmint.json")), None)
        if name is None:
            why = f"the {tag} release publishes no recipe"
        else:
            try:
                with tempfile.TemporaryDirectory() as folder:
                    return load_manifest(published_app(name, assets, Path(folder))), f"{game} {tag} release"
            except NeedsNewerPadMint:
                raise  # the release is fine; this PadMint is too old for it
            except (RuntimeError, ValueError, OSError):
                why = "could not reach the release"
    manifest, _source = manifest_for(game)
    return manifest, f"PadMint's built-in copy; {why}"


def doctor(game, target_name, repo=None, stream=None):
    """Check this computer for a game's build; install nothing. Without a checkout this is the
    player's path: the latest release's recipe, PadMint's own tools and the catalog's free space.
    With --repo it is a checkout build: that recipe's own requirements apply."""
    stream = stream or sys.stdout
    if repo is None:
        manifest, source = published_recipe(game)
    else:
        manifest, source = manifest_for(game, repo)
        source = f"your checkout {repo}" if source == "repository" else f"PadMint's built-in copy; {repo} has none"
    problems = 0

    def report(ok, label, detail=""):
        nonlocal problems
        problems += 0 if ok else 1
        print(f"{'ok  ' if ok else 'FIX '} {label}{': ' + detail if detail else ''}", file=stream)

    print(f"{manifest['name']} ({manifest['status']}, recipe: {source})", file=stream)
    report(sys.version_info >= (3, 9), "Python 3.9+", sys.version.split()[0])
    host = host_id()
    target = manifest["targets"].get(target_name)
    if target is None:
        report(False, f"{target_name} target", "not declared by this game")
    else:
        state = target["hosts"].get(host, "unsupported")
        report(state in RUNNABLE_STATES, f"{target_name} builds on {host}", state)
        for name in target.get("tools", []):  # tools PadMint itself supplies (install nothing here)
            tool = tools.lock()[name]
            if host in tool["hosts"]:
                report(True, f"{name} {tools.version(tool, host)}",
                       "PadMint's copy" if tools.installed(name, host) else "PadMint downloads it for the first build")
        missing = tools.missing_system_library(target.get("tools", []), host)
        if missing:
            report(False, missing[0], missing[1])
    if repo is None:
        for tool in player_requirements(manifest):  # the player installs these; PadMint can't
            ok, detail = check_program(tool)
            report(ok, tool["name"], detail if ok or detail == tool["note"] else f"{detail}; {tool['note']}")
        needed = catalog()[game].get("free_space_gb", 0)
        home = tools.tools_root().parent
        existing = next(path for path in [home, *home.parents] if path.exists())
        free = shutil.disk_usage(existing).free / (1 << 30)
        report(free >= needed, "free disk space", f"{free:.0f} GB free, {needed} GB needed")
        print(f"{problems} item(s) to fix" if problems else "Ready", file=stream)
        return 1 if problems else 0
    for tool in manifest.get("requirements", {}).get("tools", []):
        ok, detail = check_program(tool)
        report(ok, tool["name"], detail)
    needed = manifest.get("requirements", {}).get("disk_gb", 0)
    location = Path(repo) if repo else Path.cwd()
    free = shutil.disk_usage(location).free / 1e9
    report(free >= needed, "free disk space", f"{free:.0f} GB free, {needed} GB needed")
    if repo is not None:
        try:
            dirty = git(repo, "status", "--porcelain", "--untracked-files=normal")
            head = git(repo, "rev-parse", "HEAD")
            report(not dirty, "clean checkout", head)
            reviewed = catalog().get(game, {}).get("reviewed_revision")
            if reviewed:
                report(head == reviewed, "reviewed revision", reviewed)
        except (OSError, subprocess.CalledProcessError):
            report(False, "game checkout", "not a Git checkout")
    print(f"{problems} item(s) to fix" if problems else "Ready", file=stream)
    return 1 if problems else 0


PLATFORM_LABELS = {"android": "Android phone or tablet",
                   "ios": "iPhone or iPad (needs this Mac)"}
# Off a Mac, for games whose catalog entry says iPhone builds work there too.
OFF_MAC_IOS_LABEL = "iPhone or iPad (experimental)"
PLATFORM_NAMES = {"android": "Android", "ios": "iPhone and iPad", "macos": "Mac"}
# The phone's Download folder, shared with its apps (Termux asks once for access).
PHONE_DOWNLOADS = Path("/sdcard/Download")


def next_steps(entry, platform_name, result, stream):
    """After a build: the few steps that get this file into the game, in the player's words."""
    guide = entry.get("player_help") or f"{entry['repo_url']}#get-{entry['id']}"
    steps = (entry.get("player_next") or {}).get(platform_name)
    if not steps or result is None:
        print(f"Next: {guide}", file=stream)
        return
    print("\nWhat to do next:", file=stream)
    for number, step in enumerate(steps["steps"], 1):
        print(f"  {number}. {step.format(file=result.name)}", file=stream)
    if steps.get("note"):
        print(steps["note"], file=stream)
    print(f"Full guide: {guide}", file=stream)


def reveal(path):
    """Show the finished file in Finder, File Explorer or the file manager. Optional."""
    try:
        if sys.platform == "darwin":
            subprocess.run(["open", "-R", str(path)], check=False)
        elif os.name == "nt":
            subprocess.run(["explorer", f"/select,{path}"], check=False)
        elif shutil.which("xdg-open"):
            subprocess.Popen(["xdg-open", str(path.parent)], stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
    except OSError:
        pass


def dropped_path(text):
    """A path typed, pasted or dragged into a terminal window."""
    text = text.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "'\"":
        text = text[1:-1]
    elif os.name != "nt":
        text = re.sub(r"\\(.)", r"\1", text)
    return Path(text).expanduser()


def player_folder():
    """Where a player's own files usually are: on a phone its Download folder,
    else Downloads (or the home folder)."""
    if on_android() and PHONE_DOWNLOADS.is_dir():
        return PHONE_DOWNLOADS
    default = Path.home() / "Downloads"
    return default if default.is_dir() else Path.home()


def game_files(folder, manifest):
    """Files in folder with an extension one of the manifest's inputs accepts, newest first."""
    formats = {"." + name for item in (manifest or {}).get("inputs", []) for name in item.get("formats", [])}
    try:
        found = [path for path in folder.iterdir() if path.is_file() and path.suffix.lower() in formats]
    except OSError:
        return []
    return sorted(found, key=lambda path: path.stat().st_mtime, reverse=True)


def choose(title, options, ask, stream):
    """options: [(value, label)]. One option is chosen without asking."""
    if len(options) == 1:
        print(f"{title}: {options[0][1]}", file=stream)
        return options[0][0]
    print(title, file=stream)
    for number, (_value, label) in enumerate(options, 1):
        print(f"  {number}. {label}", file=stream)
    while True:
        answer = ask("Number: ").strip()
        if answer.isdigit() and 1 <= int(answer) <= len(options):
            return options[int(answer) - 1][0]


def file_problem(disc):
    """Why a dropped path can't be used yet, in the player's words; None when it can."""
    if not disc.is_file():
        return f"No file at {disc}"
    if game_file.cloud_only(disc):
        return game_file.CLOUD_ONLY.format(name=disc.name)
    return None


def game_from_file(disc, games, stream):
    """The offered games whose catalog entry lists the file's game ID ([] if none or unreadable).
    ROMs and raw disc images are read directly; packed discs (WBFS, RVZ) need nodtool (a few MB)."""
    if game_file.cloud_only(disc):
        return []
    game_id = game_file.header_id(disc)
    if game_id is None:
        # nodtool may download first, with its output hidden: say something so it doesn't look stuck.
        print("Reading your file…", file=stream, flush=True)
        try:
            tools.install(["nodtool"], host_id(), stream=io.StringIO())
            _title, game_id, _revision = game_file.read_disc(disc, tools.executable("nodtool", host_id()))
        except (OSError, RuntimeError, ValueError, subprocess.SubprocessError):
            return []
    matches = [(id_, name) for id_, name, _ in games if game_id in (catalog()[id_].get("game_ids") or [])]
    if len(matches) == 1:
        print(f"Game: {matches[0][1]} (from your file, {game_id})", file=stream)
    return [id_ for id_, _ in matches]


def start(ask=input, stream=None):
    """The guided path for players: as few questions as possible. When several games are
    offered and the player's file names exactly one of them, the game is not asked for.
    The copy is saved to Downloads (padmint make --out chooses another folder)."""
    stream = stream or sys.stdout
    print(f"PadMint {__version__}: make your own copy of a game from your own game file.", file=stream)
    # iPhone builds need Xcode on Apple Silicon, except games marked ios_off_mac, which also
    # build on Windows and Linux computers. An Intel Mac and a phone make Android copies.
    host = host_id()
    apple_silicon = host == "macos-arm64"
    computer_off_mac = host.startswith(("windows-", "linux-")) and not on_android()
    games = []
    for game, entry in sorted(catalog().items()):
        ios_here = apple_silicon or (computer_off_mac and entry.get("ios_off_mac", False))
        platforms = [name for name in entry.get("player_targets", []) if name != "ios" or ios_here]
        if platforms:
            name = (entry.get("manifest") or {}).get("name") or entry.get("name", game)
            games.append((game, name, platforms))
    if not games:
        raise ValueError("no game can be made on this computer yet")
    disc = game = None
    offered = games
    if len(games) > 1 and any(catalog()[id_].get("game_ids") for id_, _, _ in games):
        answer = ask("Drag your game file into this window, then press Enter "
                     "(no file? just press Enter to choose a game): ").strip()
        while answer:
            disc = dropped_path(answer)
            problem = file_problem(disc)
            if problem is None:
                break
            print(problem, file=stream)
            answer = ask("Drag the file again, or press Enter to choose a game: ").strip()
            disc = None
        if disc is not None:
            found = game_from_file(disc, games, stream)
            # Two games may share a code: then ask, offering only those.
            if len(found) > 1:
                offered = [entry for entry in games if entry[0] in found]
            game = found[0] if len(found) == 1 else None
    if game is None:
        game = choose("Game", [(game, name) for game, name, _ in offered], ask, stream)
    name, platforms = next((name, platforms) for id_, name, platforms in games if id_ == game)
    labels = dict(PLATFORM_LABELS, **({} if apple_silicon else {"ios": OFF_MAC_IOS_LABEL}))
    target = choose("Make it for", [(p, labels.get(p, p)) for p in platforms], ask, stream)
    if catalog()[game].get("player_game_file", "build") == "in-app":
        disc = None
        print(f"{name} asks for your own game file inside the app, after you install it.", file=stream)
    elif disc is None:
        # A phone has no window to drag files into: offer the game files in its Download folder.
        found = game_files(player_folder(), catalog()[game].get("manifest")) if on_android() else []
        if found:
            disc = choose(f"Your {name} game file", [(path, path.name) for path in found]
                          + [(None, "Another file (type its path)")], ask, stream)
        prompt = (f"Type the path of your own {name} game file, then press Enter: " if on_android()
                  else f"Drag your own {name} game file into this window, then press Enter: ")
        while disc is None:
            disc = dropped_path(ask(prompt))
            problem = file_problem(disc)
            if problem is not None:
                print(problem, file=stream)
                disc = None
    out = player_folder()
    print(f"Your copy will be saved in {out}", file=stream)
    results = []
    code = make(game, target, disc.resolve() if disc else None, out.resolve(), results=results)
    if code == 0:
        result = results[-1] if results else None
        next_steps(catalog()[game], target, result, stream)
        if result is not None:
            reveal(result)
    return code


def git_program():
    """Git: the system's, or the copy PadMint installs (Windows usually has none)."""
    program = tools.executable("git", host_id())
    if program == "git" and shutil.which("git") is None:
        tools.install(["git"], host_id())
        program = tools.executable("git", host_id())
    return program


def source_complete(source):
    """A finished download of a game's source: every tracked file is present.
    An attempt that was interrupted (closed window, lost connection) must not be
    reused, or later runs fail with misleading errors (padmint#8)."""
    if not (source / ".git").exists():
        return False
    git = [git_program(), "-C", str(source)]
    head = subprocess.run(git + ["rev-parse", "--verify", "-q", "HEAD"], capture_output=True)
    if head.returncode:
        return False
    missing = subprocess.run(git + ["ls-files", "--deleted"], capture_output=True, text=True)
    return missing.returncode == 0 and not missing.stdout.strip()


def _remove_tree(path):
    """Remove one of PadMint's own download folders, including Git's read-only files on Windows."""
    def writable_then_retry(function, name, _info):
        os.chmod(name, stat.S_IWRITE)
        function(name)
    if path.exists():
        shutil.rmtree(path, onerror=writable_then_retry)


def fetch_source(game, source, ref):
    """Download into a side folder and move it into place only once complete."""
    if source.exists():
        print(f"The earlier download in {source} is unfinished; downloading it again.", flush=True)
        _remove_tree(source)
    partial = source.with_name(source.name + ".partial")
    _remove_tree(partial)
    partial.parent.mkdir(parents=True, exist_ok=True)
    get_game(game, partial, ref, announce=False)
    os.replace(partial, source)
    print(f"{game} source in {source}", flush=True)


def release_source(game, ref=None):
    """The game's source at ref (default: its latest release), downloaded once and reused:
    (folder, ref, release assets). The recipe players build with lives in it."""
    entry = catalog().get(game)
    if entry is None:
        raise ValueError(f"unknown game {game}; see padmint list")
    home = tools.tools_root().parent
    assets = {}
    if ref is None:
        ref, assets = latest_release(entry["repo_url"])
    source = home / "games" / f"{game}-{re.sub(r'[^A-Za-z0-9._-]', '_', ref)}"
    if not source_complete(source):
        check_free_space(home, entry.get("free_space_gb", 0))
        fetch_source(game, source, ref)
    return source, ref, assets


def get_game(game, dest, ref=None, announce=True):
    """Clone a catalogued game's source; its build bootstrap fetches the rest."""
    entry = catalog().get(game)
    if entry is None:
        raise ValueError(f"unknown game {game}; see padmint list")
    if dest.exists() and any(dest.iterdir()):
        raise ValueError(f"{dest} is not empty")
    argv = [git_program(), "-c", "advice.detachedHead=false", "clone"] \
        + (["--branch", ref] if ref else []) \
        + [entry["repo_url"], str(dest)]
    try:
        subprocess.run(argv, check=True)
    except subprocess.CalledProcessError as error:
        raise ValueError(
            f"PadMint could not download {game}'s source from github.com (Git stopped with code "
            f"{error.returncode}; the lines above say why). Check your internet connection, and whether "
            "a VPN, a firewall or an antivirus web filter blocks github.com. Then run PadMint again."
        ) from error
    if announce:
        print(f"{game} source in {dest}")
    return 0


def list_games(stream=None):
    """What a player can build, per game. Each game's own padmint.json is the
    source of truth for build hosts, so only the catalog's player targets show."""
    stream = stream or sys.stdout
    for game, entry in sorted(catalog().items()):
        targets = ", ".join(entry.get("player_targets") or []) or "see repo"
        print(f"{game:12} {targets:12} {entry['repo_url']}", file=stream)
    return 0


def history(repo, stream=None):
    """Summarize the build attempts recorded under a checkout's build/ folder."""
    stream = stream or sys.stdout
    records = []
    for path in sorted((Path(repo) / "build").glob("**/runs/*/record.json")):
        try:
            record = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        events = path.parent / "progress.jsonl"
        seconds = None
        if events.is_file():
            lines = events.read_text().splitlines()
            if lines:
                try:
                    seconds = json.loads(lines[-1]).get("build_elapsed_seconds")
                except ValueError:
                    pass
        output = path.parent / str(record.get("output", ""))
        size = f"{output.stat().st_size / 1e6:.1f} MB" if record.get("output") and output.is_file() else "-"
        records.append((path.stat().st_mtime, record, seconds, size))
    if not records:
        print("No PadMint build records in this checkout", file=stream)
        return 0
    for _mtime, record, seconds, size in sorted(records, key=lambda item: item[0]):
        gate_result = record.get("publication_gate", {}).get("result", "-")
        duration = f"{seconds / 60:.1f} min" if isinstance(seconds, (int, float)) else "-"
        print(f"{record.get('status', '?'):9} {record.get('game', '?'):13} {record.get('target', '?'):5} "
              f"{str(record.get('revision', ''))[:10]:10} {duration:>9} {size:>9} gate {gate_result}",
              file=stream)
    return 0


def build_parser():
    parser = argparse.ArgumentParser(prog="padmint", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--version", action="version", version=f"PadMint {__version__}")
    commands = parser.add_subparsers(dest="action")
    commands.add_parser("start", help="Guided: pick a game, your game file and a folder (the default)")
    commands.add_parser("list", help="Show supported games and platforms")
    history_parser = commands.add_parser("history", help="Summarize recorded builds in a checkout")
    history_parser.add_argument("--repo", type=Path, required=True)
    ui_parser = commands.add_parser("ui", help="Open the local browser interface")
    ui_parser.add_argument("--port", type=int, default=0)
    ui_parser.add_argument("--no-open", action="store_true", help="Print the address without opening a browser")
    doctor_parser = commands.add_parser("doctor", help="Check this computer for a game's requirements")
    doctor_parser.add_argument("game")
    doctor_parser.add_argument("--target", default="ios")
    doctor_parser.add_argument("--repo", type=Path)
    tools_parser = commands.add_parser("tools", help="Download and check the tools a game's target needs")
    tools_parser.add_argument("game")
    tools_parser.add_argument("--target", default="android")
    tools_parser.add_argument("--repo", type=Path)
    get_parser = commands.add_parser("get", help="Download a game's source (installs Git if needed)")
    get_parser.add_argument("game")
    get_parser.add_argument("dest", type=Path)
    get_parser.add_argument("--ref", help="Branch or tag (default: the repository's default branch)")
    make_parser = commands.add_parser("make", help="Make your own copy of a game from your game file")
    make_parser.add_argument("game")
    make_parser.add_argument("platform", help="android, ios or macos")
    make_parser.add_argument("--disc", type=Path, help="Your own game file (when the build reads it)")
    make_parser.add_argument("--out", type=Path, default=Path.cwd(), help="Where to save the result")
    make_parser.add_argument("--jobs", type=int, choices=range(1, 17),
                             help="Parallel compile jobs (default: from this computer's cores and memory)")
    make_parser.add_argument("--ref", help=argparse.SUPPRESS)
    make_parser.add_argument("--app", type=Path, help=argparse.SUPPRESS)
    manifest_parser = commands.add_parser("check-manifest", help="Validate a padmint.json file")
    manifest_parser.add_argument("path", type=Path)
    audit_parser = commands.add_parser("audit", help="Run the release gate on files or folders")
    audit_parser.add_argument("paths", nargs="+", type=Path)
    audit_parser.add_argument("--reference", type=Path, help="Folder of original section blobs (*.bin)")
    for action in ("plan", "build"):
        sub = commands.add_parser(action, help="Show the backend command" if action == "plan"
                                  else "Build a personal copy on this computer")
        sub.add_argument("game")
        sub.add_argument("--repo", type=Path, required=True)
        sub.add_argument("--revision", required=True, help="Full commit you have reviewed and trust")
        sub.add_argument("--disc", type=Path,
                         help="Your own game image, for games that read it during the build")
        sub.add_argument("--target", default="ios")
        sub.add_argument("--app", type=Path, help="The published app a game pack links against")
        sub.add_argument("--workspace-root", type=Path,
                         help="Ignored directory below backend build/ (default: build/padmint)")
        sub.add_argument("--jobs", type=int, choices=range(1, 9), default=2)
        sub.add_argument("--source-only", action="store_true", help="Stop before compilation (if supported)")
        sub.add_argument("--no-mods", action="store_true", help="Build without mods (if supported)")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        if args.action in (None, "start"):
            return start()
        if args.action == "list":
            return list_games()
        if args.action == "history":
            return history(args.repo.expanduser().resolve())
        if args.action == "ui":
            from .ui import serve
            return serve(args.port, not args.no_open)
        if args.action == "doctor":
            repo = args.repo.expanduser().resolve() if args.repo else None
            return doctor(args.game, args.target, repo)
        if args.action == "tools":
            if args.repo:
                repo = args.repo.expanduser().resolve()
                where = f"your checkout {repo}"
            else:
                repo, ref, _assets = release_source(args.game)
                where = f"{args.game} {ref}, its latest release"
            manifest, origin = manifest_for(args.game, repo)
            print(f"Recipe: {where}" if origin == "repository" else
                  f"Recipe: PadMint's built-in copy for {args.game} (none found in {where})")
            target = manifest["targets"].get(args.target)
            if target is None:
                raise ValueError(f"{manifest['name']} has no {args.target} target")
            tools.install(target.get("tools", []), host_id())
            print(f"Tools ready in {tools.tools_root()}")
            return 0
        if args.action == "get":
            return get_game(args.game, args.dest.expanduser().resolve(), args.ref)
        if args.action == "make":
            disc = args.disc.expanduser().resolve() if args.disc else None
            if disc is not None and not disc.is_file():
                raise ValueError(f"game file not found: {disc}")
            return make(args.game, args.platform, disc, args.out.expanduser().resolve(), args.ref,
                        args.app.expanduser().resolve() if args.app else None, args.jobs)
        if args.action == "check-manifest":
            path = (repository_manifest(args.path) or args.path / "padmint.json"
                    if args.path.is_dir() else args.path)
            data = load_manifest(path)
            print(f"ok {path}: {data['id']} ({data['kind']}, {data['status']})")
            return 0
        if args.action == "audit":
            return gate.audit(args.paths, args.reference)
        repo, disc = validate(args)
        manifest, target_name, target = selection(args, repo)
        state = target["hosts"].get(host_id(), "unsupported")
        if args.action == "plan":
            root = workspace_root(args, repo)
            print(json.dumps({"game": manifest["id"], "status": manifest["status"],
                              "target": target_name, "host": host_id(), "host_state": state,
                              "argv": command(args, repo, disc, root / "CONFIG/backend",
                                              root / "CONFIG/runs/ATTEMPT/personal.ipa")}, indent=2))
            return 0
        if state not in RUNNABLE_STATES:
            raise ValueError(f"{manifest['name']} {target_name} builds are {state} on {host_id()}")
        return execute(args, repo, disc)
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        message = str(error)
        plain = message.startswith("PadMint ") or isinstance(error, NeedsNewerPadMint)
        print(message if plain else f"PadMint: {message}", file=sys.stderr)
        return 1
    except (KeyboardInterrupt, EOFError):
        return 130
