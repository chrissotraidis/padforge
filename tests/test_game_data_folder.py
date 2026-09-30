import io
import tempfile
import unittest
from pathlib import Path

from padmint import cli


class GameDataFolderTests(unittest.TestCase):
    def test_folder_beside_the_output_is_copied_once(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            built = root / "runs/1/personal.so"
            (built.parent / "personal.so.data/sys").mkdir(parents=True)
            (built.parent / "personal.so.data/sys/main.dol").write_bytes(b"synthetic")
            out = root / "Downloads"
            out.mkdir()
            stream = io.StringIO()
            target = cli.save_game_data(built, out, "Game", stream)
            self.assertEqual(target, out / "Game game data")
            self.assertEqual((target / "sys/main.dol").read_bytes(), b"synthetic")
            self.assertNotEqual((target / "sys/main.dol").stat().st_ino,
                                (built.parent / "personal.so.data/sys/main.dol").stat().st_ino)
            self.assertIn("Import from Extracted Folder", stream.getvalue())
            (target / "sys/main.dol").write_bytes(b"player's own copy")
            self.assertEqual(cli.save_game_data(built, out, "Game", io.StringIO()), target)
            self.assertEqual((target / "sys/main.dol").read_bytes(), b"player's own copy")
            self.assertFalse((out / "Game game data.partial").exists())

    def test_the_ending_names_the_button_the_platform_shows(self):
        from padmint.manifest import catalog
        labels = catalog()["kartpad"]["game_data_import"]
        self.assertEqual(labels["android"], "Import from Extracted Game Data Folder")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            built = root / "build/personal.so"
            (built.parent / "personal.so.data/sys").mkdir(parents=True)
            (built.parent / "personal.so.data/sys/main.dol").write_bytes(b"synthetic")
            stream = io.StringIO()
            cli.save_game_data(built, root, "KartPad", stream, import_label=labels["android"])
        self.assertIn("choose it with Import from Extracted Game Data Folder. It needs no key.", stream.getvalue())

    def test_backends_without_a_folder_are_unchanged(self):
        with tempfile.TemporaryDirectory() as temporary:
            self.assertIsNone(cli.save_game_data(Path(temporary) / "personal.ipa", Path(temporary), "Game"))


if __name__ == "__main__":
    unittest.main()
