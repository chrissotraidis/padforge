import hashlib
import io
import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from padmint import tools


class ToolsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        archive = self.root / "tool.zip"
        with zipfile.ZipFile(archive, "w") as bundle:
            info = zipfile.ZipInfo("tool-1/bin/tool")
            info.external_attr = 0o755 << 16
            bundle.writestr(info, "#!/bin/sh\n")
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        self.lock = {"tool": {"version": "1", "env": {"TOOL_ROOT": "tool-1"}, "hosts": {
            "test-host": {"url": archive.as_uri(), "sha256": digest, "archive": "zip",
                          "bin": ["tool-1/bin"]}}}}
        self.patches = [mock.patch.object(tools, "lock", return_value=self.lock),
                        mock.patch.dict(os.environ, {"PADMINT_HOME": str(self.root / "home")})]
        for patch in self.patches:
            patch.start()

    def tearDown(self):
        for patch in self.patches:
            patch.stop()
        self.temporary.cleanup()

    def test_install_checks_digest_and_environment_puts_tool_first(self):
        tools.install(["tool"], "test-host", io.StringIO())
        folder = tools.tools_root() / "tool-1"
        self.assertTrue((folder / "tool-1/bin/tool").is_file())
        if os.name != "nt":
            self.assertTrue(os.access(folder / "tool-1/bin/tool", os.X_OK))
        env = tools.environment(["tool"], "test-host", {"PATH": "/usr/bin"})
        self.assertEqual(env["PATH"].split(os.pathsep)[0], str(folder / "tool-1/bin"))
        self.assertEqual(env["TOOL_ROOT"], str(folder / "tool-1"))
        output = io.StringIO()
        tools.install(["tool"], "test-host", output)  # second run keeps the install
        self.assertIn("ok   tool 1", output.getvalue())

    def test_fixed_settings_reach_the_build_environment(self):
        self.lock["tool"]["set"] = {"DOTNET_SYSTEM_GLOBALIZATION_INVARIANT": "1"}
        tools.install(["tool"], "test-host", io.StringIO())
        env = tools.environment(["tool"], "test-host", {"PATH": "/usr/bin"})
        self.assertEqual(env["DOTNET_SYSTEM_GLOBALIZATION_INVARIANT"], "1")

    def test_digest_mismatch_installs_nothing(self):
        self.lock["tool"]["hosts"]["test-host"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(RuntimeError, "mismatch"):
            tools.install(["tool"], "test-host", io.StringIO())
        self.assertFalse((tools.tools_root() / "tool-1/.padmint-installed").exists())

    def test_links_in_zip_archives_become_links(self):
        archive = self.root / "linked.zip"
        with zipfile.ZipFile(archive, "w") as bundle:
            real = zipfile.ZipInfo("t/bin/clang-21")
            real.external_attr = 0o755 << 16
            bundle.writestr(real, "#!/bin/sh\necho real\n")
            link = zipfile.ZipInfo("t/bin/clang")
            link.external_attr = (0o120777) << 16
            bundle.writestr(link, "clang-21")
        folder = self.root / "out"
        tools._extract_zip(archive, folder)
        self.assertEqual((folder / "t/bin/clang").read_text(), "#!/bin/sh\necho real\n")
        if os.name != "nt":
            self.assertTrue((folder / "t/bin/clang").is_symlink())

    def test_links_may_not_leave_the_tool_folder(self):
        archive = self.root / "escape.zip"
        with zipfile.ZipFile(archive, "w") as bundle:
            link = zipfile.ZipInfo("t/evil")
            link.external_attr = (0o120777) << 16
            bundle.writestr(link, "../../etc/passwd")
        with self.assertRaisesRegex(RuntimeError, "leaves the tool folder"):
            tools._extract_zip(archive, self.root / "out2")

    def test_missing_system_git_says_how_to_install_it(self):
        self.lock["git"] = {"version": "2", "hosts": {}}
        with mock.patch.object(tools.shutil, "which", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "package manager"):
                tools.install(["git"], "linux-x86_64", io.StringIO())

    def test_lock_pins_every_download_with_a_publisher_digest(self):
        lock = json.loads(tools.LOCK.read_text())["tools"]
        for name, tool in lock.items():
            for host, entry in tool["hosts"].items():
                with self.subTest(tool=name, host=host):
                    self.assertTrue(entry["url"].startswith("https://"))
                    self.assertTrue(any(key in entry for key in tools.DIGESTS))


if __name__ == "__main__":
    unittest.main()
