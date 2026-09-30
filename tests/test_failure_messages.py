"""Failures a player can fix themselves say what happened and what to do."""
import io
import subprocess
import tempfile
import unittest
import urllib.error
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

from padmint import cli, tools


class FailureMessageTests(unittest.TestCase):
    def test_a_blocked_download_names_the_server_and_the_usual_blockers(self):
        error = urllib.error.URLError(ConnectionRefusedError(61, "Connection refused"))
        message = tools.download_problem("https://cdn.example.net/pack.zip", error)
        self.assertIn("could not reach cdn.example.net", message)
        self.assertIn("VPN, a firewall or an antivirus web filter blocks cdn.example.net", message)
        self.assertIn("finished downloads are kept", message)

    def test_a_failed_source_download_is_explained_without_a_traceback(self):
        with mock.patch.object(cli, "catalog", return_value={"game": {"repo_url": "https://github.com/x/game"}}), \
                mock.patch.object(cli, "git_program", return_value="git"), \
                mock.patch.object(cli.subprocess, "run", side_effect=subprocess.CalledProcessError(128, "git")):
            with self.assertRaises(ValueError) as caught:
                cli.get_game("game", Path(tempfile.mkdtemp()) / "src", "v1")
        self.assertIn("could not download game's source from github.com", str(caught.exception))
        self.assertIn("code 128", str(caught.exception))

    def test_likely_causes(self):
        cases = {
            "OSError: [Errno 28] No space left on device": "the disk filled up",
            "urllib.error.URLError: <urlopen error [SSL: CERTIFICATE_VERIFY_FAILED]>": "certificate check",
            "Downloading https://cdn.update.rwfc.net/RetroRewind/pack.zip\n"
            "urllib.error.URLError: <urlopen error [Errno -3] Temporary failure in name resolution>":
                "a download from cdn.update.rwfc.net was blocked or failed",
            "curl: (6) Could not resolve host: example.org": "a download from a download server",
        }
        for log, expected in cases.items():
            self.assertIn(expected, cli.likely_cause(log.splitlines()), log)
        self.assertIsNone(cli.likely_cause(["error: undefined symbol: foo"]))

    def test_the_failure_summary_ends_with_the_likely_cause(self):
        with tempfile.TemporaryDirectory() as folder:
            log = Path(folder) / "backend.log"
            log.write_text("fetching https://nas.play.rwfc.net/x\nConnection reset by peer\n")
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                cli.print_log_tail(log)
        self.assertIn("Likely cause: a download from nas.play.rwfc.net was blocked or failed", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
