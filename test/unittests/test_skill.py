# Copyright 2026 OpenVoiceOS
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import json
import unittest
from unittest.mock import Mock

from ovos_bus_client import Message

from ovos_workshop.skills.ovos import OVOSSkill
from ovos_utils.fakebus import FakeBus
from os.path import dirname
from ovos_workshop.skill_launcher import SkillLoader


class SpecificArgsSkill(OVOSSkill):
    def __init__(self, skill_id="SpecificArgsSkill", bus=None, **kwargs):
        self.inited = True
        self.initialized = False
        self.startup_called = False
        super().__init__(skill_id=skill_id, bus=bus, **kwargs)
        self.kwargs = kwargs

    def initialize(self):
        self.initialized = True

    def _startup(self, bus, skill_id=""):
        self.startup_called = True
        self.initialize()


class KwargSkill(OVOSSkill):
    def __init__(self, **kwargs):
        self.inited = True
        self.initialized = False
        self.startup_called = False
        super().__init__(**kwargs)

    def initialize(self):
        self.initialized = True

    def _startup(self, bus, skill_id=""):
        self.startup_called = True
        self.initialize()


class TestSkill(unittest.TestCase):
    def setUp(self):
        self.bus = FakeBus()
        self.bus.emitted_msgs = []

        def get_msg(msg):
            msg = json.loads(msg)
            self.bus.emitted_msgs.append(msg)

        self.bus.on("message", get_msg)

        self.skill = SkillLoader(self.bus, f"{dirname(__file__)}/ovos_tskill_abort")
        self.skill.skill_id = "abort.test"
        self.bus.emitted_msgs = []

        self.skill.load()

    def test_skill_id(self):
        self.assertTrue(isinstance(self.skill.instance, OVOSSkill))

        self.assertEqual(self.skill.skill_id, "abort.test")

        # if running in ovos-core every message will have the skill_id in context
        for msg in self.bus.emitted_msgs:
            if msg["type"] == 'mycroft.skills.loaded': # emitted by SkillLoader, not by skill
                continue
            self.assertEqual(msg["context"]["skill_id"], "abort.test")

    def test_intent_register(self):
        # OVOS-MSG-1 §2.1.1: the `.intent` authoring extension is not part of
        # the intent name, so it never reaches the wire
        padatious_intents = ["abort.test:test",
                             "abort.test:test2",
                             "abort.test:test3",
                             "abort.test:test4"]
        for msg in self.bus.emitted_msgs:
            if msg["type"] == "padatious:register_intent":
                self.assertTrue(msg["data"]["name"] in padatious_intents)

    def test_registered_events(self):
        registered_events = [e[0] for e in self.skill.instance.events]

        # intent events
        intent_triggers = [f"{self.skill.skill_id}:test",
                           f"{self.skill.skill_id}:test2",
                           f"{self.skill.skill_id}:test3"
                           ]
        for event in intent_triggers:
            self.assertTrue(event in registered_events)

        # base skill class events shared with mycroft-core
        default_skill = ["mycroft.skill.enable_intent",
                         "mycroft.skill.disable_intent",
                         "mycroft.skill.set_cross_context",
                         "mycroft.skill.remove_cross_context",
                         "mycroft.skills.settings.changed"]
        for event in default_skill:
            self.assertTrue(event in registered_events)

        # because its a ConversationalSkill class
        converse_ovos = [f"{self.skill.skill_id}.converse.ping",
                        f"{self.skill.skill_id}.converse.request",
                        "intent.service.skills.activated",
                        "intent.service.skills.deactivated",
                        f"{self.skill.skill_id}.activate",
                        f"{self.skill.skill_id}.deactivate"]
        for event in converse_ovos:
            self.assertTrue(event in registered_events)

    def tearDown(self) -> None:
        self.skill.unload()


class TestSkillNew(unittest.TestCase):

    def test_load(self):
        bus = FakeBus()
        kwarg = KwargSkill(skill_id="kwarg", bus=bus)
        self.assertTrue(kwarg.inited)
        self.assertTrue(kwarg.initialized)
        self.assertTrue(kwarg.startup_called)
        self.assertEqual(kwarg.skill_id, "kwarg")
        self.assertEqual(kwarg.bus, bus)

        gui = Mock()
        args = SpecificArgsSkill("args", bus, gui=gui)
        self.assertTrue(args.inited)
        self.assertTrue(args.initialized)
        self.assertTrue(args.startup_called)
        self.assertEqual(args.skill_id, "args")
        self.assertEqual(args.bus, bus)
        self.assertEqual(args.gui, gui)


class TestIntentBlacklistFile(unittest.TestCase):
    """OVOS-INTENT-2: a sibling '<intent>.blacklist' locale file feeds the
    intent registration blacklist alongside the 'voc_blacklist' param."""

    def setUp(self):
        self.bus = FakeBus()
        self.bus.emitted_msgs = []

        def get_msg(msg):
            self.bus.emitted_msgs.append(json.loads(msg))

        self.bus.on("message", get_msg)

        res_dir = f"{dirname(__file__)}/ovos_tskill_blacklist"
        self.skill = OVOSSkill(skill_id="blacklist.test", bus=self.bus,
                               resources_dir=res_dir)

    def _register_payload(self, intent_name):
        # registration carries the canonical name, without the file extension
        intent_name = intent_name.removesuffix(".intent")
        for msg in self.bus.emitted_msgs:
            if msg["type"] == "padatious:register_intent" and \
                    msg["data"]["name"].endswith(intent_name):
                return msg["data"]
        return None

    def test_intent_with_blacklist_file(self):
        self.bus.emitted_msgs = []
        self.skill.register_intent_file("foo.intent", None)
        data = self._register_payload("foo.intent")
        self.assertIsNotNone(data)
        self.assertIn("turn on the news", data["blacklisted_words"])
        self.assertIn("activate the alarm", data["blacklisted_words"])

    def test_intent_without_blacklist_file(self):
        self.bus.emitted_msgs = []
        self.skill.register_intent_file("bar.intent", None)
        data = self._register_payload("bar.intent")
        self.assertIsNotNone(data)
        self.assertEqual(data["blacklisted_words"], [])

    def test_voc_blacklist_param_still_merges(self):
        self.bus.emitted_msgs = []
        # even without any matching voc, the .blacklist phrases must be present
        self.skill.register_intent_file("foo.intent", None, voc_blacklist=[])
        data = self._register_payload("foo.intent")
        self.assertIsNotNone(data)
        self.assertIn("turn on the news", data["blacklisted_words"])


class TestSlotBlacklistFile(unittest.TestCase):
    """OVOS-INTENT-2 §4.3: a sibling '<slot>.blacklist' / '<entity>.blacklist'
    locale file feeds slot-value exclusions into the entity/intent
    registration payload so engines can drop blacklisted slot values."""

    def setUp(self):
        self.bus = FakeBus()
        self.bus.emitted_msgs = []

        def get_msg(msg):
            self.bus.emitted_msgs.append(json.loads(msg))

        self.bus.on("message", get_msg)

        res_dir = f"{dirname(__file__)}/ovos_tskill_blacklist"
        self.skill = OVOSSkill(skill_id="blacklist.test", bus=self.bus,
                               resources_dir=res_dir)

    def _payload(self, msg_type, name_part):
        # intent registration carries the canonical name, without the
        # `.intent` file extension
        name_part = name_part.removesuffix(".intent")
        for msg in self.bus.emitted_msgs:
            if msg["type"] == msg_type and \
                    name_part in msg["data"]["name"]:
                return msg["data"]
        return None

    def test_entity_with_blacklist_file(self):
        # NOTE: person.entity is auto-registered as soon as the skill's
        # locale resources are first touched (setUp, via OVOSSkill
        # construction) - the explicit register_entity_file() call below is
        # now a deduped no-op, so do NOT clear emitted_msgs here or the
        # only registration (the automatic one) is lost.
        self.skill.register_entity_file("person.entity")
        data = self._payload("padatious:register_entity", "person")
        self.assertIsNotNone(data)
        self.assertEqual(data["samples"], ["alice", "bob"])
        self.assertIn("he", data["blacklist"])
        self.assertIn("she", data["blacklist"])

    def test_spec_template_registration_carries_slot_blacklist(self):
        """INTENT-4: the spec register-template emission must carry the same
        slot_blacklist as the legacy padatious:register_intent payload — the
        §4.3 slot-exclusion feature must survive the legacy emit's removal."""
        self.skill.register_intent_file("foo.intent", None)
        legacy = None
        spec = None
        for msg in self.bus.emitted_msgs:
            if msg["type"] == "padatious:register_intent" and                     "foo" in msg["data"]["name"]:
                legacy = msg["data"]
            if msg["type"] == "ovos.intent.register.template" and                     msg["data"].get("intent_name") == "foo":
                spec = msg["data"]
        self.assertIsNotNone(legacy)
        self.assertIsNotNone(spec)
        self.assertTrue(legacy.get("slot_blacklist"),
                        "fixture must exercise a non-empty slot blacklist")
        self.assertEqual(spec.get("slot_blacklist"),
                         legacy["slot_blacklist"])

    def test_entity_name_is_the_clean_wire_name(self):
        """The legacy ``padatious:register_entity`` name must be exactly
        ``<skill_id>:<entity>``. A ``_<md5>`` suffix used to be appended here,
        which no consumer could resolve back to the "{slot}" token written in
        the template - every file-registered entity became an unconstrained
        wildcard slot."""
        import re
        # see test_entity_with_blacklist_file: person.entity is already
        # auto-registered by setUp, don't clear emitted_msgs
        self.skill.register_entity_file("person.entity")
        data = self._payload("padatious:register_entity", "person")
        self.assertIsNotNone(data)
        self.assertEqual(data["name"], f"{self.skill.skill_id}:person")
        self.assertIsNone(re.search(r"_[0-9a-f]{32}$", data["name"]))

    def test_legacy_and_spec_entity_names_agree(self):
        """Both wire contracts must name the same entity identically, so the
        consumer collapses the dual-emit into one registration."""
        # see test_entity_with_blacklist_file: person.entity is already
        # auto-registered by setUp, don't clear emitted_msgs
        self.skill.register_entity_file("person.entity")
        legacy = self._payload("padatious:register_entity", "person")
        spec = None
        for msg in self.bus.emitted_msgs:
            if msg["type"] == "ovos.entity.register":
                spec = msg["data"]
        self.assertIsNotNone(spec)
        self.assertEqual(legacy["name"],
                         f'{spec["skill_id"]}:{spec["entity_name"]}')

    def test_entity_without_blacklist_file(self):
        self.bus.emitted_msgs = []
        # bar has no sibling .blacklist -> empty, back-compat
        self.skill.register_entity_file("bar.entity")
        data = self._payload("padatious:register_entity", "bar")
        # bar.entity does not exist; nothing registered
        self.assertIsNone(data)

    def test_intent_slot_blacklist_keyed_by_slot(self):
        self.bus.emitted_msgs = []
        # foo.intent declares {thing}; sibling thing.blacklist excludes values
        self.skill.register_intent_file("foo.intent", None)
        data = self._payload("padatious:register_intent", "foo.intent")
        self.assertIsNotNone(data)
        self.assertIn("thing", data["slot_blacklist"])
        self.assertIn("the news", data["slot_blacklist"]["thing"])
        self.assertIn("the alarm", data["slot_blacklist"]["thing"])

    def test_intent_without_slot_blacklist(self):
        self.bus.emitted_msgs = []
        # bar.intent has no slots -> empty map, back-compat
        self.skill.register_intent_file("bar.intent", None)
        data = self._payload("padatious:register_intent", "bar.intent")
        self.assertIsNotNone(data)
        self.assertEqual(data["slot_blacklist"], {})
