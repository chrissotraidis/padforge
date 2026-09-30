import importlib.util
import shutil
import stat
import subprocess
import tempfile
import unittest
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


if __name__ == "__main__":
    unittest.main()
