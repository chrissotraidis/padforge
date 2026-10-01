import hashlib
from pathlib import Path
import tempfile
import unittest
import plistlib
import struct

from fixtures import entries, macho, write_ipa
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
        self.assertEqual(apple["linked_slices"], [{"platform": "ios", "minimum_os": "15.0.0", "sdk": "26.0.0"}])
        self.assertEqual(apple["runtime_launch"], "not-tested")

    def test_sdk27_legacy_startup_rejected_for_all_ipa_checks(self):
        members = entries()
        members["Payload/Synthetic.app/Synthetic"] = macho(27)
        # A stale plist SDK cannot disguise what the executable was linked against.
        info = plistlib.loads(members["Payload/Synthetic.app/Info.plist"])
        info["DTSDKName"] = "iphoneos26.0"
        members["Payload/Synthetic.app/Info.plist"] = plistlib.dumps(info)
        write_ipa(self.path, members)
        for check in ("ipa", "kartpad-ipa", "none"):
            with self.subTest(check=check), self.assertRaisesRegex(ValueError, "SDK 27.*scene"):
                check_output(check, self.path, "a" * 40, self.disc_hash)

    def test_sdk27_declared_scene_or_dynamic_callback(self):
        for callback in (False, True):
            members = entries()
            members["Payload/Synthetic.app/Synthetic"] = macho(27) + (SCENE_CALLBACK if callback else b"")
            info = plistlib.loads(members["Payload/Synthetic.app/Info.plist"])
            info["UIApplicationSceneManifest"] = {}
            if not callback:
                info["UIApplicationSceneManifest"] = {"UISceneConfigurations": {
                    "UIWindowSceneSessionRoleApplication": [{"UISceneDelegateClassName": "TestSceneDelegate"}]}}
            members["Payload/Synthetic.app/Info.plist"] = plistlib.dumps(info)
            write_ipa(self.path, members)
            self.assertEqual(self.check(None)["apple_compatibility"]["runtime_launch"], "not-tested")

    def test_callback_string_without_scene_manifest_is_not_adoption(self):
        members = entries()
        members["Payload/Synthetic.app/Synthetic"] = macho(27) + SCENE_CALLBACK
        write_ipa(self.path, members)
        with self.assertRaisesRegex(ValueError, "SDK 27"):
            self.check(None)

    def test_empty_scene_manifest_is_not_adoption(self):
        members = entries()
        members["Payload/Synthetic.app/Synthetic"] = macho(27)
        info = plistlib.loads(members["Payload/Synthetic.app/Info.plist"])
        info["UIApplicationSceneManifest"] = {"UIApplicationSupportsMultipleScenes": False}
        members["Payload/Synthetic.app/Info.plist"] = plistlib.dumps(info)
        write_ipa(self.path, members)
        with self.assertRaisesRegex(ValueError, "scene"):
            self.check(None)

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
        first, second = macho(), macho(27)
        header = struct.pack(">2I", 0xCAFEBABE, 2)
        table = (struct.pack(">5I", 0x100000C, 0, 48, len(first), 0)
                 + struct.pack(">5I", 0x100000C, 0, 48 + len(first), len(second), 0))
        members = entries()
        members["Payload/Synthetic.app/Synthetic"] = header + table + first + second
        write_ipa(self.path, members)
        with self.assertRaisesRegex(ValueError, "SDK 27"):
            self.check(None)
