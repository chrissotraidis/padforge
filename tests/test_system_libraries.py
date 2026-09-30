"""A system library a downloaded tool needs is checked before anything is downloaded."""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from padmint import tools

LOCK = {"android-ndk": {"version": "29", "hosts": {"linux-arm64": {"with": ["llvm"]}, "linux-x86_64": {}}},
        "llvm": {"version": "21", "only_where_listed": True, "hosts": {"linux-arm64": {}}}}


class SystemLibraryTests(unittest.TestCase):
    def missing(self, host, loadable, which=None, only_new=False):
        with mock.patch.object(tools, "lock", return_value=LOCK), \
                mock.patch.object(tools, "_loadable", side_effect=lambda lib: lib in loadable), \
                mock.patch.object(tools.shutil, "which", side_effect=lambda cmd: cmd if cmd == which else None), \
                mock.patch.object(tools, "_only_new_libxml2", return_value=only_new):
            return tools.missing_system_library(["android-ndk"], host)

    def test_llvm_on_linux_arm64_needs_libxml2_found_through_the_ndk(self):
        self.assertIsNone(self.missing("linux-arm64", {"libxml2.so.2"}))
        library, fix = self.missing("linux-arm64", set(), which="apt-get")
        self.assertEqual(library, "libxml2.so.2")
        self.assertIn("sudo apt install libxml2", fix)
        self.assertIn("Nothing has been downloaded yet", fix)
        self.assertIn("sudo dnf install libxml2", self.missing("linux-arm64", set(), which="dnf")[1])

    def test_other_hosts_need_nothing(self):
        self.assertIsNone(self.missing("linux-x86_64", set(), which="apt-get"))

    def test_only_the_new_libxml2_is_explained_instead_of_a_useless_install(self):
        for loadable, only_new in (({"libxml2.so.16"}, False), (set(), True)):
            fix = self.missing("linux-arm64", loadable, which="apt-get", only_new=only_new)[1]
            self.assertIn("only has the newer libxml2.so.16", fix)
            self.assertNotIn("sudo apt install", fix)

    def test_ubuntu_25_10_and_later_are_recognized(self):
        with tempfile.TemporaryDirectory() as folder:
            release = Path(folder) / "os-release"
            for text, expected in (('ID=ubuntu\nVERSION_ID="26.04"\n', True),
                                   ('ID=ubuntu\nVERSION_ID="25.10"\n', True),
                                   ('ID=ubuntu\nVERSION_ID="25.04"\n', False),
                                   ('ID=debian\nVERSION_ID="13"\n', False)):
                release.write_text(text)
                self.assertEqual(tools._only_new_libxml2(release), expected, text)


if __name__ == "__main__":
    unittest.main()
