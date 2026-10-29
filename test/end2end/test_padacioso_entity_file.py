# Copyright 2026 OpenVoiceOS
# Licensed under the Apache License, Version 2.0
"""End-to-end ovoscope test: a skill that calls ``register_entity_file``
for a shipped ``.entity`` file reaches the bus with one
``ovos.entity.register`` message carrying the entity name and the parsed
sample list.

Companion to ``test_padacioso_intent_file.py``: same resolver, different
file extension (``.entity`` vs ``.intent``). The fixture ships
``locale/en-US/drink.entity`` with three sample values. Every shipped
``.entity`` file is also registered automatically, so the explicit call in
``initialize`` must not stack a second registration.

**Note on what ``.entity`` does** — in OVOS, ``.entity`` files are
hints / training samples for the intent engine, not strict slot
constraints. An open ``{drink}`` slot would capture any token even
without the entity file. This test therefore asserts on the
*registration plumbing* rather than on slot-fill behaviour.
"""
from unittest import TestCase

import pytest

from ovos_spec_tools import SpecMessage

from ovos_workshop.skills.ovos import OVOSSkill

ovoscope = pytest.importorskip("ovoscope")


class _DrinkRegistrarSkill(OVOSSkill):
    """Calls ``register_entity_file`` for a file that is also discovered
    automatically."""

    def initialize(self):
        self.register_entity_file("drink.entity")


class TestPadaciosoEntityFileE2E(TestCase):
    """``register_entity_file`` -> ``LocaleResources.find`` ->
    ``intent_service.register_entity`` -> bus message
    ``ovos.entity.register`` with the entity name and the parsed samples."""

    def setUp(self):
        self.skill_id = "drinks.openvoiceos"
        self.minicroft = ovoscope.get_minicroft(
            [self.skill_id],
            extra_skills={self.skill_id: _DrinkRegistrarSkill},
            lang="en-US")

    def tearDown(self):
        if self.minicroft is not None:
            self.minicroft.stop()

    def test_registration_resolves_entity_file_and_parses_samples(self):
        registrations = [
            m.data for m in self.minicroft.boot_messages
            if m.msg_type == str(SpecMessage.ENTITY_REGISTER)
            and m.data.get("entity_name") == "drink"]

        # one registration, although the file was both discovered and named
        self.assertEqual(len(registrations), 1, registrations)
        registration = registrations[0]
        self.assertEqual(registration["skill_id"], self.skill_id)
        self.assertEqual(registration["lang"], "en-US")
        # the parsed samples prove the resolved path was opened and split
        # correctly; comments and blanks are filtered out by the reader
        self.assertEqual(sorted(registration["samples"]),
                         ["coffee", "juice", "tea"])
