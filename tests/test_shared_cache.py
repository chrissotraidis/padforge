import os
import unittest
from pathlib import Path
from unittest import mock

from padforge import cli


class SharedCacheTests(unittest.TestCase):
    def test_backends_get_one_cache_folder_for_every_checkout(self):
        with mock.patch.dict(os.environ, {"PADFORGE_HOME": "/players/home"}, clear=False):
            os.environ.pop("PADFORGE_CACHE", None)
            self.assertEqual(Path(cli.backend_env(None)["PADFORGE_CACHE"]), Path("/players/home/cache"))

    def test_a_chosen_cache_folder_is_kept(self):
        with mock.patch.dict(os.environ, {"PADFORGE_CACHE": "/elsewhere"}):
            self.assertEqual(cli.backend_env(None)["PADFORGE_CACHE"], "/elsewhere")


if __name__ == "__main__":
    unittest.main()
