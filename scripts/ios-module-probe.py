#!/usr/bin/env python3
"""Run the universal iPhone module pipeline end to end on this computer, with no game code.

Downloads PadMint's pinned open-source iPhone parts, assembles the SDK for a published
app without game code (KartPad's public IPA by default), compiles a small C++ library
that uses the app's exports and the device's C and C++ libraries, checks its imports and
puts it in a copy of the app. Used by CI on Windows, Linux and macOS.

Usage: scripts/ios-module-probe.py WORK_FOLDER [PUBLISHED_IPA]
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from padmint import ios_module, tools  # noqa: E402
from padmint.manifest import host_id  # noqa: E402
from padmint.package import validate_ipa  # noqa: E402

APP_URL = "https://github.com/chrissotraidis/kartpad/releases/download/v0.7.4/KartPad-v0.7.4-ios-unsigned.ipa"
APP_SHA256 = "74f0c7e82e1df2d3f32eb0893cb6f5040e50b6e7839272372425057e2b35714a"


def main():
    if len(sys.argv) not in (2, 3):
        raise SystemExit(__doc__)
    work = Path(sys.argv[1]).resolve()
    work.mkdir(parents=True, exist_ok=True)
    host = host_id()
    if len(sys.argv) == 3:
        app = Path(sys.argv[2]).resolve()
    else:
        import hashlib
        app = work / "published.ipa"
        data = urllib.request.urlopen(APP_URL).read()
        if hashlib.sha256(data).hexdigest() != APP_SHA256:
            raise SystemExit("published app checksum mismatch")
        app.write_bytes(data)
    tools.install(["libcxx", "cmake", "ninja"], host, any_host=True)
    env = tools.environment(["libcxx", "cmake", "ninja"], host, any_host=True)
    prepared = ios_module.prepare(work / "sdk", app, env)
    build = work / "build"
    cmake = tools.executable("cmake", host)
    subprocess.run([cmake, "-S", str(ROOT / "tests/ios-module-probe"), "-B", str(build), "-G", "Ninja",
                    f"-DCMAKE_TOOLCHAIN_FILE={prepared['toolchain']}", "-DCMAKE_BUILD_TYPE=Release"],
                   check=True, env=env)
    subprocess.run([cmake, "--build", str(build)], check=True, env=env)
    llvm = ios_module.llvm_root(env)
    module = build / "libgame.dylib"
    ios_module.check_imports(llvm, module, prepared["executable"])
    output = ios_module.insert(app, module, "Frameworks/libpadmint_probe.dylib", work / "probe.ipa", llvm,
                               work / "insert")
    report = validate_ipa(output, None, None, None)
    slices = report["apple_compatibility"]["linked_slices"]
    module_report = ios_module.linked(module)
    print(json.dumps({"host": host, "module": module_report, "app": slices}, indent=1))
    if module_report["platform"] != "ios" or module_report["minimum_os"] != "16.0.0":
        raise SystemExit("the module is not an iOS 16 arm64 library")
    print(f"Universal iPhone module pipeline passed on {host}: {output}")


if __name__ == "__main__":
    main()
