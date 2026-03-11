# Copyright 2024, OpenVoiceOS
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
"""Tests for trivially small modules: passive.py, layers.py, fallback_handler.py."""
import unittest
import warnings


class TestPassiveSkillImport(unittest.TestCase):
    """Tests for ovos_workshop/skills/passive.py."""

    def test_passive_skill_importable(self) -> None:
        from ovos_workshop.skills.passive import PassiveSkill
        self.assertIsNotNone(PassiveSkill)

    def test_passive_skill_instantiation(self) -> None:
        from ovos_workshop.skills.passive import PassiveSkill
        from ovos_utils.fakebus import FakeBus
        skill = PassiveSkill(bus=FakeBus(), skill_id="test.passive")
        self.assertIsNotNone(skill)

    def test_handle_utterance_no_op(self) -> None:
        from ovos_workshop.skills.passive import PassiveSkill
        from ovos_utils.fakebus import FakeBus
        skill = PassiveSkill(bus=FakeBus(), skill_id="test.passive2")
        # Default implementation returns None (no-op)
        result = skill.handle_utterance(["hello"], lang="en-us")
        self.assertIsNone(result)

    def test_converse_returns_false(self) -> None:
        from ovos_workshop.skills.passive import PassiveSkill
        from ovos_utils.fakebus import FakeBus
        skill = PassiveSkill(bus=FakeBus(), skill_id="test.passive3")
        result = skill.converse(["hello"], lang="en-us")
        self.assertFalse(result)


class TestSkillsLayersDeprecatedImport(unittest.TestCase):
    """Tests for ovos_workshop/skills/layers.py (deprecated re-export)."""

    def test_import_raises_deprecation_warning(self) -> None:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            import ovos_workshop.skills.layers  # noqa: F401
            self.assertTrue(
                any(issubclass(w.category, DeprecationWarning) for w in caught),
                "Expected DeprecationWarning when importing ovos_workshop.skills.layers",
            )

    def test_intent_layers_available(self) -> None:
        from ovos_workshop.skills.layers import IntentLayers
        self.assertIsNotNone(IntentLayers)


class TestFallbackHandlerDecorator(unittest.TestCase):
    """Tests for ovos_workshop/decorators/fallback_handler.py."""

    def test_fallback_handler_importable(self) -> None:
        from ovos_workshop.decorators.fallback_handler import fallback_handler
        self.assertIsNotNone(fallback_handler)

    def test_fallback_handler_sets_priority(self) -> None:
        from ovos_workshop.decorators.fallback_handler import fallback_handler

        @fallback_handler(priority=80)
        def my_fallback():
            pass

        self.assertEqual(my_fallback.fallback_priority, 80)

    def test_fallback_handler_default_priority(self) -> None:
        from ovos_workshop.decorators.fallback_handler import fallback_handler

        @fallback_handler()
        def my_fallback():
            pass

        self.assertEqual(my_fallback.fallback_priority, 50)

    def test_fallback_handler_preserves_existing_priority(self) -> None:
        """If fallback_priority already set, don't overwrite it."""
        from ovos_workshop.decorators.fallback_handler import fallback_handler

        def my_fallback():
            pass

        my_fallback.fallback_priority = 30

        decorated = fallback_handler(priority=70)(my_fallback)
        # Original priority was already set, so decorator should not overwrite
        self.assertEqual(decorated.fallback_priority, 30)


if __name__ == "__main__":
    unittest.main()
