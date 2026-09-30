"""Repair interrupted submodule downloads without discarding edits at any depth."""
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
        (library / "incoming.txt").write_text("upstream\n")
        git(library, "add", ".")
        git(library, "commit", "-qm", "two")
        self.library = library
        game = self.root / "game-source"
        game.mkdir()
        git(game, "init", "-q")
        (game / "README").write_text("game\n")
        git(game, "add", ".")
        git(game, "submodule", "add", "-q", library.as_uri(), "lib/library")
        git(game, "commit", "-qm", "game")
        self.source = game

    def download(self, where, rewind=True):
        folder = where / "game-v1"
        folder.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "clone", "-q", "--recurse-submodules", self.source.as_uri(), str(folder)],
                       check=True, capture_output=True)
        # Leave the submodule at another commit, as a download that stopped partway can.
        if rewind:
            git(folder / "lib/library", "checkout", "-q", self.first)
        return folder

    def add_nested_source(self):
        nested = self.root / "nested-source"
        nested.mkdir()
        git(nested, "init", "-q")
        (nested / "a.txt").write_text("nested one\n")
        git(nested, "add", ".")
        git(nested, "commit", "-qm", "one")
        self.nested_first = git(nested, "rev-parse", "HEAD")
        (nested / "a.txt").write_text("nested two\n")
        (nested / "incoming.txt").write_text("upstream\n")
        git(nested, "add", ".")
        git(nested, "commit", "-qm", "two")
        git(self.library, "submodule", "add", "-q", nested.as_uri(), "deps/nested library")
        git(self.library, "commit", "-qm", "nested")
        self.parent_first = git(self.library, "rev-parse", "HEAD")
        (self.library / "a.txt").write_text("three\n")
        git(self.library, "commit", "-qam", "three")
        source_library = self.source / "lib/library"
        git(source_library, "fetch", "-q")
        git(source_library, "checkout", "-q", git(self.library, "rev-parse", "HEAD"))
        git(self.source, "add", "lib/library")
        git(self.source, "commit", "-qm", "nested game")

    def nested_download(self, where=None):
        if not (self.root / "nested-source").exists():
            self.add_nested_source()
        folder = self.download(where or self.root / "home/games", rewind=False)
        git(folder / "lib/library", "checkout", "-q", self.parent_first)
        return folder

    def assert_refused_unchanged(self, folder, edited):
        library = folder / "lib/library"
        heads = [git(repo, "rev-parse", "HEAD") for repo in (folder, library, edited)]
        status = git(edited, "status", "--porcelain=v1", "--untracked-files=all", "--ignored",
                     "--ignore-submodules=none")
        index = git(edited, "ls-files", "--stage")
        files = {path.relative_to(edited): path.read_bytes() for path in edited.rglob("*")
                 if path.is_file() and ".git" not in path.relative_to(edited).parts}
        output = io.StringIO()
        with mock.patch.object(cli.subprocess, "run", wraps=subprocess.run) as run:
            self.assertEqual(cli.finish_submodules(folder, stream=output), [])
        self.assertFalse(any("update" in call.args[0] for call in run.call_args_list))
        self.assertEqual(output.getvalue(), "")
        self.assertEqual([git(repo, "rev-parse", "HEAD") for repo in (folder, library, edited)], heads)
        self.assertEqual(git(edited, "status", "--porcelain=v1", "--untracked-files=all", "--ignored",
                             "--ignore-submodules=none"), status)
        self.assertEqual(git(edited, "ls-files", "--stage"), index)
        self.assertEqual({path.relative_to(edited): path.read_bytes() for path in edited.rglob("*")
                          if path.is_file() and ".git" not in path.relative_to(edited).parts}, files)

    def test_tracked_untracked_staged_and_deleted_edits_are_preserved_at_each_depth(self):
        for nested in (False, True):
            for change in ("tracked", "untracked", "staged", "deleted", "ignored"):
                with self.subTest(nested=nested, change=change):
                    where = self.root / "home/games" / f"{nested}-{change}"
                    folder = self.nested_download(where) if nested else self.download(where)
                    edited = folder / "lib/library"
                    if nested:
                        edited = edited / "deps/nested library"
                        git(edited, "checkout", "-q", self.nested_first)
                        # Dirt must be detected even when Git config hides it.
                        git(folder / "lib/library", "config", "submodule.deps/nested library.ignore", "all")
                    git(folder, "config", "submodule.lib/library.ignore", "dirty")
                    path = edited / ("incoming.txt" if change in ("untracked", "ignored") else "a.txt")
                    if change == "deleted":
                        path.unlink()
                    else:
                        path.write_text("player's work\n")
                    if change == "staged":
                        git(edited, "add", "a.txt")
                    if change == "ignored":
                        exclude = Path(git(edited, "rev-parse", "--absolute-git-dir")) / "info/exclude"
                        exclude.write_text("incoming.txt\n")
                    self.assert_refused_unchanged(folder, edited)

    def test_edits_at_the_pinned_commit_are_preserved(self):
        folder = self.download(self.root / "home/games", rewind=False)
        library = folder / "lib/library"
        (library / "a.txt").write_text("player's work\n")
        self.assert_refused_unchanged(folder, library)

    def test_a_git_only_clone_without_an_index_finishes_its_initial_checkout(self):
        folder = self.root / "home/games/half-clone"
        git(self.root, "clone", "-q", self.source.as_uri(), str(folder))
        library = folder / "lib/library"
        git(folder, "clone", "-q", "--no-checkout", self.library.as_uri(), str(library))
        git(folder, "submodule", "absorbgitdirs")
        self.assertTrue((library / ".git").is_file())
        self.assertEqual([path.name for path in library.iterdir()], [".git"])
        self.assertFalse((library / git(library, "rev-parse", "--git-path", "index")).exists())
        with mock.patch.object(cli.subprocess, "run", wraps=subprocess.run) as run:
            self.assertEqual(cli.finish_submodules(folder, stream=io.StringIO()), ["lib/library"])
        self.assertTrue(all("--force" not in call.args[0] for call in run.call_args_list))
        self.assertEqual((library / "a.txt").read_text(), "two\n")
        cli.check_checkout(folder, git(folder, "rev-parse", "HEAD"))

    def test_a_git_only_folder_with_indexed_deletions_is_preserved(self):
        folder = self.download(self.root / "home/games", rewind=False)
        library = folder / "lib/library"
        (library / "a.txt").unlink()
        (library / "incoming.txt").unlink()
        self.assertEqual([path.name for path in library.iterdir()], [".git"])
        self.assertTrue((library / git(library, "rev-parse", "--git-path", "index")).exists())
        self.assert_refused_unchanged(folder, library)

    def test_an_initial_checkout_with_existing_files_is_preserved(self):
        folder = self.root / "home/games/half-clone"
        git(self.root, "clone", "-q", self.source.as_uri(), str(folder))
        library = folder / "lib/library"
        git(folder, "clone", "-q", "--no-checkout", self.library.as_uri(), str(library))
        (library / "a.txt").write_text("player's work\n")
        self.assert_refused_unchanged(folder, library)

    def test_an_empty_clone_is_not_changed_if_another_submodule_has_edits(self):
        git(self.source, "submodule", "add", "-q", self.library.as_uri(), "lib/other")
        git(self.source, "commit", "-qm", "other library")
        folder = self.root / "home/games/mixed"
        git(self.root, "clone", "-q", self.source.as_uri(), str(folder))
        library = folder / "lib/library"
        git(folder, "clone", "-q", "--no-checkout", self.library.as_uri(), str(library))
        other = folder / "lib/other"
        git(folder, "clone", "-q", self.library.as_uri(), str(other))
        (other / "a.txt").write_text("player's work\n")
        self.assert_refused_unchanged(folder, other)
        self.assertEqual([path.name for path in library.iterdir()], [".git"])

    def test_clean_nested_commit_mismatches_are_repaired(self):
        folder = self.nested_download()
        nested = folder / "lib/library/deps/nested library"
        git(nested, "checkout", "-q", self.nested_first)
        self.assertEqual(cli.finish_submodules(folder, stream=io.StringIO()), ["lib/library"])
        self.assertEqual(git(folder, "status", "--porcelain", "--ignore-submodules=none"), "")
        self.assertEqual((nested / "a.txt").read_text(), "nested two\n")

    def test_interrupted_nested_download_is_retried_without_force(self):
        self.add_nested_source()
        folder = self.root / "home/games/interrupted"
        git(self.root, "clone", "-q", self.source.as_uri(), str(folder))
        git(folder, "submodule", "init")
        # An outer clone finishes at an earlier commit, then its nested download fails.
        library = folder / "lib/library"
        git(folder, "clone", "-q", self.library.as_uri(), str(library))
        git(library, "checkout", "-q", self.parent_first)
        missing = self.root / "not-available-yet"
        git(library, "config", "submodule.deps/nested library.url", missing.as_uri())
        failed = subprocess.run(["git", "-C", str(library), "submodule", "update", "--init", "--recursive"],
                                capture_output=True)
        self.assertNotEqual(failed.returncode, 0)
        nested = library / "deps/nested library"
        self.assertFalse((nested / ".git").exists())
        git(library, "config", "submodule.deps/nested library.url", (self.root / "nested-source").as_uri())
        with mock.patch.object(cli.subprocess, "run", wraps=subprocess.run) as run:
            self.assertEqual(cli.finish_submodules(folder, stream=io.StringIO()), ["lib/library"])
        update = next(call.args[0] for call in run.call_args_list if "update" in call.args[0])
        self.assertNotIn("--force", update)
        self.assertIn("--checkout", update)
        self.assertEqual((nested / "a.txt").read_text(), "nested two\n")
        self.assertEqual(git(folder, "status", "--porcelain", "--ignore-submodules=none"), "")

    def test_files_in_an_uninitialized_nested_folder_are_preserved(self):
        self.add_nested_source()
        folder = self.root / "home/games/uninitialized"
        git(self.root, "clone", "-q", self.source.as_uri(), str(folder))
        library = folder / "lib/library"
        git(folder, "clone", "-q", self.library.as_uri(), str(library))
        git(library, "checkout", "-q", self.parent_first)
        nested = library / "deps/nested library"
        (nested / "a.txt").write_text("player's work\n")
        head = git(library, "rev-parse", "HEAD")
        self.assertEqual(cli.finish_submodules(folder, stream=io.StringIO()), [])
        self.assertEqual((nested / "a.txt").read_text(), "player's work\n")
        self.assertEqual(git(library, "rev-parse", "HEAD"), head)
        self.assertFalse((nested / ".git").exists())

    def test_a_failed_update_is_not_reported_as_finished(self):
        folder = self.download(self.root / "home/games")
        real_run = subprocess.run

        def fail_update(command, **kwargs):
            if "update" in command:
                self.assertTrue(kwargs.get("check"))
                raise subprocess.CalledProcessError(1, command)
            return real_run(command, **kwargs)

        with mock.patch.object(cli.subprocess, "run", side_effect=fail_update):
            with self.assertRaises(subprocess.CalledProcessError):
                cli.finish_submodules(folder, stream=io.StringIO())
        self.assertEqual(git(folder / "lib/library", "rev-parse", "HEAD"), self.first)

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
