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
"""Extended tests for ovos_workshop/skills/converse.py — ConversationalSkill."""
import json
import time
import unittest
from unittest.mock import patch


from ovos_bus_client.message import Message
from ovos_bus_client.session import Session
from ovos_utils.fakebus import FakeBus

from ovos_workshop.skills.converse import ConversationalSkill


class _ConcreteConversationalSkill(ConversationalSkill):
    """Minimal concrete subclass for testing (implements abstract methods)."""

    def can_converse(self, message: Message) -> bool:
        return True

    def converse(self, message: Message):
        return True


class TestConverseRequestUtteranceHandled(unittest.TestCase):
    """PIPELINE-1 §9.5: the core emits `ovos.utterance.handled` for a
    converse match itself; the skill must not also emit it."""

    def setUp(self) -> None:
        self.bus = FakeBus()
        self.skill = _ConcreteConversationalSkill(skill_id="converse.utt.test",
                                                  bus=self.bus)

    def test_handle_converse_request_never_emits_utterance_handled(self) -> None:
        from ovos_spec_tools import SpecMessage
        msg = Message(f"{self.skill.skill_id}.converse.request",
                      {"utterances": ["hi"], "lang": "en-US"},
                      {"utterance_id": "uid-cv"})

        captured = []
        self.bus.on(SpecMessage.UTTERANCE_HANDLED.value,
                    lambda m: captured.append(m))
        self.skill._handle_converse_request(msg)
        time.sleep(0.3)  # runs in a killable thread

        self.assertEqual(captured, [])


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
        self.assertIsInstance(self.skill, ConversationalSkill)

    def test_converse_matchers_initialized(self) -> None:
        """converse_matchers attribute is initialized as empty dict."""
        self.assertEqual(self.skill.converse_matchers, {})

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


class _CountingConversationalSkill(ConversationalSkill):
    """Records every can_converse call so the poll leg can be identified."""

    def __init__(self, *args, claims: bool = True, **kwargs):
        self.claims = claims
        self.can_converse_calls = []
        super().__init__(*args, **kwargs)

    def can_converse(self, message: Message) -> bool:
        self.can_converse_calls.append(message.msg_type)
        return self.claims

    def converse(self, message: Message):
        return True


class TestConverseBroadcastPoll(unittest.TestCase):
    """OVOS-CONVERSE-1 §4.2/§9.3 — answering the broadcast poll."""

    def setUp(self) -> None:
        self.bus = FakeBus()
        self.pongs = []
        self.bus.on("ovos.converse.pong", self.pongs.append)
        self.bus.on("skill.converse.pong", self.pongs.append)
        self.skill = _CountingConversationalSkill(skill_id="converse.test",
                                                  bus=self.bus)

    def _ping(self, *candidates, topic="ovos.converse.ping"):
        sess = Session("s")
        for skill_id in candidates:
            sess.activate_skill(skill_id)
        return Message(topic, {"utterances": ["hello"], "lang": "en-US"},
                       {"session": sess.serialize()})

    def test_broadcast_ping_is_bound(self) -> None:
        """FEATURE. The skill listens on the static broadcast topic."""
        self.assertIn("ovos.converse.ping", self.bus.ee.event_names())

    def test_legacy_ping_still_bound(self) -> None:
        """V0 COMPAT. The per-skill ping binding survives the compat window,
        so a pre-broadcast core keeps reaching this skill."""
        self.assertIn("converse.test.converse.ping", self.bus.ee.event_names())

    def test_named_candidate_answers_broadcast(self) -> None:
        """FEATURE. When named in the round, the skill pongs the spec shape."""
        self.bus.emit(self._ping("converse.test"))

        self.assertEqual(len(self.pongs), 1)
        pong = self.pongs[0]
        self.assertEqual(pong.msg_type, "ovos.converse.pong")
        self.assertEqual(pong.data["skill_id"], "converse.test")
        self.assertTrue(pong.data["result"])

    def test_unnamed_skill_stays_silent(self) -> None:
        """§9.3. Answering a round this skill is not a candidate for is
        non-conformant — the membership test is the skill's own job."""
        self.bus.emit(self._ping("some.other.skill"))
        self.assertEqual(self.pongs, [])
        self.assertEqual(self.skill.can_converse_calls, [],
                         "can_converse ran for a round this skill was not in")

    def test_decline_is_reported_as_result_false(self) -> None:
        self.skill.claims = False
        self.bus.emit(self._ping("converse.test"))
        self.assertFalse(self.pongs[0].data["result"])

    def test_both_legs_use_the_same_can_converse_gate(self) -> None:
        """FEATURE. Only the transport changes: the claim decision is the
        existing can_converse callback on both legs."""
        self.bus.emit(self._ping("converse.test"))
        self.bus.emit(self._ping("converse.test",
                                 topic="converse.test.converse.ping"))

        self.assertEqual(self.skill.can_converse_calls,
                         ["ovos.converse.ping", "converse.test.converse.ping"])
        self.assertEqual([p.msg_type for p in self.pongs],
                         ["ovos.converse.pong", "skill.converse.pong"])
        # legacy leg keeps its legacy field name
        self.assertTrue(self.pongs[1].data["can_handle"])

    def test_response_mode_holder_is_not_woken(self) -> None:
        """DEFECT (red before fix). A skill holding the response window is
        excluded from the round by the emitter, so its can_converse must not
        run — waking user code for a contest it was never entered in.
        """
        sess = Session("s")
        sess.activate_skill("converse.test")
        sess.set_response_mode("converse.test", time.time() + 300)
        ping = Message("ovos.converse.ping",
                       {"utterances": ["hello"], "lang": "en-US"},
                       {"session": sess.serialize()})
        self.bus.emit(ping)

        self.assertEqual(self.skill.can_converse_calls, [],
                         "can_converse ran for a skill core left out of the round")
        self.assertEqual(self.pongs, [])

    def test_another_skills_response_mode_does_not_exclude_us(self) -> None:
        """The exclusion is holder-specific, not a global mute."""
        sess = Session("s")
        sess.activate_skill("converse.test")
        sess.set_response_mode("some.other.skill", time.time() + 300)
        self.bus.emit(Message("ovos.converse.ping",
                              {"utterances": ["hello"], "lang": "en-US"},
                              {"session": sess.serialize()}))

        self.assertEqual(len(self.pongs), 1)
        self.assertTrue(self.pongs[0].data["result"])

    def test_candidacy_test_reads_only_canonical_fields(self) -> None:
        """DEFECT (red before fix). The candidacy test must read the canonical
        session fields.

        `active_skills` and `utterance_states` are deprecated views that log a
        WARNING every time they are read — once per ping, per skill, per
        utterance. Asserting on log records is unreliable here (the OVOS
        logger does not propagate to the stdlib root), so this booby-traps the
        deprecated properties instead: touching either one fails the test.
        """
        def _trap(name):
            def _raise(_self):
                raise AssertionError(f"candidacy test read deprecated {name}")
            return property(_raise)

        with patch.object(Session, "active_skills", _trap("active_skills")), \
             patch.object(Session, "utterance_states",
                          _trap("utterance_states")):
            self.bus.emit(self._ping("converse.test"))

        self.assertEqual(len(self.pongs), 1,
                         "the skill did not answer without the deprecated views")
