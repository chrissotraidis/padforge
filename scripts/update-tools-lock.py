#!/usr/bin/env python3
"""Regenerate padmint/tools.lock.json from the publishers' own checksums.

Every download PadMint installs is pinned here: URL, size where published and
the publisher's digest (GitHub release digests, CMake's SHA-256 list, Google's
SDK repository index, Microsoft's .NET release metadata). Nothing is hashed by
hand. Run it, review the diff, commit.
"""
import json
import re
import urllib.request
from pathlib import Path

GIT = "2.56.0"
GIT_TAG = "v2.56.0.windows.1"
DOTNET = "8.0"
CMAKE = "3.31.6"
NINJA = "v1.13.2"
NDK = ("29.0.14206865", "r29")
NODTOOL = "v2.0.0-alpha.9"
# Google publishes no Linux arm64 NDK. There, Android game packs use LLVM's own
# arm64 build (the NDK's clang major version) with the host-independent parts
# of the Linux NDK: its build scripts, sysroot and Android runtime libraries.
# On macOS, LLVM compiles N64 patch code (GoldenPad): Apple's clang cannot target
# MIPS. LLVM publishes no 21.x build for Intel Macs; 20.1.7 is its newest.
LLVM = "21.1.8"
LLVM_INTEL_MAC = "20.1.7"
NDK_PORTABLE = [f"android-ndk-{NDK[1]}/{path}" for path in (
    "source.properties", "build/", "meta/",
    "toolchains/llvm/prebuilt/linux-x86_64/sysroot/",
    "toolchains/llvm/prebuilt/linux-x86_64/lib/clang/21/lib/linux/")]
LLVM_TOOLS = ["clang", "clang++", "clang-{major}", "lld", "ld.lld", "llvm-ar", "llvm-ranlib", "llvm-nm",
              "llvm-strip", "llvm-objcopy", "llvm-readelf", "llvm-readobj", "llvm-cxxfilt"]


def fetch(url):
    with urllib.request.urlopen(url) as response:
        return response.read()


def github_assets(repo, tag):
    data = json.loads(fetch(f"https://api.github.com/repos/{repo}/releases/tags/{tag}"))
    return {asset["name"]: asset for asset in data["assets"]}


def github_file(assets, name, **extra):
    asset = assets[name]
    algo, digest = asset["digest"].split(":", 1)
    return {"url": asset["browser_download_url"], algo: digest, "size": asset["size"], **extra}


def llvm_download(release, top, **extra):
    """LLVM's release tarball, unpacking only the compilers, linkers and headers."""
    major = release.split(".")[0]
    return github_file(github_assets("llvm/llvm-project", f"llvmorg-{release}"), f"{top}.tar.xz",
                       archive="tar.xz", **extra, members=[
                           *(f"{top}/bin/{tool.format(major=major)}" for tool in LLVM_TOOLS),
                           f"{top}/lib/clang/{major}/include/"])


def main():
    tools = {}

    git = github_assets("git-for-windows/git", GIT_TAG)
    tools["git"] = {"version": GIT, "note": "Windows only; macOS and Linux use the system Git.",
                    "bin": ["cmd"], "hosts": {
        "windows-arm64": github_file(git, f"MinGit-{GIT}-arm64.zip", archive="zip"),
        "windows-x86_64": github_file(git, f"MinGit-{GIT}-64-bit.zip", archive="zip")}}

    releases = json.loads(fetch(f"https://builds.dotnet.microsoft.com/dotnet/release-metadata/{DOTNET}/releases.json"))
    sdk = releases["releases"][0]["sdk"]
    files = {item["rid"]: item for item in sdk["files"]
             if item["name"].endswith((".zip", ".tar.gz")) and "-sdk-" in item["url"]}
    rids = {"windows-arm64": "win-arm64", "windows-x86_64": "win-x64", "linux-x86_64": "linux-x64",
            "linux-arm64": "linux-arm64", "macos-arm64": "osx-arm64", "macos-x86_64": "osx-x64"}
    # Invariant globalization: Linux systems without libicu can still run the
    # SDK, and text handling is the same on every computer.
    tools["dotnet"] = {"version": sdk["version"], "bin": ["."], "env": {"DOTNET_ROOT": "."},
                       "set": {"DOTNET_SYSTEM_GLOBALIZATION_INVARIANT": "1",
                               "DOTNET_CLI_TELEMETRY_OPTOUT": "1", "DOTNET_NOLOGO": "1"}, "hosts": {
        host: {"url": files[rid]["url"], "sha512": files[rid]["hash"],
               "archive": "zip" if files[rid]["url"].endswith(".zip") else "tar.gz"}
        for host, rid in rids.items()}}

    sums = dict(reversed(line.split()) for line in fetch(
        f"https://github.com/Kitware/CMake/releases/download/v{CMAKE}/cmake-{CMAKE}-SHA-256.txt").decode().splitlines())
    cmake_names = {"windows-arm64": ("windows-arm64", "zip"), "windows-x86_64": ("windows-x86_64", "zip"),
                   "linux-x86_64": ("linux-x86_64", "tar.gz"), "linux-arm64": ("linux-aarch64", "tar.gz"),
                   "macos-arm64": ("macos-universal", "tar.gz"), "macos-x86_64": ("macos-universal", "tar.gz")}
    tools["cmake"] = {"version": CMAKE, "hosts": {}}
    for host, (suffix, archive) in cmake_names.items():
        name = f"cmake-{CMAKE}-{suffix}.{archive}"
        inner = f"cmake-{CMAKE}-{suffix}/" + ("CMake.app/Contents/bin" if host.startswith("macos") else "bin")
        tools["cmake"]["hosts"][host] = {
            "url": f"https://github.com/Kitware/CMake/releases/download/v{CMAKE}/{name}",
            "sha256": sums[name], "archive": archive, "bin": [inner]}

    ninja = github_assets("ninja-build/ninja", NINJA)
    ninja_names = {"windows-arm64": "ninja-winarm64.zip", "windows-x86_64": "ninja-win.zip",
                   "linux-x86_64": "ninja-linux.zip", "linux-arm64": "ninja-linux-aarch64.zip",
                   "macos-arm64": "ninja-mac.zip", "macos-x86_64": "ninja-mac.zip"}
    tools["ninja"] = {"version": NINJA.lstrip("v"), "bin": ["."], "hosts": {
        host: github_file(ninja, name, archive="zip") for host, name in ninja_names.items()}}

    index = fetch("https://dl.google.com/android/repository/repository2-3.xml").decode()
    start = index.index(f'path="ndk;{NDK[0]}"')
    block = index[start:index.index("</remotePackage>", start)]
    archives = {m.group(4): (m.group(1), m.group(2), m.group(3)) for m in re.finditer(
        r"<size>(\d+)</size>\s*<checksum type=\"(\w+)\">(\w+)</checksum>\s*<url>([^<]+)</url>", block)}
    ndk_host = {"windows-arm64": "windows", "windows-x86_64": "windows", "linux-x86_64": "linux",
                "macos-arm64": "darwin", "macos-x86_64": "darwin"}  # Google publishes no Linux arm64 NDK.
    tools["android-ndk"] = {"version": NDK[0], "env": {"ANDROID_NDK_ROOT": f"android-ndk-{NDK[1]}"},
                            "hosts": {}}
    for host, os_name in ndk_host.items():
        name = f"android-ndk-{NDK[1]}-{os_name}.zip"
        size, algo, digest = archives[name]
        tools["android-ndk"]["hosts"][host] = {
            "url": f"https://dl.google.com/android/repository/{name}", algo: digest,
            "size": int(size), "archive": "zip"}
    size, algo, digest = archives[f"android-ndk-{NDK[1]}-linux.zip"]
    tools["android-ndk"]["hosts"]["linux-arm64"] = {
        "url": f"https://dl.google.com/android/repository/android-ndk-{NDK[1]}-linux.zip", algo: digest,
        "size": int(size), "archive": "zip", "members": NDK_PORTABLE, "with": ["llvm"]}

    top = f"LLVM-{LLVM}-Linux-ARM64"
    mac, intel_mac = f"LLVM-{LLVM}-macOS-ARM64", f"LLVM-{LLVM_INTEL_MAC}-macOS-X64"
    tools["llvm"] = {"version": LLVM, "only_where_listed": True,
                     "note": "Linux arm64: compiles Android game packs with the NDK's portable parts. "
                             "macOS: compiles N64 patch code (GoldenPad); Apple's clang cannot target MIPS. "
                             f"LLVM publishes no 21.x build for Intel Macs, so they get {LLVM_INTEL_MAC}.",
                     "env": {"PADMINT_LLVM_ROOT": top}, "hosts": {
        "linux-arm64": llvm_download(LLVM, top),
        "macos-arm64": llvm_download(LLVM, mac, env={"PADMINT_LLVM_ROOT": mac}),
        "macos-x86_64": llvm_download(LLVM_INTEL_MAC, intel_mac, version=LLVM_INTEL_MAC,
                                      env={"PADMINT_LLVM_ROOT": intel_mac})}}

    nod = github_assets("encounter/nod", NODTOOL)
    nod_names = {"windows-arm64": "nodtool-windows-arm64.exe", "windows-x86_64": "nodtool-windows-x86_64.exe",
                 "linux-x86_64": "nodtool-linux-x86_64", "linux-arm64": "nodtool-linux-aarch64",
                 "macos-arm64": "nodtool-macos-arm64", "macos-x86_64": "nodtool-macos-x86_64"}
    tools["nodtool"] = {"version": NODTOOL.lstrip("v"), "bin": ["."], "hosts": {
        host: github_file(nod, name, archive="file",
                          rename="nodtool.exe" if host.startswith("windows") else "nodtool")
        for host, name in nod_names.items()}}

    lock = {"schema_version": 1, "tools": tools}
    path = Path(__file__).resolve().parents[1] / "padmint/tools.lock.json"
    path.write_text(json.dumps(lock, indent=2) + "\n")
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
