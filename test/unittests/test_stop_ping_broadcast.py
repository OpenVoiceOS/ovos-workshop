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
"""OVOS-STOP-1 §4.2 stoppability poll on the broadcast `ovos.stop.ping`."""
import unittest

from ovos_bus_client import Message
from ovos_bus_client.session import Session
from ovos_utils.fakebus import FakeBus

from ovos_workshop.skills.ovos import OVOSSkill

SESSION_ID = "session-under-test"


class BusySkill(OVOSSkill):
    """A skill with stoppable activity for SESSION_ID and nothing else."""

    def can_stop(self, message):
        return Session.deserialize(
            message.context["session"]).session_id == SESSION_ID

    def stop(self):
        return True


def utterance_message(session_id=SESSION_ID, utterance_id="utt-1"):
    """An entry Message as PIPELINE-1 §9.1 stamps it, both pings derive from it."""
    context = {"source": "sat-7",
               "session": Session(session_id=session_id).serialize()}
    if utterance_id is not None:
        context["utterance_id"] = utterance_id
    return Message("recognizer_loop:utterance", {"utterances": ["stop"]},
                   context)


class TestStopPingBroadcast(unittest.TestCase):
    def setUp(self):
        self.bus = FakeBus()
        self.pongs = []
        self.bus.on("ovos.stop.pong", self.pongs.append)
        self.skill = BusySkill(skill_id="busy.test", bus=self.bus)
        self.pongs.clear()

    def tearDown(self):
        self.skill.default_shutdown()

    def test_broadcast_ping_answered_with_spec_payload(self):
        self.bus.emit(utterance_message().reply("ovos.stop.ping"))

        self.assertEqual(len(self.pongs), 1)
        self.assertEqual(self.pongs[0].data,
                         {"skill_id": "busy.test", "can_handle": True})

    def test_broadcast_and_per_skill_twin_draw_a_single_pong(self):
        utterance = utterance_message()
        self.bus.emit(utterance.reply("ovos.stop.ping"))
        self.bus.emit(utterance.forward("busy.test.stop.ping",
                                        {"skill_id": "busy.test"}))

        self.assertEqual(len(self.pongs), 1)
        self.assertIs(self.pongs[0].data["can_handle"], True)

    def test_no_activity_for_session_never_claims_can_handle(self):
        self.bus.emit(utterance_message("other-session").reply("ovos.stop.ping"))

        self.assertTrue(all(pong.data["can_handle"] is False
                            for pong in self.pongs))

    def test_per_skill_twin_alone_still_answers(self):
        self.bus.emit(utterance_message().forward(
            "busy.test.stop.ping", {"skill_id": "busy.test"}))

        self.assertEqual(len(self.pongs), 1)
        self.assertIs(self.pongs[0].data["can_handle"], True)

    def test_two_rounds_in_one_session_each_get_a_pong(self):
        """PIPELINE-1 §4.5 keys the round by session_id AND utterance_id."""
        for utterance_id in ("utt-1", "utt-2"):
            self.bus.emit(utterance_message(
                utterance_id=utterance_id).reply("ovos.stop.ping"))

        self.assertEqual(len(self.pongs), 2)

    def test_two_sessions_in_one_round_window_each_get_a_pong(self):
        for session_id in (SESSION_ID, "another-session"):
            self.bus.emit(utterance_message(
                session_id=session_id).reply("ovos.stop.ping"))

        self.assertEqual(len(self.pongs), 2)

    def test_pre_spec_core_stamping_no_utterance_id_is_answered_every_time(self):
        for _ in range(2):
            self.bus.emit(utterance_message(utterance_id=None).forward(
                "busy.test.stop.ping", {"skill_id": "busy.test"}))

        self.assertEqual(len(self.pongs), 2)


if __name__ == "__main__":
    unittest.main()
