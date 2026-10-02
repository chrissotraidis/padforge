"""Exercise the phone bootstrap before Ubuntu is installed, without a device."""
import subprocess
import shutil
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "launchers/padmint-android.sh"


@unittest.skipUnless(shutil.which("sh"), "phone bootstrap requires a Unix shell")
class AndroidBootstrapTests(unittest.TestCase):
    def run_setup(self, modern=False, package_failure=False):
        with tempfile.TemporaryDirectory() as temp:
            prefix = Path(temp) / "com.termux/files/usr"
            # Stop at Ubuntu installation, before any launcher or game is written.
            mocks = """
ls() { return 0; }
wake_lock() { return 0; }
yes() { return 0; }
pkg() {
  printf 'package:%s mirror:%s\\n' "$1" "${TERMUX_PKG_NO_MIRROR_SELECT-unset}"
  return PACKAGE_STATUS
}
proot_distro() {
  if [ "$2" = '--help' ]; then
    HELP_RESULT
  else
    echo ubuntu-install
    return 17
  fi
}
""".replace("PACKAGE_STATUS", "1" if package_failure else "0").replace(
                "HELP_RESULT", "echo --name" if modern else "return 1"
            )
            # POSIX function names cannot contain executable-name hyphens.
            script = SCRIPT.read_text().replace("termux-wake-lock", "wake_lock").replace(
                "proot-distro", "proot_distro"
            )
            return subprocess.run(
                ["sh"], input=mocks + script, text=True,
                env={"PATH": "/usr/bin:/bin", "PREFIX": str(prefix)},
                capture_output=True, timeout=10,
            )

    def test_both_package_calls_keep_configured_mirror(self):
        result = self.run_setup()
        self.assertEqual(result.returncode, 17, result.stderr)
        self.assertIn("package:update mirror:1", result.stdout)
        self.assertIn("package:install mirror:1", result.stdout)

    def test_current_proot_skips_package_setup(self):
        result = self.run_setup(modern=True)
        self.assertEqual(result.returncode, 17, result.stderr)
        self.assertNotIn("package:", result.stdout)

    def test_package_failure_stops_before_install(self):
        result = self.run_setup(package_failure=True)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertNotIn("package:install", result.stdout)
        self.assertNotIn("ubuntu-install", result.stdout)


if __name__ == "__main__":
    unittest.main()
