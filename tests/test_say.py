import io
import string
import unittest
from unittest import mock

from padmint import say


def fields(text):
    return {name for _, name, _, _ in string.Formatter().parse(text) if name}


class LanguageTests(unittest.TestCase):
    def test_explicit_choice_wins_then_system_locale(self):
        self.assertEqual(say.language({"PADMINT_LANG": "es", "LANG": "pt_BR.UTF-8"}, windows=False), "es")
        self.assertEqual(say.language({"LANG": "pt_BR.UTF-8"}, windows=False), "pt")
        self.assertEqual(say.language({"LC_ALL": "es_MX.UTF-8", "LANG": "en_US.UTF-8"}, windows=False), "es")
        self.assertEqual(say.language({"LANG": "fr_FR.UTF-8"}, windows=False), "en")
        self.assertEqual(say.language({"LANG": "C"}, windows=False), "en")
        self.assertEqual(say.language({}, windows=False), "en")

    def test_windows_display_language(self):
        with mock.patch.object(say, "_windows_language", return_value="pt"):
            self.assertEqual(say.language({"LANG": "en_US.UTF-8"}, windows=True), "pt")
        with mock.patch.object(say, "_windows_language", return_value=None):
            self.assertEqual(say.language({"LANG": "es_ES.UTF-8"}, windows=True), "es")

    def test_every_message_has_all_languages_with_the_same_fields(self):
        for key, texts in say.MESSAGES.items():
            with self.subTest(key=key):
                self.assertEqual(set(texts), set(say.LANGUAGES))
                self.assertEqual({fields(text) == fields(texts["en"]) for text in texts.values()}, {True})

    def test_console_without_accents_gets_english_instead_of_an_error(self):
        ascii_out = io.TextIOWrapper(io.BytesIO(), encoding="ascii")
        with mock.patch.dict("os.environ", {"PADMINT_LANG": "es"}), mock.patch.object(say.sys, "stdout", ascii_out):
            self.assertEqual(say.t("game"), "Game")
        utf8_out = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
        with mock.patch.dict("os.environ", {"PADMINT_LANG": "es"}), mock.patch.object(say.sys, "stdout", utf8_out):
            self.assertEqual(say.t("game"), "Juego")

    def test_catalog_steps_use_their_translation_when_present(self):
        steps = {"steps": ["Install it."], "translations": {"pt": {"steps": ["Instale."]}}}
        utf8_out = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
        with mock.patch.object(say.sys, "stdout", utf8_out):
            with mock.patch.dict("os.environ", {"PADMINT_LANG": "pt"}):
                self.assertEqual(say.localized(steps, "steps"), ["Instale."])
            with mock.patch.dict("os.environ", {"PADMINT_LANG": "es"}):
                self.assertEqual(say.localized(steps, "steps"), ["Install it."])


if __name__ == "__main__":
    unittest.main()
