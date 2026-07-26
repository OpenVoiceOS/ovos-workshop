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
# Keys are kept at the **primary subtag** so the lookup is stable across
# ovos_bus_client versions (some versions fold the session lang through
# ovos_utils.lang.standardize_lang_tag's macro=True default and deliver
# "pt" rather than "pt-PT"). The stub's lookup folds to primary so the
# test is not coupled to any particular bus-client behaviour.
def _primary(tag):
    return (tag or "").split("-", 1)[0].lower()


_FAKE_TRANSLATIONS = {
    # inbound: Portuguese → English (the user's slot lands here)
    ("gatos", "pt", "en"): "cats",
    # outbound: English → Portuguese (the skill's reply lands here)
    ("Cats sleep up to sixteen hours a day.", "en", "pt"):
        "Os gatos dormem até dezasseis horas por dia.",
    ("I do not know about that animal.", "en", "pt"):
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
        kwargs.setdefault("internal_language", "en-US")
        super().__init__(*args, **kwargs)

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
        # exact-key lookup against the test's deterministic table; lang
        # tags are folded to primary so the table works whether the
        # runtime delivers "pt" or "pt-PT" (see _FAKE_TRANSLATIONS for
        # the bus-client version note). Fall through to the source text
        # so an untranslated branch surfaces in test failure output
        # instead of silently no-oping.
        key = (text, _primary(sauce_lang), _primary(target_lang))
        return _FAKE_TRANSLATIONS.get(key, text)

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
        # A real-world UniversalSkill is addressed in multiple languages;
        # padacioso registers its .intent for every entry in native_langs
        # (= core_lang + secondary_langs). Configure the test env to
        # include pt-PT so the pt-PT fact.intent gets registered and the
        # full real-world round-trip is exercised — Portuguese utterance,
        # English-only skill code, Portuguese reply.
        self.minicroft = ovoscope.get_minicroft(
            [self.skill_id],
            extra_skills={self.skill_id: _AnimalFactsUniversalSkill},
            lang="pt-PT",
            secondary_langs=["en-US"])

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

    def test_realistic_pt_user_addresses_english_only_skill(self):
        """Real round-trip: Portuguese-speaking user, English-only skill code.

        The skill ships a Portuguese ``fact.intent`` (a real-world skill
        would ship one per supported language); padacioso matches it
        against a real ``recognizer_loop:utterance`` in Portuguese and
        captures ``animal="gatos"``. The :class:`UniversalSkill`
        handler-wrapper folds that slot into ``internal_language``
        before the callback runs, so the user's skill code is
        single-language: hits an English-only API with ``"cats"``, gets
        an English fact, calls ``self.speak(fact)``. :meth:`speak`
        translates the reply back to Portuguese on the way out — the
        user never sees the English internals.

        Three failure modes this catches:

        * pt-PT ``.intent`` not registered → padacioso never matches,
          no speak fires;
        * inbound translation skipped → handler sees ``"gatos"`` instead
          of ``"cats"``, API lookup misses, user gets the fallback;
        * outbound translation skipped or argument-swapped → user
          gets the English fact verbatim instead of the translation.
        """
        spoken = []
        event = Event()
        self.minicroft.bus.on("speak", lambda m: (
            spoken.append(m.data.get("utterance", "")), event.set()))

        # A real Portuguese utterance from the user. Padacioso (bundled,
        # always available in the test env) matches the pt-PT intent
        # file the skill ships and captures the animal slot in Portuguese.
        session = Session("uni-roundtrip")
        session.lang = "pt-PT"
        self.minicroft.inject_message(Message(
            "recognizer_loop:utterance",
            {"utterances": ["conta-me um facto sobre gatos"],
             "lang": "pt-PT"},
            context={"session": session.serialize(),
                     "source": "A", "destination": "B"}))

        self.assertTrue(
            # padatious/padacioso training for two langs (pt-PT + en-US)
            # under full-suite load can take longer than 10s; 15s matches
            # the timeout used for the other padacioso e2e round-trip
            # (test_padacioso_intent_file.py)
            event.wait(timeout=15),
            "no speak within 15s — the pt-PT fact.intent likely never "
            f"matched. spoken={spoken!r}")

        # Inbound translation happened inside the skill: the handler
        # received the slot already in internal_language.
        skill = self._skill()
        self.assertEqual(
            getattr(skill, "_last_animal_seen", None), "cats",
            "handler saw the Portuguese slot 'gatos' — the inbound "
            "translate_message step in the universal_intent_handler "
            "wrapper did not run, or was bypassed.")

        # Outbound translation happened inside speak(): the user gets
        # Portuguese, never sees the English internals.
        self.assertTrue(
            any("dezasseis" in s for s in spoken),
            "expected the Portuguese translation of the English API "
            f"reply in the speak utterance; got {spoken!r}. "
            "UniversalSkill.speak may have skipped the outbound "
            "translation step, or its translate_utterance arguments "
            "are still source/target-swapped.")
