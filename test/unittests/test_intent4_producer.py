"""OVOS-INTENT-4 producer tests for IntentServiceInterface.

The producer (ovos_workshop/intents.py) emits the consolidated INTENT-4
registration topics alongside the legacy ones (dual-emit, since the
restructure is an N->1 consolidation that the bus cannot transparently
bridge — see ovos_spec_tools.MIGRATION_MAP). These tests assert the spec
payloads:

- §5 ``ovos.intent.register.keyword`` with required/optional/one_of/excluded
  vocabulary descriptors inlined ``{name, samples}``;
- §6 ``ovos.intent.register.template`` (samples inlined, ``blacklist``);
- §7 ``ovos.entity.register`` (samples inlined);
- §8.2 ``ovos.intent.deregister`` emitted spec-only (bus bridges to legacy).
"""
import os
import unittest

from ovos_spec_tools import SpecMessage
from ovos_utils.fakebus import FakeBus

from ovos_workshop.intents import IntentServiceInterface, IntentBuilder


class CapturingBus(FakeBus):
    """FakeBus that records every emitted (msg_type, data, context).

    Captures at emit() so we observe exactly what the producer hand-emits
    (the namespace bridge runs downstream of this and is out of scope here).
    """

    def __init__(self):
        super().__init__()
        self.captured = []

    def emit(self, message):
        self.captured.append((message.msg_type, message.data, message.context))
        return super().emit(message)

    def of_type(self, msg_type):
        return [(d, c) for t, d, c in self.captured if t == str(msg_type)]


class AdaptKeywordSpecTest(unittest.TestCase):
    def setUp(self):
        self.bus = CapturingBus()
        self.iface = IntentServiceInterface(self.bus)
        self.iface.set_id("test.skill")

    def test_register_keyword_intent_emits_spec_topic(self):
        # register vocab (primary + aliases) the intent will reference
        self.iface.register_adapt_keyword("setKW", "set",
                                          aliases=["change", "adjust"],
                                          lang="en-US")
        self.iface.register_adapt_keyword("brightnessKW", "brightness",
                                          aliases=["light level"],
                                          lang="en-US")
        self.iface.register_adapt_keyword("upKW", "up",
                                          aliases=["higher"], lang="en-US")
        self.iface.register_adapt_keyword("downKW", "down",
                                          aliases=["lower"], lang="en-US")
        self.iface.register_adapt_keyword("questionKW", "what is",
                                          lang="en-US")

        parser = (IntentBuilder("set_brightness")
                  .require("setKW")
                  .require("brightnessKW")
                  .one_of("upKW", "downKW")
                  .exclude("questionKW")
                  .build())

        self.iface.register_adapt_intent("set_brightness", parser)

        emitted = self.bus.of_type(SpecMessage.INTENT_REGISTER_KEYWORD)
        self.assertEqual(len(emitted), 1)
        data, context = emitted[0]

        # §3.2 identity
        self.assertEqual(data["skill_id"], "test.skill")
        self.assertEqual(data["intent_name"], "set_brightness")
        self.assertEqual(data["lang"], "en-US")
        self.assertEqual(context["skill_id"], "test.skill")

        # §5.2 all four keys present
        for key in ("required", "optional", "one_of", "excluded"):
            self.assertIn(key, data)

        # required descriptors inline the cached samples
        req = {d["name"]: d["samples"] for d in data["required"]}
        self.assertEqual(req["setKW"], ["set", "change", "adjust"])
        self.assertEqual(req["brightnessKW"], ["brightness", "light level"])

        # one_of is an array of groups; the single group has both members
        self.assertEqual(len(data["one_of"]), 1)
        group = {d["name"]: d["samples"] for d in data["one_of"][0]}
        self.assertEqual(group["upKW"], ["up", "higher"])
        self.assertEqual(group["downKW"], ["down", "lower"])

        # excluded descriptor inlines its samples
        exc = {d["name"]: d["samples"] for d in data["excluded"]}
        self.assertEqual(exc["questionKW"], ["what is"])

        # optional empty here
        self.assertEqual(data["optional"], [])

        # legacy register_intent still emitted (dual-emit)
        self.assertEqual(len(self.bus.of_type("register_intent")), 1)

    def test_munged_vocab_names_are_unmunged_on_wire(self):
        # mimic the real skill flow where vocab/parser names carry the
        # to_alnum(skill_id) prefix; the wire `name` must drop it.
        from ovos_workshop.intents import to_alnum
        prefix = to_alnum("test.skill")
        self.iface.register_adapt_keyword(prefix + "greet", "hello",
                                          lang="en-US")
        parser = IntentBuilder(prefix + "greeting").require(prefix + "greet").build()
        self.iface.register_adapt_intent("greeting", parser)

        data, _ = self.bus.of_type(SpecMessage.INTENT_REGISTER_KEYWORD)[0]
        names = [d["name"] for d in data["required"]]
        self.assertEqual(names, ["greet"])  # prefix stripped
        self.assertEqual(data["required"][0]["samples"], ["hello"])

    def test_deregister_emits_spec_only(self):
        self.iface.register_adapt_keyword("xKW", "x", lang="en-US")
        parser = IntentBuilder("foo").require("xKW").build()
        self.iface.register_adapt_intent("foo", parser)
        self.bus.captured.clear()

        self.iface.remove_intent("foo")

        spec = self.bus.of_type(SpecMessage.INTENT_DEREGISTER)
        self.assertEqual(len(spec), 1)
        data, context = spec[0]
        self.assertEqual(data["skill_id"], "test.skill")
        self.assertEqual(data["intent_name"], "foo")
        self.assertEqual(context["skill_id"], "test.skill")
        # spec-only hand emit: the producer must NOT itself emit the legacy
        # `detach_intent` (the bus MIGRATION_MAP bridges it transparently).
        self.assertEqual(self.bus.of_type("detach_intent"), [])


class PadatiousSpecTest(unittest.TestCase):
    def setUp(self):
        self.bus = CapturingBus()
        self.iface = IntentServiceInterface(self.bus)
        self.iface.set_id("music.skill")
        self.intent_file = "/tmp/intent4_producer_test.intent"
        with open(self.intent_file, "w") as f:
            f.write("# comment ignored\n(play|put on) {query}\n"
                    "i want to listen to {query}\n")
        self.entity_file = "/tmp/intent4_producer_test.entity"
        with open(self.entity_file, "w") as f:
            f.write("spotify\nyoutube music\n")

    def tearDown(self):
        for f in (self.intent_file, self.entity_file):
            if os.path.exists(f):
                os.remove(f)

    def test_register_template_emits_spec_topic(self):
        self.iface.register_padatious_intent("music.skill:play_music",
                                             self.intent_file, lang="en-US",
                                             string_blacklist=["trailer"])
        emitted = self.bus.of_type(SpecMessage.INTENT_REGISTER_TEMPLATE)
        self.assertEqual(len(emitted), 1)
        data, context = emitted[0]
        self.assertEqual(data["skill_id"], "music.skill")
        self.assertEqual(data["intent_name"], "play_music")
        self.assertEqual(data["lang"], "en-US")
        self.assertEqual(data["samples"],
                         ["(play|put on) {query}", "i want to listen to {query}"])
        self.assertEqual(data["blacklist"], ["trailer"])
        self.assertEqual(context["skill_id"], "music.skill")
        # legacy still emitted
        self.assertEqual(len(self.bus.of_type("padatious:register_intent")), 1)

    def test_register_template_blacklist_defaults_empty(self):
        self.iface.register_padatious_intent("music.skill:play_music",
                                             self.intent_file, lang="en-US")
        data, _ = self.bus.of_type(SpecMessage.INTENT_REGISTER_TEMPLATE)[0]
        self.assertEqual(data["blacklist"], [])

    def test_register_entity_emits_spec_topic(self):
        self.iface.register_padatious_entity("music.skill:engine",
                                             self.entity_file, lang="en-US")
        emitted = self.bus.of_type(SpecMessage.ENTITY_REGISTER)
        self.assertEqual(len(emitted), 1)
        data, context = emitted[0]
        self.assertEqual(data["skill_id"], "music.skill")
        self.assertEqual(data["entity_name"], "engine")
        self.assertEqual(data["lang"], "en-US")
        self.assertEqual(data["samples"], ["spotify", "youtube music"])
        self.assertEqual(context["skill_id"], "music.skill")
        self.assertEqual(len(self.bus.of_type("padatious:register_entity")), 1)


if __name__ == "__main__":
    unittest.main()
