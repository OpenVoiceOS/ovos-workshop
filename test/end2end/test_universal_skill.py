# Copyright 2026 OpenVoiceOS
# Licensed under the Apache License, Version 2.0
"""End-to-end ovoscope test: :class:`UniversalSkill` resource lookups
follow ``internal_language``, not the incoming query language.

A UniversalSkill author writes ``.dialog`` / ``.voc`` files in the skill's
internal working language and lets the framework translate utterances in and
out. The :attr:`OVOSSkill._resource_lang` extension point lets the loader
target the internal language for every lookup, so:

* a query in **any** language still finds the dialog and voc resources;
* :meth:`speak_dialog` renders the right phrase;
* :meth:`voc_match` matches against the internal-language vocab.

This test is intentionally a **tripwire** — the lang-decoupling is the
defining behaviour of UniversalSkill, and a regression would silently leave
dialogs unresolved (skill speaks the literal dialog name) and voc checks
returning ``False``.
"""
import os
from threading import Event
from unittest import TestCase

import pytest

from ovos_bus_client.message import Message
from ovos_bus_client.session import Session

from ovos_workshop.skills.auto_translatable import UniversalSkill

ovoscope = pytest.importorskip("ovoscope")

# Each skill author writes resources in their working language; this skill
# author writes English. Locale dir is shared with the regex e2e test —
# `universal_locale/` keeps the two fixtures cleanly separated.
_FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "universal_locale")


class _EchoUniversalSkill(UniversalSkill):
    """Internal language = en-US. A handler renders ``echo.dialog`` and the
    spoken phrase is captured on the bus."""

    def __init__(self, *args, **kwargs):
        super().__init__(internal_language="en-US", *args, **kwargs)
        # point load_lang at the fixture tree this test ships
        self.res_dir = _FIXTURE_DIR
        # rebind LocaleResources to the fixture tree, since __init__ ran
        # before res_dir was overridden
        from ovos_spec_tools import LocaleResources
        self._locale_resources = LocaleResources(self.res_dir)

    def translate_utterance(self, text, target_lang, sauce_lang=None):
        """No-op the translator — the test environment has no plugin and
        we want to assert on the *internal-language* phrasing anyway."""
        return text

    def translate_message(self, message):
        # ditto on the inbound side; we control the test inputs and don't
        # need the translator to be loaded.
        return message

    def initialize(self):
        self.add_event("test.universal.echo", self.handle_echo)
        self.add_event("test.universal.voc_check", self.handle_voc_check)

    def handle_echo(self, message):
        # Should find en-US/echo.dialog and render "echo: <text>" regardless
        # of the query lang carried on the message.
        text = message.data.get("text", "?")
        self.speak_dialog("echo", {"text": text})

    def handle_voc_check(self, message):
        # voc_match consults en-US/affirmative.voc; query lang on the
        # message is irrelevant because _resource_lang points at en-US.
        utt = message.data.get("utt", "")
        result = self.voc_match(utt, "affirmative")
        self.bus.emit(message.reply(
            "test.universal.voc_check.response", {"matched": result}))


class TestUniversalSkillResourceLang(TestCase):
    """Resource lookups target internal_language regardless of query lang."""

    def setUp(self):
        self.skill_id = "univtest.openvoiceos"
        self.minicroft = ovoscope.get_minicroft(
            [self.skill_id],
            extra_skills={self.skill_id: _EchoUniversalSkill})

    def tearDown(self):
        if self.minicroft is not None:
            self.minicroft.stop()

    # --- the property is what we say it is -----------------------------------

    def test_resource_lang_points_at_internal_language(self):
        """The override is the load-bearing single point — pin it."""
        skill = self.minicroft.plugin_skills[self.skill_id].instance
        self.assertEqual(skill._resource_lang, "en-US")
        self.assertEqual(skill.internal_language, "en-US")

    # --- dialog rendering follows internal_language --------------------------

    def test_speak_dialog_renders_internal_lang_resource_for_foreign_query(self):
        """A speak from a UniversalSkill handler renders the en-US dialog
        even when the message's query lang is es-ES."""
        spoken = []
        event = Event()

        def on_speak(msg):
            spoken.append(msg.data.get("utterance", ""))
            event.set()

        self.minicroft.bus.on("speak", on_speak)

        session = Session("uni-rxtest")
        session.lang = "es-ES"
        msg = Message(
            "test.universal.echo",
            {"text": "world"},
            context={"session": session.serialize(),
                     "source": "A", "destination": "B"})
        self.minicroft.inject_message(msg)

        self.assertTrue(event.wait(timeout=10),
                        f"no speak emitted within timeout; got {spoken!r}")
        # The dialog rendered to "echo: world"; even if the translator no-ops
        # (no plugin available in the test env), the en-US phrasing survives.
        self.assertTrue(
            any("world" in s for s in spoken),
            f"expected speak to carry the rendered text 'world'; got {spoken!r}")

    # --- voc_match follows internal_language ---------------------------------

    def test_voc_match_uses_internal_language_for_foreign_query(self):
        """voc_match("yes", "affirmative") fires from a query whose session
        lang is fr-FR, because the voc is en-US and _resource_lang points
        there."""
        responses = []
        event = Event()

        def on_response(msg):
            responses.append(msg.data.get("matched"))
            event.set()

        self.minicroft.bus.on("test.universal.voc_check.response", on_response)

        session = Session("uni-rxtest")
        session.lang = "fr-FR"
        msg = Message(
            "test.universal.voc_check",
            {"utt": "yes, please"},
            context={"session": session.serialize(),
                     "source": "A", "destination": "B"})
        self.minicroft.inject_message(msg)

        self.assertTrue(event.wait(timeout=10),
                        "no voc_check response; handler likely did not fire")
        self.assertEqual(
            responses, [True],
            "voc_match returned False — _resource_lang likely fell back to "
            "the query lang (fr-FR) instead of internal_language (en-US)")
