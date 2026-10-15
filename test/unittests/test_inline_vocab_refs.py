"""OVOS-INTENT-1 §3.7: an inline ``<name>`` reference in a ``.intent`` file is
an authoring convenience that must expand in place from the sibling ``.voc`` of
that name before the template reaches an intent engine. The padatious/padacioso
bus protocol carries only samples — never the ``.voc`` content — so the
reference has to be resolved during registration, otherwise the raw ``<name>``
token is trained into the engine and the intent never matches."""
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from ovos_utils.fakebus import FakeBus
from ovos_workshop.intents import IntentServiceInterface
from ovos_workshop.resource_files import ResourceFile, SkillResources

# Deliberate legacy-coverage suite: exercises the deprecated
# register_padatious_intent facade on purpose.
pytestmark = pytest.mark.filterwarnings(
    "ignore:(IntentServiceInterface\\.)?register_(adapt|padatious)_\\w+ "
    "is deprecated:DeprecationWarning"
)


class TestInlineVocabReferences(unittest.TestCase):
    """The load-time resolution path: ``load_intent_file`` / ``load_blacklist_file``
    expand every inline ``<name>`` from the sibling ``.voc`` of that name found in
    the same locale directory."""

    def _skill_dir(self, files: dict) -> str:
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        locale = Path(tmp.name, "locale", "en-us")
        locale.mkdir(parents=True)
        for name, content in files.items():
            (locale / name).write_text(content)
        return tmp.name

    def _resources(self, skill_dir):
        return SkillResources(skill_dir, "en-us", skill_id="test.skill")

    def test_intent_inline_vocab(self):
        skill_dir = self._skill_dir({
            "thing.voc": "lamp\nlight\n",
            "foo.intent": "turn on the <thing>\n",
        })
        intents = self._resources(skill_dir).load_intent_file("foo.intent")
        self.assertIn("turn on the lamp", intents)
        self.assertIn("turn on the light", intents)

    def test_blacklist_inline_vocab(self):
        skill_dir = self._skill_dir({
            "pronoun.voc": "it\nthem\n",
            "bar.blacklist": "stop <pronoun>\n",
        })
        phrases = self._resources(skill_dir).load_blacklist_file("bar.blacklist")
        self.assertIn("stop it", phrases)
        self.assertIn("stop them", phrases)

    def test_intent_without_inline_ref_unchanged(self):
        skill_dir = self._skill_dir({
            "foo.intent": "turn on the (lamp|light)\n",
        })
        intents = self._resources(skill_dir).load_intent_file("foo.intent")
        self.assertIn("turn on the lamp", intents)
        self.assertIn("turn on the light", intents)


class TestInlineVocabResources(unittest.TestCase):
    def _resources(self, files):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        locale = Path(tmp.name, "locale", "en-us")
        locale.mkdir(parents=True)
        for name, content in files.items():
            (locale / name).write_text(content)
        return SkillResources(tmp.name, "en-us", skill_id="test.skill")

    def test_vocabularies_map(self):
        resources = self._resources({
            "thing.voc": "widget\ngadget\n# comment\n",
            "foo.intent": "what about <thing>\n",
        })
        self.assertEqual(resources.vocabularies().get("thing"),
                         ["widget", "gadget"])

    def test_vocabularies_expands_alternates(self):
        resources = self._resources({
            "greeting.voc": "(hello|hi)\ngood morning\n",
        })
        self.assertEqual(sorted(resources.vocabularies()["greeting"]),
                         ["good morning", "hello", "hi"])


class TestInlineVocabRegistration(unittest.TestCase):
    """The samples emitted on the registration bus topic must already have the
    inline ``<name>`` resolved to an ``(a|b|c)`` alternation group."""

    def _capture_samples(self, files, pass_vocabs):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        locale = Path(tmp.name, "locale", "en-us")
        locale.mkdir(parents=True)
        for name, content in files.items():
            (locale / name).write_text(content)
        resources = SkillResources(tmp.name, "en-us", skill_id="test.skill")
        filename = str(ResourceFile(resources.types.intent, "foo.intent").file_path)

        bus = FakeBus()
        captured = {}
        bus.on("padatious:register_intent",
               lambda m: captured.__setitem__("samples", m.data["samples"]))
        iface = IntentServiceInterface(bus)
        iface.set_id("test.skill")
        kwargs = {"vocabs": resources.vocabularies()} if pass_vocabs else {}
        iface.register_padatious_intent("test.skill:foo.intent", filename,
                                        "en-us", **kwargs)
        return captured["samples"]

    def test_inline_reference_resolved_before_engine(self):
        samples = self._capture_samples({
            "thing.voc": "widget\ngadget\n",
            "foo.intent": "what about <thing>\n",
        }, pass_vocabs=True)
        self.assertEqual(samples, ["what about (widget|gadget)"])

    def test_raw_reference_without_vocabs_is_unresolved(self):
        samples = self._capture_samples({
            "thing.voc": "widget\ngadget\n",
            "foo.intent": "what about <thing>\n",
        }, pass_vocabs=False)
        self.assertEqual(samples, ["what about <thing>"])


class TestInlineVocabEngineEndToEnd(unittest.TestCase):
    """End-to-end proof through the real engines: a skill shipping a ``foo.intent``
    with ``<thing>`` and a sibling ``thing.voc`` matches an utterance built from a
    vocabulary member, but only when the reference is resolved at registration."""

    def _samples(self, pass_vocabs):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        locale = Path(tmp.name, "locale", "en-us")
        locale.mkdir(parents=True)
        (locale / "thing.voc").write_text("widget\ngadget\n")
        (locale / "foo.intent").write_text("what about <thing>\n")
        resources = SkillResources(tmp.name, "en-us", skill_id="test.skill")
        filename = str(ResourceFile(resources.types.intent, "foo.intent").file_path)

        bus = FakeBus()
        captured = {}
        bus.on("padatious:register_intent",
               lambda m: captured.__setitem__("samples", m.data["samples"]))
        iface = IntentServiceInterface(bus)
        iface.set_id("test.skill")
        kwargs = {"vocabs": resources.vocabularies()} if pass_vocabs else {}
        iface.register_padatious_intent("test.skill:foo.intent", filename,
                                        "en-us", **kwargs)
        return captured["samples"]

    def test_padacioso_inline_voc_intent_matches(self):
        from padacioso import IntentContainer
        engine = IntentContainer()
        engine.add_intent("foo", self._samples(pass_vocabs=True))
        self.assertEqual(engine.calc_intent("what about widget").get("name"),
                         "foo")

    def test_padacioso_raw_reference_is_rejected(self):
        # an unresolved <thing> never reaches the engine as a matchable sample:
        # padacioso cannot build an intent from the dangling reference
        from padacioso import IntentContainer
        from ovos_spec_tools.expansion import MalformedTemplate
        engine = IntentContainer()
        with self.assertRaises(MalformedTemplate):
            engine.add_intent("foo", self._samples(pass_vocabs=False))


if __name__ == "__main__":
    unittest.main()
