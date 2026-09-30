"""The player's file names the game when exactly one offered game lists its disc ID."""
import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from padmint import cli

CATALOG = {
    "kartpad": {"id": "kartpad", "repo_url": "https://github.com/example/kartpad", "game_ids": ["RMCP01"],
                "player_targets": ["android", "ios"], "manifest": {"name": "KartPad"}},
    "romgame": {"id": "romgame", "repo_url": "https://github.com/example/romgame", "player_targets": ["ios"],
                "player_game_file": "in-app", "manifest": {"name": "RomGame"}},
}


class GameFromFileTests(unittest.TestCase):
    def run_start(self, answers, read_disc):
        stream = io.StringIO()
        replies = iter(answers)
        with mock.patch.object(cli, "catalog", return_value=CATALOG), \
                mock.patch.object(cli, "host_id", return_value="macos-arm64"), \
                mock.patch.object(cli.tools, "install"), \
                mock.patch.object(cli.tools, "executable", return_value="nodtool"), \
                mock.patch.object(cli.game_file, "read_disc", side_effect=read_disc), \
                mock.patch.object(cli, "make", return_value=0) as make:
            code = cli.start(lambda _prompt: next(replies), stream)
        return code, make, stream.getvalue()

    def disc(self, folder):
        disc = Path(folder) / "Mario Kart Wii.rvz"
        disc.write_bytes(b"x")
        return disc

    def test_a_kartpad_disc_skips_the_game_menu_and_is_not_asked_for_again(self):
        with tempfile.TemporaryDirectory() as folder:
            disc = self.disc(folder)
            code, make, text = self.run_start([str(disc), "2"], lambda *_: ("MARIO KART Wii", "RMCP01", 0))
        self.assertEqual(code, 0)
        self.assertEqual(make.call_args.args[:3], ("kartpad", "ios", disc.resolve()))
        self.assertIn("Reading your file…\nGame: KartPad (from your file, RMCP01)", text)
        self.assertNotIn("1. KartPad", text)

    def test_another_disc_shows_the_menu_but_keeps_the_file(self):
        with tempfile.TemporaryDirectory() as folder:
            disc = self.disc(folder)
            _code, make, text = self.run_start([str(disc), "1", "1"], lambda *_: ("OTHER", "RMCE01", 0))
        self.assertEqual(make.call_args.args[:3], ("kartpad", "android", disc.resolve()))
        self.assertIn("1. KartPad", text)

    def test_an_unreadable_file_falls_back_to_the_menu(self):
        def unreadable(*_):
            raise ValueError("not a disc")
        with tempfile.TemporaryDirectory() as folder:
            disc = self.disc(folder)
            _code, make, text = self.run_start([str(disc), "1", "1"], unreadable)
        self.assertEqual(make.call_args.args[0], "kartpad")
        self.assertIn("1. KartPad", text)

    def test_no_file_asks_as_before(self):
        with tempfile.TemporaryDirectory() as folder:
            disc = self.disc(folder)
            _code, make, _text = self.run_start(["", "1", "1", str(disc)], lambda *_: ("", "RMCP01", 0))
        self.assertEqual(make.call_args.args[:3], ("kartpad", "android", disc.resolve()))

    def test_an_in_app_game_ignores_a_dropped_file(self):
        with tempfile.TemporaryDirectory() as folder:
            disc = self.disc(folder)
            _code, make, _text = self.run_start([str(disc), "2"], lambda *_: ("", "NXXX01", 0))
        self.assertEqual(make.call_args.args[:3], ("romgame", "ios", None))

    def test_an_icloud_only_file_is_explained_at_once_and_never_read(self):
        with tempfile.TemporaryDirectory() as folder:
            disc = self.disc(folder)
            with mock.patch.object(cli.game_file, "cloud_only", side_effect=[True, False, False]):
                _code, make, text = self.run_start([str(disc), str(disc), "1"],
                                                   lambda *_: ("", "RMCP01", 0))
        self.assertIn("is stored only in iCloud", text)
        self.assertIn("Download Now", text)
        self.assertEqual(make.call_args.args[:3], ("kartpad", "android", disc.resolve()))


if __name__ == "__main__":
    unittest.main()
