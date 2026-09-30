"""A system library a downloaded tool needs is checked before anything is downloaded."""
import io
import os
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

from padmint import cli, tools

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

    def test_the_newer_libxml2_is_enough_and_its_package_is_named_when_missing(self):
        self.assertIsNone(self.missing("linux-arm64", {"libxml2.so.16"}, which="apt-get"))
        fix = self.missing("linux-arm64", set(), which="apt-get", only_new=True)[1]
        self.assertIn("sudo apt install libxml2-16", fix)

    def test_padmint_links_its_own_llvm_to_the_newer_libxml2_and_undoes_it_later(self):
        lock = dict(LOCK, llvm=dict(LOCK["llvm"], env={"PADMINT_LLVM_ROOT": "LLVM-21"}))
        with tempfile.TemporaryDirectory() as folder:
            tool = Path(folder) / "llvm-21"
            system = Path(folder) / "system/libxml2.so.16"
            system.parent.mkdir()
            system.write_text("library")
            with mock.patch.object(tools, "lock", return_value=lock), \
                    mock.patch.object(tools, "_system_path", return_value=system):
                with mock.patch.object(tools, "_loadable", return_value=False):
                    link = tools.link_system_library("llvm", "linux-arm64", tool)
                    self.assertEqual(link, tool / "LLVM-21/lib/libxml2.so.2")
                    self.assertEqual(Path(os.readlink(link)), system)
                    self.assertEqual(tools.link_system_library("llvm", "linux-arm64", tool), link)
                    self.assertIsNone(tools.link_system_library("llvm", "linux-x86_64", tool))
                with mock.patch.object(tools, "_loadable", return_value=True):
                    self.assertIsNone(tools.link_system_library("llvm", "linux-arm64", tool))
                    self.assertFalse(link.is_symlink())

    def test_the_failure_summary_leaves_out_the_harmless_warning(self):
        with tempfile.TemporaryDirectory() as folder:
            log = Path(folder) / "backend.log"
            log.write_text("ld.lld: lib/libxml2.so.2: no version information available (required by ld.lld)\n"
                           "error: the real reason\n")
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                cli.print_log_tail(log)
        self.assertIn("the real reason", stderr.getvalue())
        self.assertNotIn("no version information", stderr.getvalue())

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
