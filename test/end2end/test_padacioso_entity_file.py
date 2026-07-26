# Copyright 2026 OpenVoiceOS
# Licensed under the Apache License, Version 2.0
"""End-to-end ovoscope test: ``register_entity_file`` round-trips through
the new ``_locate_lang_file`` resolver and reaches the bus as a
``padatious:register_entity`` event with the resolved path and the
parsed sample list.

Companion to ``test_padacioso_intent_file.py``: same resolver, different
file extension (``.entity`` vs ``.intent``). The fixture ships
``locale/en-US/drink.entity`` with three sample values; the assertion
is that the bus event carries the path of that file (proves
``_locate_lang_file`` resolved the ``.entity`` correctly) and the
parsed sample list (proves the OVOS-side entity-file reader can open
and split it).

**Note on what ``.entity`` does** — in OVOS, ``.entity`` files are
hints / training samples for the intent engine, not strict slot
constraints. An open ``{drink}`` slot would capture any token even
without the entity file. This test therefore asserts on the
*registration plumbing* rather than on slot-fill behaviour.
"""
from threading import Event
from unittest import TestCase

import pytest

from ovos_bus_client.message import Message
from ovos_bus_client.session import Session

from ovos_workshop.skills.ovos import OVOSSkill

ovoscope = pytest.importorskip("ovoscope")


class _DrinkRegistrarSkill(OVOSSkill):
    """Calls ``register_entity_file`` when poked via the bus, so the
    test can subscribe to ``padatious:register_entity`` BEFORE the
    registration fires."""

    def initialize(self):
        self.add_event("drinks.register", self._do_register)

    def _do_register(self, _msg):
        self.register_entity_file("drink.entity")


class TestPadaciosoEntityFileE2E(TestCase):
    """``register_entity_file`` -> ``_locate_lang_file(name, '.entity')``
    -> ``intent_service.register_padatious_entity`` -> bus event
    ``padatious:register_entity`` with the resolved file path and
    parsed samples."""

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
        registration = {}
        registered = Event()

        def _on_register(msg):
            # Only react to our entity — other transformers / built-ins
            # may register their own entities on the same bus event.
            if msg.data.get("file_name", "").endswith("drink.entity"):
                registration.update(msg.data)
                registered.set()

        self.minicroft.bus.on("padatious:register_entity", _on_register)

        # Trigger registration AFTER subscribing.
        session = Session("reg-1")
        session.lang = "en-US"
        self.minicroft.inject_message(Message(
            "drinks.register", {},
            context={"session": session.serialize(),
                     "source": "A", "destination": "B"}))

        self.assertTrue(
            registered.wait(timeout=10),
            "no ``padatious:register_entity`` bus event — "
            "``register_entity_file`` did not resolve drink.entity "
            "(``_locate_lang_file`` resolver may be broken for .entity)")
        self.registration = registration

        # The file_name in the event proves _locate_lang_file resolved
        # the .entity file (not None, ends with the expected suffix).
        file_name = self.registration.get("file_name", "")
        self.assertTrue(
            file_name.endswith("drink.entity"),
            f"unexpected file_name in registration event: {file_name!r}")

        # The parsed samples prove the OVOS-side entity reader opened
        # the resolved path and split it correctly. Comments and blanks
        # are filtered out by ``register_padatious_entity`` upstream.
        samples = self.registration.get("samples", [])
        self.assertEqual(sorted(samples), ["coffee", "juice", "tea"])
