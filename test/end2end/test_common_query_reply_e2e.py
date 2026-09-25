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
"""Real-bus end-to-end test proving a skill that answers a Common Query
replies on the legacy ``question:query.response`` topic, and only that
topic - not the never-emitted ``ovos.common_query.response`` spec topic -
through a real (mini) OVOS stack booted via ovoscope's ``MiniCroft``.
"""
import unittest

from ovos_bus_client.message import Message
from ovos_bus_client.session import SessionManager, Session
from ovos_utils.log import LOG
from ovos_workshop.decorators import common_query
from ovos_workshop.skills.ovos import OVOSSkill

from ovoscope import get_minicroft, CaptureSession

SKILL_ID = "test.common.query.e2e.skill"


class CommonQueryE2ESkill(OVOSSkill):
    @common_query()
    def handle_common_query(self, utterance, lang):
        return "Paris is the capital of France.", 1.0


class TestCommonQueryReplyE2E(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        LOG.set_level("ERROR")
        cls._saved_bus = SessionManager.bus
        cls.mc = get_minicroft([SKILL_ID],
                               extra_skills={SKILL_ID: CommonQueryE2ESkill})

    @classmethod
    def tearDownClass(cls):
        cls.mc.stop()
        SessionManager.bus = cls._saved_bus

    def test_answer_arrives_on_legacy_topic_only(self):
        sess = Session("e2e-common-query")
        sess.lang = "en-us"
        trigger = Message("question:query",
                          {"phrase": "capital of france"},
                          {"session": sess.serialize()})

        cap = CaptureSession(self.mc)
        cap.capture(trigger, timeout=15)
        msgs = cap.finish()

        legacy = [m for m in msgs if m.msg_type == "question:query.response"]
        spec = [m for m in msgs if m.msg_type == "ovos.common_query.response"]
        dead = [m for m in msgs if m.msg_type == "question:query.response.response"]

        self.assertTrue(legacy, "no reply on the legacy question:query.response topic")
        answered = [m for m in legacy if m.data.get("answer")]
        self.assertTrue(answered, f"no answer leg on legacy topic, saw: {legacy}")
        self.assertEqual(answered[0].data["answer"],
                          "Paris is the capital of France.")
        self.assertEqual(answered[0].data["skill_id"], SKILL_ID)

        self.assertEqual(spec, [],
                          "spec topic ovos.common_query.response must not be emitted")
        self.assertEqual(dead, [],
                          "dead .response.response topic must never appear")


if __name__ == '__main__':
    unittest.main()
