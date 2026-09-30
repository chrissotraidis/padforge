"""The player's file names the game when exactly one offered game lists its disc ID."""
import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from padmint import cli

CATALOG = {
    "kartpad": {"id": "kartpad", "repo_url": "https://github.com/example/kartpad", "game_ids": ["RMCP01"],
                "player_targets": ["android", "ios"], "manifest": {"name": "KartPad"}},
    "romgame": {"id": "romgame", "repo_url": "https://github.com/example/romgame", "player_targets": ["ios"],
                "player_game_file": "in-app", "manifest": {"name": "RomGame"}},
}


class GameFromFileTests(unittest.TestCase):
    def run_start(self, answers, read_disc):
        stream = io.StringIO()
        replies = iter(answers)
        with mock.patch.object(cli, "catalog", return_value=CATALOG), \
                mock.patch.object(cli, "host_id", return_value="macos-arm64"), \
                mock.patch.object(cli.tools, "install"), \
                mock.patch.object(cli.tools, "executable", return_value="nodtool"), \
                mock.patch.object(cli.game_file, "read_disc", side_effect=read_disc), \
                mock.patch.object(cli, "make", return_value=0) as make:
            code = cli.start(lambda _prompt: next(replies), stream)
        return code, make, stream.getvalue()

    def disc(self, folder):
        disc = Path(folder) / "Mario Kart Wii.rvz"
        disc.write_bytes(b"x")
        return disc

    def test_a_kartpad_disc_skips_the_game_menu_and_is_not_asked_for_again(self):
        with tempfile.TemporaryDirectory() as folder:
            disc = self.disc(folder)
            code, make, text = self.run_start([str(disc), "2"], lambda *_: ("MARIO KART Wii", "RMCP01", 0))
        self.assertEqual(code, 0)
        self.assertEqual(make.call_args.args[:3], ("kartpad", "ios", disc.resolve()))
        self.assertIn("Reading your file…\nGame: KartPad (from your file, RMCP01)", text)
        self.assertNotIn("1. KartPad", text)

    def test_another_disc_shows_the_menu_but_keeps_the_file(self):
        with tempfile.TemporaryDirectory() as folder:
            disc = self.disc(folder)
            _code, make, text = self.run_start([str(disc), "1", "1"], lambda *_: ("OTHER", "RMCE01", 0))
        self.assertEqual(make.call_args.args[:3], ("kartpad", "android", disc.resolve()))
        self.assertIn("1. KartPad", text)

    def test_an_unreadable_file_falls_back_to_the_menu(self):
        def unreadable(*_):
            raise ValueError("not a disc")
        with tempfile.TemporaryDirectory() as folder:
            disc = self.disc(folder)
            _code, make, text = self.run_start([str(disc), "1", "1"], unreadable)
        self.assertEqual(make.call_args.args[0], "kartpad")
        self.assertIn("1. KartPad", text)

    def test_no_file_asks_as_before(self):
        with tempfile.TemporaryDirectory() as folder:
            disc = self.disc(folder)
            _code, make, _text = self.run_start(["", "1", "1", str(disc)], lambda *_: ("", "RMCP01", 0))
        self.assertEqual(make.call_args.args[:3], ("kartpad", "android", disc.resolve()))

    def test_an_in_app_game_ignores_a_dropped_file(self):
        with tempfile.TemporaryDirectory() as folder:
            disc = self.disc(folder)
            _code, make, _text = self.run_start([str(disc), "2"], lambda *_: ("", "NXXX01", 0))
        self.assertEqual(make.call_args.args[:3], ("romgame", "ios", None))

    def test_an_icloud_only_file_is_explained_at_once_and_never_read(self):
        with tempfile.TemporaryDirectory() as folder:
            disc = self.disc(folder)
            with mock.patch.object(cli.game_file, "cloud_only", side_effect=[True, False, False]):
                _code, make, text = self.run_start([str(disc), str(disc), "1"],
                                                   lambda *_: ("", "RMCP01", 0))
        self.assertIn("is stored only in iCloud", text)
        self.assertIn("Download Now", text)
        self.assertEqual(make.call_args.args[:3], ("kartpad", "android", disc.resolve()))


def z64(code, size=0x40):
    head = bytearray(size)
    head[:4] = b"\x80\x37\x12\x40"
    head[0x3B:0x3F] = code.encode()
    return bytes(head)


def reorder(data, size):
    return b"".join(data[at:at + size][::-1] for at in range(0, len(data), size))


class HeaderIdTests(unittest.TestCase):
    def read(self, data):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "file"
            path.write_bytes(data)
            return cli.game_file.header_id(path)

    def test_an_n64_rom_in_every_byte_order(self):
        rom = z64("NGEE", 0x1000)
        self.assertEqual(self.read(rom), "NGEE")            # .z64
        self.assertEqual(self.read(reorder(rom, 2)), "NGEE")  # .v64
        self.assertEqual(self.read(reorder(rom, 4)), "NGEE")  # .n64

    def test_raw_gamecube_and_wii_disc_images(self):
        gamecube = bytearray(0x440)
        gamecube[:6], gamecube[0x1C:0x20] = b"GALE01", b"\xc2\x33\x9f\x3d"
        wii = bytearray(0x440)
        wii[:6], wii[0x18:0x1C] = b"RMCP01", b"\x5d\x1c\x9e\xa3"
        self.assertEqual(self.read(bytes(gamecube)), "GALE01")
        self.assertEqual(self.read(bytes(wii)), "RMCP01")

    def test_anything_else_is_not_guessed(self):
        self.assertIsNone(self.read(b"x"))
        self.assertIsNone(self.read(bytes(0x1000)))
        self.assertIsNone(self.read(z64("\x00\x00\x00\x00")))


ROM_CATALOG = {
    "goldenpad": {"id": "goldenpad", "repo_url": "https://github.com/example/goldenpad", "game_ids": ["NGEE"],
                  "player_targets": ["ios"], "manifest": {"name": "GoldenPad"}},
    "twina": {"id": "twina", "repo_url": "https://github.com/example/twina", "game_ids": ["NDPE"],
              "player_targets": ["ios"], "manifest": {"name": "TwinA"}},
    "twinb": {"id": "twinb", "repo_url": "https://github.com/example/twinb", "game_ids": ["NDPE"],
              "player_targets": ["ios"], "manifest": {"name": "TwinB"}},
    **CATALOG,
}


class RomFromFileTests(unittest.TestCase):
    def run_start(self, code, answers):
        stream = io.StringIO()
        with tempfile.TemporaryDirectory() as folder:
            rom = Path(folder) / "007 - GoldenEye (USA).z64"
            rom.write_bytes(z64(code, 0x1000))
            replies = iter([str(rom), *answers])
            with mock.patch.object(cli, "catalog", return_value=ROM_CATALOG), \
                    mock.patch.object(cli, "host_id", return_value="macos-arm64"), \
                    mock.patch.object(cli.tools, "install") as install, \
                    mock.patch.object(cli.game_file, "read_disc") as read_disc, \
                    mock.patch.object(cli, "make", return_value=0) as make:
                cli.start(lambda _prompt: next(replies), stream)
            return make.call_args.args[:3], rom.resolve(), install, read_disc, stream.getvalue()

    def test_padmint_7_a_goldeneye_rom_goes_straight_to_goldenpad_without_nodtool(self):
        args, rom, install, read_disc, text = self.run_start("NGEE", [])
        self.assertEqual(args, ("goldenpad", "ios", rom))
        self.assertIn("Game: GoldenPad (from your file, NGEE)", text)
        self.assertNotIn("Reading your file", text)
        self.assertNotIn("1. ", text)
        install.assert_not_called()
        read_disc.assert_not_called()

    def test_a_code_two_games_share_offers_only_those_two(self):
        args, _rom, _install, _read, text = self.run_start("NDPE", ["2"])
        self.assertEqual(args[0], "twinb")
        self.assertIn("Game\n  1. TwinA\n  2. TwinB\nMake it for", text)
        self.assertNotIn("GoldenPad", text)

    def test_an_unknown_rom_shows_every_game(self):
        args, _rom, _install, _read, text = self.run_start("NXXE", ["1"])
        self.assertEqual(args[0], "goldenpad")
        self.assertIn("KartPad", text)
        self.assertIn("TwinB", text)



if __name__ == "__main__":
    unittest.main()
