"""OVOS-INTENT-1 §3.4/§5.6 and OVOS-INTENT-4 §6.1 typed slots.

The template registration declares each slot's type in `slot_types` while the
samples on the wire keep bare `{name}` slots, and a skill reads the normalized
values an engine computed off the dispatch message.
"""
import json
import unittest
from os.path import dirname

from ovos_bus_client.message import Message
from ovos_utils.fakebus import FakeBus

from ovos_workshop.intents import IntentServiceInterface
from ovos_workshop.skills.ovos import OVOSSkill

RES_DIR = f"{dirname(__file__)}/ovos_tskill_typed"


class TypedSlotRegistrationTest(unittest.TestCase):
    """OVOS-INTENT-4 §6.1: `slots` are bare names, `slot_types` maps a bare
    name to its registered type."""

    def setUp(self):
        self.bus = FakeBus()
        self.bus.emitted_msgs = []
        self.bus.on("message", lambda msg: self.bus.emitted_msgs.append(json.loads(msg)))
        self.skill = OVOSSkill(skill_id="typed.test", bus=self.bus,
                               resources_dir=RES_DIR)

    def tearDown(self):
        # a skill left alive is shut down later by the garbage collector,
        # which lands in whichever test is running then
        self.skill.default_shutdown()
        self.skill = None

    def _payload(self, msg_type, name_part):
        for msg in self.bus.emitted_msgs:
            if msg["type"] == msg_type and name_part in msg["data"].get("name", "") + \
                    msg["data"].get("intent_name", ""):
                return msg["data"]
        return None

    def _register(self, intent_file):
        self.bus.emitted_msgs = []
        self.skill.register_intent_file(intent_file, None)
        name = intent_file.removesuffix(".intent")
        return (self._payload("ovos.intent.register.template", name),
                self._payload("padatious:register_intent", name))

    def test_typed_template_declares_slot_types(self):
        spec, _ = self._register("typed.intent")
        self.assertEqual(spec["slot_types"],
                         {"shade": "color", "count": "number"})

    def test_untyped_twin_declares_no_slot_types(self):
        spec, _ = self._register("untyped.intent")
        self.assertNotIn("slot_types", spec)

    def test_samples_identical_to_untyped_twin(self):
        typed_spec, typed_legacy = self._register("typed.intent")
        untyped_spec, untyped_legacy = self._register("untyped.intent")
        self.assertEqual(typed_spec["samples"], untyped_spec["samples"])
        self.assertEqual(typed_legacy["samples"], untyped_legacy["samples"])
        self.assertEqual(
            typed_spec["samples"],
            ["set the lights to {shade} in {count} minutes",
             "make the lights {shade}"])

    def test_unregistered_type_degrades(self):
        spec, legacy = self._register("unregistered.intent")
        self.assertNotIn("slot_types", spec)
        self.assertEqual(spec["samples"], ["turn on {x}"])
        self.assertEqual(legacy["samples"], ["turn on {x}"])

    def test_unregistered_type_warns_once_per_registration(self):
        iface = IntentServiceInterface(self.bus)
        iface.set_id("typed.test")
        with self.assertLogs("ovos_spec_tools.expansion", level="WARNING") as logs:
            iface.register_template("typed.test:unregistered",
                                    ["turn on {foo:x}"], "en-US")
        degrades = [line for line in logs.output if "{foo:x}" in line]
        self.assertEqual(len(degrades), 1, logs.output)

    def test_slot_blacklist_keyed_by_bare_name(self):
        _, legacy = self._register("typed.intent")
        self.assertEqual(sorted(legacy["slot_blacklist"]["shade"]),
                         ["it", "that"])


class TypedSlotHelperTest(unittest.TestCase):
    """OVOS-INTENT-1 §5.6: the consumer takes the entry whose `surface` equals
    the slot value; a repeated value is ambiguous and the first is taken."""

    def setUp(self):
        self.skill = OVOSSkill(skill_id="typed.test", bus=FakeBus(),
                               resources_dir=RES_DIR)

    def tearDown(self):
        # a skill left alive is shut down later by the garbage collector,
        # which lands in whichever test is running then
        self.skill.default_shutdown()
        self.skill = None

    @staticmethod
    def _dispatch(data):
        return Message("typed.test:typed", data)

    def test_value_by_surface(self):
        msg = self._dispatch({
            "shade": "light blue",
            "count": "five",
            "typed_slots": {
                "color": [{"span": [17, 27], "surface": "light blue",
                           "value": "#add8e6"}],
                "number": [{"span": [31, 35], "surface": "five", "value": 5}]}})
        self.assertEqual(self.skill.typed_slot(msg, "shade"), "#add8e6")
        self.assertEqual(self.skill.typed_slot(msg, "count"), 5)

    def test_repeated_surface_takes_first(self):
        msg = self._dispatch({
            "count": "two",
            "typed_slots": {"number": [
                {"span": [4, 7], "surface": "two", "value": 2},
                {"span": [20, 23], "surface": "two", "value": 22}]}})
        self.assertEqual(self.skill.typed_slot(msg, "count"), 2)

    def test_repeated_surface_first_is_by_span_not_list_order(self):
        # "first" is the earliest entry in the utterance, whatever order the
        # engine happened to list them in
        msg = self._dispatch({
            "count": "two",
            "typed_slots": {"number": [
                {"span": [20, 23], "surface": "two", "value": 22},
                {"span": [4, 7], "surface": "two", "value": 2}]}})
        self.assertEqual(self.skill.typed_slot(msg, "count"), 2)

    def test_no_map_is_none(self):
        msg = self._dispatch({"shade": "light blue"})
        self.assertIsNone(self.skill.typed_slot(msg, "shade"))

    def test_surface_absent_from_map_is_none(self):
        msg = self._dispatch({
            "shade": "burnt umber",
            "typed_slots": {"color": [{"span": [0, 3], "surface": "red",
                                       "value": "#ff0000"}]}})
        self.assertIsNone(self.skill.typed_slot(msg, "shade"))

    def test_slot_absent_is_none(self):
        msg = self._dispatch({
            "typed_slots": {"color": [{"span": [0, 3], "surface": "red",
                                       "value": "#ff0000"}]}})
        self.assertIsNone(self.skill.typed_slot(msg, "missing"))

    def test_entries_by_type_in_span_order(self):
        msg = self._dispatch({"typed_slots": {"number": [
            {"span": [20, 23], "surface": "two", "value": 2},
            {"span": [4, 8], "surface": "five", "value": 5}]}})
        self.assertEqual([e["value"] for e in self.skill.typed_slots(msg, "number")],
                         [5, 2])

    def test_type_absent_is_empty(self):
        msg = self._dispatch({"typed_slots": {"number": []}})
        self.assertEqual(self.skill.typed_slots(msg, "date"), [])
        self.assertEqual(self.skill.typed_slots(msg, "number"), [])
        self.assertEqual(self.skill.typed_slots(self._dispatch({}), "number"), [])


class TypedSlotJunkTest(unittest.TestCase):
    """A producer may put junk under `typed_slots`; both reads degrade to
    None / [] rather than raising."""

    def setUp(self):
        self.skill = OVOSSkill(skill_id="typed.test", bus=FakeBus(),
                               resources_dir=RES_DIR)

    def tearDown(self):
        # a skill left alive is shut down later by the garbage collector,
        # which lands in whichever test is running then
        self.skill.default_shutdown()
        self.skill = None

    def _junk(self, typed_slots):
        return Message("typed.test:typed",
                       {"shade": "red", "typed_slots": typed_slots})

    def test_non_dict_map(self):
        for junk in ("nonsense", ["color"], 3, None):
            msg = self._junk(junk)
            self.assertIsNone(self.skill.typed_slot(msg, "shade"))
            self.assertEqual(self.skill.typed_slots(msg, "color"), [])

    def test_non_list_entries(self):
        msg = self._junk({"color": {"surface": "red", "value": "#ff0000"}})
        self.assertIsNone(self.skill.typed_slot(msg, "shade"))
        self.assertEqual(self.skill.typed_slots(msg, "color"), [])

    def test_entry_missing_keys(self):
        for entry in ({"surface": "red"}, {"value": "#ff0000"},
                      {"span": [0, 3], "value": "#ff0000"},
                      {"span": [0], "surface": "red", "value": "#ff0000"},
                      {"span": "0-3", "surface": "red", "value": "#ff0000"},
                      "red", None):
            msg = self._junk({"color": [entry]})
            self.assertIsNone(self.skill.typed_slot(msg, "shade"))
            self.assertEqual(self.skill.typed_slots(msg, "color"), [])

    def test_valid_entry_survives_a_junk_sibling(self):
        msg = self._junk({"color": ["junk",
                                    {"span": [0, 3], "surface": "red",
                                     "value": "#ff0000"}]})
        self.assertEqual(self.skill.typed_slot(msg, "shade"), "#ff0000")
        self.assertEqual(len(self.skill.typed_slots(msg, "color")), 1)


class DeclaredTypeResolutionTest(unittest.TestCase):
    """A surface an engine reported under several types resolves to the type
    the intent declared for that slot (OVOS-INTENT-4 §6.1 `slot_types`)."""

    def setUp(self):
        self.skill = OVOSSkill(skill_id="typed.test", bus=FakeBus(),
                               resources_dir=RES_DIR)
        self.skill.register_intent_file("typed.intent", None)

    def tearDown(self):
        # a skill left alive is shut down later by the garbage collector,
        # which lands in whichever test is running then
        self.skill.default_shutdown()
        self.skill = None

    @staticmethod
    def _collision(slot):
        # "five" was found both as a number and as a colour name
        return Message("typed.test:typed", {
            slot: "five",
            "typed_slots": {
                "color": [{"span": [0, 4], "surface": "five",
                           "value": "#005500"}],
                "number": [{"span": [0, 4], "surface": "five", "value": 5}]}})

    def test_declared_type_wins_over_a_colliding_type(self):
        # count is declared {number:count}, shade is declared {color:shade}
        self.assertEqual(self.skill.typed_slot(self._collision("count"), "count"), 5)
        self.assertEqual(self.skill.typed_slot(self._collision("shade"), "shade"),
                         "#005500")

    def test_undeclared_slot_uses_registered_type_order(self):
        # "amount" is no slot of this intent, so the fixed REGISTERED_TYPES
        # order decides: number before duration before date before color
        self.assertEqual(self.skill.typed_slot(self._collision("amount"), "amount"), 5)

    def test_untyped_intent_slot_uses_registered_type_order(self):
        self.skill.register_intent_file("untyped.intent", None)
        msg = Message("typed.test:untyped", {
            "shade": "five",
            "typed_slots": {
                "color": [{"span": [0, 4], "surface": "five",
                           "value": "#005500"}],
                "number": [{"span": [0, 4], "surface": "five", "value": 5}]}})
        self.assertEqual(self.skill.typed_slot(msg, "shade"), 5)


if __name__ == "__main__":
    unittest.main()
