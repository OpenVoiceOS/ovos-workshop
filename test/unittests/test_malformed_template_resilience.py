"""A malformed template line in a locale file must not prevent the valid
lines of the same file from loading or reaching the intent service.

Translated locale files sometimes carry broken templates — translated slot
names (``{Medien}``), truncated slots (``{location``), adjacent slots — and
one such line must be skipped with a warning, not abort the whole resource.
"""
import os
import unittest
from os.path import join
from tempfile import TemporaryDirectory
from unittest.mock import patch

from ovos_workshop.intents import IntentServiceInterface
from ovos_workshop.resource_files import SkillResources


class MockEmitter:
    def __init__(self):
        self.messages = []

    def emit(self, message):
        self.messages.append(message)


class TestResourceLoadResilience(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.skill_dir = self._tmp.name
        self.locale = join(self.skill_dir, "locale", "de-de")
        os.makedirs(self.locale)

    def tearDown(self):
        self._tmp.cleanup()

    def _write(self, name, lines):
        path = join(self.locale, name)
        with open(path, "w") as f:
            f.write("\n".join(lines))
        return path

    def _resources(self):
        return SkillResources(self.skill_dir, "de-de", skill_id="test.skill")

    def test_intent_file_skips_malformed_lines(self):
        self._write("play.intent", ["spiele {media}",
                                    "spiele {genre}{media}",   # adjacent slots
                                    "was läuft in {location",  # truncated slot
                                    "starte {media}"])
        with patch("ovos_workshop.resource_files.LOG.warning") as warn:
            intents = self._resources().load_intent_file("play")
        self.assertEqual(intents, ["spiele {media}", "starte {media}"])
        self.assertEqual(warn.call_count, 2)
        logged = " ".join(str(c) for c in warn.call_args_list)
        self.assertIn("test.skill", logged)
        self.assertIn("play", logged)
        self.assertIn("de-de", logged)
        self.assertIn("{location", logged)

    def test_intent_file_all_lines_malformed(self):
        self._write("play.intent", ["spiele {genre}{media}", "in {location"])
        with patch("ovos_workshop.resource_files.LOG.warning"):
            intents = self._resources().load_intent_file("play")
        self.assertEqual(intents, [])

    def test_vocabulary_file_skips_malformed_lines(self):
        self._write("media.voc", ["musik", "(radio|fernsehen", "film"])
        with patch("ovos_workshop.resource_files.LOG.warning") as warn:
            vocab = self._resources().load_vocabulary_file("media")
        self.assertEqual(vocab, [["musik"], ["film"]])
        self.assertEqual(warn.call_count, 1)

    def test_blacklist_file_skips_malformed_lines(self):
        self._write("thing.voc", ["dies", "das"])
        self._write("play.blacklist", ["spiele <thing> ab",
                                       "spiele <thing> (etwas|",
                                       "halt"])
        with patch("ovos_workshop.resource_files.LOG.warning") as warn:
            phrases = self._resources().load_blacklist_file("play")
        self.assertEqual(sorted(phrases),
                         sorted(["spiele dies ab", "spiele das ab", "halt"]))
        self.assertEqual(warn.call_count, 1)

    def test_dialog_file_skips_lines_missing_data_keys(self):
        self._write("play.dialog", ["spiele {media}", "spiele {Medien}"])
        with patch("ovos_workshop.resource_files.LOG.warning") as warn:
            dialogs = self._resources().load_dialog_file(
                "play", data={"media": "musik"})
        self.assertEqual(dialogs, ["spiele musik"])
        self.assertEqual(warn.call_count, 1)


class TestWireEmissionResilience(unittest.TestCase):
    """The samples emitted on the bus must exclude malformed lines."""

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.emitter = MockEmitter()
        self.interface = IntentServiceInterface(self.emitter)
        self.interface.set_id("test.skill")

    def tearDown(self):
        self._tmp.cleanup()

    def _write(self, name, lines):
        path = join(self._tmp.name, name)
        with open(path, "w") as f:
            f.write("\n".join(lines))
        return path

    def test_register_intent_excludes_malformed_samples(self):
        path = self._write("play.intent", ["play {media}",
                                           "play {Medien}",
                                           "what is on {location",
                                           "start {media}"])
        with patch("ovos_workshop.intents.LOG.warning") as warn:
            self.interface.register_padatious_intent(
                "test.skill:play.intent", path, "de-de")
        self.assertEqual(len(self.emitter.messages), 1)
        msg = self.emitter.messages[0]
        self.assertEqual(msg.msg_type, "padatious:register_intent")
        self.assertEqual(msg.data["samples"],
                         ["play {media}", "start {media}"])
        self.assertEqual(warn.call_count, 2)
        logged = " ".join(str(c) for c in warn.call_args_list)
        self.assertIn("test.skill", logged)
        self.assertIn("play.intent", logged)
        self.assertIn("de-de", logged)
        self.assertIn("{Medien}", logged)

    def test_register_intent_keeps_vocab_references(self):
        # <name> references resolve downstream; they are not malformed
        path = self._write("play.intent", ["play <thing>", "play {Medien}"])
        with patch("ovos_workshop.intents.LOG.warning"):
            self.interface.register_padatious_intent(
                "test.skill:play.intent", path, "en-US")
        self.assertEqual(self.emitter.messages[0].data["samples"],
                         ["play <thing>"])

    def test_register_intent_skipped_when_no_valid_samples(self):
        path = self._write("play.intent", ["play {Medien}", "on {location"])
        with patch("ovos_workshop.intents.LOG.warning") as warn:
            self.interface.register_padatious_intent(
                "test.skill:play.intent", path, "de-de")
        self.assertEqual(self.emitter.messages, [])
        self.assertNotIn("play.intent", self.interface.intent_names)
        self.assertTrue(warn.call_count >= 3)

    def test_register_entity_excludes_malformed_samples(self):
        path = self._write("thing.entity", ["a movie", "ein (film|",
                                            "a song"])
        with patch("ovos_workshop.intents.LOG.warning") as warn:
            self.interface.register_padatious_entity(
                "test.skill:thing", path, "de-de")
        self.assertEqual(len(self.emitter.messages), 1)
        self.assertEqual(self.emitter.messages[0].data["samples"],
                         ["a movie", "a song"])
        self.assertEqual(warn.call_count, 1)

    def test_register_entity_skipped_when_no_valid_samples(self):
        path = self._write("thing.entity", ["ein (film|"])
        with patch("ovos_workshop.intents.LOG.warning"):
            self.interface.register_padatious_entity(
                "test.skill:thing", path, "de-de")
        self.assertEqual(self.emitter.messages, [])


if __name__ == "__main__":
    unittest.main()
