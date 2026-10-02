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
        return "Paris is the capital of France.", 1.0


class SilentCommonQuerySkill(OVOSSkill):
    """A skill that registers a common_query handler but never matches."""

    @common_query()
    def handle_common_query(self, utterance, lang):
        return None, 0


class TestCommonQueryResponse(unittest.TestCase):
    """`question:query` contains a ':' and has no `.response` counterpart
    (OVOS-MSG-1 §5.3: `response()` "MUST NOT be used" on a topic that
    "contains ':'"). The handler answers via `message.reply(...)` on the
    legacy `question:query.response` topic only, which is what
    ovos-common-query-pipeline-plugin's `ovos_commonqa/opm.py` subscribes
    to. COMMON-QUERY-1's spec topic (`ovos.common_query.response`) is not
    emitted here: its payload key is `utterance`, not the `phrase` key
    this handler produces.
    """

    def _wire_capture(self, bus):
        bus.emitted_msgs = []
        bus.on("ovos.common_query.response",
               lambda m: bus.emitted_msgs.append(m))
        bus.on("question:query.response",
               lambda m: bus.emitted_msgs.append(m))

    def _by_topic(self, bus, topic):
        return [m for m in bus.emitted_msgs if m.msg_type == topic]

    def test_answering_skill_emits_only_legacy_topic_via_reply(self):
        bus = FakeBus()
        self._wire_capture(bus)
        skill = CommonQuerySkill(skill_id="cq.test", bus=bus)
        try:
            bus.emitted_msgs = []
            bus.emit(Message("question:query", {"phrase": "capital of france"}))

            legacy = self._by_topic(bus, "question:query.response")
            # searching=True, then the answer leg
            self.assertEqual(len(legacy), 2)

            searching, answered = legacy
            self.assertIs(searching.data["searching"], True)
            self.assertEqual(answered.data["skill_id"], "cq.test")
            self.assertEqual(answered.data["answer"],
                              "Paris is the capital of France.")
            self.assertEqual(answered.data["conf"], 1.0)

            # the spec topic is not emitted by this handler
            self.assertEqual(self._by_topic(bus, "ovos.common_query.response"), [])
            # dead topic never appears: no .response() dispatch-derivation
            self.assertEqual(self._by_topic(bus, "question:query.response.response"), [])
        finally:
            skill.default_shutdown()

    def test_no_answer_skill_emits_searching_false_on_legacy_topic(self):
        bus = FakeBus()
        self._wire_capture(bus)
        skill = SilentCommonQuerySkill(skill_id="cq.silent", bus=bus)
        try:
            bus.emitted_msgs = []
            bus.emit(Message("question:query", {"phrase": "capital of france"}))

            legacy = self._by_topic(bus, "question:query.response")
            self.assertEqual(len(legacy), 2)
            self.assertIs(legacy[1].data["searching"], False)

            self.assertEqual(self._by_topic(bus, "ovos.common_query.response"), [])
        finally:
            skill.default_shutdown()

    def test_handler_does_not_raise_on_colon_topic_request(self):
        """The request Message's topic (`question:query`) contains ':'.
        OVOS-MSG-1 §5.3 says `response()` "MUST NOT be used" on such a
        topic; the handler answers via `reply(...)` instead, which is
        unaffected by that restriction and must not raise.
        """
        bus = FakeBus()
        self._wire_capture(bus)
        skill = CommonQuerySkill(skill_id="cq.test", bus=bus)
        try:
            bus.emitted_msgs = []
            request = Message("question:query", {"phrase": "capital of france"})
            self.assertIn(":", request.msg_type)
            bus.emit(request)  # must not raise
            self.assertEqual(len(self._by_topic(bus, "question:query.response")), 2)
        finally:
            skill.default_shutdown()


if __name__ == '__main__':
    unittest.main()
