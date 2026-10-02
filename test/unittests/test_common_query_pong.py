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
import unittest

from ovos_bus_client import Message
from ovos_utils.fakebus import FakeBus

from ovos_workshop.decorators import common_query
from ovos_workshop.skills.ovos import OVOSSkill


class CommonQuerySkill(OVOSSkill):
    """A skill that registers a common_query handler (can answer)."""

    @common_query()
    def handle_common_query(self, utterance, lang):
        return "answer", 1.0


class PlainSkill(OVOSSkill):
    """A skill with no common_query handler (cannot answer)."""


class TestCommonQueryPong(unittest.TestCase):
    def _get_pongs(self, bus):
        return [m for m in bus.emitted_msgs
                if m.msg_type == "ovos.common_query.pong"]

    def _wire_capture(self, bus):
        bus.emitted_msgs = []
        bus.on("ovos.common_query.pong",
               lambda m: bus.emitted_msgs.append(m))

    def test_pong_carries_ratified_fields_for_can_answer_skill(self):
        bus = FakeBus()
        self._wire_capture(bus)
        skill = CommonQuerySkill(skill_id="cq.test", bus=bus)
        try:
            bus.emitted_msgs = []  # discard the registration-time pong
            bus.emit(Message("ovos.common_query.ping",
                              {"utterance": "what is the capital of france"}))

            pongs = self._get_pongs(bus)
            self.assertEqual(len(pongs), 1)
            data = pongs[0].data
            # ratified common-query.md §6.2 fields
            self.assertEqual(data["utterance"],
                              "what is the capital of france")
            self.assertEqual(data["skill_id"], "cq.test")
            self.assertIs(data["can_answer"], True)
            # pre-spec fields kept for one stable cycle (backcompat)
            self.assertEqual(data["is_classic_cq"], False)
        finally:
            skill.default_shutdown()

    def test_no_pong_for_skill_without_common_query_handler(self):
        bus = FakeBus()
        self._wire_capture(bus)
        skill = PlainSkill(skill_id="plain.test", bus=bus)
        try:
            bus.emitted_msgs = []
            bus.emit(Message("ovos.common_query.ping",
                              {"utterance": "what is the capital of france"}))

            self.assertEqual(len(self._get_pongs(bus)), 0)
        finally:
            skill.default_shutdown()


if __name__ == '__main__':
    unittest.main()
