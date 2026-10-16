"""OVOS-INTENT-2 §4.5: a sibling '<intent>.required' locale file loads as the
union of its expanded lines and rides the OVOS-INTENT-4 §6.1 template
registration as ``required_keywords``."""
import json
import unittest
from os.path import dirname

from ovos_utils.fakebus import FakeBus

from ovos_workshop.resource_files import SkillResources
from ovos_workshop.skills.ovos import OVOSSkill

RES_DIR = f"{dirname(__file__)}/ovos_tskill_required"


class TestRequiredFile(unittest.TestCase):

    def test_expands_alternatives(self):
        res = SkillResources(f"{RES_DIR}", "en-US", skill_id="required.test")
        self.assertEqual(sorted(res.load_required_file("lifespan")),
                         ["confucius", "kong fuzi", "kongzi"])

    def test_inlines_a_vocabulary_reference(self):
        res = SkillResources(f"{RES_DIR}", "pt-PT", skill_id="required.test")
        self.assertEqual(sorted(res.load_required_file("lifespan")),
                         ["confúcio", "mestre kong"])

    def test_missing_file_loads_empty(self):
        res = SkillResources(f"{RES_DIR}", "en-US", skill_id="required.test")
        self.assertEqual(res.load_required_file("quote"), [])


class TestRequiredKeywordsRegistration(unittest.TestCase):

    def setUp(self):
        self.bus = FakeBus()
        self.emitted = []
        self.bus.on("message", lambda msg: self.emitted.append(json.loads(msg)))
        self.skill = OVOSSkill(skill_id="required.test", bus=self.bus,
                               resources_dir=RES_DIR)

    def _spec_payload(self, intent_name):
        for msg in self.emitted:
            if msg["type"] == "ovos.intent.register.template" and \
                    msg["data"].get("intent_name") == intent_name:
                return msg["data"]
        return None

    def test_registration_carries_required_keywords(self):
        self.skill.register_intent_file("lifespan.intent", None)
        data = self._spec_payload("lifespan")
        self.assertEqual(data["lang"], "en-US")
        self.assertEqual(sorted(data["required_keywords"]),
                         ["confucius", "kong fuzi", "kongzi"])

    def test_intent_without_required_file_sends_an_empty_list(self):
        self.skill.register_intent_file("quote.intent", None)
        self.assertEqual(self._spec_payload("quote")["required_keywords"], [])

    def test_changed_keywords_re_register(self):
        """A registration that differs only in its keywords is not an
        identical re-registration, so it reaches the engines."""
        iface = self.skill.intent_service
        iface.register_template("lifespan", ["when was confucius born"],
                                "en-US", required_keywords=["confucius"])
        self.emitted.clear()
        iface.register_template("lifespan", ["when was confucius born"],
                                "en-US", required_keywords=["kongzi"])
        self.assertEqual(self._spec_payload("lifespan")["required_keywords"],
                         ["kongzi"])
