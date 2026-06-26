"""Namespace bus-message tests for OVOSSkill.

OVOSSkill emits each migrated event on exactly ONE topic — the OVOS spec
``ovos.*`` topic (sourced from ``ovos_spec_tools.SpecMessage``). It never
hand-rolls a dual-emit: the MessageBusClient / FakeBus namespace migration
(driven by ``ovos_spec_tools.MIGRATION_MAP``) transparently bridges the spec
topic to its legacy counterpart, so subscribers on EITHER namespace receive it.

These tests assert exactly that — a single spec emit is observed on both the
spec topic and its legacy counterpart — for the handler-lifecycle trio
(PIPELINE-1 §8), speak (§9.6) and the stop pong (STOP-1 §4.2).
"""
import unittest

from ovos_bus_client.message import Message
from ovos_spec_tools import SpecMessage
from ovos_utils.fakebus import FakeBus

from ovos_workshop.skills.ovos import OVOSSkill


class TestBusNamespace(unittest.TestCase):

    def setUp(self):
        # default flags (modernize + emit_legacy) bridge legacy<->ovos.*
        self.bus = FakeBus()
        self.skill = OVOSSkill(skill_id="test.skill", bus=self.bus)
        self.seen = set()
        for topic in ("speak", SpecMessage.SPEAK,
                      "skill.stop.pong", SpecMessage.STOP_PONG,
                      "mycroft.skill.handler.start", SpecMessage.INTENT_HANDLER_START):
            self.bus.on(topic, lambda m: self.seen.add(m.msg_type))

    # -- speak (PIPELINE-1 §9.6) ------------------------------------------
    def test_speak_emits_spec_and_bridges_legacy(self):
        self.skill.speak("hi")
        self.assertIn(SpecMessage.SPEAK, self.seen)   # spec topic emitted
        self.assertIn("speak", self.seen)             # bus bridged to legacy

    # -- stop pong (STOP-1 §4.2) ------------------------------------------
    def test_stop_pong_emits_spec_and_bridges_legacy(self):
        self.skill._handle_stop_ack(Message("ovos.stop.ping"))
        self.assertIn(SpecMessage.STOP_PONG, self.seen)
        self.assertIn("skill.stop.pong", self.seen)

    # -- handler trio (PIPELINE-1 §8) -------------------------------------
    def test_handler_start_emits_spec_and_bridges_legacy(self):
        self.skill._on_event_start(Message("test.skill:greet"),
                                   "mycroft.skill.handler", {"name": "h"})
        self.assertIn(SpecMessage.INTENT_HANDLER_START, self.seen)
        self.assertIn("mycroft.skill.handler.start", self.seen)


if __name__ == "__main__":
    unittest.main()
