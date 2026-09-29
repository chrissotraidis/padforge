import io
import unittest
from unittest import mock

from padforge import cli


class Page(io.BytesIO):
    def __init__(self, url, body=b""):
        super().__init__(body)
        self.url = url

    def geturl(self):
        return self.url


class LatestReleaseTests(unittest.TestCase):
    def test_uses_release_pages_not_the_api(self):
        sums = b"aa  Game-v1.2.3-ios-unsigned.ipa\nbb *Game-v1.2.3-padforge.json\n"
        pages = {
            "https://github.com/x/game/releases/latest": Page("https://github.com/x/game/releases/tag/v1.2.3"),
            "https://github.com/x/game/releases/download/v1.2.3/SHA256SUMS": Page("", sums),
        }
        with mock.patch.object(cli.tools, "open_url", side_effect=lambda url: pages[url]) as opened:
            tag, assets = cli.latest_release("https://github.com/x/game")
        self.assertEqual(tag, "v1.2.3")
        self.assertEqual(assets["Game-v1.2.3-ios-unsigned.ipa"],
                         "https://github.com/x/game/releases/download/v1.2.3/Game-v1.2.3-ios-unsigned.ipa")
        self.assertIn("Game-v1.2.3-padforge.json", assets)
        self.assertIn("SHA256SUMS", assets)
        self.assertFalse(any("api.github.com" in call.args[0] for call in opened.call_args_list))

    def test_no_release_yet_is_a_plain_error(self):
        page = Page("https://github.com/x/game/releases")
        with mock.patch.object(cli.tools, "open_url", return_value=page):
            with self.assertRaisesRegex(ValueError, "no published release"):
                cli.latest_release("https://github.com/x/game")


if __name__ == "__main__":
    unittest.main()
