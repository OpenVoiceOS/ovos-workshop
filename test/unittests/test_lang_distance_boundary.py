"""The language-distance boundary used to pick locale directories and converse
matchers."""
import shutil
import tempfile
import unittest
from pathlib import Path

from ovos_workshop.resource_files import locate_lang_directories
from ovos_workshop.skills.converse import ConversationalSkill

MACROLANGUAGE_PAIRS = [("arz", "ar"), ("wuu", "zh")]
REGIONAL_PAIRS = [("ar-SA", "ar"), ("en-AU", "en-GB"), ("pt-BR", "pt-PT")]
UNRELATED_PAIRS = [("en", "zh"), ("es", "fr"), ("fr-CH", "de-CH"), ("af", "nl")]


class TestLocaleDirectoryBoundary(unittest.TestCase):
    """`locate_lang_directories` accepts a directory at the threshold."""

    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _locale(self, name: str) -> None:
        Path(self.tmp, "locale", name).mkdir(parents=True, exist_ok=True)

    def _found(self, requested: str, available: str) -> bool:
        self._locale(available)
        dirs = locate_lang_directories(requested, self.tmp)
        return any(d.name == available for d in dirs)

    def test_macrolanguage_directory_is_found(self) -> None:
        for member, macro in MACROLANGUAGE_PAIRS:
            with self.subTest(member=member):
                self.assertTrue(self._found(member, macro))

    def test_regional_directory_is_found(self) -> None:
        for requested, available in REGIONAL_PAIRS:
            with self.subTest(requested=requested):
                self.assertTrue(self._found(requested, available))

    def test_unrelated_directory_is_not_found(self) -> None:
        for requested, available in UNRELATED_PAIRS:
            with self.subTest(requested=requested):
                self.assertFalse(self._found(requested, available))


class _Matchers(dict):
    """Stands in for the converse matcher registry, which maps a tag to an
    intent container."""


class TestConverseLangBoundary(unittest.TestCase):
    """`_get_closest_lang` accepts a matcher language at the threshold."""

    @staticmethod
    def _closest(requested: str, available: str):
        skill = ConversationalSkill.__new__(ConversationalSkill)
        skill.skill_id = "test.boundary"
        skill.converse_matchers = _Matchers({available: object()})
        return ConversationalSkill._get_closest_lang(skill, requested)

    def test_macrolanguage_matcher_is_selected(self) -> None:
        for member, macro in MACROLANGUAGE_PAIRS:
            with self.subTest(member=member):
                self.assertEqual(self._closest(member, macro), macro)

    def test_regional_matcher_is_selected(self) -> None:
        for requested, available in REGIONAL_PAIRS:
            with self.subTest(requested=requested):
                self.assertEqual(self._closest(requested, available), available)

    def test_unrelated_matcher_is_rejected(self) -> None:
        for requested, available in UNRELATED_PAIRS:
            with self.subTest(requested=requested):
                self.assertIsNone(self._closest(requested, available))


if __name__ == "__main__":
    unittest.main()
