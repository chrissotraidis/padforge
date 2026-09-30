import hashlib
from pathlib import Path
import tempfile
import unittest

from fixtures import entries, write_ipa
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
