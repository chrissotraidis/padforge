import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from padforge import game_file
from padforge.manifest import validate_manifest

MANIFEST = {"name": "KartPad", "game": "Mario Kart Wii (Wii, RMCP01)",
            "inputs": [{"type": "wii-disc", "game_ids": ["RMCP01"], "revisions": [0]}]}


def header(game_id="RMCP01", revision=0, title="MarioKartWii"):
    """The top of `nodtool info` output (2.0.0-alpha.9)."""
    return (f"Format: RVZ\nLossless: true\n\nTitle: {title}\nGame ID: {game_id}\n"
            f"Disc 1, Revision {revision}\n\nPartition 0\n\tGame ID: {game_id} (00010004)\n")


class GameFileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.disc = Path(self.temp.name) / "My Disc.rvz"
        self.disc.write_bytes(b"synthetic input, not game data")

    def run_check(self, stdout, returncode=0, stderr="", manifest=MANIFEST):
        result = subprocess.CompletedProcess([], returncode, stdout, stderr)
        with mock.patch.object(game_file.subprocess, "run", return_value=result) as run:
            outcome = game_file.check(manifest, self.disc, "nodtool")
        self.assertEqual(run.call_args.args[0], ["nodtool", "info", str(self.disc)])
        return outcome

    def test_supported_disc_is_described(self):
        self.assertEqual(self.run_check(header()), "MarioKartWii (RMCP01, Europe, revision 0)")

    def test_other_region_says_which_version_is_needed(self):
        with self.assertRaisesRegex(ValueError, r"USA version \(RMCE01\).*Europe \(RMCP01\)"):
            self.run_check(header("RMCE01"))

    def test_other_game_is_named(self):
        with self.assertRaisesRegex(ValueError, r"Your file is ZELDA \(GZLE01\), not the game KartPad"):
            self.run_check(header("GZLE01", title="ZELDA"))

    def test_other_revision(self):
        with self.assertRaisesRegex(ValueError, "revision 1 of RMCP01.*revision 0"):
            self.run_check(header(revision=1))

    def test_unreadable_file_explains_likely_causes(self):
        with self.assertRaisesRegex(ValueError, "could not read My Disc.rvz.*unexpected end of file.*incomplete"):
            self.run_check("", returncode=1, stderr="Error: unexpected end of file")

    def test_games_without_disc_ids_are_not_checked(self):
        manifest = {"name": "Game", "inputs": [{"type": "wii-disc"}]}
        with mock.patch.object(game_file.subprocess, "run") as run:
            self.assertIsNone(game_file.check(manifest, self.disc, "nodtool"))
            self.assertIsNone(game_file.check(MANIFEST, None, "nodtool"))
        run.assert_not_called()

    def test_only_nodtool_is_installed_before_the_check(self):
        target = {"tools": ["dotnet", "android-ndk", "nodtool"]}
        with mock.patch.object(game_file.tools, "install") as install, \
                mock.patch.object(game_file.tools, "executable", return_value="nodtool"), \
                mock.patch.object(game_file.subprocess, "run",
                                  return_value=subprocess.CompletedProcess([], 0, header("RMCE01"), "")):
            with self.assertRaises(ValueError):
                game_file.check_before_tools(MANIFEST, target, self.disc, "linux-x86_64")
        install.assert_called_once_with(["nodtool"], "linux-x86_64")

    def test_manifest_validates_disc_ids(self):
        base = {"schema_version": 1, "id": "game", "name": "Game", "game": "Game", "kind": "disc-translation",
                "status": "experimental", "publication": {"public_binaries": False},
                "targets": {"android": {"hosts": {"linux-x86_64": "planned"}}}}
        validate_manifest(dict(base, inputs=[{"type": "wii-disc", "game_ids": ["RMCP01"], "revisions": [0]}]))
        for bad in ({"game_ids": ["rmcp01"]}, {"game_ids": "RMCP01"}, {"revisions": ["0"]}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                validate_manifest(dict(base, inputs=[dict({"type": "wii-disc"}, **bad)]))


if __name__ == "__main__":
    unittest.main()
