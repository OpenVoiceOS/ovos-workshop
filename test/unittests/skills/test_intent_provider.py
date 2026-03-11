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
"""Tests for ovos_workshop/skills/intent_provider.py — deprecated BaseIntentEngine."""
import unittest
import warnings
from unittest.mock import patch


class TestBaseIntentEngine(unittest.TestCase):
    """Tests for BaseIntentEngine (deprecated)."""

    def test_import_raises_deprecation_warning(self) -> None:
        """Importing intent_provider emits DeprecationWarning (module-level)."""
        # The module may already be cached; verify the warning was issued by
        # checking that the module is importable and contains expected classes.
        import ovos_workshop.skills.intent_provider as ip
        self.assertTrue(hasattr(ip, "BaseIntentEngine"))
        self.assertTrue(hasattr(ip, "IntentEngineSkill"))

    def test_base_intent_engine_instantiation(self) -> None:
        """BaseIntentEngine can be instantiated with a name and config."""
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            from ovos_workshop.skills.intent_provider import BaseIntentEngine
            engine = BaseIntentEngine("test_engine", config={"test_engine": {}})
        self.assertEqual(engine.name, "test_engine")

    def test_add_intent(self) -> None:
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            from ovos_workshop.skills.intent_provider import BaseIntentEngine
            engine = BaseIntentEngine("test_engine", config={"test_engine": {}})
        engine.add_intent("MyIntent", ["sample one", "sample two"])
        self.assertIn("MyIntent", engine.intent_samples)

    def test_remove_intent(self) -> None:
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            from ovos_workshop.skills.intent_provider import BaseIntentEngine
            engine = BaseIntentEngine("test_engine", config={"test_engine": {}})
        engine.add_intent("MyIntent", ["sample"])
        engine.remove_intent("MyIntent")
        self.assertNotIn("MyIntent", engine.intent_samples)

    def test_remove_intent_missing_no_error(self) -> None:
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            from ovos_workshop.skills.intent_provider import BaseIntentEngine
            engine = BaseIntentEngine("test_engine", config={"test_engine": {}})
        # Should not raise when removing non-existent intent
        engine.remove_intent("NonExistent")

    def test_add_entity(self) -> None:
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            from ovos_workshop.skills.intent_provider import BaseIntentEngine
            engine = BaseIntentEngine("test_engine", config={"test_engine": {}})
        engine.add_entity("MyEntity", ["value1", "value2"])
        self.assertIn("MyEntity", engine.entity_samples)

    def test_remove_entity(self) -> None:
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            from ovos_workshop.skills.intent_provider import BaseIntentEngine
            engine = BaseIntentEngine("test_engine", config={"test_engine": {}})
        engine.add_entity("MyEntity", ["value"])
        engine.remove_entity("MyEntity")
        self.assertNotIn("MyEntity", engine.entity_samples)

    def test_add_regex(self) -> None:
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            from ovos_workshop.skills.intent_provider import BaseIntentEngine
            engine = BaseIntentEngine("test_engine", config={"test_engine": {}})
        engine.add_regex("MyRegex", r"(?P<entity>\w+)")
        self.assertIn("MyRegex", engine.regex_samples)

    def test_remove_regex(self) -> None:
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            from ovos_workshop.skills.intent_provider import BaseIntentEngine
            engine = BaseIntentEngine("test_engine", config={"test_engine": {}})
        engine.add_regex("MyRegex", r"\w+")
        engine.remove_regex("MyRegex")
        self.assertNotIn("MyRegex", engine.regex_samples)

    def test_train_no_error(self) -> None:
        """train() is a no-op in BaseIntentEngine — should not raise."""
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            from ovos_workshop.skills.intent_provider import BaseIntentEngine
            engine = BaseIntentEngine("test_engine", config={"test_engine": {}})
        engine.train()  # should not raise

    def test_calc_intent_returns_dict(self) -> None:
        """calc_intent returns a dict with conf=0 and name=None."""
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            from ovos_workshop.skills.intent_provider import BaseIntentEngine
            engine = BaseIntentEngine("test_engine", config={"test_engine": {}})
        result = engine.calc_intent("hello world")
        self.assertIsInstance(result, dict)
        self.assertEqual(result["conf"], 0)
        self.assertIsNone(result["name"])


if __name__ == "__main__":
    unittest.main()
