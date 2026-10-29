"""OVOS-INTENT-3 §5.3 required slots, declared with the intent's handler.

The declaration travels on every registration of the intent as
`required_slots` (OVOS-INTENT-4 §6.1). A language whose templates declare no
such slot is not registered (OVOS-INTENT-4 §6.3), and the other languages
still are.
"""
import json
import unittest
from os.path import dirname
from unittest.mock import PropertyMock, patch

from ovos_utils.fakebus import FakeBus

from ovos_workshop.decorators import intent_handler
from ovos_workshop.intents import IntentBuilder, IntentServiceInterface
from ovos_workshop.skills.ovos import OVOSSkill

RES_DIR = f"{dirname(__file__)}/ovos_tskill_required"
SKILL_ID = "required.test"
SPEC = "ovos.intent.register.template"
LEGACY = "padatious:register_intent"
BAD_NAMES = ["Person", "1st", "{person}", "duration:length", "per son", ""]


class _Case(unittest.TestCase):
    skill_class = OVOSSkill
    langs = ["en-US"]

    def setUp(self):
        self.bus = FakeBus()
        self.bus.emitted_msgs = []
        self.bus.on("message", lambda msg: self.bus.emitted_msgs.append(json.loads(msg)))
        langs = patch.object(OVOSSkill, "native_langs", new_callable=PropertyMock,
                             return_value=self.langs)
        langs.start()
        self.addCleanup(langs.stop)
        self.skill = self.skill_class(skill_id=SKILL_ID, bus=self.bus,
                                      resources_dir=RES_DIR)

    def tearDown(self):
        self.skill.default_shutdown()
        self.skill = None

    def payloads(self, msg_type, intent):
        return {msg["data"]["lang"]: msg["data"] for msg in self.bus.emitted_msgs
                if msg["type"] == msg_type and intent in
                msg["data"].get("intent_name", "") + msg["data"].get("name", "")}


class RequiredSlotsPayloadTest(_Case):

    def test_spec_payload_carries_required_slots(self):
        self.skill.register_intent_file("height.intent", None,
                                        required_slots=["person"])
        self.assertEqual(self.payloads(SPEC, "height")["en-US"]["required_slots"],
                         ["person"])

    def test_legacy_payload_carries_required_slots(self):
        self.skill.register_intent_file("height.intent", None,
                                        required_slots=["person"])
        self.assertEqual(self.payloads(LEGACY, "height")["en-US"]["required_slots"],
                         ["person"])

    def test_absent_declaration_sends_empty_list(self):
        # INTENT-4 §6.1: an absent list-valued key is an empty list; sent
        # empty, like `blacklist`
        self.skill.register_intent_file("height.intent", None)
        self.assertEqual(self.payloads(SPEC, "height")["en-US"]["required_slots"], [])
        self.assertEqual(self.payloads(SPEC, "height")["en-US"]["blacklist"], [])
        self.assertEqual(self.payloads(LEGACY, "height")["en-US"]["required_slots"], [])

    def test_typed_placeholder_declares_bare_name(self):
        # INTENT-4 §6.1: a `{duration:length}` placeholder declares `length`
        self.skill.register_intent_file("timer.intent", None,
                                        required_slots=["length"])
        spec = self.payloads(SPEC, "timer")["en-US"]
        self.assertEqual(spec["required_slots"], ["length"])
        self.assertEqual(spec["samples"], ["set a timer for {length}"])
        self.assertEqual(self.payloads(LEGACY, "timer")["en-US"]["required_slots"],
                         ["length"])

    def test_undeclared_slot_skips_registration(self):
        with patch("ovos_workshop.intents.LOG.warning") as warn:
            self.skill.register_intent_file("hello.intent", None,
                                            required_slots=["person"])
        self.assertEqual(self.payloads(SPEC, "hello"), {})
        self.assertEqual(self.payloads(LEGACY, "hello"), {})
        self.assertEqual(warn.call_count, 1)
        self.assertFalse(self.skill.intent_service.get_intent("hello"))

    def test_enable_intent_keeps_required_slots(self):
        self.skill.register_intent_file("height.intent", lambda m: None,
                                        required_slots=["person"])
        self.assertTrue(self.skill.disable_intent("height"))
        self.bus.emitted_msgs = []
        self.assertTrue(self.skill.enable_intent("height"))
        self.assertEqual(self.payloads(SPEC, "height")["en-US"]["required_slots"],
                         ["person"])
        self.assertEqual(self.payloads(LEGACY, "height")["en-US"]["required_slots"],
                         ["person"])


class RequiredSlotsPerLocaleTest(_Case):
    langs = ["en-US", "pt-PT"]

    def test_locale_without_slot_is_skipped_other_registers(self):
        with patch("ovos_workshop.intents.LOG.warning") as warn:
            self.skill.register_intent_file("height.intent", None,
                                            required_slots=["person"])
        self.assertEqual(sorted(self.payloads(SPEC, "height")), ["en-US"])
        self.assertEqual(sorted(self.payloads(LEGACY, "height")), ["en-US"])
        self.assertEqual(self.payloads(SPEC, "height")["en-US"]["required_slots"],
                         ["person"])
        messages = [str(call.args[0]) for call in warn.call_args_list]
        self.assertEqual(len(messages), 1, messages)
        for part in (SKILL_ID, "height", "pt-PT", "person"):
            self.assertIn(part, messages[0])

    def test_without_declaration_both_locales_register(self):
        self.skill.register_intent_file("height.intent", None)
        self.assertEqual(sorted(self.payloads(SPEC, "height")), ["en-US", "pt-PT"])


def _decorated_skill_class():
    class DecoratedSkill(OVOSSkill):

        @intent_handler("height.intent", required_slots=["person"])
        @intent_handler("hello.intent")
        def handle_height(self, message):
            pass

        @intent_handler("timer.intent", required_slots=["length"])
        def handle_timer(self, message):
            pass

    return DecoratedSkill


class RequiredSlotsDecoratorTest(_Case):

    def setUp(self):
        self.skill_class = _decorated_skill_class()
        super().setUp()

    def test_decorator_declares_required_slots(self):
        self.assertEqual(self.payloads(SPEC, "height")["en-US"]["required_slots"],
                         ["person"])
        self.assertEqual(self.payloads(LEGACY, "height")["en-US"]["required_slots"],
                         ["person"])
        self.assertEqual(self.payloads(SPEC, "timer")["en-US"]["required_slots"],
                         ["length"])

    def test_stacked_decorator_keeps_its_own_declaration(self):
        self.assertEqual(self.payloads(SPEC, "hello")["en-US"]["required_slots"], [])


class RequiredSlotNameTest(_Case):

    def test_bad_name_rejected_by_decorator(self):
        for bad in BAD_NAMES:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                intent_handler("height.intent", required_slots=[bad])

    def test_bare_string_rejected_by_decorator(self):
        with self.assertRaises(ValueError):
            intent_handler("height.intent", required_slots="person")

    def test_bad_name_rejected_by_register_intent_file(self):
        for bad in BAD_NAMES:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.skill.register_intent_file("height.intent", None,
                                                required_slots=[bad])
        self.assertEqual(self.payloads(SPEC, "height"), {})

    def test_bad_name_rejected_by_register_template(self):
        iface = IntentServiceInterface(self.bus)
        iface.set_id(SKILL_ID)
        with self.assertRaises(ValueError):
            iface.register_template("height", ["how tall is {person}"], "en-US",
                                    required_slots=["Person"])
        self.assertEqual(self.payloads(SPEC, "height"), {})

    def test_valid_names_accepted(self):
        intent_handler("x.intent", required_slots=["person", "_x", "slot_2"])

    def test_keyword_intent_rejects_required_slots(self):
        with self.assertRaises(ValueError):
            intent_handler(IntentBuilder("kw").require("thing"),
                           required_slots=["person"])
        with self.assertRaises(ValueError):
            self.skill.register_intent(IntentBuilder("kw").require("thing"),
                                       None, required_slots=["person"])


if __name__ == "__main__":
    unittest.main()
