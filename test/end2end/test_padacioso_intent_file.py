# Copyright 2026 OpenVoiceOS
# Licensed under the Apache License, Version 2.0
"""End-to-end ovoscope test: ``register_intent_file`` round-trips through
the new ``_locate_lang_file`` resolver and triggers an intent match.

``OVOSSkill._locate_lang_file`` is the private helper introduced in PR #413
that resolves ``<lang>/<name>.intent`` (and ``.entity``) under the skill's
``locale/`` tree via :func:`ovos_spec_tools.closest_lang` + ``os.walk``.
The resolved file path is then handed to whichever intent engine the
pipeline runs — here padacioso, which is always available (pure Python,
no native deps).

The fixture ships ``locale/en-US/wave.intent`` with four utterance
samples; sending ``wave hello`` should fire the registered handler.
"""
from threading import Event
from unittest import TestCase

import pytest

from ovos_bus_client.message import Message
from ovos_bus_client.session import Session

from ovos_workshop.skills.ovos import OVOSSkill

ovoscope = pytest.importorskip("ovoscope")


class _WaveSkill(OVOSSkill):
    """Registers ``wave.intent`` via ``register_intent_file`` and speaks
    a confirmation on match."""

    def initialize(self):
        self.register_intent_file("wave.intent", self._on_wave)

    def _on_wave(self, message):
        self.speak("waving back")


class TestPadaciosoIntentFileE2E(TestCase):
    """``register_intent_file`` -> ``_locate_lang_file`` ->
    padacioso registration -> bus match."""

    def setUp(self):
        self.skill_id = "wave.openvoiceos"
        # padacioso-only pipeline so the test pins THIS path; if the
        # intent doesn't match, the failure mode is unambiguous.
        padacioso = ["ovos-padacioso-pipeline-plugin-high",
                     "ovos-padacioso-pipeline-plugin-medium",
                     "ovos-padacioso-pipeline-plugin-low"]
        self.minicroft = ovoscope.get_minicroft(
            [self.skill_id],
            extra_skills={self.skill_id: _WaveSkill},
            default_pipeline=padacioso,
            lang="en-US")

    def tearDown(self):
        if self.minicroft is not None:
            self.minicroft.stop()

    def test_intent_file_match_fires_handler(self):
        seen_speaks = []
        speak_event = Event()

        def on_speak(msg):
            utt = msg.data.get("utterance", "")
            seen_speaks.append(utt)
            if "waving back" in utt:
                speak_event.set()

        self.minicroft.bus.on("speak", on_speak)

        session = Session("wave-1")
        session.lang = "en-US"
        session.pipeline = ["ovos-padacioso-pipeline-plugin-high",
                            "ovos-padacioso-pipeline-plugin-medium",
                            "ovos-padacioso-pipeline-plugin-low"]
        utterance = Message(
            "recognizer_loop:utterance",
            {"utterances": ["wave hello"], "lang": "en-US"},
            context={"session": session.serialize(),
                     "source": "A", "destination": "B"})
        self.minicroft.inject_message(utterance)

        self.assertTrue(
            speak_event.wait(timeout=15),
            "no speak message received — ``register_intent_file`` did not "
            "register a matchable intent (``_locate_lang_file`` resolver "
            "may be broken)")
        self.assertTrue(
            any("waving back" in s for s in seen_speaks),
            f"expected `speak` with `waving back`; got: {seen_speaks}")
