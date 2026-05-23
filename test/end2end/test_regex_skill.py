# Copyright 2026 OpenVoiceOS
# Licensed under the Apache License, Version 2.0
"""End-to-end ovoscope test: a skill shipping a ``.rx`` regex file matches
through Adapt and triggers its intent handler.

This test is intentionally a **tripwire**. ``.rx`` / regex support is the one
legacy resource type we kept (the rest were dropped in PR #413); when the time
comes to actually remove regex support — separately from, and later than, the
broader ``resource_files`` deprecation — this test breaks and forces us to
pause before the change lands.
"""
from threading import Event
from unittest import TestCase

import pytest

from ovos_bus_client.message import Message
from ovos_bus_client.session import Session

from ovos_workshop.intents import IntentBuilder
from ovos_workshop.skills.ovos import OVOSSkill

ovoscope = pytest.importorskip("ovoscope")


class _RegexTestSkill(OVOSSkill):
    """A test skill that ships ``test/end2end/locale/en-US/play.rx`` and
    exposes an Adapt intent built on the regex's named ``thing`` group.

    `OVOSSkill.root_dir` defaults to the directory of the module that defines
    the class — `test/end2end/` here — so the fixture is found automatically
    by `load_regex_files`.
    """

    def initialize(self):
        # group name is the alphanumeric skill id + the regex group name —
        # this is exactly what OVOSSkill.load_regex_files prefixes onto each
        # `(?P<...>...)` in the .rx file
        group = self.alphanumeric_skill_id + "thing"
        intent = IntentBuilder("PlayIntent").require(group).build()
        self.register_intent(intent, self.handle_play)

    def handle_play(self, message):
        # the captured entity may live under either the prefixed or bare group
        # name depending on adapt internals; check both so the speak content
        # also pins the regex *capture* end-to-end, not just the handler firing
        d = message.data
        thing = (d.get(self.alphanumeric_skill_id + "thing")
                 or d.get("thing")
                 or next((v for k, v in d.items()
                          if isinstance(v, str) and "thing" in k), "?"))
        self.speak(f"playing {thing}")


class TestRegexSkillE2E(TestCase):
    """Regex-via-Adapt end-to-end tripwire."""

    def setUp(self):
        self.skill_id = "regextest.openvoiceos"
        # ovoscope's auto-default pipeline downgrades to LIGHT (no adapt) when
        # padatious / common-query are not importable — pass an explicit
        # adapt-only pipeline so this test actually exercises adapt's regex.
        adapt_pipeline = ["ovos-adapt-pipeline-plugin-high",
                          "ovos-adapt-pipeline-plugin-medium",
                          "ovos-adapt-pipeline-plugin-low"]
        # Adapt's confidence for a regex-only intent with a single named group
        # is low (~0.07 — adapt scales it by the entity count / utterance
        # weight). Lower the per-tier thresholds so the low-tier still fires.
        self.minicroft = ovoscope.get_minicroft(
            [self.skill_id],
            extra_skills={self.skill_id: _RegexTestSkill},
            default_pipeline=adapt_pipeline,
            lang="en-US",
            pipeline_config={
                "ovos-adapt-pipeline-plugin": {
                    "conf_high": 0.05,
                    "conf_med": 0.05,
                    "conf_low": 0.05}})

    def tearDown(self):
        if self.minicroft is not None:
            self.minicroft.stop()

    def test_regex_intent_fires_for_matching_utterance(self):
        """`play music please` matches the .rx pattern, Adapt fires the
        intent, the handler runs and emits a speak with the captured group."""
        seen_speaks = []
        speak_event = Event()

        def on_speak(msg):
            seen_speaks.append(msg.data.get("utterance", ""))
            speak_event.set()

        self.minicroft.bus.on("speak", on_speak)

        session = Session("rxtest")
        session.lang = "en-US"
        # pin the per-session pipeline to adapt — the regex match is an Adapt
        # feature, the default pipeline would also try padatious/fallback and
        # we want a clean "if adapt doesn't fire, the test fails" assertion
        session.pipeline = ["ovos-adapt-pipeline-plugin-high",
                            "ovos-adapt-pipeline-plugin-medium",
                            "ovos-adapt-pipeline-plugin-low"]
        utterance = Message(
            "recognizer_loop:utterance",
            {"utterances": ["play music please"], "lang": "en-US"},
            context={"session": session.serialize(),
                     "source": "A", "destination": "B"})
        self.minicroft.inject_message(utterance)

        # adapt + intent handler should run within a few seconds
        self.assertTrue(
            speak_event.wait(timeout=10),
            "no speak message received — the .rx pattern did not produce an "
            "intent match; regex support may be broken")
        self.assertTrue(
            any("playing music" in s for s in seen_speaks),
            f"expected `speak` with the captured `music`; got: {seen_speaks}")
