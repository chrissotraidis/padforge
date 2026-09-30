"""An interrupted download of a game's source is fetched again (padmint#8)."""
import io
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from padmint import cli


def git(*args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


class SourceDownloadTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.origin = self.root / "origin"
        self.origin.mkdir()
        git("init", "-q", cwd=self.origin)
        (self.origin / "padmint.json").write_text("{}")
        (self.origin / "README.md").write_text("game")
        git("add", ".", cwd=self.origin)
        git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "one", cwd=self.origin)

    def tearDown(self):
        self.temporary.cleanup()

    def clone(self, dest, ref=None):
        git("clone", "-q", str(self.origin), str(dest), cwd=self.root)
        return 0

    def test_a_finished_download_is_reused(self):
        source = self.root / "games/game-v1"
        source.parent.mkdir()
        self.clone(source)
        self.assertTrue(cli.source_complete(source))

    def test_missing_files_or_no_git_mean_unfinished(self):
        source = self.root / "games/game-v1"
        source.parent.mkdir()
        self.assertFalse(cli.source_complete(source))
        (source / ".git").mkdir(parents=True)
        self.assertFalse(cli.source_complete(source))  # the state that caused padmint#8
        cli._remove_tree(source)
        self.clone(source)
        (source / "padmint.json").unlink()
        self.assertFalse(cli.source_complete(source))

    def test_an_unfinished_download_is_replaced_and_a_leftover_partial_removed(self):
        source = self.root / "games/game-v1"
        (source / ".git").mkdir(parents=True)
        leftover = self.root / "games/game-v1.partial"
        leftover.mkdir()
        (leftover / "junk").write_text("x")
        output = io.StringIO()
        with mock.patch.object(cli, "get_game", side_effect=lambda game, dest, ref, **_: self.clone(dest)), \
                redirect_stdout(output):
            cli.fetch_source("game", source, "v1")
        self.assertTrue(cli.source_complete(source))
        self.assertFalse(leftover.exists())
        self.assertIn("unfinished; downloading it again", output.getvalue())

    def test_a_failed_download_leaves_only_the_partial_folder(self):
        source = self.root / "games/game-v1"
        with mock.patch.object(cli, "get_game", side_effect=subprocess.CalledProcessError(128, "git")):
            with self.assertRaises(subprocess.CalledProcessError):
                cli.fetch_source("game", source, "v1")
        self.assertFalse(source.exists())

    def test_a_computer_without_git_gets_padmints_copy_before_the_check(self):
        source = self.root / "games/game-v1"
        (source / ".git").mkdir(parents=True)
        with mock.patch.object(cli.shutil, "which", return_value=None), \
                mock.patch.object(cli.tools, "install") as install, \
                mock.patch.object(cli.tools, "executable", return_value="git"):
            self.assertFalse(cli.source_complete(source))
        install.assert_called_once_with(["git"], cli.host_id())

    def test_read_only_files_are_removed_for_real(self):
        folder = self.root / "ro"
        folder.mkdir()
        (folder / "object").write_text("x")
        os.chmod(folder / "object", 0o444)
        cli._remove_tree(folder)
        self.assertFalse(folder.exists())


if __name__ == "__main__":
    unittest.main()
