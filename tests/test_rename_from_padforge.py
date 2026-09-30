"""PadMint was called PadForge before 0.2.0 (padforge#25). Players and game
repositories from before the rename keep working without downloading again."""
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from padmint import cli, manifest, tools


class RenameFromPadForgeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        environ = {key: value for key, value in os.environ.items() if key != "PADMINT_HOME"}
        self.patches = [mock.patch.dict(os.environ, environ, clear=True),
                        mock.patch.object(Path, "home", return_value=self.root)]
        for patch in self.patches:
            patch.start()

    def tearDown(self):
        for patch in self.patches:
            patch.stop()
        self.temporary.cleanup()

    def test_the_padforge_folder_is_moved_once_and_its_tools_count_as_installed(self):
        tool = self.root / ".padforge/tools/tool-1"
        tool.mkdir(parents=True)
        (tool / ".padforge-installed").write_text("{}\n")
        lock = {"tool": {"version": "1", "hosts": {"test-host": {"url": "file:///unused"}}}}
        with mock.patch.object(tools, "lock", return_value=lock):
            output = io.StringIO()
            tools.install(["tool"], "test-host", output)
        self.assertEqual(tools.home(), self.root / ".padmint")
        self.assertFalse((self.root / ".padforge").exists())
        self.assertIn("ok   tool 1", output.getvalue())

    def test_a_new_player_gets_a_padmint_folder(self):
        self.assertEqual(tools.tools_root(), self.root / ".padmint/tools")
        self.assertFalse((self.root / ".padforge").exists())

    def test_build_settings_made_before_the_move_are_set_up_again(self):
        # padmint#7: CMake refused ~/.padmint/games/.../build-recomp-tools because its
        # CMakeCache.txt was written in ~/.padforge before PadMint moved the folder.
        game = self.root / ".padforge/games/goldenpad-v0.2.0"
        for name in ("build-recomp-tools", "build-current", ".git/modules/x"):
            folder = game / name
            folder.mkdir(parents=True)
        for name in ("build-recomp-tools", ".git/modules/x"):
            (game / name / "CMakeCache.txt").write_text(
                "CMAKE_CACHEFILE_DIR:INTERNAL=" + str(game / name) + "\n")
        tools.home()
        game = self.root / ".padmint/games/goldenpad-v0.2.0"
        (game / "build-current/CMakeCache.txt").write_text(
            "CMAKE_CACHEFILE_DIR:INTERNAL=" + str(game / "build-current") + "\n")
        output = io.StringIO()
        moved = cli.forget_moved_build_settings(game, stream=output)
        self.assertEqual(moved, [game / "build-recomp-tools/CMakeCache.txt"])
        self.assertFalse((game / "build-recomp-tools/CMakeCache.txt").exists())
        self.assertTrue((game / "build-current/CMakeCache.txt").exists())
        self.assertTrue((game / ".git/modules/x/CMakeCache.txt").exists())
        self.assertIn("Setting up 1 build folder(s) again", output.getvalue())
        self.assertEqual(cli.forget_moved_build_settings(game, stream=output), [])

    def test_game_repositories_still_get_padforge_variable_names(self):
        env = cli.backend_env(None)
        self.assertEqual(env["PADMINT_CACHE"], str(self.root / ".padmint/cache"))
        self.assertEqual(env["PADFORGE_CACHE"], env["PADMINT_CACHE"])

    def test_a_checkout_with_padforge_json_still_builds_and_padmint_json_wins(self):
        repo = self.root / "game"
        repo.mkdir()
        (repo / "padforge.json").write_text("{}")
        self.assertEqual(manifest.repository_manifest(repo), repo / "padforge.json")
        (repo / "padmint.json").write_text("{}")
        self.assertEqual(manifest.repository_manifest(repo), repo / "padmint.json")
        self.assertIsNone(manifest.repository_manifest(self.root))


if __name__ == "__main__":
    unittest.main()
