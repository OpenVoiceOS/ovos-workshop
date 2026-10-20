"""ConversationalSkill registers @conversational_intent methods during base init."""
import os
import tempfile
import unittest

from ovos_utils.fakebus import FakeBus

from ovos_workshop.decorators import conversational_intent
from ovos_workshop.skills.converse import ConversationalSkill


class _DecoratedSkill(ConversationalSkill):
    def can_converse(self, message) -> bool:
        return False

    @conversational_intent("greet.intent")
    def handle_greet(self, message):
        pass


class _TwoIntentSkill(ConversationalSkill):
    def can_converse(self, message) -> bool:
        return False

    @conversational_intent("greet.intent")
    def handle_greet(self, message):
        pass

    @conversational_intent("bye.intent")
    def handle_bye(self, message):
        pass


class TestConversationalIntentInit(unittest.TestCase):
    def test_decorated_intent_registers_during_init(self):
        with tempfile.TemporaryDirectory() as root:
            locale = os.path.join(root, "locale", "en-US")
            os.makedirs(locale)
            with open(os.path.join(locale, "greet.intent"), "w") as f:
                f.write("hello there\ngood morning\n")

            skill = _DecoratedSkill(bus=FakeBus(), skill_id="converse_init.test",
                                    resources_dir=root)

        self.assertIn("en-US", skill.converse_matchers)
        self.assertEqual(
            skill.converse_matchers["en-US"].calc_intent("hello there")["name"],
            "converse_init.test.converse:greet.intent")

    def test_every_intent_of_a_language_is_kept(self):
        with tempfile.TemporaryDirectory() as root:
            locale = os.path.join(root, "locale", "en-US")
            os.makedirs(locale)
            for name, text in (("greet.intent", "hello there\n"),
                               ("bye.intent", "see you later\n")):
                with open(os.path.join(locale, name), "w") as f:
                    f.write(text)

            skill = _TwoIntentSkill(bus=FakeBus(), skill_id="converse_init.test",
                                    resources_dir=root)

        matcher = skill.converse_matchers["en-US"]
        self.assertEqual(matcher.calc_intent("hello there")["name"],
                         "converse_init.test.converse:greet.intent")
        self.assertEqual(matcher.calc_intent("see you later")["name"],
                         "converse_init.test.converse:bye.intent")


if __name__ == "__main__":
    unittest.main()
