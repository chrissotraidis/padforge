"""The PadMint window: token and host checks, what the page offers, and how a build reads."""
import json
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock
from http.server import ThreadingHTTPServer

from padmint import cli
from padmint.say import phrase
from padmint.ui import Builds, make_handler

GAMES = [("kartpad", "KartPad", ["android"])]


class FinishedProcess:
    def __init__(self, code):
        self.code = code

    def poll(self):
        return self.code


class WindowTests(unittest.TestCase):
    def setUp(self):
        self.builds = Builds()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler("secret-token", self.builds))
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        patcher = mock.patch.object(cli, "player_games", return_value=GAMES)
        patcher.start()
        self.addCleanup(patcher.stop)

    def request(self, path, body=None, headers=None):
        data = None if body is None else json.dumps(body).encode()
        request = urllib.request.Request(self.base + path, data=data, headers=headers or {},
                                         method="GET" if body is None else "POST")
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, response.read()

    def test_token_and_local_host_are_required(self):
        for headers in ({}, {"X-PadMint-Token": "secret-token", "Host": "attacker.example"}):
            with self.assertRaises(urllib.error.HTTPError) as context:
                self.request("/api/player", headers=headers)
            self.assertEqual(context.exception.code, 403)
        status, body = self.request("/api/player?lang=es", headers={"X-PadMint-Token": "secret-token"})
        data = json.loads(body)
        self.assertEqual(status, 200)
        self.assertEqual([game["id"] for game in data["games"]], ["kartpad"])
        self.assertEqual(data["games"][0]["platforms"][0]["label"], "Teléfono o tableta Android")
        self.assertEqual(data["text"]["make"], "Crear mi copia")
        devil = next(app for app in data["downloads"] if app["id"] == "deviltouch")
        self.assertTrue(devil["intro"].startswith("No hace falta crear DevilTouch"))
        self.assertTrue(devil["steps"][0].startswith("Descarga la IPA de DevilTouch desde https://"))
        self.assertIn("DIABDAT.MPQ", devil["steps"][-1])
        self.assertTrue(devil["steps"][-1].startswith("Abre DevilTouch"))

    def test_page_carries_its_data_safely(self):
        _status, body = self.request("/?token=secret-token&lang=pt")
        page = body.decode()
        self.assertIn('"lang": "pt"', page)
        self.assertNotIn("__DATA__", page)
        self.assertNotIn("</script>", page.split("const T=")[1].split("\n")[0])

    def test_only_offered_games_and_devices_can_be_made(self):
        with mock.patch.object(Builds, "start") as start:
            with self.assertRaises(urllib.error.HTTPError) as context:
                self.request("/api/make", {"game": "kartpad", "platform": "ios"},
                             {"X-PadMint-Token": "secret-token"})
        self.assertEqual(context.exception.code, 400)
        start.assert_not_called()

    def test_build_output_becomes_steps_and_next_steps_in_the_players_language(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            built = folder / "KartPad-v0.7.4-android-personal.so"
            built.write_bytes(b"x")
            (folder / "result.json").write_text(json.dumps({"file": str(built)}))
            self.builds.log = folder / "output.log"
            self.builds.log.write_text(phrase("step_tools", "es") + "\n" + phrase("step_build", "es", jobs=4)
                                       + "\n[12s] backend_event: translate stage_started\n"
                                       + "[27s] build_progress: running; see backend.log\n", "utf-8")
            self.builds.job = {"game": "kartpad", "platform": "android", "lang": "es", "folder": folder,
                               "started": time.time(), "result": None}
            self.builds.process = FinishedProcess(None)
            running = self.builds.status()
            self.assertEqual((running["state"], running["step"]), ("running", "build"))
            self.assertIn("translate stage_started", running["now"])
            self.builds.process = FinishedProcess(0)
            done = self.builds.status()
        self.assertEqual(done["state"], "done")
        self.assertEqual(done["result"]["file"], str(built))
        self.assertTrue(any(built.name in step for step in done["result"]["steps"]))
        self.assertIn("no lo compartas", done["result"]["private"])

    def test_cancel_and_failure_are_told_apart(self):
        self.builds.job = {"game": "kartpad", "platform": "android", "lang": "en",
                           "folder": Path(tempfile.gettempdir()), "started": time.time(), "result": None}
        self.builds.log = Path(tempfile.gettempdir()) / "padmint-window-test-missing.log"
        for code, state in ((130, "cancelled"), (1, "failed")):
            self.builds.process = FinishedProcess(code)
            self.assertEqual(self.builds.status()["state"], state)

    def test_the_app_or_a_zip_is_refused_before_any_build(self):
        # kartpad#386: a player gave PadMint the KartPad app instead of the disc image.
        from padmint import ui
        with tempfile.TemporaryDirectory() as folder:
            app = Path(folder) / "KartPad-v0.7.4-android.apk"
            app.write_bytes(b"PK\x03\x04")
            with mock.patch.object(cli, "game_from_file") as read:
                problem = ui.check_file("kartpad", str(app), "es")
            read.assert_not_called()
        self.assertIn("KartPad-v0.7.4-android.apk no es un archivo del juego", problem)
        self.assertIn("ISO", problem)
        self.assertIn("WBFS", problem)


class OpenWindowTests(unittest.TestCase):
    def test_double_clicked_padmint_opens_the_window_but_scripts_get_the_terminal(self):
        tty = mock.Mock(isatty=lambda: True)
        with mock.patch.object(cli.sys, "stdin", tty), mock.patch.object(cli, "on_android", return_value=False), \
                mock.patch.object(cli.sys, "platform", "win32"):
            self.assertTrue(cli.wants_window({}))
            self.assertFalse(cli.wants_window({"PADMINT_TERMINAL": "1"}))
        with mock.patch.object(cli.sys, "stdin", tty), mock.patch.object(cli, "on_android", return_value=False), \
                mock.patch.object(cli.sys, "platform", "linux"):
            self.assertFalse(cli.wants_window({}))
            self.assertTrue(cli.wants_window({"DISPLAY": ":0"}))
        # A phone opens the window in its browser through Termux's termux-open-url, when it has one.
        with tempfile.NamedTemporaryFile() as opener, mock.patch.object(cli.sys, "stdin", tty), \
                mock.patch.object(cli, "on_android", return_value=True):
            with mock.patch.object(cli, "TERMUX_OPEN_URL", Path(opener.name)):
                self.assertTrue(cli.wants_window({}))
            with mock.patch.object(cli, "TERMUX_OPEN_URL", Path(opener.name + ".missing")):
                self.assertFalse(cli.wants_window({}))
        with mock.patch.object(cli.sys, "stdin", mock.Mock(isatty=lambda: False)), \
                mock.patch.object(cli, "on_android", return_value=False):
            self.assertFalse(cli.wants_window({"DISPLAY": ":0"}))

    def test_make_tells_the_window_where_the_copy_is(self):
        with tempfile.TemporaryDirectory() as folder:
            result_file = Path(folder) / "result.json"
            copy = Path(folder) / "KartPad-v1-android-personal.so"

            def fake_make(*args):
                args[-1].append(copy)
                return 0
            with mock.patch.object(cli, "make", side_effect=fake_make):
                code = cli.main(["make", "kartpad", "android", "--out", folder, "--result-file", str(result_file)])
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(result_file.read_text()), {"file": str(copy)})


if __name__ == "__main__":
    unittest.main()
