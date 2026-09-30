import io
import unittest

from padmint import cli


class ListGamesTests(unittest.TestCase):
    def test_every_game_shows_player_targets_and_repository(self):
        stream = io.StringIO()
        self.assertEqual(cli.list_games(stream), 0)
        rows = {line.split()[0]: line for line in stream.getvalue().splitlines()}
        self.assertEqual(set(rows), set(cli.catalog()))
        self.assertIn("android, ios", rows["kartpad"])
        self.assertIn("https://github.com/chrissotraidis/kartpad", rows["kartpad"])
        self.assertNotIn("planned", stream.getvalue())


if __name__ == "__main__":
    unittest.main()
