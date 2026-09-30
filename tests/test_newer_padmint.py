"""A newer game release that uses a tool this PadMint does not know stops with one plain line."""
import copy
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

from padmint import cli
from padmint.manifest import catalog

LINE = ("This version of KartPad needs a newer PadMint (it uses zigtool). Download the latest PadMint "
        "from https://github.com/chrissotraidis/padmint/releases/latest and run it again.")


class NewerPadMintTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.source = Path(self.temporary.name) / "games/kartpad-v9.9.9"
        self.source.mkdir(parents=True)
        recipe = copy.deepcopy(catalog()["kartpad"]["manifest"])
        recipe["targets"]["android"]["tools"].append("zigtool")
        (self.source / "padmint.json").write_text(json.dumps(recipe))
        self.recipe_path = Path(self.temporary.name) / "KartPad-v9.9.9-padmint.json"
        self.recipe_path.write_text(json.dumps(recipe))

    def run_main(self, argv):
        stderr = io.StringIO()
        with mock.patch.object(cli, "release_source", return_value=(self.source, "v9.9.9", {})), \
                mock.patch.object(cli, "latest_release", return_value=("v9.9.9", {self.recipe_path.name: "u"})), \
                mock.patch.object(cli, "published_app", return_value=self.recipe_path), \
                mock.patch.object(cli.tools, "install") as install, redirect_stderr(stderr):
            code = cli.main(argv)
        self.assertEqual(code, 1)
        install.assert_not_called()  # nothing downloaded
        self.assertEqual(stderr.getvalue().strip().splitlines()[-1], LINE)

    def test_make(self):
        disc = Path(self.temporary.name) / "disc.iso"
        disc.write_bytes(b"x")
        self.run_main(["make", "kartpad", "android", "--disc", str(disc), "--out", self.temporary.name])

    def test_tools(self):
        self.run_main(["tools", "kartpad", "--target", "android"])

    def test_doctor_says_so_instead_of_falling_back_to_the_built_in_recipe(self):
        self.run_main(["doctor", "kartpad", "--target", "android"])


if __name__ == "__main__":
    unittest.main()
