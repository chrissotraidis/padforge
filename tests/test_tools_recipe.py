"""`padmint tools` uses the recipe of the game's latest release, as `make` does."""
import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from padmint import cli

RECIPE = {"name": "KartPad", "targets": {"android": {"tools": ["android-ndk", "dotnet"]}}}


class ToolsRecipeTests(unittest.TestCase):
    def run_tools(self, origin, argv=("tools", "kartpad")):
        output = io.StringIO()
        with mock.patch.object(cli, "release_source", return_value=(Path("/h/games/kartpad-v0.7.2"), "v0.7.2", {})) \
                as source, \
                mock.patch.object(cli, "manifest_for", return_value=(RECIPE, origin)) as recipe, \
                mock.patch.object(cli.tools, "install") as install, redirect_stdout(output):
            self.assertEqual(cli.main(list(argv)), 0)
        return source, recipe, install, output.getvalue()

    def test_without_a_checkout_the_latest_release_recipe_is_used_and_named(self):
        source, recipe, install, text = self.run_tools("repository")
        source.assert_called_once_with("kartpad")
        self.assertEqual(recipe.call_args.args, ("kartpad", Path("/h/games/kartpad-v0.7.2")))
        self.assertEqual(install.call_args.args[0], ["android-ndk", "dotnet"])
        self.assertIn("Recipe: kartpad v0.7.2, its latest release", text)

    def test_a_fallback_to_the_built_in_recipe_is_said_out_loud(self):
        _source, _recipe, _install, text = self.run_tools("catalog")
        self.assertIn("Recipe: PadMint's built-in copy for kartpad", text)

    def test_a_checkout_given_with_repo_is_used_as_is(self):
        source, recipe, _install, text = self.run_tools("repository", ("tools", "kartpad", "--repo", "/src/kartpad"))
        source.assert_not_called()
        self.assertEqual(recipe.call_args.args[1], Path("/src/kartpad").resolve())
        self.assertIn("Recipe: your checkout", text)


if __name__ == "__main__":
    unittest.main()
