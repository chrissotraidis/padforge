"""Local UI: token and host checks, and read-only endpoints."""
import json
import threading
import unittest
import urllib.error
import urllib.request
from unittest import mock
from http.server import ThreadingHTTPServer

from padmint import cli
from padmint.ui import PAGE, Builds, make_handler


class UITests(unittest.TestCase):
    def setUp(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler("secret-token", Builds()))
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def get(self, path, headers=None):
        request = urllib.request.Request(self.base + path, headers=headers or {})
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, response.read()

    def test_token_is_required(self):
        with self.assertRaises(urllib.error.HTTPError) as context:
            self.get("/api/games")
        self.assertEqual(context.exception.code, 403)
        status, body = self.get("/api/games", {"X-PadMint-Token": "secret-token"})
        self.assertEqual(status, 200)
        self.assertIn("kartpad", [game["id"] for game in json.loads(body)])

    def test_foreign_host_header_is_rejected(self):
        with self.assertRaises(urllib.error.HTTPError) as context:
            self.get("/api/games", {"X-PadMint-Token": "secret-token", "Host": "attacker.example"})
        self.assertEqual(context.exception.code, 403)

    def test_page_embeds_token_and_valid_script_strings(self):
        status, body = self.get("/?token=secret-token")
        self.assertEqual(status, 200)
        self.assertIn(b"secret-token", body)
        self.assertIn('join("\\n")', PAGE)

    def test_doctor_runs_through_the_cli(self):
        request = urllib.request.Request(self.base + "/api/doctor", method="POST",
                                         data=json.dumps({"game": "kartpad", "target": "android"}).encode(),
                                         headers={"X-PadMint-Token": "secret-token"})
        with mock.patch.object(cli, "latest_release", side_effect=RuntimeError("offline")), \
                mock.patch.object(cli, "host_id", return_value="windows-x86_64"), \
                mock.patch.object(cli.tools, "missing_system_library", return_value=None):
            with urllib.request.urlopen(request, timeout=60) as response:
                result = json.loads(response.read())
        self.assertIn("recipe: PadMint's built-in copy; could not reach the release", result["output"])
        self.assertIn("android builds on windows-x86_64: experimental", result["output"])
        self.assertNotIn("xcodebuild", result["output"])


if __name__ == "__main__":
    unittest.main()
