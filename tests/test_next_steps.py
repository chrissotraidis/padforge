"""After a build, the player sees what to do with the file, in steps."""
import copy
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from padmint import cli
from padmint import manifest
from padmint.manifest import catalog

ENTRY = {"id": "game", "repo_url": "https://github.com/example/game", "player_targets": ["android"],
         "player_next": {"android": {"steps": ["Copy {file} to the phone.", "Open Game and pick {file}."],
                                     "note": "Updates keep it working."}}}


class NextStepsTests(unittest.TestCase):
    def test_phone_steps_use_the_existing_files_and_actual_output_folder(self):
        entry = catalog()["kartpad"]
        result = Path("/sdcard/Download/My builds/KartPad-v0.7.3-android-personal.so")
        stream = io.StringIO()
        with mock.patch.object(cli, "on_android", return_value=True):
            cli.next_steps(entry, "android", result, stream)
        text = stream.getvalue()
        self.assertIn("already on this phone", text)
        self.assertIn(str(result.parent), text)
        self.assertIn(result.name, text)
        self.assertIn("Import Game next to Mario Kart Wii", text)
        self.assertIn("Game Data & Saves", text)
        self.assertIn("Import from Extracted Game Data Folder", text)
        self.assertIn("KartPad game data", text)
        self.assertNotIn("Copy ", text)
        self.assertNotIn("USB cable", text)

    def test_desktop_kartpad_steps_still_explain_the_transfer(self):
        stream = io.StringIO()
        with mock.patch.object(cli, "on_android", return_value=False):
            cli.next_steps(catalog()["kartpad"], "android", Path("/out/pack.so"), stream)
        text = stream.getvalue()
        self.assertIn("Copy pack.so to the phone or tablet", text)
        self.assertIn("USB cable", text)
        self.assertNotIn("already on this phone", text)

    def test_phone_without_special_steps_keeps_the_existing_instructions(self):
        stream = io.StringIO()
        with mock.patch.object(cli, "on_android", return_value=True):
            cli.next_steps(ENTRY, "android", Path("/out/pack.so"), stream)
        self.assertIn("  1. Copy pack.so to the phone.", stream.getvalue())

    def test_catalog_rejects_malformed_phone_steps(self):
        entry = copy.deepcopy(ENTRY)
        entry["free_space_gb"] = 1
        with tempfile.TemporaryDirectory() as folder, mock.patch.object(manifest, "CATALOG", Path(folder)):
            for instructions in ("not a list", [1], None):
                entry["player_next"]["android"]["phone_steps"] = instructions
                (Path(folder) / "game.json").write_text(json.dumps(entry))
                with self.subTest(instructions=instructions), self.assertRaisesRegex(ValueError, "phone_steps"):
                    catalog()

    def test_steps_name_the_finished_file_and_end_with_the_guide(self):
        stream = io.StringIO()
        cli.next_steps(ENTRY, "android", Path("/out/Game-v1-android-personal.so"), stream)
        text = stream.getvalue()
        self.assertIn("  1. Copy Game-v1-android-personal.so to the phone.", text)
        self.assertIn("  2. Open Game and pick Game-v1-android-personal.so.", text)
        self.assertIn("Updates keep it working.", text)
        self.assertIn("Full guide: https://github.com/example/game#get-game", text)

    def test_without_steps_or_a_file_the_guide_link_is_shown(self):
        for platform, result in (("ios", Path("/out/x.ipa")), ("android", None)):
            stream = io.StringIO()
            cli.next_steps(ENTRY, platform, result, stream)
            self.assertEqual(stream.getvalue(), "Next: https://github.com/example/game#get-game\n")

    def test_start_shows_steps_and_the_file_after_a_build(self):
        stream = io.StringIO()
        result = Path("/out/Game-v1-android-personal.so")

        def make(*_args, results=None, **_kwargs):
            results.append(result)
            return 0

        disc = Path(__file__)
        replies = iter([str(disc), ""])
        with mock.patch.object(cli, "catalog", return_value={"game": ENTRY}), \
                mock.patch.object(cli, "host_id", return_value="linux-x86_64"), \
                mock.patch.object(cli, "make", side_effect=make), \
                mock.patch.object(cli, "reveal") as reveal:
            self.assertEqual(cli.start(lambda _prompt: next(replies), stream), 0)
        reveal.assert_called_once_with(result)
        self.assertIn("What to do next:", stream.getvalue())

    def test_only_kartpad_promises_its_pack_survives_updates(self):
        entries = catalog()
        with_note = sorted(game for game, entry in entries.items()
                           if any(steps.get("note") for steps in (entry.get("player_next") or {}).values()))
        self.assertEqual(with_note, ["kartpad"])
        self.assertIn("{file}", " ".join(entries["kartpad"]["player_next"]["android"]["steps"]))


if __name__ == "__main__":
    unittest.main()
