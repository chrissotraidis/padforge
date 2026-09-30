import ntpath
import unittest
from unittest import mock

from padforge import tools


class LongPathTests(unittest.TestCase):
    def windows(self, path):
        with mock.patch.object(tools.os, "name", "nt"), \
                mock.patch.object(tools.os.path, "abspath", ntpath.abspath):
            return tools._long(path)

    def test_windows_paths_get_the_extended_length_prefix(self):
        self.assertEqual(self.windows(r"C:\Users\name\.padforge\tools\ndk.partial"),
                         r"\\?\C:\Users\name\.padforge\tools\ndk.partial")
        self.assertEqual(self.windows(r"\\?\C:\already"), r"\\?\C:\already")
        self.assertEqual(self.windows(r"\\server\share\home"), r"\\?\UNC\server\share\home")

    def test_other_systems_are_unchanged(self):
        with mock.patch.object(tools.os, "name", "posix"):
            self.assertEqual(tools._long("/home/name/.padforge/tools"), "/home/name/.padforge/tools")


if __name__ == "__main__":
    unittest.main()
