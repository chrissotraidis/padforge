import hashlib
from pathlib import Path
import tempfile
import unittest
import plistlib
import struct

from fixtures import entries, legacy_macho, macho, write_ipa
from padmint.apple import SCENE_CALLBACK
from padmint.cli import check_output
from padmint.package import validate_ipa


class PackageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "synthetic.ipa"
        self.disc_hash = hashlib.sha256(b"synthetic input, not game data").hexdigest()

    def check(self, game="kartpad"):
        return validate_ipa(self.path, game, "a" * 40, self.disc_hash)

    def test_minimal_structure_for_both_backends(self):
        for game in ("kartpad", "bluewake"):
            write_ipa(self.path, entries(game))
            self.assertEqual(self.check(game)["check"], "minimal-ipa-structure-and-provenance")

    def test_required_members(self):
        for game in ("kartpad", "bluewake"):
            members = entries(game)
            for missing in members:
                with self.subTest(game=game, missing=missing):
                    write_ipa(self.path, {k: v for k, v in members.items() if k != missing})
                    with self.assertRaises(ValueError):
                        self.check(game)

    def test_wrong_disc_provenance(self):
        write_ipa(self.path, entries(disc=b"different input"))
        with self.assertRaisesRegex(ValueError, "disc/profile"):
            self.check()

    def test_wrong_bluewake_revision(self):
        write_ipa(self.path, entries("bluewake", revision="b" * 40))
        with self.assertRaisesRegex(ValueError, "requested build"):
            self.check("bluewake")

    def test_wrong_bluewake_module_hash(self):
        members = entries("bluewake")
        members["Payload/Synthetic.app/Frameworks/gGZLE01_recomp.dylib"] += b"changed"
        write_ipa(self.path, members)
        with self.assertRaisesRegex(ValueError, "module hash"):
            self.check("bluewake")

    def test_bad_plist_and_provenance(self):
        for name in ("Payload/Synthetic.app/Info.plist", "KartPadBuilderProvenance.json"):
            members = entries()
            members[name] = b"invalid"
            write_ipa(self.path, members)
            with self.assertRaises(ValueError):
                self.check()

    def test_non_executable_payload(self):
        members = entries()
        members["Payload/Synthetic.app/Synthetic"] = b"plain text executable"
        write_ipa(self.path, members)
        with self.assertRaisesRegex(ValueError, "Mach-O"):
            self.check()

    def test_truncated_xml_plist_is_rejected(self):
        members = entries()
        members["Payload/Synthetic.app/Info.plist"] = b'<?xml version="1.0"?><plist><dict>'
        write_ipa(self.path, members)
        with self.assertRaises(ValueError):
            self.check()

    def test_linked_sdk_is_recorded(self):
        write_ipa(self.path, entries())
        apple = self.check()["apple_compatibility"]
        self.assertEqual({key: apple["linked_slices"][0][key] for key in ("platform", "minimum_os", "sdk")},
                         {"platform": "ios", "minimum_os": "15.0.0", "sdk": "26.0.0"})
        self.assertEqual(apple["runtime_launch"], "not-tested")

    def test_sdk27_launch_method_alone_is_unverified_for_all_ipa_checks(self):
        members = entries()
        members["Payload/Synthetic.app/Synthetic"] = legacy_macho()
        # A stale plist SDK cannot disguise what the executable was linked against.
        info = plistlib.loads(members["Payload/Synthetic.app/Info.plist"])
        info["DTSDKName"] = "iphoneos26.0"
        members["Payload/Synthetic.app/Info.plist"] = plistlib.dumps(info)
        write_ipa(self.path, members)
        for check in ("ipa", "kartpad-ipa", "none"):
            with self.subTest(check=check):
                result = check_output(check, self.path, "a" * 40, self.disc_hash)["apple_compatibility"]
                self.assertEqual(result["scene_startup"], "unverified")
                self.assertEqual(result["linked_slices"][0]["sdk"], "27.0.0")

    def test_sdk27_declared_scene_or_dynamic_callback(self):
        for callback in (False, True):
            members = entries()
            symbols = ((b"-[TestDelegate " + SCENE_CALLBACK + b"]", 0x0E, 1),) if callback else ()
            members["Payload/Synthetic.app/Synthetic"] = macho(27, symbols=symbols)
            info = plistlib.loads(members["Payload/Synthetic.app/Info.plist"])
            if not callback:
                info["UIApplicationSceneManifest"] = {"UISceneConfigurations": {
                    "UIWindowSceneSessionRoleApplication": [{"UISceneDelegateClassName": "TestSceneDelegate"}]}}
            members["Payload/Synthetic.app/Info.plist"] = plistlib.dumps(info)
            write_ipa(self.path, members)
            result = self.check(None)["apple_compatibility"]
            self.assertEqual(result["runtime_launch"], "not-tested")
            self.assertEqual(result["scene_startup"], "defined-configuration-callback" if callback else "declared")

    def test_callback_metadata_is_not_an_implemented_method(self):
        for manifest in (None, {}):
            members = entries()
            members["Payload/Synthetic.app/Synthetic"] = legacy_macho() + SCENE_CALLBACK
            info = plistlib.loads(members["Payload/Synthetic.app/Info.plist"])
            if manifest is not None:
                info["UIApplicationSceneManifest"] = manifest
            members["Payload/Synthetic.app/Info.plist"] = plistlib.dumps(info)
            write_ipa(self.path, members)
            with self.subTest(manifest=manifest):
                self.assertEqual(self.check(None)["apple_compatibility"]["scene_startup"], "unverified")

    def test_imported_debug_and_class_symbols_are_not_scene_methods(self):
        launch = (b"-[TestDelegate application:didFinishLaunchingWithOptions:]", 0x0E, 1)
        for name, kind, section in ((b"-[TestDelegate " + SCENE_CALLBACK + b"]", 1, 0),
                                    (b"-[TestDelegate " + SCENE_CALLBACK + b"]", 0xEE, 1),
                                    (b"+[TestDelegate " + SCENE_CALLBACK + b"]", 0x0E, 1)):
            members = entries()
            members["Payload/Synthetic.app/Synthetic"] = macho(27, symbols=(launch, (name, kind, section)))
            write_ipa(self.path, members)
            with self.subTest(kind=kind):
                self.assertEqual(self.check(None)["apple_compatibility"]["scene_startup"], "unverified")

    def test_framework_managed_and_stripped_methods_remain_unverified(self):
        for binary in (macho(27), macho(27, swiftui=True),
                       macho(27, swiftui=True, symbols=((b"-[Adapter application:didFinishLaunchingWithOptions:]", 0x0E, 1),))):
            members = entries()
            members["Payload/Synthetic.app/Synthetic"] = binary
            write_ipa(self.path, members)
            result = self.check(None)["apple_compatibility"]
            self.assertEqual(result["scene_startup"], "unverified")
            self.assertEqual(result["runtime_launch"], "not-tested")

    def test_symbol_tables_are_bounded_and_names_are_terminated(self):
        binary = legacy_macho()
        symtab = 32 + 24 + 152
        symbol_offset = struct.unpack_from("<I", binary, symtab + 8)[0]
        corruptions = [binary[:offset] + struct.pack("<I", 0xFFFFFFFF) + binary[offset + 4:]
                       for offset in (symtab + 8, symtab + 12, symtab + 16, symtab + 20)]
        corruptions += [binary[:symbol_offset] + struct.pack("<I", 0xFFFFFFFF) + binary[symbol_offset + 4:],
                        binary.replace(b"]\0", b"]x")]
        for corrupted in corruptions:
            members = entries()
            members["Payload/Synthetic.app/Synthetic"] = corrupted
            write_ipa(self.path, members)
            with self.subTest(binary=corrupted[:84]), self.assertRaises(ValueError):
                self.check(None)

    def test_empty_scene_manifest_is_not_adoption(self):
        members = entries()
        members["Payload/Synthetic.app/Synthetic"] = legacy_macho()
        info = plistlib.loads(members["Payload/Synthetic.app/Info.plist"])
        info["UIApplicationSceneManifest"] = {"UIApplicationSupportsMultipleScenes": False}
        members["Payload/Synthetic.app/Info.plist"] = plistlib.dumps(info)
        write_ipa(self.path, members)
        self.assertEqual(self.check(None)["apple_compatibility"]["scene_startup"], "unverified")

    def test_wrong_platform_and_bad_load_commands(self):
        for binary in (macho(platform=7), macho(platform=1), macho()[:40],
                       macho()[:12] + struct.pack("<I", 6) + macho()[16:],
                       macho()[:36] + struct.pack("<I", 7) + macho()[40:]):
            members = entries()
            members["Payload/Synthetic.app/Synthetic"] = binary
            write_ipa(self.path, members)
            with self.subTest(binary=binary[:40]), self.assertRaises(ValueError):
                self.check(None)

    def test_universal_executable_checks_every_slice(self):
        first, second = macho(), legacy_macho()
        header = struct.pack(">2I", 0xCAFEBABE, 2)
        table = (struct.pack(">5I", 0x100000C, 0, 48, len(first), 0)
                 + struct.pack(">5I", 0x100000C, 0, 48 + len(first), len(second), 0))
        members = entries()
        members["Payload/Synthetic.app/Synthetic"] = header + table + first + second
        write_ipa(self.path, members)
        result = self.check(None)["apple_compatibility"]
        self.assertEqual(result["linked_slices"][1]["sdk"], "27.0.0")
        self.assertEqual(result["scene_startup"], "unverified")

    def test_callback_section_and_address_must_exist(self):
        binary = macho(27, symbols=((b"-[TestDelegate " + SCENE_CALLBACK + b"]", 0x0E, 1),))
        symbol_offset = struct.unpack_from("<I", binary, 32 + 24 + 152 + 8)[0]
        invalid_section = binary[:symbol_offset + 5] + b"\xff" + binary[symbol_offset + 6:]
        invalid_address = binary[:symbol_offset + 8] + struct.pack("<Q", 0xFFFF) + binary[symbol_offset + 16:]
        for corrupted in (invalid_section, invalid_address):
            members = entries()
            members["Payload/Synthetic.app/Synthetic"] = corrupted
            write_ipa(self.path, members)
            with self.assertRaisesRegex(ValueError, "section"):
                self.check(None)

    def test_linked_framework_name_must_be_terminated(self):
        binary = macho(27, swiftui=True)
        command_length = struct.unpack_from("<I", binary, 32 + 24 + 4)[0]
        end = 32 + 24 + command_length
        corrupted = binary[:32 + 24 + 24] + binary[32 + 24 + 24:end].replace(b"\0", b"x") + binary[end:]
        members = entries()
        members["Payload/Synthetic.app/Synthetic"] = corrupted
        write_ipa(self.path, members)
        with self.assertRaisesRegex(ValueError, "unterminated"):
            self.check(None)

    def test_universal_dynamic_callback_offsets_are_slice_relative(self):
        first = macho(27, symbols=((b"-[TestDelegate " + SCENE_CALLBACK + b"]", 0x0E, 1),))
        second = macho(27, swiftui=True)
        header = struct.pack(">2I", 0xCAFEBABE, 2)
        table = (struct.pack(">5I", 0x100000C, 0, 48, len(first), 0)
                 + struct.pack(">5I", 0x100000C, 0, 48 + len(first), len(second), 0))
        members = entries()
        members["Payload/Synthetic.app/Synthetic"] = header + table + first + second
        write_ipa(self.path, members)
        result = self.check(None)["apple_compatibility"]
        self.assertTrue(result["linked_slices"][0]["defined_scene_callback"])
        self.assertEqual(result["scene_startup"], "unverified")
