import hashlib
import io
import os
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from padmint import tools


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ToolPartsTests(unittest.TestCase):
    """Partial extraction, host-only tools and companion tools (Linux arm64 packs)."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        ndk = self.root / "ndk.zip"
        with zipfile.ZipFile(ndk, "w") as bundle:
            for name in ("ndk/source.properties", "ndk/build/tool.cmake", "ndk/prebuilt/x86_64-only-binary"):
                bundle.writestr(name, name)
        llvm = self.root / "llvm.tar.xz"
        with tarfile.open(llvm, "w:xz") as bundle:
            for name, data in (("llvm/bin/clang-21", b"compiler"), ("llvm/bin/clang-tidy", b"not needed")):
                info = tarfile.TarInfo(name)
                info.size, info.mode = len(data), 0o755
                bundle.addfile(info, io.BytesIO(data))
            link = tarfile.TarInfo("llvm/bin/clang")
            link.type, link.linkname = tarfile.SYMTYPE, "clang-21"
            bundle.addfile(link)
        self.lock = {
            "android-ndk": {"version": "1", "hosts": {
                "arm-host": {"url": ndk.as_uri(), "sha256": digest(ndk), "archive": "zip",
                             "members": ["ndk/source.properties", "ndk/build/"], "with": ["llvm"]},
                "other-host": {"url": ndk.as_uri(), "sha256": digest(ndk), "archive": "zip"}}},
            "llvm": {"version": "21", "only_where_listed": True, "env": {"PADMINT_LLVM_ROOT": "llvm"},
                     "hosts": {"arm-host": {"url": llvm.as_uri(), "sha256": digest(llvm), "archive": "tar.xz",
                                            "members": ["llvm/bin/clang", "llvm/bin/clang-21"]}}}}
        for patch in (mock.patch.object(tools, "lock", return_value=self.lock),
                      mock.patch.dict(os.environ, {"PADMINT_HOME": str(self.root / "home")})):
            patch.start()
            self.addCleanup(patch.stop)

    def test_host_download_brings_its_companion_and_only_listed_members(self):
        tools.install(["android-ndk"], "arm-host", io.StringIO())
        ndk = self.root / "home/tools/android-ndk-1/ndk"
        self.assertTrue((ndk / "build/tool.cmake").is_file())
        self.assertFalse((ndk / "prebuilt").exists())
        llvm = self.root / "home/tools/llvm-21/llvm/bin"
        self.assertEqual((llvm / "clang").read_bytes(), b"compiler")  # the link resolves
        self.assertFalse((llvm / "clang-tidy").exists())
        env = tools.environment(["android-ndk"], "arm-host", {"PATH": ""})
        self.assertEqual(env["PADMINT_LLVM_ROOT"], str(self.root / "home/tools/llvm-21/llvm"))

    def test_host_only_tool_is_skipped_elsewhere(self):
        tools.install(["android-ndk", "llvm"], "other-host", io.StringIO())
        self.assertTrue((self.root / "home/tools/android-ndk-1/ndk/prebuilt").exists())
        self.assertFalse((self.root / "home/tools/llvm-21").exists())

    def test_a_host_may_pin_its_own_version_and_folder(self):
        # Intel Macs get an older LLVM than the tool's version (no 21.x build exists for them).
        llvm = self.lock["llvm"]
        llvm["hosts"]["intel-mac"] = dict(llvm["hosts"]["arm-host"], version="20",
                                          env={"PADMINT_LLVM_ROOT": "llvm/bin/.."})
        self.assertFalse(tools.installed("llvm", "intel-mac"))
        tools.install(["llvm"], "intel-mac", io.StringIO())
        self.assertTrue(tools.installed("llvm", "intel-mac"))
        self.assertTrue((self.root / "home/tools/llvm-20/llvm/bin/clang").is_file())
        self.assertFalse((self.root / "home/tools/llvm-21").exists())
        env = tools.environment(["llvm"], "intel-mac", {"PATH": ""})
        self.assertEqual(env["PADMINT_LLVM_ROOT"], str(self.root / "home/tools/llvm-20/llvm/bin/.."))

    def test_a_changed_lock_entry_installs_again(self):
        tools.install(["llvm"], "arm-host", io.StringIO())
        self.lock["llvm"]["hosts"]["arm-host"]["members"].append("llvm/bin/clang-tidy")
        output = io.StringIO()
        tools.install(["llvm"], "arm-host", output)
        self.assertIn("got  llvm 21", output.getvalue())
        self.assertEqual((self.root / "home/tools/llvm-21/llvm/bin/clang-tidy").read_bytes(), b"not needed")

    def test_a_download_without_a_listed_file_installs_nothing(self):
        self.lock["llvm"]["hosts"]["arm-host"]["members"].append("llvm/bin/ld64.lld")
        with self.assertRaisesRegex(RuntimeError, "no llvm/bin/ld64.lld"):
            tools.install(["llvm"], "arm-host", io.StringIO())
        self.assertFalse((self.root / "home/tools/llvm-21").exists())


if __name__ == "__main__":
    unittest.main()
