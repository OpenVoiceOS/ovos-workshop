import unittest
from tempfile import TemporaryDirectory
from pathlib import Path


class TestInlineVocabReferences(unittest.TestCase):
    """OVOS-INTENT-1 §3.7: an inline ``<name>`` reference in a ``.intent`` or
    ``.blacklist`` file must expand in place from the sibling ``.voc`` of that
    name found in the same locale directory."""

    def _skill_dir(self, files: dict) -> str:
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        locale = Path(tmp.name, "locale", "en-us")
        locale.mkdir(parents=True)
        for name, content in files.items():
            (locale / name).write_text(content)
        return tmp.name

    def _resources(self, skill_dir):
        from ovos_workshop.resource_files import SkillResources
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


if __name__ == "__main__":
    unittest.main()
