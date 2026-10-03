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

from . import __version__, awake, game_file, gate, ios_module, tools
from .say import MESSAGES, localized, phrase, t
from .manifest import (RUNNABLE_STATES, NeedsNewerPadMint, catalog, expand, host_id, load_manifest,
                       manifest_for, manifest_sha256, needs_build_input, on_android,
                       repository_manifest)
from .package import validate_ipa


def git(repo, *args):
    return subprocess.check_output([tools.executable("git", host_id()), "-C", str(repo), *args],
                                   text=True).strip()


def digest(path):
    """SHA-256 of a file, or of a folder: its files' relative paths and contents, in order."""
    if path.is_dir():
        result = hashlib.sha256()
        for file in sorted(item for item in path.rglob("*") if item.is_file()):
            result.update(file.relative_to(path).as_posix().encode() + b"\0" + digest(file).encode() + b"\n")
        return result.hexdigest()
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


def run_steps(steps, argvs, cwd, log_path, event_path, emit, before_each, values=None, tool_names=(),
              target_name=None, any_host=False):
    """Run a manifest's ordered steps; PadMint emits the stage events itself."""
    event_path.parent.mkdir(parents=True, exist_ok=True)
    code, cancelled = 0, False
    for step, argv in zip(steps, argvs):
        stage = step["stage"]
        env = backend_env((values or {}).get("jobs"), tool_names, target_name, any_host)
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
            "python": sys.executable, "ios_sdk": getattr(args, "ios_sdk", ""),
            "ios_toolchain": getattr(args, "ios_toolchain", "")}


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


# Apple's /usr/bin/python3, which PadMint.command runs, is an xcrun shim: it exports the Mac
# SDK as SDKROOT, and /usr/local as CPATH and LIBRARY_PATH, to everything PadMint starts.
# A device build must pick its own SDK and libraries. With the Mac's, CMake links iPhone code
# against macOS libraries (MaskPad: "building for 'iOS', but linking in dylib ... built for macOS").
DEVICE_TARGETS = {"ios": "iPhone", "tvos": "Apple TV"}
HOST_BUILD_VARIABLES = ("SDKROOT", "CPATH", "LIBRARY_PATH")


def inherited_env(target_name=None):
    """(this process's environment without host build variables for a device target, their names)."""
    env = dict(os.environ)
    removed = [key for key in HOST_BUILD_VARIABLES if key in env] if target_name in DEVICE_TARGETS else []
    for key in removed:
        del env[key]
    return env, removed


def backend_env(jobs, tool_names=(), target_name=None, any_host=False):
    """Environment for backend processes: PadMint's tools first on PATH, and the
    job cap for `cmake --build`. PADMINT_CACHE is a folder shared by every
    checkout of every game version, for downloads a backend can reuse after an
    update (it must still check them, as for any cache). For iPhone and Apple TV
    targets the inherited SDKROOT, CPATH and LIBRARY_PATH are left out."""
    base, _removed = inherited_env(target_name)
    env = tools.environment(tool_names, host_id(), base, any_host) if tool_names else base
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
    if check == "none" and output.suffix.lower() == ".ipa":
        return validate_ipa(output, None, game_revision, disc_sha256)
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
        folder_output = target.get("output") == "folder"
        output = attempt / ("personal" if folder_output else f"personal.{target.get('output', 'ipa')}")
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
            message = (f"{backend.get('stage', '')} {backend.get('event', '')}{counts}".strip()
                       or fields.get("status") or fields.get("reason") or "")
            print(f"[{record['build_elapsed_seconds']}s] {event}: {message}".strip(), flush=True)
            stage = backend.get("stage")
            if stage:
                report("stage", stage=stage, event=backend.get("event"), completed=backend.get("completed"),
                       total=backend.get("total"), unit=backend.get("unit"))
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
        _env, removed = inherited_env(target_name)
        if removed:
            note = (f"PadMint ignores {', '.join(removed)} for {DEVICE_TARGETS[target_name]} builds: "
                    "they point at this Mac's own SDK or libraries.")
            print(note, flush=True)
            with (attempt / "backend.log").open("a") as log:
                log.write(note + "\n")

        def recheck(phase):
            record["checkout_check"] = phase + "-failed"
            check_checkout(repo, args.revision)
            record["checkout_check"] = phase + "-passed"

        try:
            module_spec = None if args.source_only else target.get("ios_module")
            if module_spec:
                # The universal iPhone pipeline: PadMint's open-source SDK for the steps,
                # then PadMint checks the module and puts it in the published app.
                if not app_path(args):
                    raise ValueError("an iPhone game module needs the published app (--app)")
                print("Preparing the iPhone SDK from open-source parts…", flush=True)
                module_env = backend_env(args.jobs, target.get("tools", []), target_name, any_host=True)
                prepared = ios_module.prepare(work / "padmint-ios-sdk", Path(app_path(args)), module_env)
                args.ios_sdk, args.ios_toolchain = str(prepared["sdk"]), str(prepared["toolchain"])
            argv = command(args, repo, disc, work, output)
            events = work / "logs/progress.jsonl"
            if "steps" in target:
                code, cancelled = run_steps(target["steps"], argv, repo, attempt / "backend.log",
                                            events, emit, lambda: recheck("before-launch"),
                                            values=placeholder_values(args, repo, disc, work, output),
                                            tool_names=target.get("tools", []), target_name=target_name,
                                            any_host=bool(module_spec))
            else:
                code, cancelled = run_process(argv, repo, attempt / "backend.log", events, emit,
                                              before_spawn=lambda: recheck("before-launch"),
                                              append=True,  # after PadMint's own notes
                                              env=backend_env(args.jobs, target.get("tools", []), target_name,
                                                              bool(module_spec)))
            recheck("after-exit")
            if code == 0 and module_spec:
                module_file = Path(expand([module_spec["file"]],
                                          placeholder_values(args, repo, disc, work, output))[0])
                llvm = ios_module.llvm_root(module_env)
                ios_module.check_imports(llvm, module_file, prepared["executable"])
                ios_module.insert(Path(app_path(args)), module_file, module_spec["into"], output, llvm,
                                  work / "padmint-ios-module")
                print(f"Added your game module to the app: {module_spec['into']}", flush=True)
            if code == 0 and folder_output and not args.source_only:
                finished = Path(expand([target["folder"]], placeholder_values(args, repo, disc, work, output))[0])
                if finished.is_dir():
                    # Moved, not copied: the folder holds a copy of the disc, so a second copy
                    # would double the space it takes. The backend makes it again next time.
                    shutil.move(str(finished), str(output))
            if code == 0 and not args.source_only:
                if not (output.is_dir() and any(output.iterdir()) if folder_output
                        else output.is_file() and output.stat().st_size > 0):
                    raise ValueError("Backend exited successfully but produced no output")
                record["package_validation"] = check_output(target.get("check", "none"), output,
                                                            args.revision, identity["disc_sha256"])
                apple = record["package_validation"].get("apple_compatibility", {})
                if apple.get("scene_startup") == "unverified" and any(
                        int(item["sdk"].split(".")[0]) >= 27 for item in apple["linked_slices"]):
                    print("Apple scene startup could not be verified from this package. "
                          "The build is complete, but launch on your device still needs testing.", flush=True)
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
            record["failure_message"] = str(error)
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
        return ("a secure download failed its certificate check. Check this device's date and time "
                "and install available certificate updates. On a managed network, ask its administrator "
                "to check HTTPS access, or retry on another trusted network. Keep certificate "
                "verification and security software enabled, then run PadMint again.")
    if NETWORK_ERRORS.search(text):
        hosts = re.findall(r"https?://([A-Za-z0-9.-]+)", text)
        where = hosts[-1] if hosts else "a download server"
        return (f"a download from {where} was blocked or failed. Check your internet connection, and "
                f"whether a VPN, a firewall or an antivirus web filter blocks {where}. Then run PadMint "
                "again; finished downloads are kept.")
    return None


def latest_release(repo_url):
    """The game's latest GitHub release that PadMint builds from: tag and downloadable assets.

    Uses the release web pages, not GitHub's API: the API allows 60 unsigned
    requests an hour per network address, which shared networks run out of.
    /releases/latest redirects to the tag, and every Pad release lists its
    files in SHA256SUMS. A game's latest release can be for something PadMint
    does not build (BlueWake publishes ready-to-play Windows downloads): then
    the newest release that publishes a PadMint recipe is used instead.
    """
    base = repo_url.removesuffix(".git").rstrip("/")
    with tools.open_url(f"{base}/releases/latest") as response:
        landed = response.geturl()
    if "/releases/tag/" not in landed:
        raise ValueError(f"{base} has no published release yet")
    tag = urllib.parse.unquote(landed.rsplit("/releases/tag/", 1)[1].split("?")[0].strip("/"))
    latest = release_assets(base, tag)
    if has_recipe(latest[1]):
        return latest
    for other in release_tags(base)[:RECENT_RELEASES]:
        if other != tag:
            found = release_assets(base, other)
            if has_recipe(found[1]):
                return found
    return latest


RECENT_RELEASES = 8


def has_recipe(assets):
    return any(name.endswith("-padmint.json") for name in assets)


def release_tags(base):
    """Tags on the game's releases page, newest first (the page lists the most recent few).
    Empty when the page cannot be read."""
    try:
        with tools.open_url(f"{base}/releases") as response:
            page = response.read().decode("utf-8", "replace")
    except (RuntimeError, OSError):
        return []
    path = urllib.parse.urlsplit(base).path
    tags = []
    for found in re.findall(re.escape(path) + r'/releases/tag/([^"?#<>\s]+)', page):
        tag = urllib.parse.unquote(found.strip("/"))
        if tag not in tags:
            tags.append(tag)
    return tags


def release_assets(base, tag):
    """(tag, assets) for one release, from its SHA256SUMS."""
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


def player_target(manifest, platform_name):
    """Reject unavailable targets/hosts before the player downloads build inputs."""
    target = manifest["targets"].get(platform_name)
    if target is None or ("command" not in target and "steps" not in target):
        raise ValueError(f"{manifest['name']} cannot be built for {platform_name} yet")
    host = host_id()
    state = target["hosts"].get(host, "unsupported")
    if state not in RUNNABLE_STATES:
        available = ", ".join(f"{name} ({status})" for name, status in target["hosts"].items()
                              if status in RUNNABLE_STATES) or "none yet"
        raise ValueError(f"{manifest['name']} {platform_name} builds are {state} on {host}. "
                         f"Available build hosts: {available}.")
    return target


def report(phase, **fields):
    """One line in the window's events file (PADMINT_EVENTS): what PadMint is doing, so the
    page can show it as it happens. The terminal output does not change."""
    path = os.environ.get("PADMINT_EVENTS")
    if not path:
        return
    try:
        with open(path, "a", encoding="utf-8") as stream:
            stream.write(json.dumps(dict(phase=phase, time=round(time.time(), 1), **fields)) + "\n")
    except OSError:
        pass


def _make(game, platform_name, disc, out, ref=None, app=None, jobs=None, results=None):
    entry = catalog().get(game)
    if entry is None:
        raise ValueError(f"unknown game {game}; see padmint list")
    release = None
    report("release", state="running", repo=entry["repo_url"])
    if ref is None:
        # Only small release metadata/recipe downloads precede this check. Pin
        # the source and app assets to that same tag, even if Latest changes.
        release = latest_release(entry["repo_url"])
        manifest, _source = published_recipe(game, release=release)
        player_target(manifest, platform_name)
    report("release", state="done", repo=entry["repo_url"], version=release[0] if release else ref)
    home = tools.tools_root().parent
    source, ref, assets = release_source(game, ref, release=release)
    report("source", state="done", repo=entry["repo_url"], version=ref, folder=str(source))
    manifest, _source = manifest_for(game, source)
    # Explicit refs skip release preflight/network lookup; both paths must
    # trust the actual selected checkout's recipe before installing tools.
    target = player_target(manifest, platform_name)
    if not needs_build_input(manifest):
        disc = None  # the game file is added in the app, not read by the build
    elif disc is None:
        raise ValueError(f"{manifest['name']} needs your own game file (--disc)")
    missing_programs = [(tool, detail) for tool in player_requirements(manifest)
                        for ok, detail in [check_program(tool)] if not ok]
    if missing_programs:
        raise ValueError(f"{manifest['name']} needs these installed first:\n"
                         + "".join(f"  {label(tool)}: {tool['note']}\n" for tool, _ in missing_programs)
                         + "Then run PadMint again.")
    missing = tools.missing_system_library(target.get("tools", []), host_id())
    if missing:
        raise ValueError(missing[1])
    accepted = game_file.check_before_tools(manifest, target, disc, host_id())
    if accepted:
        print(f"Your game file: {accepted}", flush=True)
    print(t("step_tools"), flush=True)
    report("tools", state="running", folder=str(tools.tools_root()))
    tools.install(target.get("tools", []), host_id(), any_host=bool(target.get("ios_module")),
                  report=lambda **fields: report("tool", **fields))
    report("tools", state="done", folder=str(tools.tools_root()))
    version = (read_game_version(source) or {}).get("version") or ref.lstrip("v")
    if target.get("published_app") and app is None:
        name = target["published_app"].format(version=version)
        print(t("published_app", name=name), flush=True)
        report("app", state="running", name=name, repo=entry["repo_url"])
        app = published_app(name, assets, home / "apps" / game)
        report("app", state="done", name=name, repo=entry["repo_url"])
    jobs = jobs or default_jobs()
    print(t("step_build", jobs=jobs), flush=True)
    report("build", state="running", jobs=jobs)
    args = argparse.Namespace(game=game, repo=source, revision=git(source, "rev-parse", "HEAD"),
                              disc=disc, target=platform_name, workspace_root=None, jobs=jobs,
                              source_only=False, no_mods=False, app=app)
    finish_submodules(source)
    code = execute(args, source, disc)
    if code != 0:
        report("build", state="cancelled" if code == 130 else "failed")
        if code != 130:
            print(t("build_stopped", url=f"{entry['repo_url']}/issues"), file=sys.stderr)
        return code
    report("build", state="done")
    report("save", state="running", folder=str(out))
    out.mkdir(parents=True, exist_ok=True)
    safe_version = re.sub(r"[^A-Za-z0-9._-]", "_", version)  # a branch name such as codex/x has a slash
    result = out / f"{manifest['name']}-v{safe_version}-{platform_name}-personal{args.output_path.suffix}"
    if args.output_path.is_dir():
        if result.exists():
            # An update: write the new files over the old folder, so anything the player
            # added to it stays.
            copy_files(tools._long(args.output_path), tools._long(result))
        else:
            shutil.move(str(args.output_path), str(result))
    else:
        shutil.copyfile(args.output_path, result)
    platform_label = t(f"platform_{platform_name}") if f"platform_{platform_name}" in MESSAGES else platform_name
    print(t("your_copy", name=manifest["name"], platform=platform_label, path=result))
    if results is not None:
        results.append(result)
    save_game_data(args.output_path, out, manifest["name"],
                   import_label=(entry.get("game_data_import") or {}).get(platform_name))
    report("save", state="done", folder=str(out), file=str(result))
    print(t("keep_private"))
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
        print(t("data_exists", name=name, path=target), file=stream)
        return target
    partial = target.with_name(target.name + ".partial")
    if partial.exists():
        shutil.rmtree(tools._long(partial))
    size = sum(p.stat().st_size for p in data.rglob("*") if p.is_file()) / (1 << 30)
    print(t("data_saving", name=name, size=f"{size:.1f}"), file=stream, flush=True)
    copy_files(tools._long(data), tools._long(partial))
    partial.replace(target)
    print(t("data_saved_phone" if on_android() else "data_saved_computer", name=name, path=target,
            label=import_label or "Import from Extracted Folder"), file=stream)
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
    return [tool for tool in host_requirements(manifest) if tool.get("player")]


def host_requirements(manifest):
    """The recipe's requirements.tools that apply on this computer: all, except those whose
    "hosts" name other build hosts."""
    return [tool for tool in manifest.get("requirements", {}).get("tools", [])
            if host_id() in tool.get("hosts", [host_id()])]


def label(tool):
    """What a requirements.tools entry is called for people: its label, else the program's name."""
    return tool.get("label", tool["name"])


def check_program(tool):
    """(ok, detail) for a requirements.tools entry: on PATH, its version check runs without an
    error (xcrun is always there, but xcrun metal fails until the Metal Toolchain is installed),
    and new enough if it names a minimum. The name may be a path with %VARIABLES% (Visual
    Studio's vswhere.exe is never on PATH)."""
    path = shutil.which(os.path.expandvars(tool["name"]))
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
    if result.returncode:
        return False, tool.get("note") or f"{detail} (exit {result.returncode})"
    if "min_version" not in tool:
        return True, detail
    found = version_tuple(text[0]) if text else None  # no answer is not a version
    return (found is not None and found >= version_tuple(str(tool["min_version"])),
            f"{detail} (need {tool['min_version']}+)" if text else tool.get("note") or "not installed")


def published_recipe(game, release=None):
    """(recipe, where it came from): the one the game's latest release publishes, checked
    against the release's SHA256SUMS, or PadMint's built-in copy when that can't be had."""
    entry = catalog().get(game)
    if entry is None:
        raise ValueError(f"unknown game {game}; see padmint list")
    try:
        tag, assets = release if release is not None else latest_release(entry["repo_url"])
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
            report(ok, label(tool), detail if ok or detail == tool["note"] else f"{detail}; {tool['note']}")
        needed = catalog()[game].get("free_space_gb", 0)
        home = tools.tools_root().parent
        existing = next(path for path in [home, *home.parents] if path.exists())
        free = shutil.disk_usage(existing).free / (1 << 30)
        report(free >= needed, "free disk space", f"{free:.0f} GB free, {needed} GB needed")
        print(f"{problems} item(s) to fix" if problems else "Ready", file=stream)
        return 1 if problems else 0
    for tool in host_requirements(manifest):
        ok, detail = check_program(tool)
        report(ok, label(tool), detail)
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


PLATFORM_NAMES = {"android": "Android", "ios": "iPhone and iPad", "macos": "Mac"}
# The phone's Download folder, shared with its apps (Termux asks once for access).
PHONE_DOWNLOADS = Path("/sdcard/Download")
# Termux's command that opens an address in the phone's browser. Ubuntu inside Termux
# (proot-distro) sees Termux's own files, so PadMint can run it from there.
TERMUX_OPEN_URL = Path("/data/data/com.termux/files/usr/bin/termux-open-url")


def next_step_text(entry, platform_name, result, lang=None):
    """(steps, note, guide): the few steps that get this file into the game, in the player's words."""
    guide = entry.get("player_help") or f"{entry['repo_url']}#get-{entry['id']}"
    steps = (entry.get("player_next") or {}).get(platform_name)
    if not steps or result is None:
        return [], None, guide
    instructions = localized(steps, "steps", lang)
    if platform_name == "android" and on_android():
        instructions = localized(steps, "phone_steps", lang) or instructions
    return ([step.format(file=result.name, folder=result.parent) for step in instructions],
            localized(steps, "note", lang), guide)


def next_steps(entry, platform_name, result, stream):
    """After a build: the few steps that get this file into the game, in the player's words."""
    instructions, note, guide = next_step_text(entry, platform_name, result)
    if not instructions:
        print(t("next_link", guide=guide), file=stream)
        return
    print(t("step_next"), file=stream)
    for number, step in enumerate(instructions, 1):
        print(f"  {number}. {step}", file=stream)
    if note:
        print(note, file=stream)
    print(t("full_guide", guide=guide), file=stream)


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


def choose(title, options, ask, stream, prompt=None):
    """options: [(value, label)]. One option is chosen without asking."""
    prompt = prompt or t("number")
    if len(options) == 1:
        print(f"{title}: {options[0][1]}", file=stream)
        return options[0][0]
    print(title, file=stream)
    for number, (_value, label) in enumerate(options, 1):
        print(f"  {number}. {label}", file=stream)
    while True:
        answer = ask(prompt).strip()
        if answer.isdigit() and 1 <= int(answer) <= len(options):
            return options[int(answer) - 1][0]
        print(t("menu_range", count=len(options)), file=stream, flush=True)


def file_problem(disc):
    """Why a dropped path can't be used yet, in the player's words; None when it can."""
    if not disc.is_file():
        return t("no_file", path=disc)
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
        print(t("reading_file"), file=stream, flush=True)
        try:
            tools.install(["nodtool"], host_id(), stream=io.StringIO())
            _title, game_id, _revision = game_file.read_disc(disc, tools.executable("nodtool", host_id()))
        except (OSError, RuntimeError, ValueError, subprocess.SubprocessError):
            return []
    matches = [(id_, name) for id_, name, _ in games if game_id in (catalog()[id_].get("game_ids") or [])]
    if len(matches) == 1:
        print(t("game_from_file", name=matches[0][1], game_id=game_id), file=stream)
    return [id_ for id_, _ in matches]


def player_games():
    """[(game, name, platforms)] a player can make on this computer. iPhone builds need Xcode
    on Apple Silicon, except games marked ios_off_mac, which also build on Windows and Linux
    computers. An Intel Mac and a phone make Android copies. A Windows copy is made on the
    Windows PC it runs on."""
    host = host_id()
    apple_silicon = host == "macos-arm64"
    computer_off_mac = host.startswith(("windows-", "linux-")) and not on_android()
    here = {"ios": None, "windows": host.startswith("windows-")}
    games = []
    for game, entry in sorted(catalog().items()):
        ios_here = apple_silicon or (computer_off_mac and entry.get("ios_off_mac", False))
        here["ios"] = ios_here
        platforms = [name for name in entry.get("player_targets", []) if here.get(name, True)]
        if platforms:
            name = (entry.get("manifest") or {}).get("name") or entry.get("name", game)
            games.append((game, name, platforms))
    return games


def platform_label(platform_name, lang=None):
    """How the menu names a device: an iPhone copy needs this Mac, or is experimental elsewhere."""
    key = {"android": "android", "ios": "ios_mac" if host_id() == "macos-arm64" else "ios_off_mac",
           "windows": "windows_here"}
    if platform_name not in key:
        return platform_name
    return phrase(key[platform_name], lang) if lang else t(key[platform_name])


def downloads():
    """[(app, name)]: apps with nothing to build, only their published app and the player's
    own files (catalog "download")."""
    return [(app, entry["name"]) for app, entry in sorted(catalog().items()) if entry.get("download")]


def download_steps(app, stream, lang=None):
    """How to get an app that needs no build, in the player's words."""
    entry = catalog()[app]
    say = (lambda key, **fields: phrase(key, lang, **fields)) if lang else t
    print(say("download_intro", name=entry["name"]), file=stream)
    for number, step in enumerate(localized(entry["download"], "steps", lang), 1):
        print(f"  {number}. {step}", file=stream)
    if entry.get("player_help"):
        print(say("full_guide", guide=entry["player_help"]), file=stream)
    return 0


def wants_window(environ=None):
    """PadMint opened by double-click (or typed in Termux on a phone) shows its window in the
    web browser. A script, a Linux computer without a desktop, a phone without Termux's
    termux-open-url, or PADMINT_TERMINAL=1 gets the terminal questions."""
    environ = os.environ if environ is None else environ
    if environ.get("PADMINT_TERMINAL") or not sys.stdin or not sys.stdin.isatty():
        return False
    if on_android():
        return TERMUX_OPEN_URL.exists()
    if sys.platform.startswith("linux") and not (environ.get("DISPLAY") or environ.get("WAYLAND_DISPLAY")):
        return False
    return True


def start(ask=input, stream=None):
    """The guided path for players: as few questions as possible. When several games are
    offered and the player's file names exactly one of them, the game is not asked for.
    The copy is saved to Downloads (padmint make --out chooses another folder)."""
    stream = stream or sys.stdout
    print(t("intro", version=__version__), file=stream)
    games = player_games()
    if not games:
        raise ValueError("no game can be made on this computer yet")
    disc = game = None
    offered = games
    if len(games) > 1 and any(catalog()[id_].get("game_ids") for id_, _, _ in games):
        answer = ask(t("drag_or_choose")).strip()
        while answer:
            disc = dropped_path(answer)
            problem = file_problem(disc)
            if problem is None:
                break
            print(problem, file=stream)
            answer = ask(t("drag_again")).strip()
            disc = None
        if disc is not None:
            found = game_from_file(disc, games, stream)
            # Two games may share a code: then ask, offering only those.
            if len(found) > 1:
                offered = [entry for entry in games if entry[0] in found]
            game = found[0] if len(found) == 1 else None
    if game is None:
        # iPhone and iPad apps to download: offered on computers, not on a phone making its own copy.
        extra = ([(app, f"{name} ({t('no_build')})") for app, name in downloads()]
                 if offered is games and not on_android() else [])
        game = choose(t("game"), [(game, name) for game, name, _ in offered] + extra, ask, stream)
        if game in dict(downloads()):
            return download_steps(game, stream)
    if catalog()[game].get("ready_to_play"):
        ready = catalog()[game]["ready_to_play"]
        print(f"\n{localized(ready, 'text')}\n  {ready['url']}\n", file=stream, flush=True)
    name, platforms = next((name, platforms) for id_, name, platforms in games if id_ == game)
    target = choose(t("make_it_for"), [(p, platform_label(p)) for p in platforms], ask, stream)
    if catalog()[game].get("player_game_file", "build") == "in-app":
        disc = None
        print(f"{name} asks for your own game file inside the app, after you install it.", file=stream)
    elif disc is None:
        # A phone has no window to drag files into: offer the game files in its Download folder.
        found = game_files(player_folder(), catalog()[game].get("manifest")) if on_android() else []
        if found:
            print("Choose a file from your phone's Download folder. Enter the number beside its "
                  "filename, not the game's disc ID (such as RMCP01).", file=stream, flush=True)
            disc = choose(f"Your {name} game file", [(path, path.name) for path in found]
                          + [(None, "Another file (type its path)")], ask, stream,
                          prompt="File number: ")
        elif on_android():
            print("No supported game file was found in your phone's Download folder. "
                  "Copy your disc image there and run padmint again, or enter its full file path below.",
                  file=stream, flush=True)
        prompt = t("type_game_file", name=name) if on_android() else t("drag_game_file", name=name)
        while disc is None:
            disc = dropped_path(ask(prompt))
            problem = file_problem(disc)
            if problem is not None:
                print(problem, file=stream)
                disc = None
        if on_android():
            print(f"Using file: {disc.name}", file=stream, flush=True)
    out = player_folder()
    print(t("saved_in", folder=out), file=stream)
    print(t("plan"), file=stream, flush=True)
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


def finish_submodules(repo, stream=None):
    """A download that stops partway can leave a submodule half cloned. Git reports it as
    changed (" M lib/rt64"), so PadMint's clean-checkout check refused every later run.
    Only for PadMint's own game folders. A changed gitlink is not proof of an interrupted
    download: refuse file edits anywhere inside it before updating without force.
    Anything else keeps the refusal (execute re-checks)."""
    games = (tools.tools_root().parent / "games").resolve()
    if games not in Path(repo).resolve().parents or not (Path(repo) / ".git").exists():
        return []
    command = [git_program(), "-C", str(repo)]
    status = subprocess.run(command + ["status", "--porcelain=v1", "-z", "--untracked-files=normal",
                                       "--ignore-submodules=none"],
                            capture_output=True, text=True)
    stage = subprocess.run(command + ["ls-files", "--stage", "-z"], capture_output=True, text=True)
    if status.returncode or stage.returncode or not status.stdout:
        return []
    gitlinks = {entry.split("\t", 1)[1] for entry in stage.stdout.split("\0") if entry.startswith("160000 ")}
    entries = [entry for entry in status.stdout.split("\0") if entry]
    # Unstaged (first column blank) changes to gitlinks only; a rename or staged change is not ours.
    if not all(entry[0] == " " and entry[3:] in gitlinks for entry in entries):
        return []
    paths = [entry[3:] for entry in entries]
    empty_clones = []

    def safe_to_update(folder):
        # An uninitialized submodule must be empty. Otherwise Git could inspect its
        # parent instead, or its initial checkout could overwrite existing files.
        if folder.is_symlink():
            return False
        if not (folder / ".git").exists():
            return not folder.exists() or (folder.is_dir() and not any(folder.iterdir()))
        nested = [command[0], "-C", str(folder)]
        # Clone can stop before the initial checkout. No files AND no index is
        # distinct from tracked deletions, which must keep the normal refusal.
        if all(path.name == ".git" for path in folder.iterdir()):
            index = subprocess.run(nested + ["rev-parse", "--git-path", "index"],
                                   capture_output=True, text=True)
            if index.returncode:
                return False
            if not (folder / index.stdout.strip()).exists():
                empty_clones.append(nested)
                return True
        status = subprocess.run(nested + ["status", "--porcelain=v1", "-z", "--untracked-files=all",
                                         "--ignore-submodules=none", "--ignored"],
                                capture_output=True, text=True)
        stage = subprocess.run(nested + ["ls-files", "--stage", "-z"], capture_output=True, text=True)
        if status.returncode or stage.returncode:
            return False
        links = {entry.split("\t", 1)[1] for entry in stage.stdout.split("\0")
                 if entry.startswith("160000 ")}
        entries = [entry for entry in status.stdout.split("\0") if entry]
        if not all(entry[0] == " " and entry[3:] in links for entry in entries):
            return False
        return all(safe_to_update(folder / path) for path in links)

    if not all(safe_to_update(Path(repo) / path) for path in paths):
        return []
    print(f"PadMint is finishing {', '.join(paths)} in {Path(repo).name}: an earlier download "
          "stopped partway.", file=stream or sys.stdout, flush=True)
    for nested in empty_clones:
        # update skips checkout when HEAD already matches the parent's gitlink.
        subprocess.run(nested + ["checkout", "--detach", "HEAD"], check=True)
    subprocess.run(command + ["submodule", "update", "--init", "--recursive", "--checkout", "--", *paths],
                   check=True)
    return paths


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


def release_source(game, ref=None, release=None):
    """The game's source at ref (default: its latest release), downloaded once and reused:
    (folder, ref, release assets). The recipe players build with lives in it."""
    entry = catalog().get(game)
    if entry is None:
        raise ValueError(f"unknown game {game}; see padmint list")
    home = tools.tools_root().parent
    assets = {}
    if ref is None:
        ref, assets = release if release is not None else latest_release(entry["repo_url"])
    source = home / "games" / f"{game}-{re.sub(r'[^A-Za-z0-9._-]', '_', ref)}"
    if not source_complete(source):
        check_free_space(home, entry.get("free_space_gb", 0))
        report("source", state="running", repo=entry["repo_url"], version=ref)
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
        targets = ", ".join(entry.get("player_targets") or []) or (
            "no build needed" if entry.get("download") else "see repo")
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
    commands.add_parser("start", help="Guided, in this terminal: pick a game, your game file and a device")
    commands.add_parser("list", help="Show supported games and platforms")
    history_parser = commands.add_parser("history", help="Summarize recorded builds in a checkout")
    history_parser.add_argument("--repo", type=Path, required=True)
    ui_parser = commands.add_parser("ui", help="Open the PadMint window in your web browser (the default)")
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
    make_parser.add_argument("platform", help="android, ios, macos or windows")
    make_parser.add_argument("--disc", type=Path, help="Your own game file (when the build reads it)")
    make_parser.add_argument("--out", type=Path, default=Path.cwd(), help="Where to save the result")
    make_parser.add_argument("--jobs", type=int, choices=range(1, 17),
                             help="Parallel compile jobs (default: from this computer's cores and memory)")
    make_parser.add_argument("--ref", help=argparse.SUPPRESS)
    make_parser.add_argument("--app", type=Path, help=argparse.SUPPRESS)
    make_parser.add_argument("--result-file", type=Path, help=argparse.SUPPRESS)  # the window reads it
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
        if args.action is None and wants_window():
            from .ui import serve
            return serve()
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
            tools.install(target.get("tools", []), host_id(), any_host=bool(target.get("ios_module")))
            print(f"Tools ready in {tools.tools_root()}")
            return 0
        if args.action == "get":
            return get_game(args.game, args.dest.expanduser().resolve(), args.ref)
        if args.action == "make":
            disc = args.disc.expanduser().resolve() if args.disc else None
            if disc is not None and not disc.is_file():
                raise ValueError(f"game file not found: {disc}")
            results = []
            code = make(args.game, args.platform, disc, args.out.expanduser().resolve(), args.ref,
                        args.app.expanduser().resolve() if args.app else None, args.jobs, results)
            if args.result_file and code == 0 and results:
                atomic_json(args.result_file, {"file": str(results[-1])})
            return code
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
