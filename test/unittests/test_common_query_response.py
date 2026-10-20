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
import inspect
import logging
import unittest
from contextlib import contextmanager
from unittest.mock import patch

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


class _Records(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.WARNING)
        self.records = []

    def emit(self, record):
        self.records.append(record)


@contextmanager
def response_is_never_called():
    """Fail if the code under test calls `Message.response()` or if
    ovos-spec-tools logs a WARNING on `ovos_spec_tools.message`. This holds
    whatever the installed ovos-spec-tools does with `response()` on a
    dispatch topic (raise, warn or pass).
    """
    logger = logging.getLogger("ovos_spec_tools.message")
    handler = _Records()
    logger.addHandler(handler)
    try:
        with patch.object(
                Message, "response",
                side_effect=AssertionError(
                    "response() must not be called on question:query")
        ) as response:
            yield
        assert response.call_count == 0, \
            "response() was called on question:query"
        assert not handler.records, \
            f"ovos_spec_tools.message logged: {handler.records}"
    finally:
        logger.removeHandler(handler)


class TestCommonQueryResponse(unittest.TestCase):
    """`question:query` contains a ':' and has no `.response` counterpart
    (OVOS-MSG-1 §5.3: "A dispatch topic (§2.1.1) has no `.response`
    counterpart"). The handler names the answering topic and derives it
    with `message.reply(...)` on the legacy `question:query.response`
    topic only, which is what ovos-common-query-pipeline-plugin's
    `ovos_commonqa/opm.py` subscribes to. COMMON-QUERY-1's spec topic
    (`ovos.common_query.response`) is not emitted here: its payload key is
    `utterance`, not the `phrase` key this handler produces.

    `Message` is the ovos-spec-tools class (see `test_message_is_spec_tools`).
    """

    def test_message_is_spec_tools(self):
        self.assertIn("ovos_spec_tools", inspect.getfile(Message))

    def _wire_capture(self, bus):
        bus.emitted_msgs = []
        for topic in ("ovos.common_query.response",
                      "question:query.response",
                      "question:query.response.response"):
            bus.on(topic, lambda m: bus.emitted_msgs.append(m))

    def _by_topic(self, bus, topic):
        return [m for m in bus.emitted_msgs if m.msg_type == topic]

    def test_answering_skill_emits_only_legacy_topic_via_reply(self):
        bus = FakeBus()
        self._wire_capture(bus)
        skill = CommonQuerySkill(skill_id="cq.test", bus=bus)
        try:
            bus.emitted_msgs = []
            with response_is_never_called():
                bus.emit(Message("question:query",
                                 {"phrase": "capital of france"}))

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
            # the captured topic set includes question:query.response.response
            self.assertEqual(self._by_topic(bus, "question:query.response.response"), [])
        finally:
            skill.default_shutdown()

    def test_no_answer_skill_emits_searching_false_on_legacy_topic(self):
        bus = FakeBus()
        self._wire_capture(bus)
        skill = SilentCommonQuerySkill(skill_id="cq.silent", bus=bus)
        try:
            bus.emitted_msgs = []
            with response_is_never_called():
                bus.emit(Message("question:query",
                                 {"phrase": "capital of france"}))

            legacy = self._by_topic(bus, "question:query.response")
            self.assertEqual(len(legacy), 2)
            self.assertIs(legacy[1].data["searching"], False)

            self.assertEqual(self._by_topic(bus, "ovos.common_query.response"), [])
        finally:
            skill.default_shutdown()

    def test_handler_does_not_raise_on_colon_topic_request(self):
        """The request Message's topic (`question:query`) contains ':', so
        the §5.3 shorthand is undefined for it. The handler names the
        answering topic and derives it with `reply(...)`, which does not
        raise.
        """
        bus = FakeBus()
        self._wire_capture(bus)
        skill = CommonQuerySkill(skill_id="cq.test", bus=bus)
        try:
            bus.emitted_msgs = []
            request = Message("question:query", {"phrase": "capital of france"})
            self.assertIn(":", request.msg_type)
            with response_is_never_called():
                bus.emit(request)  # must not raise
            self.assertEqual(len(self._by_topic(bus, "question:query.response")), 2)
        finally:
            skill.default_shutdown()


if __name__ == '__main__':
    unittest.main()
