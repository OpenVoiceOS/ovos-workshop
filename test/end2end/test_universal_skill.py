# Copyright 2026 OpenVoiceOS
# Licensed under the Apache License, Version 2.0
"""End-to-end ovoscope test: :class:`UniversalSkill` resource lookups
follow ``internal_language``, not the incoming query language.

The realistic motivating scenario is a skill backed by an English-only
external API — Wolfram Alpha, animal facts, a weather provider — that an
OVOS user can still address in any language. The skill author writes
``.intent`` / ``.dialog`` / ``.voc`` files in English (``internal_language``);
incoming utterances are translated *into* English before the handler runs,
and outgoing speech is translated back to the user's language by
:meth:`UniversalSkill.speak`.

The lang-decoupling is the **defining behaviour** of UniversalSkill, and a
regression would silently strand dialogs (skill speaks the literal dialog
name) and break vocab checks. This module is a tripwire over the three
public surfaces — :attr:`OVOSSkill._resource_lang`, :meth:`speak_dialog`,
and :meth:`voc_match` — plus one full round-trip simulating the real-world
flow with deterministic stubs (no network, no real translator plugin).
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
# author writes English. Fixture tree shipped alongside the test module.
_FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "universal_locale")


# A small, deterministic, offline "translation table" stands in for the
# real translator plugin: the test pins exact phrasing on both sides of
# the boundary without needing network or a model. Keys are the source
# string; ``(source_lang, target_lang)`` selects the direction.
# Bidirectional, deterministic translation stub. UniversalSkill drives
# translation **inside the skill** in both directions: the inbound handler
# wrapper translates message slots into ``internal_language`` before the
# callback runs, and :meth:`UniversalSkill.speak` translates outbound text
# from ``internal_language`` to the user's session lang. The test pins
# both legs.
#
# NB: ovos_bus_client.Session.deserialize folds the session lang through
# ovos_utils.lang.standardize_lang_tag (whose old macro=True default still
# lives in the bundled release), so a session lang of "pt-PT" reaches the
# handler as "pt". Keys reflect what the runtime actually delivers.
_FAKE_TRANSLATIONS = {
    # inbound: Portuguese → English (the user's slot lands here)
    ("gatos", "pt", "en-US"): "cats",
    # outbound: English → Portuguese (the skill's reply lands here)
    ("Cats sleep up to sixteen hours a day.", "en-US", "pt"):
        "Os gatos dormem até dezasseis horas por dia.",
    ("I do not know about that animal.", "en-US", "pt"):
        "Não conheço esse animal.",
}


class _AnimalFactsUniversalSkill(UniversalSkill):
    """An English-only "animal facts" skill: API returns English; the
    skill author wrote the .intent file in English; users may ask in any
    language and get the reply in their own language."""

    # Stand-in for the external API — a static dict keeps the test
    # hermetic. A real skill would call out to Wolfram / a facts service.
    _FAKE_API = {
        "cat": "Cats sleep up to sixteen hours a day.",
        "cats": "Cats sleep up to sixteen hours a day.",
    }

    def __init__(self, *args, **kwargs):
        # resources_dir is honoured at __init__ time (before _startup
        # runs initialize); pass it through so register_intent_file
        # finds fact.intent in the fixture tree.
        kwargs.setdefault("resources_dir", _FIXTURE_DIR)
        # The handler reads a captured ``animal`` slot; tell
        # translate_message to fold that key into internal_language too,
        # alongside the default ``utterance`` / ``utterances`` keys.
        kwargs.setdefault("translate_keys",
                          ["animal", "utterance", "utterances"])
        super().__init__(internal_language="en-US", *args, **kwargs)

    # --- stubbed translation (no plugin, no network) ----------------------
    #
    # UniversalSkill drives translation inside the skill in both
    # directions: translate_message folds incoming text to
    # internal_language before the wrapped handler fires, and speak()
    # translates outgoing text from internal_language to the user's
    # session lang. Both legs route through translate_utterance, so the
    # stub override is enough to control the whole table.

    def translate_utterance(self, text, target_lang, sauce_lang=None):
        sauce_lang = sauce_lang or self.internal_language
        # exact-key lookup against the test's deterministic table; fall
        # through to the source text so an untranslated branch surfaces
        # in test failure output instead of silently no-oping.
        return _FAKE_TRANSLATIONS.get((text, sauce_lang, target_lang), text)

    # --- skill surface ----------------------------------------------------
    def initialize(self):
        self.register_intent_file("fact.intent", self.handle_fact)
        # also expose direct event handlers for the two narrower
        # tripwire assertions (no intent pipeline needed)
        self.add_event("test.universal.voc_check", self.handle_voc_check)
        self.add_event("test.universal.dialog_check", self.handle_dialog_check)

    def handle_fact(self, message):
        # The handler always receives the slot in ``internal_language``:
        # UniversalSkill's universal_intent_handler wrapper ran
        # translate_message on the way in, so a Portuguese "gatos" arrives
        # here as "cats". The handler calls the English-only API directly
        # and lets UniversalSkill.speak translate the reply back to the
        # user's session lang on the way out.
        animal = (message.data.get("animal") or "").lower().strip()
        # record what the handler saw so the test can assert on the
        # inbound translation as well as the outbound speak.
        self._last_animal_seen = animal
        fact = self._FAKE_API.get(animal, "I do not know about that animal.")
        self.speak(fact)

    def handle_voc_check(self, message):
        # Pins that voc_match consults the en-US affirmative.voc even
        # when the message's query lang is foreign.
        utt = message.data.get("utt", "")
        self.bus.emit(message.reply(
            "test.universal.voc_check.response",
            {"matched": self.voc_match(utt, "affirmative")}))

    def handle_dialog_check(self, message):
        # Pins that speak_dialog resolves the en-US echo.dialog
        # regardless of session lang.
        self.speak_dialog("echo", {"text": message.data.get("text", "")})


class TestUniversalSkillResourceLang(TestCase):
    """The three legs of the contract: the override returns the right
    value, dialogs render from internal_language, voc_match queries
    internal_language. Plus a real-world API round-trip."""

    def setUp(self):
        self.skill_id = "univtest.openvoiceos"
        # explicit lang="en-US" — Configuration().lang controls native_langs
        # on the skill, which controls which language the .intent file
        # registers under. The skill ships en-US only.
        self.minicroft = ovoscope.get_minicroft(
            [self.skill_id],
            extra_skills={self.skill_id: _AnimalFactsUniversalSkill},
            lang="en-US")

    def tearDown(self):
        if self.minicroft is not None:
            self.minicroft.stop()

    def _skill(self):
        return self.minicroft.plugin_skills[self.skill_id].instance

    # --- the override itself ----------------------------------------------

    def test_resource_lang_points_at_internal_language(self):
        skill = self._skill()
        self.assertEqual(skill._resource_lang, "en-US")
        self.assertEqual(skill.internal_language, "en-US")

    # --- dialog rendering follows internal_language -----------------------

    def test_speak_dialog_renders_internal_lang_resource_for_foreign_query(self):
        """A speak_dialog from a UniversalSkill handler renders the en-US
        ``.dialog`` even when the message session lang is es-ES."""
        spoken = []
        event = Event()
        self.minicroft.bus.on("speak", lambda m: (
            spoken.append(m.data.get("utterance", "")), event.set()))

        session = Session("uni-dialog")
        session.lang = "es-ES"
        self.minicroft.inject_message(Message(
            "test.universal.dialog_check",
            {"text": "world"},
            context={"session": session.serialize(),
                     "source": "A", "destination": "B"}))

        self.assertTrue(event.wait(timeout=10),
                        f"no speak within timeout; got {spoken!r}")
        self.assertTrue(
            any("world" in s for s in spoken),
            f"expected dialog text 'world' in {spoken!r}")

    # --- voc_match follows internal_language ------------------------------

    def test_voc_match_uses_internal_language_for_foreign_query(self):
        """voc_match("yes please", "affirmative") fires from a fr-FR session
        because the voc is en-US and _resource_lang points there."""
        responses = []
        event = Event()
        self.minicroft.bus.on(
            "test.universal.voc_check.response",
            lambda m: (responses.append(m.data.get("matched")), event.set()))

        session = Session("uni-voc")
        session.lang = "fr-FR"
        self.minicroft.inject_message(Message(
            "test.universal.voc_check",
            {"utt": "yes, please"},
            context={"session": session.serialize(),
                     "source": "A", "destination": "B"}))

        self.assertTrue(event.wait(timeout=10),
                        "no voc_check response — handler did not fire")
        self.assertEqual(
            responses, [True],
            "voc_match returned False — _resource_lang likely fell back to "
            "the query lang (fr-FR) instead of internal_language (en-US)")

    # --- realistic full round-trip ----------------------------------------

    def test_realistic_english_only_api_roundtrip_to_portuguese(self):
        """Wolfram-style English-only skill addressed from Portuguese.

        UniversalSkill drives translation **inside the skill** in both
        directions: the inbound wrapper translates the captured slot into
        ``internal_language`` before the callback runs, the callback hits
        the English API, and :meth:`UniversalSkill.speak` translates the
        reply back to the user's session lang on the way out.

        Failure modes this test catches:

        * intent file resolved against the wrong language → registration
          fails with ``Unable to find fact.intent``;
        * the inbound translation step is bypassed → the handler sees
          the Portuguese slot and the API lookup misses;
        * the outbound translation step is dropped → the user gets an
          English reply.
        """
        # Step 1: the intent file registered against the en-US tree.
        # `Unable to find fact.intent` would have logged otherwise.
        self.assertTrue(
            any("fact.intent" in str(name) for name in
                self.minicroft.bus.ee.event_names()),
            "fact.intent did not register against the en-US fixture; "
            "_resource_lang → LocaleResources.find could not resolve it")

        # Step 2: emit the intent-match event with a *Portuguese* slot —
        # that is what a hypothetical pt-PT intent matcher would capture.
        # The UniversalSkill handler wrapper translates `animal: "gatos"`
        # → `"cats"` before our callback runs; the callback then calls
        # the English API and `speak` translates the reply on the way out.
        spoken = []
        event = Event()
        self.minicroft.bus.on("speak", lambda m: (
            spoken.append(m.data.get("utterance", "")), event.set()))

        session = Session("uni-roundtrip")
        session.lang = "pt-PT"  # user speaks Portuguese
        self.minicroft.inject_message(Message(
            f"{self.skill_id}:fact.intent",
            # Portuguese slot — exactly what a pt-PT intent matcher would
            # have captured. The UniversalSkill wrapper translates it
            # into ``internal_language`` (en-US) before our handler runs.
            {"animal": "gatos",
             "utterance": "conta-me um facto sobre gatos"},
            context={"session": session.serialize(),
                     "source": "A", "destination": "B"}))

        self.assertTrue(
            event.wait(timeout=10),
            f"no speak within timeout — handler did not fire. "
            f"spoken={spoken!r}")

        # Inbound translation: the handler saw the slot already folded
        # into internal_language. If translate_message ran before the
        # wrapped callback, ``_last_animal_seen`` is the English form.
        skill = self._skill()
        self.assertEqual(
            getattr(skill, "_last_animal_seen", None), "cats",
            "the inbound translation step did not run — the handler "
            "saw the Portuguese slot 'gatos' instead of 'cats'. The "
            "universal_intent_handler wrapper that calls "
            "translate_message may not be in the dispatch chain.")

        # Outbound translation: the English fact came back as Portuguese.
        self.assertTrue(
            any("dezasseis" in s for s in spoken),
            "expected the Portuguese translation of the English API "
            f"reply in the speak utterance; got {spoken!r}. "
            "UniversalSkill.speak may have dropped the outbound "
            "translation step, or its translate_utterance call uses "
            "swapped target/source args (returning the source text).")
