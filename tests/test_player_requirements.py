"""A recipe can mark programs the player installs themselves (requirements.tools with
"player": true and a note). The player path checks only those, before any download
(padmint#7: GoldenPad needed Homebrew SDL2, found only after minutes of building)."""
import copy
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from padmint import cli
from padmint.manifest import catalog, validate_manifest

SDL2 = {"name": "sdl2-config", "player": True, "note": "Install SDL2: brew install sdl2"}
DEVELOPER = {"name": "rg", "version_args": ["--version"]}


def recipe(*tools):
    data = copy.deepcopy(catalog()["kartpad"]["manifest"])
    data["requirements"] = {"disk_gb": 1, "tools": list(tools)}
    return data


def which_without(*missing):
    return lambda name: None if name in missing else f"/usr/bin/{name}"


class ManifestFieldTests(unittest.TestCase):
    def test_player_is_true_or_false_and_needs_a_note(self):
        validate_manifest(recipe(SDL2, DEVELOPER))
        with self.assertRaisesRegex(ValueError, "player must be true or false"):
            validate_manifest(recipe(dict(SDL2, player="yes")))
        with self.assertRaisesRegex(ValueError, "needs a note"):
            validate_manifest(recipe({"name": "sdl2-config", "player": True}))


class DoctorTests(unittest.TestCase):
    def doctor(self, data, missing):
        stream = io.StringIO()
        with mock.patch.object(cli, "published_recipe", return_value=(data, "game v1 release")), \
                mock.patch.object(cli, "host_id", return_value="linux-arm64"), \
                mock.patch.object(cli.tools, "missing_system_library", return_value=None), \
                mock.patch.object(cli.tools, "installed", return_value=True), \
                mock.patch.object(cli.shutil, "which", side_effect=which_without(*missing)):
            code = cli.doctor("kartpad", "android", stream=stream)
        return stream.getvalue(), code

    def test_the_player_path_checks_only_what_the_player_installs(self):
        text, code = self.doctor(recipe(SDL2, DEVELOPER), missing=("sdl2-config", "rg"))
        self.assertEqual(code, 1)
        self.assertIn("FIX  sdl2-config: Install SDL2: brew install sdl2", text)
        self.assertNotIn("rg", text.replace("recipe", ""))

    def test_installed_is_ok(self):
        text, _code = self.doctor(recipe(SDL2), missing=())
        self.assertIn("ok   sdl2-config: /usr/bin/sdl2-config", text)


class MakeTests(unittest.TestCase):
    def make(self, data, missing):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "home/games/game-v1.2.3"
            source.mkdir(parents=True)
            (source / "version.json").write_text(json.dumps({"version": "1.2.3", "build": 7}))
            with mock.patch.object(cli, "catalog", return_value={"game": {"repo_url": "https://x/game"}}), \
                    mock.patch.object(cli.tools, "tools_root", return_value=root / "home/tools"), \
                    mock.patch.object(cli.tools, "install") as install, \
                    mock.patch.object(cli.tools, "missing_system_library", return_value=None), \
                    mock.patch.object(cli, "latest_release", return_value=("v1.2.3", {})), \
                    mock.patch.object(cli, "source_complete", return_value=True), \
                    mock.patch.object(cli, "manifest_for", return_value=(data, "repository")), \
                    mock.patch.object(cli, "git", return_value="0" * 40), \
                    mock.patch.object(cli.shutil, "which", side_effect=which_without(*missing)), \
                    mock.patch.object(cli, "execute", return_value=1) as execute:
                try:
                    return cli.make("game", "android", None, root / "out"), install, execute
                except ValueError as error:
                    return str(error), install, execute

    def game(self, *tools):
        return {"name": "GoldenPad", "inputs": [{"type": "rom", "when": "in-app"}],
                "requirements": {"tools": list(tools)},
                "targets": {"android": {"steps": [], "tools": ["cmake"]}}}

    def test_a_missing_program_stops_before_any_download_and_says_how_to_install_it(self):
        xdelta = {"name": "xdelta3", "player": True, "note": "Install xdelta: brew install xdelta"}
        result, install, execute = self.make(self.game(SDL2, xdelta, DEVELOPER),
                                             missing=("sdl2-config", "xdelta3", "rg"))
        self.assertEqual(result, "GoldenPad needs these installed first:\n"
                                 "  sdl2-config: Install SDL2: brew install sdl2\n"
                                 "  xdelta3: Install xdelta: brew install xdelta\n"
                                 "Then run PadMint again.")
        install.assert_not_called()
        execute.assert_not_called()

    def test_developer_only_programs_are_not_the_players_business(self):
        _result, install, execute = self.make(self.game(SDL2, DEVELOPER), missing=("rg",))
        install.assert_called_once()
        execute.assert_called_once()


if __name__ == "__main__":
    unittest.main()
