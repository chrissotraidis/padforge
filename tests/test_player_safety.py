from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock

from padmint import cli, tools


class PlayerSafetyTests(unittest.TestCase):
    def test_jobs_follow_cores_and_memory(self):
        gb = 1 << 30
        self.assertEqual(cli.default_jobs(cores=8, memory=8 * gb), 5)
        self.assertEqual(cli.default_jobs(cores=4, memory=32 * gb), 4)
        self.assertEqual(cli.default_jobs(cores=64, memory=256 * gb), 16)
        self.assertEqual(cli.default_jobs(cores=2, memory=1 * gb), 1)
        self.assertEqual(cli.default_jobs(cores=12, memory=0), 4)  # memory unknown
        self.assertGreaterEqual(cli.default_jobs(), 1)

    def test_free_space_is_checked_on_the_nearest_existing_folder(self):
        with tempfile.TemporaryDirectory() as folder:
            missing = Path(folder) / "not" / "yet"
            cli.check_free_space(missing, needed_gb=0)
            cli.check_free_space(missing, needed_gb=1)
            usage = shutil.disk_usage(folder)
            with self.assertRaisesRegex(ValueError, "GB free"):
                cli.check_free_space(missing, needed_gb=int(usage.free / (1 << 30)) + 2)

    def test_only_kartpad_declares_its_space_need(self):
        self.assertEqual(cli.catalog()["kartpad"]["free_space_gb"], 16)

    def test_certificate_failure_is_explained(self):
        error = OSError("<urlopen error [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed>")
        with mock.patch("urllib.request.urlopen", side_effect=error):
            with self.assertRaisesRegex(RuntimeError, "Install Certificates"):
                tools.open_url("https://example.invalid/tool.zip")
        with mock.patch("urllib.request.urlopen", side_effect=TimeoutError("timed out")):
            with self.assertRaisesRegex(RuntimeError, "internet connection"):
                tools.open_url("https://example.invalid/tool.zip")

    def test_failed_build_shows_the_end_of_its_log(self):
        with tempfile.TemporaryDirectory() as folder:
            log = Path(folder) / "backend.log"
            log.write_text("\n".join(f"line {n}" for n in range(40)) + "\nFailed: disc format error\n")
            with mock.patch("sys.stderr") as stderr:
                cli.print_log_tail(log)
            shown = "".join(call.args[0] for call in stderr.write.call_args_list)
            self.assertIn("Failed: disc format error", shown)
            self.assertNotIn("line 20\n", shown)


if __name__ == "__main__":
    unittest.main()
