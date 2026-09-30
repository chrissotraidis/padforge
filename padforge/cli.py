"""PadForge: build your own copy of a supported Pad game on your own computer.

Run with no command for the guided path. Other commands: make, list, doctor,
tools, get, check-manifest, audit, plan, build. Game backends keep their own
validation and caching; PadForge validates inputs, runs the backend, relays
progress, and records and audits the result.
"""
import argparse
import contextlib
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import time
import urllib.parse
import uuid

from . import __version__, game_file, gate, tools
from .manifest import (RUNNABLE_STATES, catalog, expand, host_id, load_manifest,
                       manifest_for, manifest_sha256, needs_build_input)
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
                raise ValueError("Another PadForge process is using this checkout") from None
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
            raise ValueError("Another PadForge process is using this checkout") from None
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
    """Run a manifest's ordered steps; PadForge emits the stage events itself."""
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

    Windows PadForge ships Python's embeddable package, whose ._pth file makes
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
    """Environment for backend processes: PadForge's tools first on PATH, and the
    job cap for `cmake --build`."""
    env = tools.environment(tool_names, host_id()) if tool_names else dict(os.environ)
    if jobs:
        env.setdefault("CMAKE_BUILD_PARALLEL_LEVEL", str(jobs))
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
    root = selected.expanduser().resolve() if selected else (repo / "build/padforge").resolve()
    # Compare resolved paths: a home folder reached through a link (macOS /tmp,
    # a moved or synced user folder) otherwise stops every build here.
    if repo.resolve() / "build" not in root.parents:
        raise ValueError("Workspace root must be below the backend's build directory")
    return root


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
    lock_root = repo / "build/padforge"
    root = workspace_root(args, repo)
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    if subprocess.run([tools.executable("git", host_id()), "-C", str(repo), "check-ignore", "-q",
                       str(root)]).returncode:
        raise ValueError("Backend must ignore build/padforge before running")
    lock_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    with workspace_lock(lock_root / "runner.lock"):
        if disc:
            print("Hashing the disc for the build record…", flush=True)
        mods = (not args.no_mods) if "no-mods" in target.get("options", {}) else "backend-default"
        identity = {"schema_version": 1, "padforge_version": __version__,
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
            print_log_tail(attempt / "backend.log")
        print(f"Build record: {attempt / 'record.json'}")
        return code if code >= 0 else 128 - code


def print_log_tail(log, lines=15):
    """Show the end of the backend log, where the reason for a failure is."""
    try:
        tail = log.read_text(errors="replace").splitlines()[-lines:]
    except OSError:
        return
    if tail:
        print(f"Last lines of {log}:", file=sys.stderr)
        for line in tail:
            print("  " + line[-300:], file=sys.stderr)


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
        raise ValueError(f"PadForge needs about {needed_gb} GB free for this build, but the drive with "
                         f"{folder} has {free_gb:.1f} GB free. Free up space and run PadForge again.")


def make(game, platform_name, disc, out, ref=None, app=None, jobs=None):
    """The player's command: from their own game file to their own copy, in one step."""
    entry = catalog().get(game)
    if entry is None:
        raise ValueError(f"unknown game {game}; see padforge list")
    home = tools.tools_root().parent
    assets = {}
    if ref is None:
        ref, assets = latest_release(entry["repo_url"])
    source = home / "games" / f"{game}-{re.sub(r'[^A-Za-z0-9._-]', '_', ref)}"
    if not source.exists():
        check_free_space(home, entry.get("free_space_gb", 0))
        get_game(game, source, ref)
    manifest, _source = manifest_for(game, source)
    target = manifest["targets"].get(platform_name)
    if target is None or ("command" not in target and "steps" not in target):
        raise ValueError(f"{manifest['name']} cannot be built for {platform_name} yet")
    if not needs_build_input(manifest):
        disc = None  # the game file is added in the app, not read by the build
    elif disc is None:
        raise ValueError(f"{manifest['name']} needs your own game file (--disc)")
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
    print(f"Your {manifest['name']} for {platform_name}: {result}")
    save_game_data(args.output_path, out, manifest["name"])
    print("It contains game code made from your own copy: keep it to yourself.")
    return 0


def save_game_data(built, out, name, stream=None):
    """A backend may leave the game data folder the player imports into the app
    (files/ and sys/, as Dolphin's Extract Entire Disc makes) beside its output,
    as "<output>.data". Copy it once into the player's folder: a real copy, so
    it never shares files with PadForge's build cache."""
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
    shutil.copytree(tools._long(data), tools._long(partial))
    partial.replace(target)
    print(f"Your {name} game data folder: {target}\n"
          f"  New to {name}? Copy it to your device and choose it with Import from Extracted Folder. "
          "It needs no key.", file=stream)
    return target


def version_tuple(text):
    match = re.search(r"\d+(?:\.\d+)*", text)
    return tuple(int(part) for part in match.group().split(".")) if match else None


def doctor(game, target_name, repo=None, stream=None):
    """Check this computer against a game's declared requirements; install nothing."""
    stream = stream or sys.stdout
    manifest, source = manifest_for(game, repo)
    problems = 0

    def report(ok, label, detail=""):
        nonlocal problems
        problems += 0 if ok else 1
        print(f"{'ok  ' if ok else 'FIX '} {label}{': ' + detail if detail else ''}", file=stream)

    print(f"{manifest['name']} ({manifest['status']}, manifest from {source})", file=stream)
    report(sys.version_info >= (3, 9), "Python 3.9+", sys.version.split()[0])
    host = host_id()
    target = manifest["targets"].get(target_name)
    if target is None:
        report(False, f"{target_name} target", "not declared by this game")
    else:
        state = target["hosts"].get(host, "unsupported")
        report(state in RUNNABLE_STATES, f"{target_name} builds on {host}", state)
    for tool in manifest.get("requirements", {}).get("tools", []):
        path = shutil.which(tool["name"])
        if path is None:
            report(False, tool["name"], tool.get("note", "not found on PATH"))
            continue
        detail = path
        ok = True
        if "version_args" in tool:
            try:
                result = subprocess.run([path, *tool["version_args"]], capture_output=True,
                                        text=True, timeout=30)
                text = (result.stdout or result.stderr).strip().splitlines()
                detail = text[0] if text else path
                found = version_tuple(detail)
                if "min_version" in tool:
                    minimum = version_tuple(str(tool["min_version"]))
                    ok = found is not None and found >= minimum
                    detail += f" (need {tool['min_version']}+)"
            except (OSError, subprocess.TimeoutExpired):
                ok, detail = False, "could not run version check"
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


def dropped_path(text):
    """A path typed, pasted or dragged into a terminal window."""
    text = text.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "'\"":
        text = text[1:-1]
    elif os.name != "nt":
        text = re.sub(r"\\(.)", r"\1", text)
    return Path(text).expanduser()


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


def start(ask=input, stream=None):
    """The guided path for players: pick the game, then give your game file and a folder."""
    stream = stream or sys.stdout
    print(f"PadForge {__version__}: make your own copy of a game from your own game file.", file=stream)
    # iPhone builds need Xcode on Apple Silicon; an Intel Mac makes Android copies.
    apple_silicon = host_id() == "macos-arm64"
    games = []
    for game, entry in sorted(catalog().items()):
        platforms = [name for name in entry.get("player_targets", []) if name != "ios" or apple_silicon]
        if platforms:
            name = (entry.get("manifest") or {}).get("name") or entry.get("name", game)
            games.append((game, name, platforms))
    if not games:
        raise ValueError("no game can be made on this computer yet")
    game = choose("Game", [(game, name) for game, name, _ in games], ask, stream)
    name, platforms = next((name, platforms) for id_, name, platforms in games if id_ == game)
    target = choose("Make it for", [(p, PLATFORM_LABELS.get(p, p)) for p in platforms], ask, stream)
    disc = None
    if catalog()[game].get("player_game_file", "build") == "in-app":
        print(f"{name} asks for your own game file inside the app, after you install it.", file=stream)
    else:
        while True:
            disc = dropped_path(ask(f"Drag your own {name} game file into this window, then press Enter: "))
            if disc.is_file():
                break
            print(f"No file at {disc}", file=stream)
    default = Path.home() / "Downloads"
    default = default if default.is_dir() else Path.home()
    answer = ask(f"Save it in which folder? Press Enter for {default}: ").strip()
    out = dropped_path(answer) if answer else default
    code = make(game, target, disc.resolve() if disc else None, out.resolve())
    if code == 0:
        entry = catalog()[game]
        print(f"Next: {entry.get('player_help') or entry['repo_url'] + '#get-' + game}", file=stream)
    return code


def get_game(game, dest, ref=None):
    """Clone a catalogued game's source; its build bootstrap fetches the rest."""
    entry = catalog().get(game)
    if entry is None:
        raise ValueError(f"unknown game {game}; see padforge list")
    if dest.exists() and any(dest.iterdir()):
        raise ValueError(f"{dest} is not empty")
    if shutil.which("git") is None:
        tools.install(["git"], host_id())
    argv = [tools.executable("git", host_id()), "clone"] + (["--branch", ref] if ref else []) \
        + [entry["repo_url"], str(dest)]
    subprocess.run(argv, check=True)
    print(f"{game} source in {dest}")
    return 0


def list_games(stream=None):
    stream = stream or sys.stdout
    for game, entry in sorted(catalog().items()):
        manifest = entry.get("manifest")
        if manifest is None:
            print(f"{game:12} manifest in repository  {entry['repo_url']}", file=stream)
            continue
        cells = ", ".join(f"{target}: " + "/".join(f"{host} {state}" for host, state in sorted(info["hosts"].items()))
                          for target, info in sorted(manifest["targets"].items()))
        print(f"{game:12} {manifest['kind']:17} {manifest['status']:15} {cells}", file=stream)
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
        print("No PadForge build records in this checkout", file=stream)
        return 0
    for _mtime, record, seconds, size in sorted(records, key=lambda item: item[0]):
        gate_result = record.get("publication_gate", {}).get("result", "-")
        duration = f"{seconds / 60:.1f} min" if isinstance(seconds, (int, float)) else "-"
        print(f"{record.get('status', '?'):9} {record.get('game', '?'):13} {record.get('target', '?'):5} "
              f"{str(record.get('revision', ''))[:10]:10} {duration:>9} {size:>9} gate {gate_result}",
              file=stream)
    return 0


def build_parser():
    parser = argparse.ArgumentParser(prog="padforge", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--version", action="version", version=f"PadForge {__version__}")
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
    manifest_parser = commands.add_parser("check-manifest", help="Validate a padforge.json file")
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
                         help="Ignored directory below backend build/ (default: build/padforge)")
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
            repo = args.repo.expanduser().resolve() if args.repo else None
            manifest, _source = manifest_for(args.game, repo)
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
            path = args.path / "padforge.json" if args.path.is_dir() else args.path
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
        print(f"PadForge: {error}", file=sys.stderr)
        return 1
    except (KeyboardInterrupt, EOFError):
        return 130
