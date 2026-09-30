import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from padmint import cli, manifest, tools

CATALOG = {
    "kartpad": {"id": "kartpad", "repo_url": "https://github.com/example/kartpad",
                "player_targets": ["android", "ios"],
                "manifest": {"name": "KartPad", "inputs": [{"type": "wii-disc", "formats": ["iso", "rvz"]}]}},
    "other": {"id": "other", "repo_url": "https://github.com/example/other"},
    "romgame": {"id": "romgame", "repo_url": "https://github.com/example/romgame", "player_targets": ["ios"],
                "player_game_file": "in-app", "manifest": {"name": "RomGame"}},
    "repogame": {"id": "repogame", "name": "RepoGame", "repo_url": "https://github.com/example/repogame",
                 "player_targets": ["ios"], "player_game_file": "in-app", "manifest": None,
                 "player_help": "https://github.com/example/repogame#get-started"},
}


class StartTests(unittest.TestCase):
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
        self.assertEqual(make.call_args.args[3], Path(folder).resolve())

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


class PhoneStartTests(unittest.TestCase):
    """On an Android phone (Ubuntu in Termux) nothing can be dragged into the window."""

    def run_on_phone(self, answers, downloads):
        replies = iter(answers)
        stream = io.StringIO()
        with mock.patch.object(cli, "catalog", return_value=CATALOG), \
                mock.patch.object(cli, "host_id", return_value="linux-arm64"), \
                mock.patch.object(cli, "on_android", return_value=True), \
                mock.patch.object(cli, "PHONE_DOWNLOADS", downloads), \
                mock.patch.object(cli, "make", return_value=0) as make:
            code = cli.start(lambda _prompt: next(replies), stream)
        return code, make, stream.getvalue()

    def test_offers_game_files_from_the_download_folder_and_saves_there(self):
        with tempfile.TemporaryDirectory() as folder:
            downloads = Path(folder)
            (downloads / "notes.txt").write_text("x")
            disc = downloads / "mkw.rvz"
            disc.write_bytes(b"x")
            code, make, shown = self.run_on_phone(["1", ""], downloads)
        self.assertEqual(code, 0)
        self.assertEqual(make.call_args.args[:4], ("kartpad", "android", disc.resolve(), downloads.resolve()))
        self.assertIn("1. mkw.rvz", shown)
        self.assertNotIn("notes.txt", shown)

    def test_another_file_is_typed(self):
        with tempfile.TemporaryDirectory() as folder:
            downloads = Path(folder)
            (downloads / "mkw.iso").write_bytes(b"x")
            other = downloads / "sub"
            other.mkdir()
            disc = other / "disc.rvz"
            disc.write_bytes(b"x")
            _code, make, _shown = self.run_on_phone(["2", str(disc), ""], downloads)
        self.assertEqual(make.call_args.args[2], disc.resolve())

    def test_folder_without_game_files_asks_for_a_path(self):
        with tempfile.TemporaryDirectory() as folder, tempfile.TemporaryDirectory() as elsewhere:
            downloads = Path(folder)
            disc = Path(elsewhere) / "disc.iso"
            disc.write_bytes(b"x")
            code, make, shown = self.run_on_phone([str(Path(elsewhere) / "missing.rvz"), str(disc), ""],
                                                  downloads)
        self.assertEqual(code, 0)
        self.assertEqual(make.call_args.args[2], disc.resolve())
        self.assertIn("No file at", shown)

    def test_phone_is_linux_with_android_system_files(self):
        with tempfile.TemporaryDirectory() as folder:
            mark = Path(folder) / "build.prop"
            with mock.patch("padmint.manifest.ANDROID_MARK", mark), \
                    mock.patch("padmint.manifest.platform.system", return_value="Linux"):
                self.assertFalse(manifest.on_android())
                mark.write_text("ro.build.version.release=16\n")
                self.assertTrue(manifest.on_android())

    def test_dotnet_heap_is_limited_on_a_phone_only(self):
        with tempfile.TemporaryDirectory() as folder:
            dotnet = Path(folder) / "tools/dotnet-8"
            dotnet.mkdir(parents=True)
            (dotnet / ".padmint-installed").write_text("{}")
            lock = {"dotnet": {"version": "8", "bin": ["."], "hosts": {"linux-arm64": {}}}}
            with mock.patch.dict(tools.os.environ, {"PADMINT_HOME": folder}), \
                    mock.patch.object(tools, "lock", return_value=lock):
                for phone in (False, True):
                    with mock.patch.object(tools, "on_android", return_value=phone):
                        env = tools.environment(["dotnet"], "linux-arm64", base={})
                    self.assertEqual(env.get("DOTNET_GCHeapHardLimit"), tools.ANDROID_DOTNET_HEAP if phone else None)


if __name__ == "__main__":
    unittest.main()
