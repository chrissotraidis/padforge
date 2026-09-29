"""Manifest, catalog, doctor and gate coverage; synthetic data only."""
import copy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from padforge import gate
from padforge.cli import doctor, main
from padforge.manifest import catalog, expand, manifest_for, validate_manifest

FAKE_KEY = bytes(range(0xA0, 0xB0))
FAKE = {"Synthetic key": (FAKE_KEY[:4].hex(), hashlib.sha256(FAKE_KEY).hexdigest())}


def minimal():
    return copy.deepcopy(catalog()["kartpad"]["manifest"])


class ManifestTests(unittest.TestCase):
    def test_catalog_entries_validate(self):
        entries = catalog()
        self.assertTrue({"bluewake", "kartpad"} <= set(entries))
        for game, entry in entries.items():
            self.assertEqual(entry["id"], game)

    def test_rejects_unknown_placeholder_kind_and_host(self):
        for path, value in ((("targets", "ios", "command"), ["{home}/x"]),
                            (("kind",), "rom-dump"),
                            (("targets", "ios", "hosts"), {"amiga": "verified"})):
            data = minimal()
            node = data
            for key in path[:-1]:
                node = node[key]
            node[path[-1]] = value
            with self.subTest(path=path), self.assertRaises(ValueError):
                validate_manifest(data)

    def test_runnable_host_requires_command_and_publication_flag(self):
        data = minimal()
        del data["targets"]["ios"]["command"]
        with self.assertRaisesRegex(ValueError, "no command"):
            validate_manifest(data)
        data = minimal()
        del data["publication"]
        with self.assertRaisesRegex(ValueError, "public_binaries"):
            validate_manifest(data)

    def test_repository_manifest_wins_and_must_match(self):
        with tempfile.TemporaryDirectory() as folder:
            data = minimal()
            data["status"] = "supported"
            (Path(folder) / "padforge.json").write_text(json.dumps(data))
            self.assertEqual(manifest_for("kartpad", folder), (data, "repository"))
            with self.assertRaisesRegex(ValueError, "declares kartpad"):
                manifest_for("bluewake", folder)

    def test_expand_keeps_values_as_single_arguments(self):
        argv = expand(["{disc}", "--jobs", "{jobs}"], {"disc": "a disc; rm {x}", "jobs": "2"})
        self.assertEqual(argv, ["a disc; rm {x}", "--jobs", "2"])

    def test_planned_target_is_refused(self):
        with tempfile.TemporaryDirectory() as folder, patch("sys.stderr", io.StringIO()) as err:
            disc = Path(folder) / "disc.iso"
            disc.write_bytes(b"synthetic")
            code = main(["plan", "kartpad", "--repo", folder, "--revision", "0" * 40,
                         "--disc", str(disc), "--target", "android"])
            self.assertEqual(code, 1)
            self.assertTrue(err.getvalue())

    def test_doctor_reports_without_installing(self):
        stream = io.StringIO()
        code = doctor("kartpad", "android", stream=stream)
        self.assertEqual(code, 1)
        self.assertIn("planned", stream.getvalue())
        self.assertIn("free disk space", stream.getvalue())


class GateTests(unittest.TestCase):
    def setUp(self):
        self.patcher = patch.object(gate, "KEY_FINGERPRINTS", FAKE)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def test_key_forms_detected(self):
        wrapped = ",\n".join(", ".join(f"0x{b:02X}" for b in FAKE_KEY[i:i + 8]) for i in (0, 8))
        for data in (b"xx" + FAKE_KEY + b"yy", FAKE_KEY.hex().upper().encode(), wrapped.encode()):
            with self.subTest(data=data[:12]):
                self.assertEqual(gate.key_findings(data), ["Synthetic key"])

    def test_prefix_alone_and_partial_lists_are_not_keys(self):
        self.assertEqual(gate.key_findings(FAKE_KEY[:4] + bytes(12)), [])
        self.assertEqual(gate.key_findings(", ".join(f"0x{b:02x}" for b in FAKE_KEY[:8]).encode()), [])

    def test_real_fingerprints_hold_no_key_material(self):
        source = Path(gate.__file__).read_bytes()
        for prefix, digest in gate.KEY_FINGERPRINTS.values():
            self.assertEqual(len(prefix), 8)
            self.assertEqual(len(digest), 64)
        self.patcher.stop()
        self.assertEqual(gate.key_findings(source), [])
        self.patcher.start()

    def test_archive_findings_and_fail_closed(self):
        name = "func_" + format(0x80001000, "08X")
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as archive:
            archive.writestr("code.c", f"void {name}(void) {{ }}")
            archive.writestr("provenance.json", '{"containsTranslatedGameCode": true}')
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "package.zip"
            path.write_bytes(stream.getvalue())
            findings, _ = gate.check(str(path))
            self.assertEqual(len(findings), 2)
            tarball = Path(folder) / "source.tar.gz"
            tarball.write_bytes(b"\x1f\x8bsynthetic")
            self.assertIn("fails closed", gate.check(str(tarball))[0][0])
            clean = Path(folder) / "clean.txt"
            clean.write_text("runtime only")
            self.assertEqual(gate.audit([clean], stream=io.StringIO()), 0)

    def test_compressed_streams_and_tar_are_read(self):
        import bz2, gzip, tarfile
        with tempfile.TemporaryDirectory() as folder:
            hidden = Path(folder) / "save.sav.gz"
            hidden.write_bytes(gzip.compress(b"xx" + FAKE_KEY + b"yy"))
            self.assertEqual(gate.check(str(hidden))[0], ["Synthetic key in save.sav.gz!save.sav"])
            plain = Path(folder) / "sample1.bz2"
            plain.write_bytes(bz2.compress(b"ordinary test data"))
            self.assertEqual(gate.check(str(plain))[0], [])
            member = io.BytesIO()
            with tarfile.open(fileobj=member, mode="w:gz") as archive:
                info = tarfile.TarInfo("src/key.c")
                body = FAKE_KEY.hex().encode()
                info.size = len(body)
                archive.addfile(info, io.BytesIO(body))
            tarball = Path(folder) / "source.tar.gz"
            tarball.write_bytes(member.getvalue())
            self.assertEqual(gate.check(str(tarball))[0], ["Synthetic key in source.tar.gz!source.tar!src/key.c"])
            trailing = Path(folder) / "two.gz"
            trailing.write_bytes(gzip.compress(b"a") + gzip.compress(b"b"))
            self.assertIn("fails closed", gate.check(str(trailing))[0][0])


if __name__ == "__main__":
    unittest.main()
