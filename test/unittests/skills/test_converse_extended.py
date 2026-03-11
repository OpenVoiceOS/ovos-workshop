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
"""Extended tests for ovos_workshop/skills/converse.py — ConversationalSkill."""
import json
import unittest
from unittest.mock import patch

from ovos_bus_client.message import Message
from ovos_utils.fakebus import FakeBus

from ovos_workshop.skills.converse import ConversationalSkill


class _ConcreteConversationalSkill(ConversationalSkill):
    """Minimal concrete subclass for testing (implements abstract methods)."""

    def can_converse(self, message: Message) -> bool:
        return True

    def converse(self, message: Message):
        return True


class TestConversationalSkillInit(unittest.TestCase):
    """Tests for ConversationalSkill basic initialization."""

    def setUp(self) -> None:
        self.bus = FakeBus()
        self.bus.emitted_msgs = []

        def capture(msg: str) -> None:
            self.bus.emitted_msgs.append(json.loads(msg))

        self.bus.on("message", capture)
        self.skill = _ConcreteConversationalSkill(skill_id="converse.test", bus=self.bus)

    def test_is_conversational_skill(self) -> None:
        from ovos_workshop.skills.converse import ConversationalSkill
        self.assertIsInstance(self.skill, ConversationalSkill)

    def test_converse_matchers_initialized(self) -> None:
        """converse_matchers attribute is initialized as empty dict."""
        self.assertIsInstance(self.skill.converse_matchers, dict)

    def test_skill_id_set(self) -> None:
        self.assertEqual(self.skill.skill_id, "converse.test")


class TestConversationalSkillActivate(unittest.TestCase):
    """Tests for activate/deactivate bus message emission."""

    def setUp(self) -> None:
        self.bus = FakeBus()
        self.emitted = []

        def capture(msg: str) -> None:
            self.emitted.append(json.loads(msg))

        self.bus.on("message", capture)
        self.skill = _ConcreteConversationalSkill(skill_id="converse.test", bus=self.bus)
        self.emitted.clear()

    def test_activate_emits_message(self) -> None:
        """activate() emits intent.service.skills.activate message."""
        self.skill.activate(duration_minutes=5)
        msg_types = [m["type"] for m in self.emitted]
        self.assertIn("intent.service.skills.activate", msg_types)

    def test_activate_includes_skill_id(self) -> None:
        """activate() message data includes the skill_id."""
        self.skill.activate(duration_minutes=5)
        activate_msgs = [m for m in self.emitted if m["type"] == "intent.service.skills.activate"]
        self.assertTrue(len(activate_msgs) > 0)
        self.assertEqual(activate_msgs[0]["data"]["skill_id"], "converse.test")

    def test_deactivate_emits_message(self) -> None:
        """deactivate() emits intent.service.skills.deactivate message."""
        self.skill.deactivate()
        msg_types = [m["type"] for m in self.emitted]
        self.assertIn("intent.service.skills.deactivate", msg_types)

    def test_deactivate_includes_skill_id(self) -> None:
        """deactivate() message data includes the skill_id."""
        self.skill.deactivate()
        deact_msgs = [m for m in self.emitted if m["type"] == "intent.service.skills.deactivate"]
        self.assertTrue(len(deact_msgs) > 0)
        self.assertEqual(deact_msgs[0]["data"]["skill_id"], "converse.test")


class TestConversationalSkillCanConverse(unittest.TestCase):
    """Tests for can_converse returning bool."""

    def setUp(self) -> None:
        self.bus = FakeBus()
        self.skill = _ConcreteConversationalSkill(skill_id="converse.test2", bus=self.bus)

    def test_can_converse_returns_bool(self) -> None:
        msg = Message("test", data={"utterances": ["hello"], "lang": "en-us"})
        result = self.skill.can_converse(msg)
        self.assertIsInstance(result, bool)
        self.assertTrue(result)


class TestConversationalSkillHandlers(unittest.TestCase):
    """Tests for handle_activate and handle_deactivate default no-ops."""

    def setUp(self) -> None:
        self.bus = FakeBus()
        self.skill = _ConcreteConversationalSkill(skill_id="converse.test3", bus=self.bus)

    def test_handle_activate_no_error(self) -> None:
        """handle_activate default implementation does nothing and doesn't raise."""
        msg = Message("converse.test3.activate")
        self.skill.handle_activate(msg)  # Should not raise

    def test_handle_deactivate_no_error(self) -> None:
        """handle_deactivate default implementation does nothing and doesn't raise."""
        msg = Message("converse.test3.deactivate")
        self.skill.handle_deactivate(msg)  # Should not raise


if __name__ == "__main__":
    unittest.main()
