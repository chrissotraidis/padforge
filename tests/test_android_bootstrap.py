"""Exercise the phone bootstrap before Ubuntu is installed, without a device."""
import subprocess
import shutil
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "launchers/padmint-android.sh"


@unittest.skipUnless(shutil.which("sh"), "phone bootstrap requires a Unix shell")
class AndroidBootstrapTests(unittest.TestCase):
    def run_setup(self, help_text="", package_failure=False, phone=None):
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
    printf '%s\\n' 'HELP_TEXT'
  else
    echo "ubuntu-install $*"
    return 17
  fi
}
""".replace("PACKAGE_STATUS", "1" if package_failure else "0").replace("HELP_TEXT", help_text)
            env = {"PATH": "/usr/bin:/bin", "PREFIX": str(prefix)}
            if phone is None:
                env["PADMINT_SKIP_PHONE_CHECK"] = "1"
            else:
                machine, free_kb = phone
                mocks += f"uname() {{ echo {machine}; }}\ndf() {{ printf 'x\\n/dev/x 1 1 {free_kb} 1% /\\n'; }}\n"
            # POSIX function names cannot contain executable-name hyphens.
            script = SCRIPT.read_text().replace("termux-wake-lock", "wake_lock").replace(
                "proot-distro", "proot_distro"
            )
            return subprocess.run(["sh"], input=mocks + script, text=True, env=env,
                                  capture_output=True, timeout=10)

    def test_proot_distro_5_installs_ubuntu_by_name_without_package_setup(self):
        result = self.run_setup(help_text="  --name NAME")
        self.assertEqual(result.returncode, 17, result.stderr)
        self.assertNotIn("package:", result.stdout)
        self.assertIn("ubuntu-install install --name padmint ubuntu:24.04", result.stdout)
        self.assertIn("PadMint setup stopped while: Ubuntu inside Termux", result.stdout)

    def test_proot_distro_4_is_updated_first_and_still_works(self):
        # A Termux mirror that offers only proot-distro 4.37 (Discord, 3 Oct): no --name.
        result = self.run_setup(help_text="  --override-alias [new alias]")
        self.assertEqual(result.returncode, 17, result.stderr)
        self.assertIn("package:update mirror:1", result.stdout)
        self.assertIn("package:install mirror:1", result.stdout)
        self.assertIn("ubuntu-install install padmint", result.stdout)
        self.assertNotIn("--name", result.stdout)

    def test_a_proot_distro_too_old_for_either_stops_with_what_to_do(self):
        result = self.run_setup()
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertNotIn("ubuntu-install", result.stdout)
        self.assertIn("Install Termux from F-Droid", result.stdout)

    def test_package_failure_stops_before_install(self):
        result = self.run_setup(package_failure=True)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertNotIn("package:install", result.stdout)
        self.assertNotIn("ubuntu-install", result.stdout)
        self.assertIn("Termux could not update its packages", result.stdout)

    def test_phones_that_cannot_build_are_told_before_any_download(self):
        for phone, message in ((("armv7l", 99999999), "needs a 64-bit phone"),
                               (("aarch64", 5 * 1048576), "it has 5 GB")):
            result = self.run_setup(help_text="  --name NAME", phone=phone)
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertIn(message, result.stdout)
            self.assertIn("android-with-a-computer", result.stdout)
            self.assertNotIn("ubuntu-install", result.stdout)
            self.assertNotIn("package:", result.stdout)


if __name__ == "__main__":
    unittest.main()
