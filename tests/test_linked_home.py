import argparse
import os
import tempfile
import unittest
from pathlib import Path

from padmint import cli


@unittest.skipIf(os.name == "nt", "symbolic links need extra rights on Windows")
class LinkedHomeTests(unittest.TestCase):
    def test_game_checkout_reached_through_a_link_can_build(self):
        with tempfile.TemporaryDirectory() as temporary:
            real = Path(temporary).resolve() / "real-home"
            (real / "games/game").mkdir(parents=True)
            link = Path(temporary).resolve() / "linked-home"
            link.symlink_to(real, target_is_directory=True)
            repo = link / "games/game"
            root = cli.workspace_root(argparse.Namespace(workspace_root=None), repo)
            self.assertEqual(root, real / "games/game/build/padmint")
            with self.assertRaisesRegex(ValueError, "below the backend"):
                cli.workspace_root(argparse.Namespace(workspace_root=link / "elsewhere"), repo)


if __name__ == "__main__":
    unittest.main()
