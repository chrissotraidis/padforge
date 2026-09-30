"""Games offered to players must say how much free space their first build needs; without it
doctor said "0 GB needed" (GoldenPad: "14 GB free, 0 GB needed") and make's check did nothing."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from padmint import manifest


class FreeSpaceTests(unittest.TestCase):
    def test_a_game_offered_to_players_needs_free_space_gb(self):
        entry = {"schema_version": 1, "id": "somepad", "repo_url": "https://example.invalid/somepad",
                 "player_targets": ["ios"], "manifest": None}
        with tempfile.TemporaryDirectory() as folder, mock.patch.object(manifest, "CATALOG", Path(folder)):
            path = Path(folder) / "somepad.json"
            path.write_text(json.dumps(entry))
            with self.assertRaisesRegex(ValueError, "free_space_gb .*required for games with player_targets"):
                manifest.catalog()
            path.write_text(json.dumps(dict(entry, free_space_gb=6)))
            self.assertEqual(manifest.catalog()["somepad"]["free_space_gb"], 6)
            path.write_text(json.dumps(dict(entry, player_targets=[])))  # not offered: optional
            self.assertNotIn("free_space_gb", manifest.catalog()["somepad"])
        for game, entry in manifest.catalog().items():
            if entry.get("player_targets"):
                self.assertGreaterEqual(entry["free_space_gb"], 3, game)


if __name__ == "__main__":
    unittest.main()
