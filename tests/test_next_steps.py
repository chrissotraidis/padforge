"""After a build, the player sees what to do with the file, in steps."""
import io
import unittest
from pathlib import Path
from unittest import mock

from padmint import cli
from padmint.manifest import catalog

ENTRY = {"id": "game", "repo_url": "https://github.com/example/game", "player_targets": ["android"],
         "player_next": {"android": {"steps": ["Copy {file} to the phone.", "Open Game and pick {file}."],
                                     "note": "Updates keep it working."}}}


class NextStepsTests(unittest.TestCase):
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
