import io
import errno
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

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

    def test_phone_export_does_not_ask_for_another_device_transfer(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            built = root / "build/personal.so"
            (built.parent / "personal.so.data/sys").mkdir(parents=True)
            (built.parent / "personal.so.data/sys/main.dol").write_bytes(b"synthetic")
            stream = io.StringIO()
            with mock.patch.object(cli, "on_android", return_value=True):
                target = cli.save_game_data(built, root, "Game", stream)
            self.assertIn(str(target), stream.getvalue())
            self.assertIn("already on this phone", stream.getvalue())
            self.assertIn("choose it with Import from Extracted Folder", stream.getvalue())
            self.assertNotIn("Copy it to your device", stream.getvalue())
            self.assertEqual((target / "sys/main.dol").read_bytes(), b"synthetic")

    def test_backends_without_a_folder_are_unchanged(self):
        with tempfile.TemporaryDirectory() as temporary:
            self.assertIsNone(cli.save_game_data(Path(temporary) / "personal.ipa", Path(temporary), "Game"))

    def test_copied_paths_have_no_dot_parts(self):
        """Windows' extended-length paths (\\\\?\\) take "." literally: C:\\out\\.\\cert.bin fails."""
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "data"
            (source / "sys").mkdir(parents=True)
            (source / "cert.bin").write_bytes(b"top")
            (source / "sys/main.dol").write_bytes(b"nested")
            target = str(Path(temporary) / "out")
            written = []
            real_copy = shutil.copyfile

            def recording_copy(src, dst):
                written.append(dst)
                return real_copy(src, dst)

            with mock.patch.object(cli.shutil, "copyfile", recording_copy):
                cli.copy_files(str(source), target)
            self.assertEqual(len(written), 2)
            for path in written:
                self.assertNotIn(os.curdir, Path(path).relative_to(target).parts[:-1], path)
                self.assertNotIn(os.sep + os.curdir + os.sep, path)
            self.assertEqual((Path(target) / "cert.bin").read_bytes(), b"top")

    @unittest.skipIf(os.name == "nt", "symbolic links need extra rights on Windows")
    def test_links_that_cannot_be_read_as_links_are_copied(self):
        """Termux's Ubuntu (proot) lists the backend's hard links as links, but
        reading one as a link fails with "Invalid argument"."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            built = root / "runs/1/personal.so"
            files = built.parent / "personal.so.data/files/Race"
            files.mkdir(parents=True)
            (root / "extracted.szs").write_bytes(b"synthetic track")
            (files / "Course.szs").symlink_to(root / "extracted.szs")
            out = root / "Download"
            out.mkdir()

            def unreadable(path, *args, **kwargs):
                raise OSError(errno.EINVAL, "Invalid argument", str(path))

            with mock.patch("os.readlink", unreadable):
                target = cli.save_game_data(built, out, "Game", io.StringIO())
            copied = target / "files/Race/Course.szs"
            self.assertFalse(copied.is_symlink())
            self.assertEqual(copied.read_bytes(), b"synthetic track")


if __name__ == "__main__":
    unittest.main()
