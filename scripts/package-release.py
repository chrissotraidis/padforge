#!/usr/bin/env python3
"""Make PadMint's release downloads: Windows (Python included), macOS and Linux.

Usage: scripts/package-release.py OUTPUT_FOLDER
Writes PadMint-vX.Y.Z-windows.zip, -macos.zip, -linux.zip and SHA256SUMS,
then runs PadMint's own release gate on them (ZIP everywhere: the gate opens
ZIP archives only).
"""
import hashlib
import io
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from padmint import __version__, gate  # noqa: E402

# Python's official embeddable package; digest from python.org's release page.
PYTHON = "3.13.15"
PYTHON_URL = f"https://www.python.org/ftp/python/{PYTHON}/python-{PYTHON}-embed-amd64.zip"
PYTHON_SHA256 = "d1f04d990aee1253d8569e8e5104e30fa9f5fa830899f14843448872d936a2cf"


def payload():
    """(archive path, source path) for everything a player needs."""
    files = [ROOT / name for name in (
        "README.md", "STATUS.md", "STATUS-HISTORY.md",
        "docs/COMPATIBILITY.md", "docs/ADDING_A_GAME.md",
    )]
    files += sorted((ROOT / "padmint").glob("*.py")) + [ROOT / "padmint/tools.lock.json"]
    files += sorted((ROOT / "catalog").glob("*.json"))
    return [(path.relative_to(ROOT).as_posix(), path) for path in files]


def add(bundle, name, data, executable=False):
    info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
    # Unix mode with the regular-file type bit: macOS's Archive Utility (what a
    # double-click in Finder uses) drops permissions stored without it, which
    # left PadMint.command unable to start (padmint#7).
    info.create_system = 3
    info.external_attr = (0o100755 if executable else 0o100644) << 16
    info.compress_type = zipfile.ZIP_DEFLATED
    bundle.writestr(info, data)


def windows_python():
    with urllib.request.urlopen(PYTHON_URL) as response:
        data = response.read()
    if hashlib.sha256(data).hexdigest() != PYTHON_SHA256:
        raise SystemExit(f"sha256 mismatch for {PYTHON_URL}")
    return zipfile.ZipFile(io.BytesIO(data))


def make_zip(path, top, launcher, python=None):
    with zipfile.ZipFile(path, "w") as bundle:
        for name, source in payload():
            add(bundle, f"{top}/{name}", source.read_bytes())
        add(bundle, f"{top}/{launcher.name}", launcher.read_bytes(), executable=True)
        if python is not None:
            for info in python.infolist():
                data = python.read(info)
                if info.filename.endswith("._pth"):
                    # The embedded Python also finds the padmint package beside it.
                    lines = data.decode().splitlines()
                    lines.insert(lines.index(".") + 1, "..")
                    data = ("\r\n".join(lines) + "\r\n").encode()
                add(bundle, f"{top}/python/{info.filename}", data)


def main():
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    out = Path(sys.argv[1]).resolve()
    out.mkdir(parents=True, exist_ok=True)
    top = f"PadMint-v{__version__}"
    launchers = ROOT / "launchers"
    made = [out / f"{top}-windows.zip", out / f"{top}-macos.zip", out / f"{top}-linux.zip"]
    make_zip(made[0], top, launchers / "PadMint.cmd", windows_python())
    make_zip(made[1], top, launchers / "PadMint.command")
    make_zip(made[2], top, launchers / "padmint.sh")
    sums = "".join(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n" for p in made)
    (out / "SHA256SUMS").write_bytes(sums.encode("utf-8"))
    print(sums, end="")
    return gate.audit(made, None)


if __name__ == "__main__":
    raise SystemExit(main())
