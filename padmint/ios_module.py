"""iPhone game modules on any computer: one pipeline for every game.

A game whose published iPhone app contains no game code declares an
`ios_module` in its recipe. PadMint then assembles the SDK below, gives the
game's build steps {ios_sdk} and {ios_toolchain}, checks the module the steps
build against the published app, and puts it inside a copy of that app.
The game repository only compiles its own code.

Apple's SDK may only be used on Apple computers, so the module is compiled with
LLVM against headers assembled here, on Windows, Linux and Macs alike, from:

- Apple's open-source releases (github.com/apple-oss-distributions, APSL 2.0):
  the C library, xnu, pthread, malloc and platform headers a pack includes,
  with the definitions Apple's own iPhone header install applies, and the
  availability headers made by Apple's AvailabilityVersions script;
- LLVM's libc++ headers (Apache 2.0 with LLVM exceptions), configured as LLVM
  configures libc++ for Apple systems (libcxx/cmake/caches/Apple.cmake);
- math.h, fenv.h and TargetConditionals.h written for KartPad and shared here
  (padmint/ios-sdk/include), because Apple publishes no arm64 source for them.

No Apple library is copied. The pack is linked with LLVM's ld64.lld in a flat
namespace: every name it imports is looked up by name when the app loads it,
which is how Apple's linker already binds the app's own exports in a pack built
on a Mac (-undefined dynamic_lookup). ld64.lld cannot mark a looked-up name as
thread-local, so the text stubs (write_stubs) name the app's thread-local
exports; they also stand in for libSystem and libc++, whose names are found on
the iPhone at load time.
PadMint downloads every part pinned by digest and names its folder in an
environment variable (SOURCES). SOURCES.json in the assembled SDK records the
origin, digest and license of every file.

Moved from KartPad's builder (kartpad_builder/ios_sdk.py, GPL-3.0-or-later,
same author) so every game shares it.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
import stat
import zipfile


class ModuleError(ValueError):
    """An iPhone module could not be prepared, checked or added; the message says why."""


HEADERS_DIR = Path(__file__).resolve().parent / "ios-sdk" / "include"



DEPLOYMENT_TARGET = "16.0"
TRIPLE = f"arm64-apple-ios{DEPLOYMENT_TARGET}"
SCHEMA = 1
# CMake's iOS platform accepts only sysroots named like Apple's (".../iPhoneOS...").
FOLDER = "iPhoneOS-open-source.sdk"

# Source name: (PadMint's environment variable, license of its files).
SOURCES = {
    "libc": ("PADMINT_APPLE_LIBC", "APSL-2.0"),
    "xnu": ("PADMINT_APPLE_XNU", "APSL-2.0"),
    "libpthread": ("PADMINT_APPLE_LIBPTHREAD", "APSL-2.0"),
    "libmalloc": ("PADMINT_APPLE_LIBMALLOC", "APSL-2.0"),
    "libplatform": ("PADMINT_APPLE_LIBPLATFORM", "APSL-2.0"),
    "availability": ("PADMINT_APPLE_AVAILABILITY", "APSL-2.0"),
    "libcxx": ("PADMINT_LIBCXX", "Apache-2.0 WITH LLVM-exception"),
}

# (source, folder there, folder under usr/include, file names or "*").
HEADERS = (
    ("libc", "include", "",
     "___wctype.h __wctype.h __xlocale.h _abort.h _bounds.h _ctermid.h _ctype.h _locale.h "
     "_locale_posix2008.h _mb_cur_max.h _printf.h _stdio.h _stdlib.h _string.h _strings.h _time.h "
     "_types.h _wchar.h _wctype.h _xlocale.h alloca.h ctype.h errno.h limits.h locale.h runetype.h "
     "stddef.h stdint.h stdio.h stdlib.h string.h time.h unistd.h wchar.h wctype.h xlocale.h"),
    ("libc", "include/_types", "_types", "*"),
    ("libc", "include/xlocale", "xlocale", "*"),
    ("libc", "include/FreeBSD", "", "nl_types.h"),
    ("xnu", "bsd/sys", "sys",
     "__endian.h _endian.h _types.h appleapiopts.h cdefs.h errno.h resource.h signal.h stdio.h "
     "syslimits.h types.h wait.h"),
    ("xnu", "bsd/sys/_types", "sys/_types", "*"),
    ("xnu", "bsd/arm", "arm", "_endian.h _limits.h _mcontext.h _types.h endian.h limits.h signal.h types.h"),
    ("xnu", "bsd/machine", "machine", "_endian.h _mcontext.h _types.h endian.h limits.h signal.h types.h"),
    ("xnu", "osfmk/mach/arm", "mach/arm", "_structs.h"),
    ("xnu", "osfmk/mach/machine", "mach/machine", "_structs.h"),
    ("xnu", "libkern/libkern", "libkern", "_OSByteOrder.h"),
    ("xnu", "libkern/libkern/arm", "libkern/arm", "_OSByteOrder.h"),
    ("libpthread", "include/pthread", "", "pthread.h sched.h"),
    ("libpthread", "include/pthread", "pthread", "pthread_impl.h qos.h sched.h"),
    ("libpthread", "include/sys/_pthread", "sys/_pthread", "*"),
    ("libpthread", "include/sys", "sys", "qos.h"),
    ("libmalloc", "include/malloc", "malloc", "_malloc.h _malloc_type.h _ptrcheck.h"),
    ("libplatform", "include", "", "setjmp.h"),
    ("libplatform", "include/libkern", "libkern", "OSCacheControl.h"),
)

# Names Apple's iPhone header install defines (xnu: makedefs/MakeInc.def,
# SINCFRAME_UNIFDEF with PLATFORM=iPhoneOS; Libc: xcodescripts/headers.sh with
# generate_features.pl for iphoneos). The names it leaves undefined are
# undefined when a pack compiles too, so only these are resolved.
INSTALL_DEFINES = {
    "xnu": ("XNU_PLATFORM_iPhoneOS", "_OPEN_SOURCE_", "__OPEN_SOURCE__", "MODULES_SUPPORTED"),
    "libc": ("UNIFDEF_BLOCKS", "UNIFDEF_MOVE_LOCALTIME", "UNIFDEF_TZDIR_SYMLINK"),
}
AVAILABILITY_HEADERS = ("Availability.h", "AvailabilityInternal.h", "AvailabilityInternalLegacy.h",
                        "AvailabilityMacros.h", "AvailabilityVersions.h")
# libc++ as LLVM configures it for Apple systems (libcxx/cmake/caches/Apple.cmake
# and libcxx/CMakeLists.txt defaults): ABI 1, vendor availability markup on,
# no hardening by default, libdispatch parallel algorithms.
LIBCXX_SITE = {
    "_LIBCPP_ABI_VERSION": "1", "_LIBCPP_ABI_NAMESPACE": "__1",
    "_LIBCPP_ABI_FORCE_ITANIUM": "0", "_LIBCPP_ABI_FORCE_MICROSOFT": "0",
    "_LIBCPP_HAS_THREADS": "1", "_LIBCPP_HAS_MONOTONIC_CLOCK": "1", "_LIBCPP_HAS_TERMINAL": "1",
    "_LIBCPP_HAS_MUSL_LIBC": "0", "_LIBCPP_HAS_THREAD_API_PTHREAD": "0",
    "_LIBCPP_HAS_THREAD_API_EXTERNAL": "0", "_LIBCPP_HAS_THREAD_API_WIN32": "0",
    "_LIBCPP_DISABLE_VISIBILITY_ANNOTATIONS": None, "_LIBCPP_HAS_VENDOR_AVAILABILITY_ANNOTATIONS": "1",
    "_LIBCPP_NO_VCRUNTIME": None, "_LIBCPP_TYPEINFO_COMPARISON_IMPLEMENTATION": None,
    "_LIBCPP_HAS_FILESYSTEM": "1", "_LIBCPP_HAS_RANDOM_DEVICE": "1", "_LIBCPP_HAS_LOCALIZATION": "1",
    "_LIBCPP_HAS_UNICODE": "1", "_LIBCPP_HAS_WIDE_CHARACTERS": "1", "_LIBCPP_HAS_NO_STD_MODULES": None,
    "_LIBCPP_HAS_TIME_ZONE_DATABASE": "0", "_LIBCPP_INSTRUMENTED_WITH_ASAN": "0",
    "_LIBCPP_PSTL_BACKEND_SERIAL": None, "_LIBCPP_PSTL_BACKEND_STD_THREAD": None,
    "_LIBCPP_PSTL_BACKEND_LIBDISPATCH": "", "_LIBCPP_HARDENING_MODE_DEFAULT": "2",
}
LIBSYSTEM = "/usr/lib/libSystem.B.dylib"
LIBCXX = "/usr/lib/libc++.1.dylib"


def source_roots(env=None) -> dict[str, Path]:
    """The folders PadMint installed (environment variables in SOURCES)."""
    env = os.environ if env is None else env
    roots, missing = {}, []
    for name, (variable, _) in SOURCES.items():
        value = env.get(variable)
        if value and Path(value).is_dir():
            roots[name] = Path(value)
        else:
            missing.append(variable)
    if missing:
        raise ModuleError("iPhone game modules need the open-source iOS headers PadMint installs "
                          f"({', '.join(missing)} not set); update PadMint and run it again")
    return roots


def _resolve_defines(text: str, names) -> str:
    """Apple's install-time unifdef for names it defines, applied to directives only."""
    pattern = "|".join(map(re.escape, names))
    lines = []
    for line in text.split("\n"):
        match = re.match(r"(\s*#\s*)(ifdef|ifndef|if|elif)\b(.*)$", line)
        if match:
            head, keyword, rest = match.groups()
            if keyword in ("ifdef", "ifndef"):
                word = re.match(r"\s*(\w+)(.*)$", rest)
                if word and re.fullmatch(pattern, word.group(1)):
                    line = f"{head}if {'1' if keyword == 'ifdef' else '0'}{word.group(2)}"
            else:
                rest = re.sub(rf"\bdefined\s*\(\s*({pattern})\s*\)|\bdefined\s+({pattern})\b", "1", rest)
                rest = re.sub(rf"\b({pattern})\b", "1", rest)
                line = f"{head}{keyword}{rest}"
        lines.append(line)
    return "\n".join(lines)


def _strip_libc_blocks(text: str) -> str:
    """Libc's install deletes //Begin-Libc ... //End-Libc (xcodescripts/strip-header.ed)."""
    return re.sub(r"(?ms)^//Begin-Libc\n.*?^//End-Libc\n", "", text)


# Apple's script copies a NamedTemporaryFile while it is still open, which
# Windows refuses; there the file is kept until the script's with-block ends.
_AVAILABILITY = ("import functools, runpy, sys, tempfile\n"
                 "if sys.platform == 'win32':\n"
                 "    keep = {'delete_on_close': False} if sys.version_info >= (3, 12) else {'delete': False}\n"
                 "    tempfile.NamedTemporaryFile = functools.partial(tempfile.NamedTemporaryFile, **keep)\n"
                 "sys.argv = sys.argv[1:]\n"
                 "runpy.run_path(sys.argv[0], run_name='__main__')\n")


def _run_availability(root: Path, *args: str) -> str:
    result = subprocess.run([sys.executable, "-c", _AVAILABILITY, str(root / "availability"), *args],
                            capture_output=True, text=True)
    if result.returncode != 0:
        raise ModuleError(f"Apple's availability script failed: {result.stderr.strip()}")
    return result.stdout


def _symbol_aliasing(availability: Path) -> str:
    """sys/_symbol_aliasing.h, as xnu's bsd/sys/make_symbol_aliasing.sh writes it."""
    out = ["/* Generated by PadMint from Apple's version list, as xnu's",
           " * bsd/sys/make_symbol_aliasing.sh does (APSL 2.0). */",
           "#ifndef _CDEFS_H_",
           '# error "Never use <sys/_symbol_aliasing.h> directly.  Use <sys/cdefs.h> instead."',
           "#endif", ""]
    for version in _run_availability(availability, "--ios").split():
        parts = version.split(".")
        if len(parts) != 2:
            continue  # no defines for releases with a third number
        value, name = f"{int(parts[0])}{int(parts[1]):02d}00", f"__IPHONE_{parts[0]}_{parts[1]}"
        out += [f"#if defined(__ENVIRONMENT_IPHONE_OS_VERSION_MIN_REQUIRED__) && "
                f"__ENVIRONMENT_IPHONE_OS_VERSION_MIN_REQUIRED__ >= {value}",
                f"#define __DARWIN_ALIAS_STARTING_IPHONE_{name}(x) x", "#else",
                f"#define __DARWIN_ALIAS_STARTING_IPHONE_{name}(x)", "#endif", ""]
    for version in _run_availability(availability, "--macosx").split():
        major, minor, patch = (version.split(".") + ["0", "0"])[:3]
        major, minor, patch = int(major), int(minor), int(patch)
        if major < 10 or (major == 10 and minor < 10):
            value, name = f"{major}{minor}0", f"__MAC_{major}_{minor}"
        else:
            value = f"{major}{minor:02d}{patch:02d}"
            name = f"__MAC_{major}_{minor}_{patch}" if patch else f"__MAC_{major}_{minor}"
        out += [f"#if defined(__ENVIRONMENT_MAC_OS_X_VERSION_MIN_REQUIRED__) && "
                f"__ENVIRONMENT_MAC_OS_X_VERSION_MIN_REQUIRED__ >= {value}",
                f"#define __DARWIN_ALIAS_STARTING_MAC_{name}(x) x", "#else",
                f"#define __DARWIN_ALIAS_STARTING_MAC_{name}(x)", "#endif", ""]
    return "\n".join(out) + "\n"


def _posix_availability() -> str:
    """sys/_posix_availability.h, as xnu's bsd/sys/make_posix_availability.sh writes it."""
    out = ["/* Generated by PadMint as xnu's bsd/sys/make_posix_availability.sh does (APSL 2.0). */",
           "#ifndef _CDEFS_H_",
           '# error "Never use <sys/_posix_availability.h> directly.  Use <sys/cdefs.h> instead."',
           "#endif", ""]
    for value in ("198808L", "199009L", "199209L", "199309L", "199506L", "200112L", "200809L"):
        out += [f"#if !defined(_DARWIN_C_SOURCE) && defined(_POSIX_C_SOURCE) && _POSIX_C_SOURCE >= {value}",
                f"#define ___POSIX_C_DEPRECATED_STARTING_{value} __deprecated", "#else",
                f"#define ___POSIX_C_DEPRECATED_STARTING_{value}", "#endif", ""]
    return "\n".join(out) + "\n"


def _config_site(template: str) -> str:
    """libc++'s __config_site from its CMake template with LIBCXX_SITE."""
    def replace(match):
        kind, name = match.group(1), match.group(2)
        value = LIBCXX_SITE[name]
        if kind == "cmakedefine01":
            return f"#define {name} {value}"
        return f"/* #undef {name} */" if value is None else f"#define {name} {value}".rstrip()
    text = re.sub(r"#(cmakedefine01|cmakedefine) (\w+)(?: @\w+@)?", replace, template)
    return text.replace("@_LIBCPP_ABI_DEFINES@", "").replace("@_LIBCPP_EXTRA_SITE_DEFINES@", "")


class _Writer:
    def __init__(self, sdk: Path):
        self.sdk, self.records = sdk, []

    def write(self, relative: str, data: bytes, origin: str, license_id: str) -> None:
        path = self.sdk / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        self.records.append({"file": relative, "sha256": hashlib.sha256(data).hexdigest(),
                             "from": origin, "license": license_id})


def _file_license(data: bytes, default: str) -> str:
    head = data[:4096].decode("latin-1")
    if "Apple Public Source License" in head:
        return "APSL-2.0" if "Version 2.0" in head else "APSL-1.1"
    if "Redistribution and use in source and binary forms" in head:
        if "advertising materials" in head:
            return "BSD-4-Clause-UC"  # UC Berkeley rescinded the advertising clause in 1999
        if "Neither the name" in head or "may be used to endorse" in head:
            return "BSD-3-Clause"
        return "BSD-2-Clause"
    return default


def assemble(sdk: Path, roots: dict[str, Path]) -> Path:
    """Write the SDK to sdk (replaced if present); returns sdk."""
    if sdk.exists():
        shutil.rmtree(sdk)
    include = "usr/include"
    out = _Writer(sdk)
    for source, folder, target, names in HEADERS:
        base = roots[source] / folder
        files = sorted(p.name for p in base.glob("*.h")) if names == "*" else names.split()
        for name in files:
            original = base / name
            if not original.is_file():
                raise ModuleError(f"missing {folder}/{name} in {roots[source]}; run PadMint again")
            data = original.read_bytes()
            if source == "libc":
                data = _strip_libc_blocks(data.decode("latin-1")).encode("latin-1")
            if source in INSTALL_DEFINES:
                data = _resolve_defines(data.decode("latin-1"), INSTALL_DEFINES[source]).encode("latin-1")
            relative = f"{include}/{target}/{name}".replace("//", "/")
            out.write(relative, data, f"{source}:{folder}/{name}", _file_license(data, SOURCES[source][1]))
    availability = roots["availability"]
    generated = sdk / "_availability"
    generated.mkdir(parents=True)
    for name in AVAILABILITY_HEADERS:
        _run_availability(availability, "--preprocess", str(availability / "templates" / name),
                          str(generated / name))
        # Line endings as on every other host (the script writes text mode).
        out.write(f"{include}/{name}", (generated / name).read_bytes().replace(b"\r\n", b"\n"),
                  f"availability:templates/{name} (preprocessed by Apple's availability script)", "APSL-2.0")
    shutil.rmtree(generated)
    out.write(f"{include}/sys/_symbol_aliasing.h", _symbol_aliasing(availability).encode(),
              "generated (xnu bsd/sys/make_symbol_aliasing.sh)", "APSL-2.0")
    out.write(f"{include}/sys/_posix_availability.h", _posix_availability().encode(),
              "generated (xnu bsd/sys/make_posix_availability.sh)", "APSL-2.0")
    for path in sorted(HEADERS_DIR.rglob("*.h")):
        relative = path.relative_to(HEADERS_DIR).as_posix()
        out.write(f"{include}/{relative}", path.read_bytes(), f"padmint:ios-sdk/include/{relative}",
                  "GPL-3.0-or-later")
    libcxx = roots["libcxx"]
    for path in sorted((libcxx / "include").rglob("*")):
        relative = path.relative_to(libcxx / "include").as_posix()
        if not path.is_file() or relative == "CMakeLists.txt" or relative.endswith(".in"):
            continue
        out.write(f"{include}/c++/v1/{relative}", path.read_bytes(), f"libcxx:include/{relative}",
                  SOURCES["libcxx"][1])
    out.write(f"{include}/c++/v1/__config_site",
              _config_site((libcxx / "include/__config_site.in").read_text()).encode(),
              "libcxx:include/__config_site.in (Apple configuration)", SOURCES["libcxx"][1])
    out.write(f"{include}/c++/v1/__assertion_handler",
              (libcxx / "vendor/llvm/default_assertion_handler.in").read_bytes(),
              "libcxx:vendor/llvm/default_assertion_handler.in", SOURCES["libcxx"][1])
    settings = {"CanonicalName": f"iphoneos{DEPLOYMENT_TARGET}", "DisplayName": "iOS (open-source headers)",
                "Version": DEPLOYMENT_TARGET, "MaximumDeploymentTarget": DEPLOYMENT_TARGET,
                "DefaultDeploymentTarget": DEPLOYMENT_TARGET, "IsBaseSDK": "YES"}
    (sdk / "SDKSettings.json").write_text(json.dumps(settings, indent=1) + "\n")
    write_stubs(sdk)
    (sdk / "SOURCES.json").write_text(json.dumps(
        {"schema": SCHEMA, "note": "Every file in this SDK, where it came from and its license. "
         "Personal use only: it builds your own game pack.", "files": out.records}, indent=1) + "\n")
    return sdk


def _tbd(install_name: str, symbols=(), thread_locals=(), note="") -> str:
    def names(items):
        return ", ".join(f"'{name}'" for name in sorted(set(items)))
    exports = f"    symbols:         [ {names(symbols)} ]\n" if symbols else ""
    if thread_locals:
        exports += f"    thread-local-symbols: [ {names(thread_locals)} ]\n"
    body = f"exports:\n  - targets:         [ arm64-ios ]\n{exports}" if exports else ""
    return (f"--- !tapi-tbd\n{note}tbd-version:     4\ntargets:         [ arm64-ios ]\n"
            f"install-name:    '{install_name}'\n{body}...\n")


def write_stubs(sdk: Path, app_thread_locals=()) -> None:
    """Text stubs for -lSystem and -lc++. Linked in a flat namespace, their only
    job is to tell the linker what it cannot infer: lazy binding's
    dyld_stub_binder, and which of the app's exports are thread-local."""
    lib = sdk / "usr/lib"
    lib.mkdir(parents=True, exist_ok=True)
    note = ("# Generated by PadMint (padmint.ios_module). The thread-local names are the\n"
            "# app's exports, found by name at load time (flat namespace).\n") if app_thread_locals else ""
    (lib / "libSystem.tbd").write_text(_tbd(LIBSYSTEM, ["dyld_stub_binder"], app_thread_locals, note))
    (lib / "libc++.tbd").write_text(_tbd(LIBCXX))


def llvm_tool(llvm: Path, name: str) -> Path:
    tool = llvm / "bin" / (name + (".exe" if os.name == "nt" else ""))
    if not tool.is_file():
        raise ModuleError(f"missing LLVM tool {tool}; run PadMint again")
    return tool


def toolchain(sdk: Path, llvm: Path) -> Path:
    """A CMake toolchain file: LLVM's clang and ld64.lld with this SDK."""
    def cm(path: Path) -> str:
        return path.as_posix()
    clang, clangxx = llvm_tool(llvm, "clang"), llvm_tool(llvm, "clang++")
    llvm_tool(llvm, "ld64.lld")
    text = f"""# iPhone game modules without Apple's SDK (padmint.ios_module).
set(CMAKE_SYSTEM_NAME iOS)
set(CMAKE_SYSTEM_PROCESSOR arm64)
set(CMAKE_OSX_SYSROOT "{cm(sdk)}" CACHE PATH "")
set(CMAKE_OSX_ARCHITECTURES arm64 CACHE STRING "")
set(CMAKE_OSX_DEPLOYMENT_TARGET {DEPLOYMENT_TARGET} CACHE STRING "")
set(CMAKE_C_COMPILER "{cm(clang)}")
set(CMAKE_CXX_COMPILER "{cm(clangxx)}")
set(CMAKE_ASM_COMPILER "{cm(clang)}")
set(CMAKE_C_COMPILER_TARGET {TRIPLE})
set(CMAKE_CXX_COMPILER_TARGET {TRIPLE})
set(CMAKE_ASM_COMPILER_TARGET {TRIPLE})
set(CMAKE_AR "{cm(llvm_tool(llvm, 'llvm-ar'))}" CACHE FILEPATH "")
set(CMAKE_RANLIB "{cm(llvm_tool(llvm, 'llvm-ranlib'))}" CACHE FILEPATH "")
set(CMAKE_INSTALL_NAME_TOOL "{cm(llvm_tool(llvm, 'llvm-install-name-tool'))}" CACHE FILEPATH "")
# ld64.lld (a linker version recent enough for -platform_version), flat namespace.
set(CMAKE_SHARED_LINKER_FLAGS_INIT "-fuse-ld=lld -mlinker-version=955 -Wl,-flat_namespace")
set(CMAKE_MODULE_LINKER_FLAGS_INIT "-fuse-ld=lld -mlinker-version=955 -Wl,-flat_namespace")
set(CMAKE_EXE_LINKER_FLAGS_INIT "-fuse-ld=lld -mlinker-version=955")
# Hundreds of objects with long paths exceed Windows' command-line limit.
set(CMAKE_C_USE_RESPONSE_FILE_FOR_OBJECTS 1)
set(CMAKE_CXX_USE_RESPONSE_FILE_FOR_OBJECTS 1)
set(CMAKE_FIND_ROOT_PATH "{cm(sdk)}")
set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)
set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE ONLY)
set(CMAKE_TRY_COMPILE_TARGET_TYPE STATIC_LIBRARY)
"""
    path = sdk / "toolchain.cmake"
    path.write_text(text)
    return path


# --- One pipeline for every game: prepare, check and insert ---------------------------------


def published_executable(app_ipa: Path, destination: Path) -> tuple[str, Path]:
    """Write the published app's main executable to destination; returns (app folder, path)."""
    import plistlib
    with zipfile.ZipFile(app_ipa) as archive:
        plists = [name for name in archive.namelist() if name.startswith("Payload/")
                  and name.count("/") == 2 and name.endswith(".app/Info.plist")]
        if len(plists) != 1:
            raise ModuleError(f"{app_ipa.name} is not an iPhone app with one Payload/*.app")
        app = plists[0].rsplit("/", 1)[0]
        executable = plistlib.loads(archive.read(plists[0])).get("CFBundleExecutable")
        if not isinstance(executable, str) or not executable or "/" in executable:
            raise ModuleError(f"{app_ipa.name} names no valid main executable")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(archive.read(f"{app}/{executable}"))
    return app, destination


def app_thread_locals(llvm: Path, executable: Path) -> list[str]:
    """The published app's thread-local exports (its __thread_vars section)."""
    listing = subprocess.run([str(llvm_tool(llvm, "llvm-nm")), "-m", "-g", "--defined-only", str(executable)],
                             check=True, capture_output=True, text=True).stdout
    return sorted(line.split()[-1] for line in listing.splitlines() if "(__DATA,__thread_vars)" in line)


def llvm_root(env=None) -> Path:
    env = os.environ if env is None else env
    value = env.get("PADMINT_LLVM_ROOT")
    if not value or not Path(value).is_dir():
        raise ModuleError("iPhone game modules need the LLVM PadMint installs (PADMINT_LLVM_ROOT); "
                          "update PadMint and run it again")
    return Path(value)


def prepare(folder: Path, app_ipa: Path, env=None) -> dict:
    """Assemble the SDK in folder for the published app: {"sdk", "toolchain", "executable"}."""
    roots, llvm = source_roots(env), llvm_root(env)
    _app, executable = published_executable(app_ipa, folder / "app-executable")
    sdk = assemble(folder / FOLDER, roots)
    write_stubs(sdk, app_thread_locals(llvm, executable))
    return {"sdk": sdk, "toolchain": toolchain(sdk, llvm), "executable": executable}


def _names(command: list) -> set:
    return set(subprocess.run(command, check=True, capture_output=True, text=True).stdout.split())


_STANDARD = re.compile(r"((typeinfo name|typeinfo|construction vtable|vtable|VTT|guard variable) for "
                       r"|(non-)?virtual thunk to )?(std::|__cxxabiv1::|operator (new|delete))")


def check_imports(llvm: Path, module: Path, executable: Path, stream=None) -> None:
    """Every name a module imports is looked up by name when it loads. Names the app does
    not export must be the C library's (libSystem) or the C++ standard library's: a missing
    app name would otherwise only show on the device."""
    nm = str(llvm_tool(llvm, "llvm-nm"))
    imports = _names([nm, "-u", "-j", str(module)])
    system = sorted(imports - _names([nm, "-g", "--defined-only", "-j", str(executable)]))
    cxx = [name for name in system if name.startswith("__Z")]
    readable = subprocess.run([str(llvm_tool(llvm, "llvm-cxxfilt"))], input="".join(name + "\n" for name in cxx),
                              capture_output=True, text=True, check=True).stdout.splitlines()
    unknown = [text for text in readable if not _STANDARD.match(text)]
    if unknown:
        raise ModuleError("the game module needs names the published app does not export: "
                          + ", ".join(unknown[:10]))
    print(f"Game module imports: {len(imports) - len(system)} from the app, {len(system)} from the "
          "device's C and C++ libraries.", file=stream or sys.stdout, flush=True)


def _member(into: str) -> str:
    parts = into.split("/")
    if (not into or into.startswith("/") or "\\" in into or any(part in ("", ".", "..") for part in parts)
            or not into.endswith(".dylib")):
        raise ModuleError(f"ios_module.into must be a relative .dylib path inside the app, not {into!r}")
    return into


def insert(app_ipa: Path, module: Path, into: str, output: Path, llvm: Path, work: Path) -> Path:
    """A copy of the published app with the module at <app>/<into>, stripped of local
    symbols and named @rpath/<file> (unsigned: the player's sideloading tool signs it)."""
    into = _member(into)
    if not module.is_file() or module.stat().st_size == 0:
        raise ModuleError(f"the build made no game module at {module}")
    with module.open("rb") as stream:
        if stream.read(4) not in (b"\xcf\xfa\xed\xfe", b"\xfe\xed\xfa\xcf"):
            raise ModuleError(f"{module.name} is not a 64-bit Mach-O library")
    work.mkdir(parents=True, exist_ok=True)
    ready = work / Path(into).name
    shutil.copyfile(module, ready)
    subprocess.run([str(llvm_tool(llvm, "llvm-strip")), "-x", str(ready)], check=True)
    subprocess.run([str(llvm_tool(llvm, "llvm-install-name-tool")), "-id", f"@rpath/{ready.name}", str(ready)],
                   check=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    partial = output.with_name(output.name + ".partial")
    with zipfile.ZipFile(app_ipa) as source:
        plists = [n for n in source.namelist() if n.startswith("Payload/") and n.count("/") == 2
                  and n.endswith(".app/Info.plist")]
        if len(plists) != 1:
            raise ModuleError(f"{app_ipa.name} is not an iPhone app with one Payload/*.app")
        member = f"{plists[0].rsplit('/', 1)[0]}/{into}"
        if member in source.namelist():
            raise ModuleError(f"the published app already contains {into}; use the app without game code")
        with zipfile.ZipFile(partial, "w", compression=zipfile.ZIP_DEFLATED) as target:
            for item in source.infolist():
                target.writestr(item, source.read(item))
            info = zipfile.ZipInfo(member, (1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o755) << 16
            target.writestr(info, ready.read_bytes(), compress_type=zipfile.ZIP_DEFLATED)
    partial.replace(output)
    return output


def linked(module: Path) -> dict:
    """A module's platform and minimum OS from its LC_BUILD_VERSION (64-bit arm64 dylib)."""
    import struct
    from .apple import PLATFORMS, version
    data = module.read_bytes()
    if len(data) < 32 or data[:4] != b"\xcf\xfa\xed\xfe":
        raise ModuleError(f"{module.name} is not a 64-bit little-endian Mach-O file")
    cputype, _sub, filetype, count, size = struct.unpack_from("<5I", data, 4)
    if cputype != 0x100000C or filetype != 6:
        raise ModuleError(f"{module.name} is not an arm64 dynamic library")
    offset, end = 32, 32 + size
    for _ in range(count):
        command, length = struct.unpack_from("<2I", data, offset)
        if length < 8 or offset + length > end:
            break
        if command == 0x32:
            platform, minimum, sdk = struct.unpack_from("<3I", data, offset + 8)
            return {"platform": PLATFORMS.get(platform, str(platform)), "minimum_os": version(minimum),
                    "sdk": version(sdk)}
        offset += length
    raise ModuleError(f"{module.name} declares no platform")
