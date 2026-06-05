"""Namespace bus-message tests for OVOSSkill.

Each skill-emitted event goes out in exactly one namespace, chosen by the
``legacy_namespace`` config (default True): the legacy ``mycroft.*`` topics or
the OVOS spec ``ovos.*`` topics. Both modes are covered for the handler trio
(PIPELINE-1 §8), speak (§9.6) and the stop pong (STOP-1 §4.2).
"""
import unittest

from ovos_bus_client.message import Message
from ovos_config.config import Configuration
from ovos_utils.fakebus import FakeBus

from ovos_workshop.skills.ovos import OVOSSkill


class TestBusNamespace(unittest.TestCase):

    def setUp(self):
        self.bus = FakeBus()
        self.skill = OVOSSkill(skill_id="test.skill", bus=self.bus)
        self.seen = set()
        for topic in ("speak", "ovos.utterance.speak",
                      "skill.stop.pong", "ovos.stop.pong",
                      "mycroft.skill.handler.start", "ovos.intent.handler.start"):
            self.bus.on(topic, lambda m: self.seen.add(m.msg_type))

    def tearDown(self):
        Configuration()["legacy_namespace"] = True

    # -- speak (PIPELINE-1 §9.6) ------------------------------------------
    def test_speak_legacy_namespace(self):
        Configuration()["legacy_namespace"] = True
        self.skill.speak("hi")
        self.assertIn("speak", self.seen)
        self.assertNotIn("ovos.utterance.speak", self.seen)

    def test_speak_spec_namespace(self):
        Configuration()["legacy_namespace"] = False
        self.skill.speak("hi")
        self.assertIn("ovos.utterance.speak", self.seen)
        self.assertNotIn("speak", self.seen)

    # -- stop pong (STOP-1 §4.2) ------------------------------------------
    def test_stop_pong_legacy_namespace(self):
        Configuration()["legacy_namespace"] = True
        self.skill._handle_stop_ack(Message("test.skill.stop.ping"))
        self.assertIn("skill.stop.pong", self.seen)
        self.assertNotIn("ovos.stop.pong", self.seen)

    def test_stop_pong_spec_namespace(self):
        Configuration()["legacy_namespace"] = False
        self.skill._handle_stop_ack(Message("ovos.stop.ping"))
        self.assertIn("ovos.stop.pong", self.seen)
        self.assertNotIn("skill.stop.pong", self.seen)

    # -- handler trio (PIPELINE-1 §8) -------------------------------------
    def test_handler_start_legacy_namespace(self):
        Configuration()["legacy_namespace"] = True
        self.skill._on_event_start(Message("test.skill:greet"),
                                   "mycroft.skill.handler", {"name": "h"})
        self.assertIn("mycroft.skill.handler.start", self.seen)
        self.assertNotIn("ovos.intent.handler.start", self.seen)

    def test_handler_start_spec_namespace(self):
        Configuration()["legacy_namespace"] = False
        self.skill._on_event_start(Message("test.skill:greet"),
                                   "mycroft.skill.handler", {"name": "h"})
        self.assertIn("ovos.intent.handler.start", self.seen)
        self.assertNotIn("mycroft.skill.handler.start", self.seen)


if __name__ == "__main__":
    unittest.main()
