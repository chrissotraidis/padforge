"""A download that stops partway can leave a submodule half cloned, which git status reports
as changed, so PadMint refused every later run. PadMint finishes those submodules, but only
in its own game folders and only when submodules are the only difference."""
import io
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from padmint import cli

# Local file:// submodules need this since Git 2.38.
FILE_PROTOCOL = {"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "protocol.file.allow",
                 "GIT_CONFIG_VALUE_0": "always"}


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), "-c", "user.email=t@example.invalid", "-c", "user.name=T",
                           *args], check=True, capture_output=True, text=True).stdout.strip()


class FinishSubmodulesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="padmint submodules ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        patches = [mock.patch.dict(os.environ, dict(FILE_PROTOCOL, PADMINT_HOME=str(self.root / "home")))]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        library = self.root / "library"
        library.mkdir()
        git(library, "init", "-q")
        (library / "a.txt").write_text("one\n")
        git(library, "add", ".")
        git(library, "commit", "-qm", "one")
        self.first = git(library, "rev-parse", "HEAD")
        (library / "a.txt").write_text("two\n")
        git(library, "commit", "-qam", "two")
        game = self.root / "game-source"
        game.mkdir()
        git(game, "init", "-q")
        (game / "README").write_text("game\n")
        git(game, "add", ".")
        git(game, "submodule", "add", "-q", library.as_uri(), "lib/library")
        git(game, "commit", "-qm", "game")
        self.source = game

    def download(self, where):
        folder = where / "game-v1"
        folder.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "clone", "-q", "--recurse-submodules", self.source.as_uri(), str(folder)],
                       check=True, capture_output=True)
        # Leave the submodule at another commit, as a download that stopped partway can.
        git(folder / "lib/library", "checkout", "-q", self.first)
        return folder

    def test_a_game_folder_whose_only_differences_are_submodules_is_finished(self):
        folder = self.download(self.root / "home/games")
        self.assertEqual(git(folder, "status", "--porcelain"), "M lib/library")  # " M", stripped
        output = io.StringIO()
        self.assertEqual(cli.finish_submodules(folder, stream=output), ["lib/library"])
        self.assertEqual(output.getvalue(), "PadMint is finishing lib/library in game-v1: "
                                            "an earlier download stopped partway.\n")
        self.assertEqual(git(folder, "status", "--porcelain"), "")
        cli.check_checkout(folder, git(folder, "rev-parse", "HEAD"))

    def test_any_other_change_keeps_the_refusal(self):
        folder = self.download(self.root / "home/games")
        (folder / "README").write_text("edited\n")
        self.assertEqual(cli.finish_submodules(folder, stream=io.StringIO()), [])
        self.assertEqual(git(folder / "lib/library", "rev-parse", "HEAD"), self.first)  # untouched
        with self.assertRaisesRegex(ValueError, "local changes"):
            cli.check_checkout(folder, git(folder, "rev-parse", "HEAD"))

    def test_a_folder_the_player_passed_in_is_never_changed(self):
        folder = self.download(self.root / "elsewhere")
        self.assertEqual(cli.finish_submodules(folder, stream=io.StringIO()), [])
        self.assertEqual(git(folder / "lib/library", "rev-parse", "HEAD"), self.first)

    def test_a_clean_folder_is_left_alone(self):
        folder = self.download(self.root / "home/games")
        git(folder / "lib/library", "checkout", "-q", "-")
        output = io.StringIO()
        self.assertEqual(cli.finish_submodules(folder, stream=output), [])
        self.assertEqual(output.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
