# Copyright 2026 OpenVoiceOS
# Licensed under the Apache License, Version 2.0
"""End-to-end ovoscope test: ``voc_match`` on a plain ``OVOSSkill``
loads ``.voc`` phrases through ``LocaleResources.load_vocabulary``,
caches them in ``_voc_cache``, and matches utterances.

``voc_match`` / ``voc_list`` are the workhorse skill-side helpers for
keyword detection (used by stop / cancel / confirmation flows across
the ecosystem). They were rewired off ``SkillResources`` onto
``LocaleResources`` in PR #413; a silent regression would make every
keyword check return ``False`` and break those flows.

The fixture ships ``locale/en-US/yes.voc`` with five affirmative
phrases. The skill exposes a bus handler that calls ``self.voc_match``
on the inbound text and echoes the boolean result back, so the test
can assert both the True case (``"sure thing"``) and the False case
(``"no idea"``) deterministically.
"""
from threading import Event
from unittest import TestCase

import pytest

from ovos_bus_client.message import Message
from ovos_bus_client.session import Session

from ovos_workshop.skills.ovos import OVOSSkill

ovoscope = pytest.importorskip("ovoscope")


class _AffirmativeSkill(OVOSSkill):

    def initialize(self):
        self.add_event("affirm.check", self._on_check)

    def _on_check(self, message):
        utt = message.data.get("utterance", "")
        self.bus.emit(message.reply("affirm.result",
                                    {"matched": self.voc_match(utt, "yes")}))


class TestVocMatchE2E(TestCase):
    """``voc_match`` -> ``voc_list`` -> ``LocaleResources.load_vocabulary``
    -> ``_voc_cache`` -> bus reply."""

    def setUp(self):
        self.skill_id = "affirm.openvoiceos"
        self.minicroft = ovoscope.get_minicroft(
            [self.skill_id],
            extra_skills={self.skill_id: _AffirmativeSkill},
            lang="en-US")

    def tearDown(self):
        if self.minicroft is not None:
            self.minicroft.stop()

    def _ask(self, utterance: str) -> bool:
        reply = {}
        got = Event()

        def on_result(msg):
            reply["matched"] = msg.data.get("matched")
            got.set()

        self.minicroft.bus.on("affirm.result", on_result)

        session = Session("voc-1")
        session.lang = "en-US"
        self.minicroft.inject_message(Message(
            "affirm.check",
            {"utterance": utterance},
            context={"session": session.serialize(),
                     "source": "A", "destination": "B"}))
        self.assertTrue(got.wait(timeout=10),
                        f"no affirm.result for {utterance!r}")
        return reply["matched"]

    def test_phrase_in_voc_file_matches(self):
        self.assertTrue(self._ask("sure thing"),
                        "voc_match returned False for an in-vocabulary "
                        "phrase — LocaleResources.load_vocabulary may have "
                        "returned an empty list")

    def test_phrase_not_in_voc_file_does_not_match(self):
        self.assertFalse(self._ask("no idea"),
                         "voc_match returned True for an out-of-vocabulary "
                         "phrase")
