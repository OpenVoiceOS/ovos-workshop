"""
Tests for locale directory lookup and language resource resolution.

Covers:
- _get_word() resolves word_connectors.json via get_language_dir()
- _get_dialog() resolves bundled .dialog files via get_language_dir()
- join_word_list() produces correct output for all supported language
  variants, including case-insensitive and short-code inputs
- All locale folders present in ovos_workshop/locale/ have valid
  word_connectors.json with "and"/"or" keys
"""
import json
import os
import unittest
from os.path import dirname, join

from ovos_workshop.skills.ovos import _get_word, _get_dialog, join_word_list

LOCALE_DIR = join(dirname(dirname(dirname(__file__))),
                  "ovos_workshop", "locale")


class TestGetWord(unittest.TestCase):
    """_get_word() must resolve connectors for all supported langs."""

    def test_canonical_tag(self):
        self.assertEqual(_get_word("en-US", "and"), "and")
        self.assertEqual(_get_word("en-US", "or"), "or")

    def test_short_code_resolves(self):
        """Plain 'en' should match en-US folder."""
        self.assertEqual(_get_word("en", "and"), "and")

    def test_lowercase_tag_resolves(self):
        """en-us (all-lowercase) must still resolve."""
        self.assertEqual(_get_word("en-us", "and"), "and")

    def test_italian_canonical(self):
        self.assertEqual(_get_word("it-IT", "and"), "e")
        self.assertEqual(_get_word("it-IT", "or"), "o")

    def test_italian_short_code(self):
        """'it' must resolve to it-IT folder."""
        self.assertEqual(_get_word("it", "and"), "e")
        self.assertEqual(_get_word("it", "or"), "o")

    def test_spanish_canonical(self):
        self.assertEqual(_get_word("es-ES", "and"), "y")
        self.assertEqual(_get_word("es-ES", "or"), "o")

    def test_spanish_short_code(self):
        self.assertEqual(_get_word("es", "and"), "y")
        self.assertEqual(_get_word("es", "or"), "o")

    def test_german(self):
        self.assertEqual(_get_word("de-DE", "and"), "und")

    def test_french(self):
        self.assertEqual(_get_word("fr-FR", "and"), "et")

    def test_missing_lang_returns_fallback(self):
        """Unknown language must return ', ' not raise."""
        result = _get_word("xx-XX", "and")
        self.assertEqual(result, ", ")

    def test_all_locale_folders_have_connectors(self):
        """Every locale folder must contain a parseable word_connectors.json
        with both 'and' and 'or' keys."""
        for folder in os.listdir(LOCALE_DIR):
            path = join(LOCALE_DIR, folder, "word_connectors.json")
            if not os.path.isfile(path):
                continue  # not every locale needs connectors
            with open(path) as f:
                data = json.load(f)
            self.assertIn("and", data,
                          f"{folder}/word_connectors.json missing 'and'")
            self.assertIn("or", data,
                          f"{folder}/word_connectors.json missing 'or'")


class TestGetDialog(unittest.TestCase):
    """_get_dialog() must resolve bundled .dialog files."""

    def test_known_dialog_canonical(self):
        # game_pause.dialog has no template variables — safe to render as-is
        result = _get_dialog("game_pause", "en-US")
        self.assertNotEqual(result, "game_pause",
                            "Expected dialog text, got fallback phrase")

    def test_known_dialog_lowercase_tag(self):
        result = _get_dialog("game_pause", "en-us")
        self.assertNotEqual(result, "game_pause")

    def test_known_dialog_short_code(self):
        result = _get_dialog("game_pause", "en")
        self.assertNotEqual(result, "game_pause")

    def test_known_dialog_with_context(self):
        result = _get_dialog("skill.error", "en-US", context={"skill": "test_skill"})
        self.assertIn("test_skill", result)

    def test_missing_dialog_returns_phrase(self):
        result = _get_dialog("nonexistent.dialog.phrase", "en-US")
        self.assertEqual(result, "nonexistent.dialog.phrase")

    def test_missing_lang_returns_phrase(self):
        result = _get_dialog("skill.error", "xx-XX")
        self.assertEqual(result, "skill.error")


class TestJoinWordList(unittest.TestCase):
    """join_word_list() end-to-end for several languages and input shapes."""

    # --- English ---
    def test_en_two_items_and(self):
        self.assertEqual(join_word_list(["a", "b"], "and", ",", "en-US"),
                         "a and b")

    def test_en_three_items_and(self):
        self.assertEqual(join_word_list(["a", "b", "c"], "and", ",", "en-US"),
                         "a, b and c")

    def test_en_two_items_or(self):
        self.assertEqual(join_word_list(["x", "y"], "or", ",", "en-US"),
                         "x or y")

    def test_en_single_item(self):
        self.assertEqual(join_word_list(["only"], "and", ",", "en-US"), "only")

    def test_en_empty(self):
        self.assertEqual(join_word_list([], "and", ",", "en-US"), "")

    # --- Italian (euphony) ---
    def test_it_and_basic(self):
        self.assertEqual(
            join_word_list(["mare", "montagna"], "and", ",", "it-IT"),
            "mare e montagna")

    def test_it_and_euphonic(self):
        """'e' + vowel 'e' → 'ed'"""
        self.assertEqual(
            join_word_list(["inverno", "estate"], "and", ",", "it-IT"),
            "inverno ed estate")

    def test_it_or_euphonic(self):
        """'o' + vowel 'o' → 'od'"""
        self.assertEqual(
            join_word_list(["mare", "oceano"], "or", ",", "it-IT"),
            "mare od oceano")

    def test_it_short_code(self):
        """Short code 'it' must produce the same result as 'it-IT'."""
        self.assertEqual(
            join_word_list(["mare", "montagna"], "and", ",", "it"),
            join_word_list(["mare", "montagna"], "and", ",", "it-IT"))

    # --- Spanish (euphony) ---
    def test_es_and_euphonic(self):
        """'y' before 'i' → 'e'"""
        self.assertEqual(
            join_word_list(["Juan", "Irene"], "and", ",", "es-ES"),
            "Juan e Irene")

    def test_es_or_euphonic(self):
        """'o' before 'o' → 'u'"""
        self.assertEqual(
            join_word_list(["uno", "otro"], "or", ",", "es-ES"),
            "uno u otro")

    def test_es_and_no_euphony(self):
        self.assertEqual(
            join_word_list(["tierra", "agua"], "and", ",", "es-ES"),
            "tierra y agua")

    def test_es_short_code(self):
        self.assertEqual(
            join_word_list(["tierra", "agua"], "and", ",", "es"),
            join_word_list(["tierra", "agua"], "and", ",", "es-ES"))

    # --- German ---
    def test_de_and(self):
        self.assertEqual(
            join_word_list(["Hund", "Katze"], "and", ",", "de-DE"),
            "Hund und Katze")

    # --- French ---
    def test_fr_and(self):
        self.assertEqual(
            join_word_list(["chien", "chat"], "and", ",", "fr-FR"),
            "chien et chat")


if __name__ == "__main__":
    unittest.main()
