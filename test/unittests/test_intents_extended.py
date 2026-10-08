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
"""Extended tests for ovos_workshop/intents.py — IntentBuilder, Intent, IntentServiceInterface."""
import unittest
from unittest.mock import MagicMock, patch

import pytest
from ovos_utils.fakebus import FakeBus

# Deliberate legacy-coverage suite: exercises the deprecated
# register_adapt_intent facade on purpose.
pytestmark = pytest.mark.filterwarnings(
    "ignore:(IntentServiceInterface\\.)?register_(adapt|padatious)_\\w+ "
    "is deprecated:DeprecationWarning"
)


class TestIntentBuilder(unittest.TestCase):
    """Tests for IntentBuilder fluent API."""

    def test_instantiation(self) -> None:
        from ovos_workshop.intents import IntentBuilder
        builder = IntentBuilder("TestIntent")
        self.assertEqual(builder.name, "TestIntent")

    def test_require_returns_self(self) -> None:
        from ovos_workshop.intents import IntentBuilder
        builder = IntentBuilder("TestIntent")
        result = builder.require("Entity")
        self.assertIs(result, builder)

    def test_require_adds_to_requires(self) -> None:
        from ovos_workshop.intents import IntentBuilder
        builder = IntentBuilder("TestIntent").require("Action")
        self.assertIn(("Action", "Action"), builder.requires)

    def test_require_custom_attribute_name(self) -> None:
        from ovos_workshop.intents import IntentBuilder
        builder = IntentBuilder("TestIntent").require("Action", "verb")
        self.assertIn(("Action", "verb"), builder.requires)

    def test_optionally_returns_self(self) -> None:
        from ovos_workshop.intents import IntentBuilder
        builder = IntentBuilder("TestIntent")
        result = builder.optionally("Target")
        self.assertIs(result, builder)

    def test_optionally_adds_to_optional(self) -> None:
        from ovos_workshop.intents import IntentBuilder
        builder = IntentBuilder("TestIntent").optionally("Target")
        self.assertIn(("Target", "Target"), builder.optional)

    def test_one_of_returns_self(self) -> None:
        from ovos_workshop.intents import IntentBuilder
        builder = IntentBuilder("TestIntent")
        result = builder.one_of("A", "B")
        self.assertIs(result, builder)

    def test_one_of_adds_to_at_least_one(self) -> None:
        from ovos_workshop.intents import IntentBuilder
        builder = IntentBuilder("TestIntent").one_of("A", "B")
        self.assertEqual(len(builder.at_least_one), 1)

    def test_exclude_returns_self(self) -> None:
        from ovos_workshop.intents import IntentBuilder
        builder = IntentBuilder("TestIntent")
        result = builder.exclude("NotThis")
        self.assertIs(result, builder)

    def test_exclude_adds_to_excludes(self) -> None:
        from ovos_workshop.intents import IntentBuilder
        builder = IntentBuilder("TestIntent").exclude("NotThis")
        self.assertIn("NotThis", builder.excludes)

    def test_build_returns_intent(self) -> None:
        from ovos_workshop.intents import IntentBuilder, Intent
        intent = IntentBuilder("TestIntent").require("Action").build()
        self.assertIsInstance(intent, Intent)

    def test_build_preserves_name(self) -> None:
        from ovos_workshop.intents import IntentBuilder
        intent = IntentBuilder("MyIntent").build()
        self.assertEqual(intent.name, "MyIntent")

    def test_chaining(self) -> None:
        from ovos_workshop.intents import IntentBuilder
        intent = (
            IntentBuilder("ChainedIntent")
            .require("Action")
            .optionally("Target")
            .one_of("A", "B")
            .exclude("Bad")
            .build()
        )
        self.assertEqual(intent.name, "ChainedIntent")
        self.assertEqual(len(intent.requires), 1)
        self.assertEqual(len(intent.optional), 1)
        self.assertEqual(len(intent.at_least_one), 1)
        self.assertEqual(len(intent.excludes), 1)


class TestIntent(unittest.TestCase):
    """Tests for the Intent class."""

    def test_instantiation_defaults(self) -> None:
        from ovos_workshop.intents import Intent
        intent = Intent(name="Test")
        self.assertEqual(intent.name, "Test")
        self.assertEqual(intent.requires, [])
        self.assertEqual(intent.at_least_one, [])
        self.assertEqual(intent.optional, [])
        self.assertEqual(intent.excludes, [])

    def test_instantiation_with_params(self) -> None:
        from ovos_workshop.intents import Intent
        intent = Intent(
            name="WithParams",
            requires=[("Action", "Action")],
            optional=[("Target", "Target")],
        )
        self.assertEqual(intent.requires, [("Action", "Action")])
        self.assertEqual(intent.optional, [("Target", "Target")])


class TestIntentServiceInterface(unittest.TestCase):
    """Tests for IntentServiceInterface."""

    def test_instantiation(self) -> None:
        from ovos_workshop.intents import IntentServiceInterface
        iface = IntentServiceInterface()
        self.assertIsNotNone(iface)

    def test_bus_raises_without_set(self) -> None:
        from ovos_workshop.intents import IntentServiceInterface
        iface = IntentServiceInterface()
        with self.assertRaises(RuntimeError):
            _ = iface.bus

    def test_set_bus(self) -> None:
        from ovos_workshop.intents import IntentServiceInterface
        bus = FakeBus()
        iface = IntentServiceInterface(bus=bus)
        self.assertIs(iface.bus, bus)

    def test_set_id(self) -> None:
        from ovos_workshop.intents import IntentServiceInterface
        iface = IntentServiceInterface()
        iface.set_id("my.skill")
        self.assertEqual(iface.skill_id, "my.skill")

    def test_intent_names_empty_initially(self) -> None:
        from ovos_workshop.intents import IntentServiceInterface
        iface = IntentServiceInterface()
        self.assertEqual(iface.intent_names, [])

    def test_register_adapt_intent_adds_to_list(self) -> None:
        from ovos_workshop.intents import IntentServiceInterface, IntentBuilder
        bus = FakeBus()
        iface = IntentServiceInterface(bus=bus)
        iface.set_id("test.skill")
        parser = IntentBuilder("TestIntent").require("Action").build()
        iface.register_adapt_intent("TestIntent", parser)
        self.assertIn("TestIntent", iface.intent_names)

    def test_to_alnum(self) -> None:
        from ovos_workshop.intents import to_alnum
        self.assertEqual(to_alnum("my.skill-id"), "my_skill_id")
        self.assertEqual(to_alnum("abc123"), "abc123")

    def test_munge_regex(self) -> None:
        from ovos_workshop.intents import munge_regex
        regex = r"(?P<entity>\w+)"
        munged = munge_regex(regex, "my.skill")
        self.assertIn("my_skill", munged)


if __name__ == "__main__":
    unittest.main()
