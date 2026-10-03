"""The universal iPhone module pipeline (padmint/ios_module.py). Synthetic trees and
stand-in LLVM tools only; the real ones come from PadMint's pinned downloads."""
import argparse
import copy
import io
import json
import os
from contextlib import redirect_stdout
from pathlib import Path
import shlex
import stat
import subprocess
import tempfile
import unittest
from unittest import mock
import zipfile

from padmint import ios_module, tools
from padmint.cli import execute, validate
from padmint.manifest import validate_manifest
from fixtures import entries, macho, write_ipa

# Stands in for Apple's AvailabilityVersions script: version lists and --preprocess.
AVAILABILITY = """import sys
if sys.argv[1] == "--ios": print("15.0 16.0 16.0.1 17.3")
elif sys.argv[1] == "--macosx": print("10.9 10.15 14.3")
else: open(sys.argv[3], "w").write("/* " + sys.argv[2].replace(chr(92), "/").rsplit("/", 1)[-1] + " */\\n")
"""

MODULE_TARGET = {
    "schema_version": 1, "id": "kartpad", "name": "Synthetic", "game": "Synthetic",
    "kind": "disc-translation", "status": "draft-untested",
    "inputs": [{"type": "disc", "when": "in-app"}],
    "targets": {"ios": {
        "hosts": {"macos-arm64": "experimental", "linux-x86_64": "experimental"},
        "output": "ipa", "check": "ipa", "tools": ["libcxx"],
        "published_app": "Synthetic-v{version}-ios-unsigned.ipa",
        "ios_module": {"file": "{work}/module/libgame.dylib", "into": "Frameworks/libgame.dylib"},
        "steps": [{"stage": "compile", "command": ["/bin/sh", "{repo}/scripts/compile.sh", "{ios_toolchain}",
                                                   "{work}/module/libgame.dylib"]}]}},
    "publication": {"public_binaries": False},
}


def fake_llvm(root, imports=(), app_exports=()):
    """bin/ tools that behave enough like LLVM's for the checks: nm lists names, the rest no-op."""
    bin_dir = root / "bin"
    bin_dir.mkdir(parents=True)
    def tool(name, body):
        path = bin_dir / name
        path.write_text("#!/bin/sh\n" + body)
        path.chmod(path.stat().st_mode | stat.S_IXUSR)
    listing = {"-u": "\n".join(imports), "-g": "\n".join(app_exports)}
    tool("llvm-nm", 'case "$1" in -u) printf "%s\\n" ' + shlex.quote(listing["-u"])
         + ' ;; -m) ;; *) printf "%s\\n" ' + shlex.quote(listing["-g"]) + " ;; esac\n")
    tool("llvm-cxxfilt", "while read -r line; do case \"$line\" in __ZNSt*) echo \"std::x\";; "
                         "*) echo \"KartPad::missing()\";; esac; done\n")
    for name in ("llvm-strip", "llvm-install-name-tool", "clang", "clang++", "ld64.lld", "llvm-ar", "llvm-ranlib"):
        tool(name, "exit 0\n")
    return root


class SdkAssemblyTests(unittest.TestCase):
    def test_install_defines_resolve_only_named_directives(self):
        text = ("#ifdef XNU_PLATFORM_iPhoneOS\n#ifndef __OPEN_SOURCE__ /* x */\n"
                "#if defined(MODULES_SUPPORTED) && defined(__arm64__)\n#elif XNU_PLATFORM_iPhoneOS || KERNEL\n"
                "#if XNU_PLATFORM_MacOSX\nint XNU_PLATFORM_iPhoneOS;\n")
        self.assertEqual(ios_module._resolve_defines(text, ios_module.INSTALL_DEFINES["xnu"]).split("\n"), [
            "#if 1", "#if 0 /* x */", "#if 1 && defined(__arm64__)", "#elif 1 || KERNEL",
            "#if XNU_PLATFORM_MacOSX", "int XNU_PLATFORM_iPhoneOS;", ""])

    def test_libc_install_blocks_are_removed(self):
        text = "a\n//Begin-Libc\n#ifndef LIBC_ALIAS_X\n//End-Libc\nint x;\n//Begin-Libc\n#else\n#endif\n//End-Libc\nb\n"
        self.assertEqual(ios_module._strip_libc_blocks(text), "a\nint x;\nb\n")

    def test_stubs_name_the_apps_thread_locals(self):
        with tempfile.TemporaryDirectory() as temporary:
            sdk = Path(temporary)
            ios_module.write_stubs(sdk, ["_g_b", "_g_a"])
            system = (sdk / "usr/lib/libSystem.tbd").read_text()
            self.assertIn("install-name:    '/usr/lib/libSystem.B.dylib'", system)
            self.assertIn("thread-local-symbols: [ '_g_a', '_g_b' ]", system)

    def test_missing_sources_name_what_padmint_installs(self):
        with self.assertRaisesRegex(ios_module.ModuleError, "PADMINT_APPLE_XNU"):
            ios_module.source_roots({})

    def test_assembles_every_header_with_its_origin_and_license(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            roots = {name: root / name for name in ios_module.SOURCES}
            for source, folder, _target, names in ios_module.HEADERS:
                for name in (["_a.h"] if names == "*" else names.split()):
                    path = roots[source] / folder / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    notice = "Apple Public Source License Version 2.0" if source != "libc" else "plain"
                    path.write_text(f"/* {notice} */\n#ifdef XNU_PLATFORM_iPhoneOS\nint {name[:-2]};\n#endif\n")
            (roots["availability"] / "templates").mkdir(parents=True)
            (roots["availability"] / "availability").write_text(AVAILABILITY)
            (roots["libcxx"] / "include").mkdir(parents=True)
            (roots["libcxx"] / "include/vector").write_text("// vector\n")
            (roots["libcxx"] / "include/__config_site.in").write_text("#cmakedefine01 _LIBCPP_HAS_THREADS\n")
            (roots["libcxx"] / "vendor/llvm").mkdir(parents=True)
            (roots["libcxx"] / "vendor/llvm/default_assertion_handler.in").write_text("// handler\n")
            sdk = ios_module.assemble(root / "sdk", roots)
            include = sdk / "usr/include"
            self.assertIn("#if 1", (include / "sys/cdefs.h").read_text())
            self.assertTrue((include / "math.h").is_file() and (include / "TargetConditionals.h").is_file())
            files = {item["file"]: item for item in json.loads((sdk / "SOURCES.json").read_text())["files"]}
            self.assertEqual(files["usr/include/math.h"]["from"], "padmint:ios-sdk/include/math.h")
            self.assertEqual(files["usr/include/math.h"]["license"], "GPL-3.0-or-later")
            self.assertEqual(files["usr/include/sys/cdefs.h"]["license"], "APSL-2.0")


class RecipeAndToolTests(unittest.TestCase):
    def test_ios_module_recipe_rules(self):
        validate_manifest(copy.deepcopy(MODULE_TARGET))
        for change, message in (
                (lambda t: t.pop("published_app"), "needs published_app"),
                (lambda t: t.update(tools=[]), "needs the libcxx tool"),
                (lambda t: t["ios_module"].update(into="../escape.dylib"), "relative .dylib path"),
                (lambda t: t["ios_module"].update(into="Frameworks/game.so"), "relative .dylib path")):
            manifest = copy.deepcopy(MODULE_TARGET)
            change(manifest["targets"]["ios"])
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                validate_manifest(manifest)

    def test_mac_gets_source_archives_only_when_a_module_recipe_asks(self):
        table = tools.lock()
        self.assertIsNone(tools.host_entry(table["libcxx"], "macos-arm64"))
        entry = tools.host_entry(table["libcxx"], "macos-arm64", any_host=True)
        self.assertEqual(entry, table["libcxx"]["hosts"]["linux-arm64"])
        # Companions come along (LLVM's Apple Silicon build carries ld64.lld for the module).
        names = tools._with_companions(["libcxx"], "macos-arm64", table, any_host=True)
        self.assertIn("llvm", names)
        self.assertIn("apple-xnu", names)
        members = table["llvm"]["hosts"]["macos-arm64"]["members"]
        self.assertIn("LLVM-22.1.8-macOS-ARM64/bin/ld64.lld", members)
        # Existing recipes (KartPad lists libcxx for Windows/Linux) download nothing new on a Mac.
        self.assertEqual(tools._with_companions(["libcxx"], "macos-arm64", table), ["libcxx"])


class InsertAndCheckTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        members = entries()
        members.pop("KartPadBuilderProvenance.json")
        self.app = self.root / "app.ipa"
        write_ipa(self.app, members)
        self.module = self.root / "libgame.dylib"
        self.module.write_bytes(macho())

    def test_module_goes_into_a_copy_of_the_app_as_an_executable_file(self):
        llvm = fake_llvm(self.root / "llvm")
        output = ios_module.insert(self.app, self.module, "Frameworks/libgame.dylib", self.root / "out.ipa",
                                   llvm, self.root / "work")
        with zipfile.ZipFile(output) as archive:
            info = archive.getinfo("Payload/Synthetic.app/Frameworks/libgame.dylib")
            self.assertEqual(stat.S_IMODE(info.external_attr >> 16), 0o755)
            self.assertEqual(archive.read(info), macho())
            self.assertIn("Payload/Synthetic.app/Synthetic", archive.namelist())
        with zipfile.ZipFile(self.app) as original:
            self.assertNotIn("Payload/Synthetic.app/Frameworks/libgame.dylib", original.namelist())

    def test_refuses_an_app_that_already_has_game_code_and_non_mach_o_files(self):
        llvm = fake_llvm(self.root / "llvm")
        once = ios_module.insert(self.app, self.module, "Frameworks/libgame.dylib", self.root / "once.ipa",
                                 llvm, self.root / "w1")
        with self.assertRaisesRegex(ios_module.ModuleError, "already contains"):
            ios_module.insert(once, self.module, "Frameworks/libgame.dylib", self.root / "twice.ipa", llvm,
                              self.root / "w2")
        self.module.write_bytes(b"not a library")
        with self.assertRaisesRegex(ios_module.ModuleError, "not a 64-bit Mach-O"):
            ios_module.insert(self.app, self.module, "Frameworks/libgame.dylib", self.root / "bad.ipa", llvm,
                              self.root / "w3")
        self.assertFalse((self.root / "bad.ipa").exists())

    def test_imports_must_come_from_the_app_or_the_system_libraries(self):
        executable = self.root / "app-executable"
        executable.write_bytes(macho())
        good = fake_llvm(self.root / "good", imports=["_app_function", "_memcpy", "__ZNSt3__14coutE"],
                         app_exports=["_app_function"])
        output = io.StringIO()
        ios_module.check_imports(good, self.module, executable, output)
        self.assertIn("1 from the app, 2 from the device's C and C++ libraries", output.getvalue())
        bad = fake_llvm(self.root / "bad", imports=["__ZN7KartPad7missingEv"], app_exports=[])
        with self.assertRaisesRegex(ios_module.ModuleError, "does not export: KartPad::missing"):
            ios_module.check_imports(bad, self.module, executable)


class BuildFlowTests(unittest.TestCase):
    """padmint build with an ios_module: the game's step compiles, PadMint adds the module."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="padmint module ")
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name).resolve()
        self.root = root
        self.repo = root / "backend"
        (self.repo / "scripts").mkdir(parents=True)
        members = entries()
        members.pop("KartPadBuilderProvenance.json")
        self.app = root / "Synthetic-v1.0.0-ios-unsigned.ipa"
        write_ipa(self.app, members)
        self.seen = root / "toolchain-seen"
        library = root / "built.dylib"
        library.write_bytes(macho())
        (self.repo / ".gitignore").write_text("build/\n")
        (self.repo / "scripts/compile.sh").write_text(
            'echo "$1" > %s\nmkdir -p "$(dirname "$2")"\ncp %s "$2"\n'
            % (shlex.quote(str(self.seen)), shlex.quote(str(library))))
        (self.repo / "padmint.json").write_text(json.dumps(MODULE_TARGET))
        for command in (["init", "-q"], ["config", "user.email", "t@example.invalid"], ["config", "user.name", "T"],
                        ["add", "."], ["commit", "-qm", "synthetic"]):
            subprocess.run(["git", "-C", str(self.repo), *command], check=True)
        revision = subprocess.check_output(["git", "-C", str(self.repo), "rev-parse", "HEAD"], text=True).strip()
        self.args = argparse.Namespace(game="kartpad", repo=self.repo, disc=None, revision=revision,
                                       source_only=False, no_mods=False, jobs=2, app=self.app)

    def test_step_gets_the_toolchain_and_the_output_is_the_app_with_the_module(self):
        toolchain = self.root / "sdk/toolchain.cmake"
        executable = self.root / "sdk/app-executable"
        executable.parent.mkdir(parents=True)
        executable.write_bytes(macho())
        llvm = fake_llvm(self.root / "llvm", imports=["_memcpy"])
        prepared = {"sdk": self.root / "sdk", "toolchain": toolchain, "executable": executable}
        repo, disc = validate(self.args)
        with mock.patch.object(ios_module, "prepare", return_value=prepared) as prepare, \
                mock.patch.object(ios_module, "llvm_root", return_value=llvm), \
                mock.patch("padmint.cli.host_id", return_value="macos-arm64"), \
                redirect_stdout(io.StringIO()) as shown:
            self.assertEqual(execute(self.args, repo, disc), 0)
        prepare.assert_called_once()
        self.assertEqual(self.seen.read_text().strip(), str(toolchain))
        self.assertIn("Added your game module to the app: Frameworks/libgame.dylib", shown.getvalue())
        record_path = next((self.repo / "build/padmint").glob("*/runs/*/record.json"))
        record = json.loads(record_path.read_text())
        self.assertEqual(record["status"], "completed")
        with zipfile.ZipFile(record_path.parent / "personal.ipa") as archive:
            self.assertIn("Payload/Synthetic.app/Frameworks/libgame.dylib", archive.namelist())

    def test_a_module_the_app_cannot_load_stops_the_build(self):
        executable = self.root / "app-executable"
        executable.write_bytes(macho())
        llvm = fake_llvm(self.root / "llvm", imports=["__ZN7KartPad7missingEv"])
        prepared = {"sdk": self.root, "toolchain": self.root / "toolchain.cmake", "executable": executable}
        repo, disc = validate(self.args)
        with mock.patch.object(ios_module, "prepare", return_value=prepared), \
                mock.patch.object(ios_module, "llvm_root", return_value=llvm), \
                mock.patch("padmint.cli.host_id", return_value="macos-arm64"), \
                redirect_stdout(io.StringIO()):
            self.assertEqual(execute(self.args, repo, disc), 1)
        record = json.loads(next((self.repo / "build/padmint").glob("*/runs/*/record.json")).read_text())
        self.assertEqual(record["status"], "failed")
        self.assertIn("does not export", record["failure_message"])


if __name__ == "__main__":
    unittest.main()
