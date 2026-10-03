import io
import unittest
from unittest import mock

from padmint import cli


class Page(io.BytesIO):
    def __init__(self, url, body=b""):
        super().__init__(body)
        self.url = url

    def geturl(self):
        return self.url


class LatestReleaseTests(unittest.TestCase):
    def test_uses_release_pages_not_the_api(self):
        sums = b"aa  Game-v1.2.3-ios-unsigned.ipa\nbb *Game-v1.2.3-padmint.json\n"
        pages = {
            "https://github.com/x/game/releases/latest": Page("https://github.com/x/game/releases/tag/v1.2.3"),
            "https://github.com/x/game/releases/download/v1.2.3/SHA256SUMS": Page("", sums),
        }
        with mock.patch.object(cli.tools, "open_url", side_effect=lambda url: pages[url]) as opened:
            tag, assets = cli.latest_release("https://github.com/x/game")
        self.assertEqual(tag, "v1.2.3")
        self.assertEqual(assets["Game-v1.2.3-ios-unsigned.ipa"],
                         "https://github.com/x/game/releases/download/v1.2.3/Game-v1.2.3-ios-unsigned.ipa")
        self.assertIn("Game-v1.2.3-padmint.json", assets)
        self.assertIn("SHA256SUMS", assets)
        self.assertFalse(any("api.github.com" in call.args[0] for call in opened.call_args_list))

    def test_a_latest_release_without_a_recipe_falls_back_to_the_newest_with_one(self):
        # BlueWake's latest release can be its ready-to-play Windows download, with no PadMint recipe.
        listing = (b'<a href="/x/game/releases/tag/v0.4.0">v0.4.0</a>'
                   b'<a href="/x/game/releases/tag/v0.4.0">again</a>'
                   b'<a href="/x/game/releases/tag/v0.1.0">v0.1.0</a>')
        pages = {
            "https://github.com/x/game/releases/latest": Page("https://github.com/x/game/releases/tag/v0.4.0"),
            "https://github.com/x/game/releases/download/v0.4.0/SHA256SUMS": Page("", b"aa  Game-v0.4.0-windows.zip\n"),
            "https://github.com/x/game/releases": Page("", listing),
            "https://github.com/x/game/releases/download/v0.1.0/SHA256SUMS":
                Page("", b"bb  Game-v0.1.0-ios-unsigned.ipa\ncc  Game-v0.1.0-padmint.json\n"),
        }
        with mock.patch.object(cli.tools, "open_url", side_effect=lambda url: pages[url]):
            tag, assets = cli.latest_release("https://github.com/x/game")
        self.assertEqual(tag, "v0.1.0")
        self.assertIn("Game-v0.1.0-ios-unsigned.ipa", assets)

    def test_without_a_readable_releases_page_the_latest_is_kept(self):
        pages = {
            "https://github.com/x/game/releases/latest": Page("https://github.com/x/game/releases/tag/v2"),
            "https://github.com/x/game/releases/download/v2/SHA256SUMS": Page("", b"aa  Game-v2-windows.zip\n"),
        }

        def opened(url):
            if url not in pages:
                raise RuntimeError("offline")
            return pages[url]
        with mock.patch.object(cli.tools, "open_url", side_effect=opened):
            tag, assets = cli.latest_release("https://github.com/x/game")
        self.assertEqual(tag, "v2")
        self.assertIn("Game-v2-windows.zip", assets)

    def test_no_release_yet_is_a_plain_error(self):
        page = Page("https://github.com/x/game/releases")
        with mock.patch.object(cli.tools, "open_url", return_value=page):
            with self.assertRaisesRegex(ValueError, "no published release"):
                cli.latest_release("https://github.com/x/game")


if __name__ == "__main__":
    unittest.main()
