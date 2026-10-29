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
"""Plain skills decline the converse poll.

ovos-core makes every dispatched skill a converse candidate and waits for ALL candidates to answer (up to 0.5 s).
Before #339 every OVOSSkill answered "no"; after it, plain skills stayed silent and every utterance waited out the
timeout. These tests pin the restored answer, and that ConversationalSkill still gives only its real one.
"""
import time
import unittest

from ovos_bus_client import Message
from ovos_bus_client.session import Session
from ovos_utils.fakebus import FakeBus

from ovos_workshop.skills.converse import ConversationalSkill
from ovos_workshop.skills.ovos import OVOSSkill


class PlainSkill(OVOSSkill):
    """No converse support."""


class TalkativeSkill(ConversationalSkill):
    """Always wants to converse."""

    def can_converse(self, message):
        return True


def ping(topic, candidates, data=None):
    """A converse ping derived from an utterance whose session names `candidates`."""
    session = Session(session_id="s1")
    session.converse_handlers = [{"skill_id": s, "activated_at": time.time()} for s in candidates]
    entry = Message("recognizer_loop:utterance", {"utterances": ["yes"]},
                    {"session": session.serialize(), "utterance_id": "utt-1"})
    return entry.reply(topic, data or {})


class TestPlainSkillDeclinesConverse(unittest.TestCase):
    def setUp(self):
        self.bus = FakeBus()
        self.pongs = []
        self.bus.on("ovos.converse.pong", self.pongs.append)
        self.bus.on("skill.converse.pong", self.pongs.append)
        self.skills = []

    def tearDown(self):
        for skill in self.skills:
            skill.default_shutdown()

    def load(self, cls, skill_id):
        skill = cls(skill_id=skill_id, bus=self.bus)
        self.skills.append(skill)
        self.pongs.clear()
        return skill

    def test_named_plain_skill_declines_the_broadcast_poll(self):
        self.load(PlainSkill, "plain.test")
        self.bus.emit(ping("ovos.converse.ping", ["plain.test"]))
        self.assertEqual([(p.msg_type, p.data) for p in self.pongs],
                         [("ovos.converse.pong", {"skill_id": "plain.test", "result": False})])
        self.assertEqual(self.pongs[0].context.get("utterance_id"), "utt-1", "core discards pongs without it")

    def test_unnamed_plain_skill_stays_silent(self):
        self.load(PlainSkill, "plain.test")
        self.bus.emit(ping("ovos.converse.ping", ["someone.else"]))
        self.assertEqual(self.pongs, [])

    def test_plain_skill_declines_the_per_skill_ping(self):
        self.load(PlainSkill, "plain.test")
        self.bus.emit(ping("plain.test.converse.ping", ["plain.test"], {"skill_id": "plain.test"}))
        self.assertEqual([(p.msg_type, p.data) for p in self.pongs],
                         [("skill.converse.pong", {"skill_id": "plain.test", "can_handle": False})])

    def test_conversational_skill_gives_only_its_real_answer(self):
        self.load(TalkativeSkill, "talk.test")
        self.bus.emit(ping("ovos.converse.ping", ["talk.test"]))
        self.assertEqual([p.data for p in self.pongs], [{"skill_id": "talk.test", "result": True}])


if __name__ == "__main__":
    unittest.main()
