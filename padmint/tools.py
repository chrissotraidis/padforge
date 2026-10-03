"""Tools PadMint downloads for a game: pinned, checked, kept in PadMint's own folder.

The lock (tools.lock.json, made by scripts/update-tools-lock.py) names every
download and the publisher's digest. Nothing is installed system-wide: builds
get the tools on PATH, plus the environment variables they need.
"""
import ctypes
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tarfile
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

from .manifest import on_android
from .say import t

LOCK = Path(__file__).with_name("tools.lock.json")
DIGESTS = ("sha512", "sha256", "sha1")
# Seconds without any data before a download counts as stalled.
TIMEOUT = 60
# .NET reserves 256 GB of address space for its heap unless the heap has a limit;
# Android kernels give a program less ("GC heap initialization failed"), so on a
# phone the heap gets a limit above any phone's memory.
ANDROID_DOTNET_HEAP = "0x400000000"


def open_url(url):
    """urlopen that gives up on a stalled connection and explains failures plainly."""
    try:
        return urllib.request.urlopen(url, timeout=TIMEOUT)
    except OSError as error:  # URLError, timeouts and SSL errors are all OSErrors
        raise RuntimeError(download_problem(url, error)) from error


def download_problem(url, error):
    if "CERTIFICATE_VERIFY_FAILED" in str(error):
        return ("This Python cannot check website certificates, so PadMint cannot download. "
                "On a Mac, start PadMint with PadMint.command (it uses Apple's Python), or run "
                "Install Certificates.command in your Python folder. Then run PadMint again.")
    host = urllib.parse.urlsplit(url).hostname or url
    reason = getattr(error, "reason", error)
    return (f"PadMint could not reach {host} to download {url} ({reason}). Check your internet "
            f"connection, and whether a VPN, a firewall or an antivirus web filter blocks {host}. "
            "Then run PadMint again; finished downloads are kept.")


def lock():
    return json.loads(LOCK.read_text())["tools"]


def tools_root():
    return home() / "tools"


def home():
    """PadMint's own folder. PadMint was called PadForge before 0.2.0; its folder
    (~/.padforge) is moved here once so downloaded tools are not fetched again."""
    chosen = os.environ.get("PADMINT_HOME")
    if chosen:
        return Path(chosen)
    folder, legacy = Path.home() / ".padmint", Path.home() / ".padforge"
    if not folder.exists() and legacy.is_dir():
        try:
            legacy.rename(folder)
        except OSError:  # For example a file still open on Windows: keep using it.
            return folder if folder.exists() else legacy
    return folder


def version(tool, host):
    """A host's download may pin its own version (LLVM has no 21.x build for
    Intel Macs, so they get 20.1.7)."""
    return tool["hosts"].get(host, {}).get("version", tool["version"])


def _folder(name, tool, host):
    return tools_root() / f"{name}-{version(tool, host)}"


def installed(name, host):
    """True when PadMint's own copy of a tool is ready for this host."""
    return _installed(_folder(name, lock()[name], host))


def _marker(folder):
    return folder / ".padmint-installed"


def _installed(folder, entry=None):
    """Installed from this lock entry. A changed entry (for example more members
    of the same archive) installs again; PadForge's markers are kept as they are."""
    marker = _marker(folder)
    if not marker.is_file():
        return (folder / ".padforge-installed").is_file()
    if entry is None:
        return True
    try:
        return json.loads(marker.read_text()) == entry
    except ValueError:
        return False


def _download(entry, destination, stream, label=""):
    algo = next(key for key in DIGESTS if key in entry)
    digest = hashlib.new(algo)
    partial = destination.with_name(destination.name + ".partial")
    name, _, version_text = (label or "a tool").partition(" ")
    host = urllib.parse.urlsplit(entry["url"]).hostname or entry["url"]
    print(t("downloading", name=name, version=version_text, host=host), file=stream, flush=True)
    with open_url(entry["url"]) as response, partial.open("wb") as handle:
        total = int(response.headers.get("Content-Length") or 0)
        done, shown = 0, 0
        try:
            while chunk := response.read(1 << 20):
                digest.update(chunk)
                handle.write(chunk)
                done += len(chunk)
                # Big tools (the Android NDK is over 1 GB) show progress every 10%.
                if total > 50 << 20 and done * 10 // total > shown:
                    shown = done * 10 // total
                    print(t("percent", percent=shown * 10, size=f"{total / (1 << 30):.1f}"),
                          file=stream, flush=True)
        except OSError as error:
            raise RuntimeError(download_problem(entry["url"], error)) from error
    if digest.hexdigest() != entry[algo].lower():
        partial.unlink()
        raise RuntimeError(f"{algo} mismatch for {entry['url']}; nothing was installed")
    partial.replace(destination)


def _wanted(name, members):
    """members (from the lock) lists the only paths to unpack: exact names, or
    folders ending in "/". None unpacks everything."""
    if members is None:
        return True
    return any(name == item or (item.endswith("/") and name.startswith(item)) for item in members)


def _check_members(folder, members):
    """Every file the lock names must be in the download (folders may be empty)."""
    for item in members or []:
        path = Path(_long(folder / item))
        if not item.endswith("/") and not (path.exists() or path.is_symlink()):
            raise RuntimeError(f"the download has no {item}; nothing was installed")


def _extract_zip(archive, folder, members=None):
    links = []
    base = Path(_long(folder))
    with zipfile.ZipFile(archive) as bundle:
        for info in bundle.infolist():
            if not _wanted(info.filename, members):
                continue
            mode = info.external_attr >> 16
            if stat.S_ISLNK(mode):
                # zipfile would write the link as a small text file (the NDK's
                # clang is a link to clang-NN); make real links afterwards.
                links.append((info.filename, bundle.read(info).decode()))
                continue
            path = bundle.extract(info, base)
            if mode & 0o111 and os.name != "nt":
                os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    root = base.resolve()
    for name, target in links:
        link = base / name
        source = (link.parent / target).resolve()
        if (not link.resolve().is_relative_to(root) or Path(target).is_absolute()
                or not source.is_relative_to(root)):
            raise RuntimeError(f"link {name} -> {target} leaves the tool folder; nothing was installed")
        link.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.symlink(target, link, target_is_directory=source.is_dir())
        except OSError:  # Windows without link permission
            if source.is_dir():
                shutil.copytree(source, link)
            else:
                shutil.copy2(source, link)


def _extract_tar(archive, folder, members=None):
    with tarfile.open(archive) as bundle:
        chosen = [item for item in bundle.getmembers() if _wanted(item.name, members)]
        if os.name == "nt":
            # Extended-length paths (\\?\C:\...) accept only backslashes; tar names use "/".
            for item in chosen:
                item.name = item.name.replace("/", "\\")
        if sys.version_info >= (3, 12):
            bundle.extractall(_long(folder), members=chosen, filter="data")
        else:
            bundle.extractall(_long(folder), members=chosen)


def _long(path):
    r"""On Windows, the extended-length form of path (\\?\C:\...).

    The Android NDK nests files about 235 characters deep, so below
    C:\Users\<name>\.padmint it passes Windows' 260-character limit once the
    user name is longer than 24 characters. Extended-length paths have no such
    limit. Other systems get the path unchanged.
    """
    if os.name != "nt":
        return str(path)
    full = os.path.abspath(str(path))
    if full.startswith("\\\\?\\"):
        return full
    if full.startswith("\\\\"):  # \\server\share\... on a network drive
        return "\\\\?\\UNC\\" + full[2:]
    return "\\\\?\\" + full


# Libraries a downloaded tool loads from the system, per host. Checked before any
# download: LLVM's linker for Linux arm64 needs libxml2.so.2, which minimal Linux
# installs lack and Ubuntu 25.10 and later no longer ship (they have libxml2.so.16).
SYSTEM_LIBRARIES = {("llvm", "linux-arm64"): {"library": "libxml2.so.2", "newer": "libxml2.so.16"}}


def _loadable(library):
    try:
        ctypes.CDLL(library)
        return True
    except OSError:
        return False


def missing_system_library(names, host):
    """(library, how to fix it) for the first system library these tools need and this
    computer lacks; None when everything is there. A newer library PadMint can link to
    (libxml2.so.16 for libxml2.so.2) counts as there."""
    table = lock()
    for name in _with_companions([n for n in names if n in table], host, table):
        need = SYSTEM_LIBRARIES.get((name, host))
        if need and not _loadable(need["library"]) and not _loadable(need["newer"]):
            return need["library"], system_library_fix(need["library"])
    return None


def system_library_fix(library):
    if library == "libxml2.so.2" and _only_new_libxml2():
        command = "sudo apt install libxml2-16"
    elif shutil.which("apt-get"):
        command = "sudo apt install libxml2"
    elif shutil.which("dnf"):
        command = "sudo dnf install libxml2"
    else:
        command = "install the package that provides libxml2.so.2 or libxml2.so.16"
    return (f"LLVM's linker, which PadMint downloads for this computer, needs the libxml2 library "
            f"({library}). Install it first ({command}), then run PadMint again. Nothing has been "
            "downloaded yet.")


def _system_path(library):
    """Where the system keeps a shared library (Linux), or None."""
    for ldconfig in ("ldconfig", "/sbin/ldconfig"):
        try:
            listing = subprocess.run([ldconfig, "-p"], capture_output=True, text=True).stdout
        except OSError:
            continue
        for line in listing.splitlines():
            name, _, path = line.strip().partition(" => ")
            if name.split(" (")[0] == library and path:
                return Path(path)
    for folder in ("/usr/lib/aarch64-linux-gnu", "/lib/aarch64-linux-gnu", "/usr/lib64", "/usr/lib"):
        if (Path(folder) / library).exists():
            return Path(folder) / library
    return None


def link_system_library(name, host, folder):
    """When the system has only the newer library, point the tool's own lib folder at it
    (LLVM's binaries look in $ORIGIN/../lib first). Only PadMint's folder is changed."""
    need = SYSTEM_LIBRARIES.get((name, host))
    if not need:
        return None
    root = next(iter(lock()[name].get("env", {}).values()), "")
    link = folder / root / "lib" / need["library"]
    if _loadable(need["library"]):
        if link.is_symlink():
            link.unlink()  # the system has the real library now
        return None
    if link.is_symlink() or link.exists():
        return link
    target = _system_path(need["newer"])
    if target is None:
        return None
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(target)
    return link


def _only_new_libxml2(os_release=Path("/etc/os-release")):
    """Ubuntu 25.10 and later ship only libxml2.so.16 (package libxml2-16)."""
    try:
        fields = dict(line.split("=", 1) for line in os_release.read_text().splitlines() if "=" in line)
    except OSError:
        return False
    if fields.get("ID", "").strip('"') != "ubuntu":
        return False
    try:
        version = tuple(int(part) for part in fields.get("VERSION_ID", "").strip('"').split("."))
    except ValueError:
        return False
    return version >= (25, 10)


def host_entry(tool, host, any_host=False):
    """A tool's download for host. Source archives marked any_host (the same files
    on every computer) also serve unlisted hosts when the caller asks for it: the
    universal iPhone module pipeline uses them on Macs too, without changing what
    existing recipes download there."""
    entry = tool["hosts"].get(host)
    if entry is None and any_host and tool.get("any_host") and tool["hosts"]:
        entry = tool["hosts"][sorted(tool["hosts"])[0]]
    return entry


def _with_companions(names, host, table, any_host=False):
    """names plus the tools a host's download declares it comes "with" (the
    Linux arm64 NDK comes with LLVM), so game manifests need not name them."""
    result = []
    for name in names:
        for item in [name, *(host_entry(table[name], host, any_host) or {}).get("with", [])]:
            if item not in result:
                result.append(item)
    return result


def install(names, host, stream=None, any_host=False):
    """Install the named tools for this host; already-installed tools are kept."""
    stream = stream or sys.stdout
    table = lock()
    for name in _with_companions(names, host, table, any_host):
        tool = table[name]
        entry = host_entry(tool, host, any_host)
        if entry is None:
            if tool.get("only_where_listed"):
                continue  # this host does not need it
            if name == "git" and shutil.which("git"):
                print(f"ok   git (system {shutil.which('git')})", file=stream)
                continue
            if name == "git":
                raise RuntimeError(
                    "Git is needed. Install it with your system's package manager "
                    "(for example: sudo apt install git, or on a Mac: xcode-select --install), "
                    "then run PadMint again.")
            raise RuntimeError(f"{name} {tool['version']} has no download for {host}")
        folder = _folder(name, tool, host)
        if _installed(folder, entry):
            print(t("tool_ready", name=name, version=version(tool, host)), file=stream)
            _report_link(link_system_library(name, host, folder), stream)
            continue
        staging = folder.with_name(folder.name + ".partial")
        if staging.exists():
            shutil.rmtree(_long(staging))
        staging.mkdir(parents=True)
        archive = staging / "download"
        _download(entry, archive, stream, f"{name} {version(tool, host)}")
        kind = entry["archive"]
        if kind != "file" and archive.stat().st_size > 50 << 20:
            # Unpacking the 0.8 GB Android NDK prints nothing for minutes on Windows.
            print(t("unpacking", name=name), file=stream, flush=True)
        if kind == "zip":
            _extract_zip(archive, staging, entry.get("members"))
            archive.unlink()
        elif kind in ("tar.gz", "tar.xz"):
            _extract_tar(archive, staging, entry.get("members"))
            archive.unlink()
        else:
            target = staging / entry["rename"]
            archive.replace(target)
            target.chmod(0o755)
        _check_members(staging, entry.get("members"))
        if folder.exists():
            shutil.rmtree(_long(folder))
        staging.replace(folder)
        _marker(folder).write_text(json.dumps(entry) + "\n")
        print(t("tool_got", name=name, version=version(tool, host)), file=stream)
        _report_link(link_system_library(name, host, folder), stream)


def _report_link(link, stream):
    if link is not None:
        print(f"ok   {link.name} (uses this computer's {Path(os.readlink(link)).name})", file=stream)


def environment(names, host, base=None, any_host=False):
    """base (default os.environ) with installed tools first on PATH."""
    env = dict(os.environ if base is None else base)
    paths = []
    table = lock()
    for name in _with_companions(names, host, table, any_host):
        tool = table[name]
        entry = host_entry(tool, host, any_host)
        folder = _folder(name, tool, host)
        if entry is None or not _installed(folder):
            continue
        for relative in entry.get("bin", tool.get("bin", [])):
            paths.append(str(folder / relative))
        for key, relative in entry.get("env", tool.get("env", {})).items():
            env[key] = str(folder / relative)
        env.update(tool.get("set", {}))
        if name == "dotnet" and on_android():
            env.setdefault("DOTNET_GCHeapHardLimit", ANDROID_DOTNET_HEAP)
    if paths:
        env["PATH"] = os.pathsep.join(paths + [env.get("PATH", "")])
    return env


def executable(name, host):
    """Full path to a tool: PadMint's installed copy first, then the system's.
    (Windows looks programs up on the parent's PATH, so pass full paths.)"""
    return shutil.which(name, path=environment([name], host).get("PATH")) or name
