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

    TOPICS = ("ovos.intent.register.template", "padatious:register_intent")

    def setUp(self):
        self.bus = FakeBus()
        self.emitted = []
        self.bus.on("message", lambda msg: self.emitted.append(json.loads(msg)))
        self.skill = OVOSSkill(skill_id="required.test", bus=self.bus,
                               resources_dir=RES_DIR)
        self.skill.config_core = {"lang": "en-US", "secondary_langs": ["pt-PT"]}

    def _payloads(self, topic, intent_name):
        """Payloads of ``topic`` for ``intent_name``, keyed by language."""
        found = {}
        for msg in self.emitted:
            data = msg["data"]
            name = data.get("intent_name") or data.get("name", "")
            if msg["type"] == topic and name.split(":")[-1] == intent_name:
                found[data["lang"]] = data
        return found

    def test_every_locale_sends_its_own_keywords_on_both_topics(self):
        self.skill.register_intent_file("lifespan.intent", None)
        for topic in self.TOPICS:
            with self.subTest(topic=topic):
                payloads = self._payloads(topic, "lifespan")
                self.assertEqual(
                    {lang: sorted(data["required_keywords"])
                     for lang, data in payloads.items()},
                    {"en-US": ["confucius", "kong fuzi", "kongzi"],
                     "pt-PT": ["confúcio", "mestre kong"]})

    def test_no_required_slots_are_sent(self):
        self.skill.register_intent_file("lifespan.intent", None)
        for topic in self.TOPICS:
            for lang, data in self._payloads(topic, "lifespan").items():
                with self.subTest(topic=topic, lang=lang):
                    self.assertEqual(data.get("required_slots", []), [])

    def test_intent_without_required_file_sends_an_empty_list(self):
        self.skill.register_intent_file("quote.intent", None)
        for topic in self.TOPICS:
            payloads = self._payloads(topic, "quote")
            with self.subTest(topic=topic):
                self.assertEqual(
                    {lang: data["required_keywords"]
                     for lang, data in payloads.items()},
                    {"en-US": [], "pt-PT": []})

    def test_changed_keywords_re_register(self):
        """A registration that differs only in its keywords is not an
        identical re-registration, so it reaches the engines."""
        iface = self.skill.intent_service
        iface.register_template("lifespan", ["when was confucius born"],
                                "en-US", required_keywords=["confucius"])
        self.emitted.clear()
        iface.register_template("lifespan", ["when was confucius born"],
                                "en-US", required_keywords=["kongzi"])
        for topic in self.TOPICS:
            with self.subTest(topic=topic):
                self.assertEqual(
                    self._payloads(topic, "lifespan")["en-US"]["required_keywords"],
                    ["kongzi"])
