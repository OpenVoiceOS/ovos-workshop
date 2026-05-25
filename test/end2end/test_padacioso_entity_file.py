# Copyright 2026 OpenVoiceOS
# Licensed under the Apache License, Version 2.0
"""End-to-end ovoscope test: ``register_entity_file`` registers a constrained
slot value-set through ``_locate_lang_file`` and pads an intent's slot
matching to only the entity's enumerated values.

Companion to ``test_padacioso_intent_file.py``: same resolver, different
resource role. The fixture ships:

- ``locale/en-US/order.intent`` — three samples using a ``{drink}`` slot.
- ``locale/en-US/drink.entity`` — ``coffee``/``tea``/``juice``.

A successful match captures the ``{drink}`` slot. The handler echoes it
in its speak so the assert can confirm the slot was filled (slot fill
fails if the entity wasn't registered, because the bare ``{drink}``
slot would either fail to match or capture the wrong span).
"""
from threading import Event
from unittest import TestCase

import pytest

from ovos_bus_client.message import Message
from ovos_bus_client.session import Session

from ovos_workshop.skills.ovos import OVOSSkill

ovoscope = pytest.importorskip("ovoscope")


class _OrderSkill(OVOSSkill):

    def initialize(self):
        self.register_entity_file("drink.entity")
        self.register_intent_file("order.intent", self._on_order)

    def _on_order(self, message):
        drink = message.data.get("drink", "<empty>")
        self.speak(f"ordering {drink}")


class TestPadaciosoEntityFileE2E(TestCase):

    def setUp(self):
        self.skill_id = "order.openvoiceos"
        padacioso = ["ovos-padacioso-pipeline-plugin-high",
                     "ovos-padacioso-pipeline-plugin-medium",
                     "ovos-padacioso-pipeline-plugin-low"]
        self.minicroft = ovoscope.get_minicroft(
            [self.skill_id],
            extra_skills={self.skill_id: _OrderSkill},
            default_pipeline=padacioso,
            lang="en-US")

    def tearDown(self):
        if self.minicroft is not None:
            self.minicroft.stop()

    def test_entity_constrained_slot_fills_from_entity_file(self):
        seen_speaks = []
        speak_event = Event()

        def on_speak(msg):
            seen_speaks.append(msg.data.get("utterance", ""))
            speak_event.set()

        self.minicroft.bus.on("speak", on_speak)

        session = Session("order-1")
        session.lang = "en-US"
        session.pipeline = ["ovos-padacioso-pipeline-plugin-high",
                            "ovos-padacioso-pipeline-plugin-medium",
                            "ovos-padacioso-pipeline-plugin-low"]
        utterance = Message(
            "recognizer_loop:utterance",
            {"utterances": ["i want a coffee"], "lang": "en-US"},
            context={"session": session.serialize(),
                     "source": "A", "destination": "B"})
        self.minicroft.inject_message(utterance)

        self.assertTrue(
            speak_event.wait(timeout=15),
            "no speak message — register_entity_file path "
            "(_locate_lang_file resolving the .entity) is broken")
        self.assertTrue(
            any("ordering coffee" in s for s in seen_speaks),
            f"slot ``{{drink}}`` not filled from drink.entity; "
            f"got: {seen_speaks}")
