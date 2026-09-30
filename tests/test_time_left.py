"""Time left per stage comes from the newest completed build of the same game and target."""
import json
import os
import tempfile
import unittest
from pathlib import Path

from padmint import cli


def run(root, name, game, status, stages, end, age):
    folder = Path(root) / "key" / "runs" / name
    folder.mkdir(parents=True)
    record = folder / "record.json"
    record.write_text(json.dumps({"game": game, "target": "android", "status": status}))
    lines = [{"event": "backend_event", "build_elapsed_seconds": seconds,
              "backend": {"event": "stage_started", "stage": stage}} for stage, seconds in stages]
    lines.append({"event": "build_" + status, "build_elapsed_seconds": end})
    (folder / "progress.jsonl").write_text("".join(json.dumps(line) + "\n" for line in lines))
    os.utime(record, (age, age))


class TimeLeftTests(unittest.TestCase):
    def test_the_newest_completed_build_of_the_same_game_and_target_is_used(self):
        with tempfile.TemporaryDirectory() as root:
            run(root, "old", "kartpad", "completed", [("translate", 0), ("package", 600)], 900, 1000)
            run(root, "new", "kartpad", "completed", [("translate", 0), ("package", 300)], 480, 2000)
            run(root, "failed", "kartpad", "failed", [("translate", 0)], 5, 3000)
            run(root, "other", "bluewake", "completed", [("translate", 0)], 60, 4000)
            self.assertEqual(cli.previous_timings([root], "kartpad", "android"),
                             {"translate": 480, "package": 180})
            self.assertEqual(cli.previous_timings([root], "kartpad", "ios"), {})

    def test_a_first_build_shows_nothing(self):
        with tempfile.TemporaryDirectory() as root:
            self.assertEqual(cli.previous_timings([root, Path(root) / "missing"], "kartpad", "android"), {})

    def test_wording(self):
        self.assertEqual(cli.time_left(20), "less than a minute left")
        self.assertEqual(cli.time_left(70), "about 1 minute left")
        self.assertEqual(cli.time_left(14.5 * 60), "about 14 minutes left")


if __name__ == "__main__":
    unittest.main()
