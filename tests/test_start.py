import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from padmint import cli

CATALOG = {
    "kartpad": {"id": "kartpad", "repo_url": "https://github.com/example/kartpad",
                "player_targets": ["android", "ios"], "manifest": {"name": "KartPad"}},
    "other": {"id": "other", "repo_url": "https://github.com/example/other"},
    "romgame": {"id": "romgame", "repo_url": "https://github.com/example/romgame", "player_targets": ["ios"],
                "player_game_file": "in-app", "manifest": {"name": "RomGame"}},
    "repogame": {"id": "repogame", "name": "RepoGame", "repo_url": "https://github.com/example/repogame",
                 "player_targets": ["ios"], "player_game_file": "in-app", "manifest": None,
                 "player_help": "https://github.com/example/repogame#get-started"},
}


class StartTests(unittest.TestCase):
    def setUp(self):
        downloads = Path.home() / "Downloads"
        self.out = (downloads if downloads.is_dir() else Path.home()).resolve()

    def run_start(self, answers, host):
        replies = iter(answers)
        with mock.patch.object(cli, "catalog", return_value=CATALOG), \
                mock.patch.object(cli, "host_id", return_value=host), \
                mock.patch.object(cli, "make", return_value=0) as make:
            code = cli.start(lambda _prompt: next(replies), io.StringIO())
        return code, make

    def test_asks_only_for_the_game_file_and_folder_when_one_choice_remains(self):
        with tempfile.TemporaryDirectory() as folder:
            disc = Path(folder) / "My Disc.wbfs"
            disc.write_bytes(b"x")
            code, make = self.run_start(["1", f"'{disc}'", folder], "linux-x86_64")
        self.assertEqual(code, 0)
        self.assertEqual(make.call_args.args[:3], ("kartpad", "android", disc.resolve()))
        self.assertEqual(make.call_args.args[3], self.out)  # saved to Downloads without asking

    def test_mac_also_offers_iphone(self):
        with tempfile.TemporaryDirectory() as folder:
            disc = Path(folder) / "disc.wbfs"
            disc.write_bytes(b"x")
            _code, make = self.run_start(["1", "2", str(disc), folder], "macos-arm64")
        self.assertEqual(make.call_args.args[1], "ios")

    def test_intel_mac_offers_android_only(self):
        with tempfile.TemporaryDirectory() as folder:
            disc = Path(folder) / "disc.wbfs"
            disc.write_bytes(b"x")
            _code, make = self.run_start(["1", str(disc), folder], "macos-x86_64")
        self.assertEqual(make.call_args.args[:2], ("kartpad", "android"))

    def test_game_file_added_in_the_app_is_not_asked_for(self):
        with tempfile.TemporaryDirectory() as folder:
            _code, make = self.run_start(["3", folder], "macos-arm64")
        self.assertEqual(make.call_args.args[:3], ("romgame", "ios", None))

    def test_game_with_manifest_in_its_repository_is_offered_with_its_help_link(self):
        stream = io.StringIO()
        with tempfile.TemporaryDirectory() as folder:
            replies = iter(["2", folder])
            with mock.patch.object(cli, "catalog", return_value=CATALOG), \
                    mock.patch.object(cli, "host_id", return_value="macos-arm64"), \
                    mock.patch.object(cli, "make", return_value=0) as make:
                cli.start(lambda _prompt: next(replies), stream)
        self.assertEqual(make.call_args.args[:3], ("repogame", "ios", None))
        self.assertIn("2. RepoGame", stream.getvalue())
        self.assertIn("Next: https://github.com/example/repogame#get-started", stream.getvalue())

    def test_dragged_paths_lose_quotes_and_escapes(self):
        self.assertEqual(cli.dropped_path('"C:/Games/My Disc.wbfs"'), Path("C:/Games/My Disc.wbfs"))
        if cli.os.name != "nt":
            self.assertEqual(cli.dropped_path("/tmp/My\\ Disc.wbfs "), Path("/tmp/My Disc.wbfs"))


if __name__ == "__main__":
    unittest.main()
