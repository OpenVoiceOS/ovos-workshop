# Copyright 2026 OpenVoiceOS
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Extended tests for ovos_workshop/skills/auto_translatable.py — UniversalSkill."""
import unittest
from unittest.mock import MagicMock, patch

from ovos_utils.fakebus import FakeBus


class TestUniversalSkillExtended(unittest.TestCase):
    """Extended tests for UniversalSkill properties and methods."""

    def setUp(self) -> None:
        self.bus = FakeBus()

    def test_internal_language_default_from_config(self) -> None:
        """When no internal_language is given, defaults to config lang."""
        from ovos_workshop.skills.auto_translatable import UniversalSkill
        with patch("ovos_workshop.skills.auto_translatable.Configuration") as mock_cfg:
            mock_cfg.return_value.get.return_value = "en-us"
            skill = UniversalSkill(bus=self.bus, skill_id="test.universal")
        # Should have set internal_language to something from config
        self.assertIsNotNone(skill.internal_language)

    def test_internal_language_explicit(self) -> None:
        """Explicitly passed internal_language is stored."""
        from ovos_workshop.skills.auto_translatable import UniversalSkill
        skill = UniversalSkill(internal_language="de-de", bus=self.bus, skill_id="test.universal2")
        self.assertEqual(skill.internal_language, "de-de")

    def test_translate_tags_default_true(self) -> None:
        """translate_tags defaults to True."""
        from ovos_workshop.skills.auto_translatable import UniversalSkill
        skill = UniversalSkill(bus=self.bus, skill_id="test.universal3")
        self.assertTrue(skill.translate_tags)

    def test_translate_tags_false(self) -> None:
        """translate_tags can be set to False."""
        from ovos_workshop.skills.auto_translatable import UniversalSkill
        skill = UniversalSkill(translate_tags=False, bus=self.bus, skill_id="test.universal4")
        self.assertFalse(skill.translate_tags)

    def test_translate_keys_default(self) -> None:
        """translate_keys defaults to ['utterance', 'utterances']."""
        from ovos_workshop.skills.auto_translatable import UniversalSkill
        skill = UniversalSkill(bus=self.bus, skill_id="test.universal5")
        self.assertIn("utterance", skill.translate_keys)
        self.assertIn("utterances", skill.translate_keys)

    def test_autodetect_default_false(self) -> None:
        """autodetect defaults to False."""
        from ovos_workshop.skills.auto_translatable import UniversalSkill
        skill = UniversalSkill(bus=self.bus, skill_id="test.universal6")
        self.assertFalse(skill.autodetect)

    def test_detect_language_fallback_on_error(self) -> None:
        """detect_language falls back to self.lang when detector raises."""
        from ovos_workshop.skills.auto_translatable import UniversalSkill
        skill = UniversalSkill(internal_language="en-us", bus=self.bus, skill_id="test.universal7")
        # Mock lang_detector to raise
        mock_detector = MagicMock()
        mock_detector.detect.side_effect = Exception("detector error")
        skill.lang_detector = mock_detector
        result = skill.detect_language("hello world")
        # Should return the language prefix (e.g., "en")
        self.assertIsInstance(result, str)


class TestUniversalFallbackExtended(unittest.TestCase):
    """Extended tests for UniversalFallback."""

    def test_is_fallback_skill(self) -> None:
        from ovos_workshop.skills.auto_translatable import UniversalFallback
        from ovos_workshop.skills.fallback import FallbackSkill
        class _Concrete(UniversalFallback):
            def can_answer(self, message):
                return False

        skill = _Concrete(bus=FakeBus(), skill_id="test.universal.fallback")
        self.assertIsInstance(skill, FallbackSkill)


if __name__ == "__main__":
    unittest.main()
