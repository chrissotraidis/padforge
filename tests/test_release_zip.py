import contextlib
import hashlib
import importlib.util
import io
import shutil
import stat
import subprocess
import tempfile
import unittest
from unittest import mock
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("package_release", ROOT / "scripts/package-release.py")
package_release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(package_release)


class ReleaseZipTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.zip = self.root / "PadMint-macos.zip"
        package_release.make_zip(self.zip, "PadMint-vX", ROOT / "launchers/PadMint.command")

    def test_launcher_is_a_regular_executable_file(self):
        with zipfile.ZipFile(self.zip) as bundle:
            modes = {info.filename: info.external_attr >> 16 for info in bundle.infolist()}
        launcher = modes["PadMint-vX/PadMint.command"]
        self.assertTrue(stat.S_ISREG(launcher))
        self.assertEqual(stat.S_IMODE(launcher), 0o755)
        self.assertTrue(all(stat.S_ISREG(mode) for mode in modes.values()))
        self.assertEqual(stat.S_IMODE(modes["PadMint-vX/README.md"]), 0o644)

    @unittest.skipUnless(shutil.which("ditto"), "macOS only: ditto is what Finder uses to unzip")
    def test_finder_style_unzip_keeps_the_launcher_executable(self):
        out = self.root / "unzipped"
        subprocess.run(["ditto", "-x", "-k", str(self.zip), str(out)], check=True)
        mode = (out / "PadMint-vX/PadMint.command").stat().st_mode
        self.assertTrue(mode & stat.S_IXUSR)


class ReleaseChecksumTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()

    def package(self):
        # Package only repository files; no downloaded Python or private input.
        with mock.patch.object(package_release.sys, "argv", ["package-release.py", str(self.root)]), \
                mock.patch.object(package_release, "windows_python", return_value=None), \
                mock.patch.object(package_release.gate, "audit", return_value=0) as audit, \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(package_release.main(), 0)
        paths = [self.root / f"PadMint-v{package_release.__version__}-{host}.zip"
                 for host in ("windows", "macos", "linux")]
        audit.assert_called_once_with(paths, None)
        return paths

    def assert_manifest(self, paths):
        raw = (self.root / "SHA256SUMS").read_bytes()
        expected = "".join(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n"
                           for path in paths).encode("utf-8")
        self.assertEqual(raw, expected)
        self.assertNotIn(b"\r", raw)
        self.assertEqual(raw.count(b"\n"), 3)
        self.assertTrue(raw.endswith(b"\n"))

    def test_checksum_manifest_has_exact_lf_bytes_and_all_zip_hashes(self):
        self.assert_manifest(self.package())

    def test_windows_text_newline_translation_cannot_change_manifest(self):
        def windows_write_text(path, text, *args, **kwargs):
            return path.write_bytes(text.replace("\n", "\r\n").encode("utf-8"))

        # Reproduce Windows text-mode translation even when running on macOS.
        with mock.patch.object(Path, "write_text", windows_write_text):
            self.assert_manifest(self.package())


if __name__ == "__main__":
    unittest.main()
