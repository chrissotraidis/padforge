"""`padmint.json` schema v1: what a game repository declares to PadMint.

A game repository owns its manifest. PadMint's catalog (`catalog/*.json`) lists
supported games and may carry an interim manifest for a repository that has not
added its own yet. Game-specific work stays in the game repository.
"""
import hashlib
import json
from pathlib import Path
import platform
import re
import string

SCHEMA_VERSION = 1
KINDS = {"disc-translation", "emulator-shell", "decomp-patches", "upstream-engine", "clean-engine"}
STATUSES = {"draft-untested", "experimental", "supported", "retired"}
HOSTS = {"macos-arm64", "macos-x86_64", "linux-x86_64", "linux-arm64", "windows-x86_64", "windows-arm64"}
HOST_STATES = {"verified", "experimental", "planned", "unsupported"}
RUNNABLE_STATES = {"verified", "experimental"}
TARGETS = {"ios", "macos", "android", "windows", "linux"}
# {app}: the published app a game pack links against (padmint build --app).
# {python}: the Python running PadMint (Windows has no python3 command).
PLACEHOLDERS = {"repo", "disc", "work", "output", "jobs", "app", "python"}
CHECKS = {"bluewake-ipa", "kartpad-ipa", "ipa", "none"}
INPUT_TIMES = {"build", "in-app"}
CATALOG = Path(__file__).resolve().parent.parent / "catalog"
_ID = re.compile(r"[a-z0-9][a-z0-9-]{0,39}")


def _require(condition, message):
    if not condition:
        raise ValueError(f"padmint.json: {message}")


def _argv(value, where):
    _require(isinstance(value, list) and all(isinstance(item, str) for item in value),
             f"{where} must be a list of strings")
    for item in value:
        for _, field, _, _ in string.Formatter().parse(item):
            _require(field is None or field in PLACEHOLDERS,
                     f"{where} uses unknown placeholder {{{field}}}")


def validate_manifest(data):
    """Validate a manifest dictionary and return it unchanged."""
    _require(isinstance(data, dict), "manifest must be an object")
    _require(data.get("schema_version") == SCHEMA_VERSION, f"schema_version must be {SCHEMA_VERSION}")
    _require(isinstance(data.get("id"), str) and _ID.fullmatch(data["id"]), "id must be a short lowercase slug")
    for field in ("name", "game"):
        _require(isinstance(data.get(field), str) and data[field], f"{field} is required")
    _require(data.get("kind") in KINDS, f"kind must be one of {sorted(KINDS)}")
    _require(data.get("status") in STATUSES, f"status must be one of {sorted(STATUSES)}")
    inputs = data.get("inputs")
    _require(isinstance(inputs, list) and inputs, "inputs must list at least one accepted input")
    for item in inputs:
        _require(isinstance(item, dict) and isinstance(item.get("type"), str), "each input needs a type")
        _require(isinstance(item.get("formats", []), list), "input formats must be a list")
        _require(item.get("when", "build") in INPUT_TIMES, f"input when must be one of {sorted(INPUT_TIMES)}")
        for digest in item.get("verified_sha256", []):
            _require(isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest),
                     "verified_sha256 entries must be lowercase SHA-256 digests")
        game_ids = item.get("game_ids", [])
        _require(isinstance(game_ids, list) and all(isinstance(gid, str) and re.fullmatch(r"[0-9A-Z]{6}", gid)
                                                    for gid in game_ids),
                 "input game_ids must be six-character disc IDs such as RMCP01")
        revisions = item.get("revisions", [])
        _require(isinstance(revisions, list) and all(isinstance(value, int) and value >= 0 for value in revisions),
                 "input revisions must be disc revision numbers")
    targets = data.get("targets")
    _require(isinstance(targets, dict) and targets, "targets must declare at least one target")
    for name, target in targets.items():
        where = f"targets.{name}"
        _require(name in TARGETS, f"unknown target {name}")
        _require(isinstance(target, dict), f"{where} must be an object")
        hosts = target.get("hosts")
        _require(isinstance(hosts, dict) and hosts, f"{where}.hosts must map hosts to states")
        for host, state in hosts.items():
            _require(host in HOSTS, f"{where}.hosts has unknown host {host}")
            _require(state in HOST_STATES, f"{where}.hosts.{host} must be one of {sorted(HOST_STATES)}")
        runnable = any(state in RUNNABLE_STATES for state in hosts.values())
        _require(not ("command" in target and "steps" in target), f"{where} uses command or steps, not both")
        if "command" in target:
            _argv(target["command"], f"{where}.command")
        if "steps" in target:
            steps = target["steps"]
            _require(isinstance(steps, list) and steps, f"{where}.steps must be a non-empty list")
            names = []
            for index, step in enumerate(steps):
                _require(isinstance(step, dict) and isinstance(step.get("stage"), str) and step["stage"],
                         f"{where}.steps[{index}] needs a stage name")
                _argv(step.get("command"), f"{where}.steps[{index}].command")
                _require(step["command"], f"{where}.steps[{index}].command must not be empty")
                env = step.get("env", {})
                _require(isinstance(env, dict) and all(re.fullmatch(r"[A-Z][A-Z0-9_]*", key) for key in env),
                         f"{where}.steps[{index}].env must map UPPER_CASE names to values")
                _argv(list(env.values()), f"{where}.steps[{index}].env")
                names.append(step["stage"])
            _require(len(names) == len(set(names)), f"{where}.steps stage names must be unique")
            _require(not target.get("modes") and not target.get("options"),
                     f"{where}: steps targets do not support modes or options yet")
        _require(not runnable or "command" in target or "steps" in target,
                 f"{where} has a runnable host but no command or steps")
        if "tools" in target:
            from .tools import lock
            known = lock()
            _require(isinstance(target["tools"], list)
                     and all(isinstance(item, str) and item in known for item in target["tools"]),
                     f"{where}.tools must name tools from PadMint's tool lock: {sorted(known)}")
        if "published_app" in target:
            _require(isinstance(target["published_app"], str) and "{version}" in target["published_app"],
                     f"{where}.published_app must name the release asset, with {{version}}")
        modes = target.get("modes", {"full": []})
        _require(isinstance(modes, dict) and "full" in modes, f"{where}.modes must include full")
        for mode, extra in modes.items():
            _argv(extra, f"{where}.modes.{mode}")
        options = target.get("options", {})
        _require(isinstance(options, dict), f"{where}.options must be an object")
        for option, extra in options.items():
            _argv(extra, f"{where}.options.{option}")
        _require(target.get("check", "none") in CHECKS, f"{where}.check must be one of {sorted(CHECKS)}")
    requirements = data.get("requirements", {})
    _require(isinstance(requirements, dict), "requirements must be an object")
    for tool in requirements.get("tools", []):
        _require(isinstance(tool, dict) and isinstance(tool.get("name"), str), "each tool needs a name")
        if "version_args" in tool:
            _argv(tool["version_args"], f"tool {tool['name']}.version_args")
        if "min_version" in tool:
            _require(re.fullmatch(r"\d+(\.\d+)*", str(tool["min_version"])), "min_version must be dotted digits")
    disk = requirements.get("disk_gb", 0)
    _require(isinstance(disk, (int, float)) and disk >= 0, "requirements.disk_gb must be a number")
    publication = data.get("publication")
    _require(isinstance(publication, dict) and isinstance(publication.get("public_binaries"), bool),
             "publication.public_binaries must be true or false")
    return data


def manifest_sha256(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def needs_build_input(data):
    """True when the backend reads the player's disc/ROM during the build."""
    return any(item.get("when", "build") == "build" for item in data["inputs"])


def load_manifest(path):
    with Path(path).open() as stream:
        return validate_manifest(json.load(stream))


def catalog():
    """Return catalog entries keyed by game ID."""
    entries = {}
    for path in sorted(CATALOG.glob("*.json")):
        with path.open() as stream:
            entry = json.load(stream)
        if not isinstance(entry, dict) or entry.get("id") != path.stem:
            raise ValueError(f"catalog/{path.name}: id must match the file name")
        if not str(entry.get("repo_url", "")).startswith("https://"):
            raise ValueError(f"catalog/{path.name}: repo_url must be an https URL")
        revision = entry.get("reviewed_revision")
        if revision is not None and not re.fullmatch(r"[0-9a-f]{40}", str(revision)):
            raise ValueError(f"catalog/{path.name}: reviewed_revision must be a full commit or null")
        targets = entry.get("player_targets", [])
        if not isinstance(targets, list) or not set(targets) <= {"android", "ios", "macos"}:
            raise ValueError(f"catalog/{path.name}: player_targets lists android, ios or macos")
        if entry.get("player_game_file", "build") not in ("build", "in-app"):
            raise ValueError(f"catalog/{path.name}: player_game_file is build or in-app")
        for platform, steps in (entry.get("player_next") or {}).items():
            if platform not in targets or not isinstance(steps, dict) or not steps.get("steps") \
                    or not all(isinstance(step, str) for step in steps["steps"]):
                raise ValueError(f"catalog/{path.name}: player_next.{platform} needs a player target "
                                 "and a list of steps")
        ids = entry.get("game_ids", [])
        if not isinstance(ids, list) or not all(re.fullmatch(r"[0-9A-Z]{6}", str(i)) for i in ids):
            raise ValueError(f"catalog/{path.name}: game_ids lists six-character disc IDs")
        space = entry.get("free_space_gb", 0)
        if not isinstance(space, int) or isinstance(space, bool) or space < 0:
            raise ValueError(f"catalog/{path.name}: free_space_gb is a whole number of GB")
        if entry.get("manifest") is not None:
            validate_manifest(entry["manifest"])
            if entry["manifest"]["id"] != entry["id"]:
                raise ValueError(f"catalog/{path.name}: interim manifest id mismatch")
        entries[entry["id"]] = entry
    return entries


def repository_manifest(repo):
    """A checkout's padmint.json, or padforge.json from before the rename (0.2.0)."""
    for name in ("padmint.json", "padforge.json"):
        if (Path(repo) / name).is_file():
            return Path(repo) / name
    return None


def manifest_for(game, repo=None):
    """The game repository's own manifest wins; otherwise the catalog's interim one."""
    path = repository_manifest(repo) if repo is not None else None
    if path is not None:
        data = load_manifest(path)
        if data["id"] != game:
            raise ValueError(f"Checkout's {path.name} declares {data['id']}, not {game}")
        return data, "repository"
    entry = catalog().get(game)
    if entry is None:
        raise ValueError(f"Unknown game {game}; see 'padmint list'")
    if entry.get("manifest") is None:
        raise ValueError(f"{game} expects padmint.json in its checkout")
    return entry["manifest"], "catalog"


def host_id():
    system = {"Darwin": "macos", "Linux": "linux", "Windows": "windows"}.get(platform.system(), platform.system().lower())
    machine = platform.machine().lower()
    machine = {"aarch64": "arm64", "amd64": "x86_64"}.get(machine, machine)
    return f"{system}-{machine}"


def expand(template, values):
    """Fill placeholders inside a fixed argument list; values never become shell text."""
    return [item.format_map(values) for item in template]
