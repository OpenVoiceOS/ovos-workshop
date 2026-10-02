"""
Tests for locale directory lookup and language resource resolution.

Covers:
- _get_word() resolves word_connectors.json via CoreResources
- join_word_list() produces correct output for all supported language
  variants, including case-insensitive and short-code inputs
- All locale folders present in ovos_workshop/locale/ have valid
  word_connectors.json with "and"/"or" keys
- Euphony rules loaded from JSON config produce correct transformations
- util.py helpers: simple_trace, normalize_word, apply_euphony
"""
import json
import os
import unittest
from os.path import dirname, join

from ovos_workshop.skills.util import (
    _get_word, join_word_list, simple_trace,
    _normalize_word, _apply_euphony, _load_euphony_rules
)

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


class TestSimpleTrace(unittest.TestCase):
    """simple_trace() formatting."""

    def test_removes_last_line(self):
        tb = simple_trace(["File x\n", "  foo()\n", "Error\n"])
        self.assertIn("File x", tb)
        self.assertIn("foo()", tb)
        self.assertNotIn("Error", tb)

    def test_skips_blank_lines(self):
        tb = simple_trace(["line1\n", "\n", "line2\n", "last\n"])
        self.assertNotIn("\n\n", tb)

    def test_starts_with_traceback(self):
        tb = simple_trace(["a\n", "b\n"])
        self.assertTrue(tb.startswith("Traceback:\n"))


class TestNormalizeWord(unittest.TestCase):
    """_normalize_word() applies language-specific normalization."""

    def test_strip_leading_h(self):
        rules = {"normalize": {"strip_leading_h": True}}
        self.assertEqual(_normalize_word("hombre", rules), "ombre")

    def test_replace_accents(self):
        rules = {"normalize": {"replace_accents": {"ó": "o", "í": "i"}}}
        self.assertEqual(_normalize_word("ídolo", rules), "idolo")

    def test_both_normalize_steps(self):
        rules = {"normalize": {"strip_leading_h": True, "replace_accents": {"í": "i"}}}
        self.assertEqual(_normalize_word("híbrido", rules), "ibrido")

    def test_empty_normalize(self):
        rules = {"normalize": {}}
        self.assertEqual(_normalize_word("hello", rules), "hello")

    def test_empty_word(self):
        rules = {"normalize": {"strip_leading_h": True}}
        self.assertEqual(_normalize_word("", rules), "")


class TestApplyEuphony(unittest.TestCase):
    """_apply_euphony() rule engine tests."""

    def test_starts_with_vowel_match(self):
        rules = {"normalize": {}, "rules": [
            {"connector": "e", "condition": "starts_with_vowel",
             "vowels": ["e"], "replace_with": "ed"}
        ]}
        self.assertEqual(_apply_euphony("e", "estate", rules), "ed")

    def test_starts_with_vowel_no_match(self):
        rules = {"normalize": {}, "rules": [
            {"connector": "e", "condition": "starts_with_vowel",
             "vowels": ["e"], "replace_with": "ed"}
        ]}
        self.assertEqual(_apply_euphony("e", "montagna", rules), "e")

    def test_starts_with_any_except_applies(self):
        rules = {"normalize": {"strip_leading_h": True,
                                "replace_accents": {"í": "i"}},
                 "rules": [
            {"connector": "y", "condition": "starts_with_any_except",
             "letters": ["i"], "excluded_patterns": ["io", "ia", "ie"],
             "replace_with": "e"}
        ]}
        self.assertEqual(_apply_euphony("y", "Irene", rules), "e")

    def test_starts_with_any_except_excluded(self):
        """Should NOT transform y→e before 'hielo' (diphthong ie)."""
        rules = {"normalize": {"strip_leading_h": True},
                 "rules": [
            {"connector": "y", "condition": "starts_with_any_except",
             "letters": ["i"], "excluded_patterns": ["io", "ia", "ie"],
             "replace_with": "e"}
        ]}
        self.assertEqual(_apply_euphony("y", "hielo", rules), "y")

    def test_no_rules_returns_connector(self):
        self.assertEqual(_apply_euphony("and", "word", {}), "and")
        self.assertEqual(_apply_euphony("and", "word", None), "and")

    def test_empty_next_word(self):
        rules = {"rules": [{"connector": "e", "condition": "starts_with_vowel",
                             "vowels": ["e"], "replace_with": "ed"}]}
        self.assertEqual(_apply_euphony("e", "", rules), "e")

    def test_wrong_connector_skipped(self):
        rules = {"normalize": {}, "rules": [
            {"connector": "o", "condition": "starts_with_vowel",
             "vowels": ["o"], "replace_with": "od"}
        ]}
        self.assertEqual(_apply_euphony("e", "oceano", rules), "e")


class TestEuphonyJsonSchema(unittest.TestCase):
    """All euphony.json files must have valid structure."""

    def test_all_euphony_files_valid(self):
        for folder in os.listdir(LOCALE_DIR):
            path = join(LOCALE_DIR, folder, "euphony.json")
            if not os.path.isfile(path):
                continue
            with open(path, encoding='utf-8') as f:
                data = json.load(f)
            self.assertIn("rules", data,
                          f"{folder}/euphony.json missing 'rules'")
            self.assertIsInstance(data["rules"], list,
                                 f"{folder}/euphony.json 'rules' must be a list")
            for rule in data["rules"]:
                self.assertIn("connector", rule,
                              f"{folder}/euphony.json rule missing 'connector'")
                self.assertIn("condition", rule,
                              f"{folder}/euphony.json rule missing 'condition'")
                self.assertIn("replace_with", rule,
                              f"{folder}/euphony.json rule missing 'replace_with'")


class TestWordConnectorsAllLocales(unittest.TestCase):
    """Every locale with word_connectors.json must have valid and/or keys."""

    def test_all_locales_have_word_connectors(self):
        missing = []
        for folder in sorted(os.listdir(LOCALE_DIR)):
            folder_path = join(LOCALE_DIR, folder)
            if not os.path.isdir(folder_path):
                continue
            wc_path = join(folder_path, "word_connectors.json")
            if not os.path.isfile(wc_path):
                missing.append(folder)
        self.assertEqual(missing, [],
                         f"Locale folders missing word_connectors.json: {missing}")

    def test_connectors_have_and_or(self):
        for folder in os.listdir(LOCALE_DIR):
            path = join(LOCALE_DIR, folder, "word_connectors.json")
            if not os.path.isfile(path):
                continue
            with open(path, encoding='utf-8') as f:
                data = json.load(f)
            self.assertIn("and", data,
                          f"{folder}/word_connectors.json missing 'and'")
            self.assertIn("or", data,
                          f"{folder}/word_connectors.json missing 'or'")
            # Values must be non-empty strings
            self.assertIsInstance(data["and"], str,
                                 f"{folder} 'and' must be a string")
            self.assertIsInstance(data["or"], str,
                                 f"{folder} 'or' must be a string")
            self.assertTrue(data["and"].strip(),
                            f"{folder} 'and' must not be empty")
            self.assertTrue(data["or"].strip(),
                            f"{folder} 'or' must not be empty")


class TestJoinWordListMoreLanguages(unittest.TestCase):
    """join_word_list() for newly added languages."""

    def test_pt_br_and(self):
        self.assertEqual(
            join_word_list(["gato", "cachorro"], "and", ",", "pt-BR"),
            "gato e cachorro")

    def test_ru_and(self):
        self.assertEqual(
            join_word_list(["кот", "собака"], "and", ",", "ru-RU"),
            "кот и собака")

    def test_tr_and(self):
        self.assertEqual(
            join_word_list(["kedi", "köpek"], "and", ",", "tr-TR"),
            "kedi ve köpek")

    def test_ja_and(self):
        self.assertEqual(
            join_word_list(["猫", "犬"], "and", ",", "ja-JP"),
            "猫 と 犬")

    def test_zh_or(self):
        self.assertEqual(
            join_word_list(["猫", "狗"], "or", ",", "zh-CN"),
            "猫 或 狗")

    def test_ar_and(self):
        self.assertEqual(
            join_word_list(["قط", "كلب"], "and", ",", "ar-SA"),
            "قط و كلب")

    def test_sv_and(self):
        self.assertEqual(
            join_word_list(["katt", "hund"], "and", ",", "sv-SE"),
            "katt och hund")

    def test_hu_or(self):
        self.assertEqual(
            join_word_list(["macska", "kutya"], "or", ",", "hu-HU"),
            "macska vagy kutya")

    def test_three_items_ru(self):
        self.assertEqual(
            join_word_list(["раз", "два", "три"], "and", ",", "ru-RU"),
            "раз, два и три")

    # --- Occitan (euphony: e → et before any vowel) ---
    def test_oc_and_before_vowel(self):
        self.assertEqual(
            join_word_list(["pan", "aiga"], "and", ",", "oc-FR"),
            "pan et aiga")

    def test_oc_and_before_consonant(self):
        self.assertEqual(
            join_word_list(["pan", "vin"], "and", ",", "oc-FR"),
            "pan e vin")

    # --- Asturian (euphony: y → e before i, o → u before o) ---
    def test_ast_and_before_i(self):
        self.assertEqual(
            join_word_list(["Juan", "Irene"], "and", ",", "ast-ES"),
            "Juan e Irene")

    def test_ast_and_no_euphony(self):
        self.assertEqual(
            join_word_list(["pan", "agua"], "and", ",", "ast-ES"),
            "pan y agua")

    def test_ast_or_before_o(self):
        self.assertEqual(
            join_word_list(["uno", "otro"], "or", ",", "ast-ES"),
            "uno u otro")

    # --- Aragonese (euphony: y → e before i, o → u before o) ---
    def test_an_and_before_i(self):
        self.assertEqual(
            join_word_list(["Juan", "Irene"], "and", ",", "an-ES"),
            "Juan e Irene")

    def test_an_and_no_euphony(self):
        self.assertEqual(
            join_word_list(["pan", "augua"], "and", ",", "an-ES"),
            "pan y augua")

    def test_an_or_before_o(self):
        self.assertEqual(
            join_word_list(["uno", "otro"], "or", ",", "an-ES"),
            "uno u otro")


if __name__ == "__main__":
    unittest.main()