# Copyright 2026 OpenVoiceOS
# Licensed under the Apache License, Version 2.0
"""End-to-end ovoscope test: ``speak_dialog`` rendering through the
spec-tools-backed path.

The new ``OVOSSkill.render_dialog`` resolves dialogs through
:class:`ovos_spec_tools.LocaleResources.load_dialog` and renders via
:func:`ovos_spec_tools.render`, threading the skill's vocabularies for
``<voc>`` reference substitution. This is the bread-and-butter skill
operation; silent breakage in the chain would render every dialog as
the dialog *filename* rather than the dialog text.

The fixture ships:

- ``locale/en-US/greet.dialog`` — ``Hello {name}, <salutation>`` (a
  slot and a vocab reference in one template).
- ``locale/en-US/salutation.voc`` — single phrase ``welcome aboard``.

A successful render produces ``Hello Alice, welcome aboard``.
"""
from threading import Event
from unittest import TestCase

import pytest

from ovos_bus_client.message import Message
from ovos_bus_client.session import Session

from ovos_workshop.skills.ovos import OVOSSkill

ovoscope = pytest.importorskip("ovoscope")


class _GreeterSkill(OVOSSkill):
    """Echoes the greeting back via ``speak_dialog`` when sent a
    ``greeter.greet`` bus message."""

    def initialize(self):
        self.add_event("greeter.greet", self._on_greet)

    def _on_greet(self, message):
        self.speak_dialog("greet", data={"name": message.data.get("name", "")})


class TestSpeakDialogE2E(TestCase):
    """``speak_dialog`` -> ``render_dialog`` -> ``LocaleResources.load_dialog``
    -> ``ovos_spec_tools.render`` -> bus ``speak`` message."""

    def setUp(self):
        self.skill_id = "greeter.openvoiceos"
        self.minicroft = ovoscope.get_minicroft(
            [self.skill_id],
            extra_skills={self.skill_id: _GreeterSkill},
            lang="en-US")

    def tearDown(self):
        if self.minicroft is not None:
            self.minicroft.stop()

    def test_speak_dialog_expands_slot_and_voc_reference(self):
        seen_speaks = []
        speak_event = Event()

        def on_speak(msg):
            utt = msg.data.get("utterance", "")
            seen_speaks.append(utt)
            # Gate the wait on the assertion target — protects against
            # any unrelated bus traffic that happens to emit `speak`.
            if "Alice" in utt:
                speak_event.set()

        self.minicroft.bus.on("speak", on_speak)

        session = Session("greet-1")
        session.lang = "en-US"
        msg = Message(
            "greeter.greet",
            {"name": "Alice"},
            context={"session": session.serialize(),
                     "source": "A", "destination": "B"})
        self.minicroft.inject_message(msg)

        self.assertTrue(
            speak_event.wait(timeout=10),
            "no speak message received — speak_dialog/render_dialog chain "
            "is broken")
        # The {name} slot resolves to "Alice" and the <salutation> voc
        # reference resolves to its single .voc entry.
        self.assertTrue(
            any("Alice" in s for s in seen_speaks),
            f"slot ``{{name}}`` not substituted; got: {seen_speaks}")
        self.assertTrue(
            any("welcome aboard" in s for s in seen_speaks),
            f"``<salutation>`` voc reference not resolved; got: "
            f"{seen_speaks}")
