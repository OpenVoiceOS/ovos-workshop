"""OVOS-INTENT-4 producer tests for IntentServiceInterface.

Asserts the dual-emitted spec payloads: §5 ovos.intent.register.keyword,
§6 ovos.intent.register.template, §7 ovos.entity.register, §8.2
ovos.intent.deregister.
"""
import os
import unittest
from hashlib import md5

import pytest
from ovos_spec_tools import SpecMessage
from ovos_utils.fakebus import FakeBus

from ovos_workshop.intents import (IntentServiceInterface, IntentBuilder,
                                    munge_intent_parser, to_alnum)

# Deliberate legacy-coverage suite: exercises the deprecated
# register_adapt_*/register_padatious_* facade on purpose to guard the
# OVOS-INTENT-4 producer payloads those shims still emit.
pytestmark = pytest.mark.filterwarnings(
    "ignore:(IntentServiceInterface\\.)?register_(adapt|padatious)_\\w+ "
    "is deprecated:DeprecationWarning"
)


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

    def test_register_keyword_intent_context_gating_undeclared_defaults_empty(self):
        """OVOS-CONTEXT-1 §6/§6.1: an intent with no gating declaration has
        no precondition - both fields ride the payload as empty lists."""
        self.iface.register_adapt_keyword("setKW", "set", lang="en-US")
        parser = IntentBuilder("set_brightness").require("setKW").build()
        self.iface.register_intent("set_brightness", parser)

        data, _ = self.bus.of_type(SpecMessage.INTENT_REGISTER_KEYWORD)[0]
        self.assertEqual(data["requires_context"], [])
        self.assertEqual(data["excludes_context"], [])
        legacy, _ = self.bus.of_type("register_intent")[0]
        self.assertEqual(legacy["requires_context"], [])
        self.assertEqual(legacy["excludes_context"], [])

    def test_register_keyword_intent_context_gating_verbatim_both_payloads(self):
        """CONTEXT-1 §6 states an engine that does not implement
        OVOS-CONTEXT-1 "ignores them and matches as if absent" - the
        declaration must still reach the wire on adapt/keyword
        registrations, both the spec `ovos.intent.register.keyword`
        payload (INTENT-4 §5, same unknown-fields tolerance as §6) and the
        legacy `register_intent` payload. Short-form (bare string) and
        long-form ({"key":..., "scope":...}) entries both survive
        verbatim, and round-trip through Message (de)serialization."""
        requires = ["confirming_milk"]
        excludes = [{"key": "active_room", "scope": "shared"}]
        self.iface.register_adapt_keyword("setKW", "set", lang="en-US")
        parser = IntentBuilder("set_brightness").require("setKW").build()
        self.iface.register_intent("set_brightness", parser,
                                   requires_context=requires,
                                   excludes_context=excludes)

        data, _ = self.bus.of_type(SpecMessage.INTENT_REGISTER_KEYWORD)[0]
        self.assertEqual(data["requires_context"], requires)
        self.assertEqual(data["excludes_context"], excludes)

        legacy, _ = self.bus.of_type("register_intent")[0]
        self.assertEqual(legacy["requires_context"], requires)
        self.assertEqual(legacy["excludes_context"], excludes)

        from ovos_bus_client.message import Message
        for msg_type, payload in ((SpecMessage.INTENT_REGISTER_KEYWORD, data),
                                   ("register_intent", legacy)):
            wire = Message(msg_type, payload).serialize()
            restored = Message.deserialize(wire)
            self.assertEqual(restored.data["requires_context"], requires)
            self.assertEqual(restored.data["excludes_context"], excludes)

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

    def test_register_template_context_gating_undeclared_defaults_empty(self):
        """OVOS-CONTEXT-1 §6/§6.1: an intent that declares no
        requires_context/excludes_context has no gating precondition -
        both fields ride the payload as empty lists rather than being
        omitted."""
        self.iface.register_template("music.skill:play_music",
                                     ["play {query}"], lang="en-US")
        data, _ = self.bus.of_type(SpecMessage.INTENT_REGISTER_TEMPLATE)[0]
        self.assertEqual(data["requires_context"], [])
        self.assertEqual(data["excludes_context"], [])
        legacy, _ = self.bus.of_type("padatious:register_intent")[0]
        self.assertEqual(legacy["requires_context"], [])
        self.assertEqual(legacy["excludes_context"], [])

    def test_register_template_context_gating_verbatim_both_payloads(self):
        """§6 short-form and §6.1 long-form entries ride verbatim on both
        the spec `ovos.intent.register.template` payload and the legacy
        `padatious:register_intent` payload; a captured payload round-trips
        through Message (de)serialization unchanged."""
        requires = ["confirming_milk"]
        excludes = [{"key": "active_room", "scope": "shared"}]
        self.iface.register_template("music.skill:play_music",
                                     ["play {query}"], lang="en-US",
                                     requires_context=requires,
                                     excludes_context=excludes)

        data, _ = self.bus.of_type(SpecMessage.INTENT_REGISTER_TEMPLATE)[0]
        self.assertEqual(data["requires_context"], requires)
        self.assertEqual(data["excludes_context"], excludes)

        legacy, _ = self.bus.of_type("padatious:register_intent")[0]
        self.assertEqual(legacy["requires_context"], requires)
        self.assertEqual(legacy["excludes_context"], excludes)

        # round-trip through Message (de)serialization: nothing is lost or
        # mutated by the JSON envelope both topics actually travel over.
        from ovos_bus_client.message import Message
        for msg_type, payload in ((SpecMessage.INTENT_REGISTER_TEMPLATE, data),
                                   ("padatious:register_intent", legacy)):
            wire = Message(msg_type, payload).serialize()
            restored = Message.deserialize(wire)
            self.assertEqual(restored.data["requires_context"], requires)
            self.assertEqual(restored.data["excludes_context"], excludes)

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


class RealMungedFlowSpecTest(unittest.TestCase):
    """Reproduce the real skill registration flow (munged names, `.intent`/
    `_<md5>` id munging) and assert the emitted spec payload is un-munged."""

    SKILL_ID = "music.skill"

    def setUp(self):
        self.bus = CapturingBus()
        self.iface = IntentServiceInterface(self.bus)
        self.iface.set_id(self.SKILL_ID)

    # §5.2 `excluded` descriptors must survive munging
    def test_excluded_survives_munged_flow(self):
        prefix = to_alnum(self.SKILL_ID)
        # vocab is registered under MUNGED names (alphanumeric_skill_id prefix),
        # exactly as OVOSSkill.load_vocab_files does
        self.iface.register_adapt_keyword(prefix + "setKW", "set",
                                          aliases=["change"], lang="en-US")
        self.iface.register_adapt_keyword(prefix + "questionKW", "what is",
                                          lang="en-US")
        # the skill builds the parser with UN-munged names, then munges it
        parser = (IntentBuilder("set_brightness")
                  .require("setKW")
                  .exclude("questionKW")
                  .build())
        munge_intent_parser(parser, "set_brightness", self.SKILL_ID)
        self.iface.register_adapt_intent("set_brightness", parser)

        data, _ = self.bus.of_type(SpecMessage.INTENT_REGISTER_KEYWORD)[0]
        # the excluded descriptor must be present with its samples inlined,
        # un-munged on the wire
        exc = {d["name"]: d["samples"] for d in data["excluded"]}
        self.assertEqual(exc, {"questionKW": ["what is"]})
        req = {d["name"]: d["samples"] for d in data["required"]}
        self.assertEqual(req, {"setKW": ["set", "change"]})

    # §6 template intent_name must drop the `.intent` suffix
    def test_template_intent_name_strips_dot_intent(self):
        intent_file = "/tmp/intent4_real_play.intent"
        with open(intent_file, "w") as f:
            f.write("(play|put on) {query}\n")
        try:
            # OVOSSkill.register_intent_file builds `<skill_id>:<file>.intent`
            internal_name = f"{self.SKILL_ID}:play.intent"
            self.iface.register_padatious_intent(internal_name, intent_file,
                                                 lang="en-US")
            data, _ = self.bus.of_type(SpecMessage.INTENT_REGISTER_TEMPLATE)[0]
            self.assertEqual(data["intent_name"], "play")
        finally:
            os.remove(intent_file)

    # §7 entity_name must drop the `_<md5>` hash munge
    def test_entity_name_strips_hash_munge(self):
        entity_file = "/tmp/intent4_real_engine.entity"
        with open(entity_file, "w") as f:
            f.write("spotify\nyoutube music\n")
        try:
            # OVOSSkill.register_entity_file builds
            # `<skill_id>:<basename>_<md5(entity_file)>`
            basename = "engine"
            digest = md5("engine".encode("utf-8")).hexdigest()
            internal_name = f"{self.SKILL_ID}:{basename}_{digest}"
            self.iface.register_padatious_entity(internal_name, entity_file,
                                                 lang="en-US")
            data, _ = self.bus.of_type(SpecMessage.ENTITY_REGISTER)[0]
            self.assertEqual(data["entity_name"], "engine")
        finally:
            os.remove(entity_file)


class DeprecatedFacadeTest(unittest.TestCase):
    """The adapt/padatious engine names are back-compat shims; each one emits
    a DeprecationWarning while still performing its registration."""

    def setUp(self):
        self.bus = CapturingBus()
        self.iface = IntentServiceInterface(self.bus)
        self.iface.set_id("dep.skill")

    def _assert_deprecated(self, func, *args, **kwargs):
        with self.assertWarns(DeprecationWarning):
            return func(*args, **kwargs)

    def test_register_adapt_keyword_deprecated(self):
        self._assert_deprecated(self.iface.register_adapt_keyword,
                                "kw", "hello", lang="en-US")

    def test_register_adapt_intent_deprecated(self):
        self.iface.register_adapt_keyword("kw", "hello", lang="en-US")
        parser = IntentBuilder("greet").require("kw").build()
        self._assert_deprecated(self.iface.register_adapt_intent, "greet",
                                parser)

    def test_register_adapt_regex_deprecated_emits_vocab(self):
        self._assert_deprecated(self.iface.register_adapt_regex,
                                "(?P<name>.*)", lang="en-US")
        self.assertEqual(len(self.bus.of_type("register_vocab")), 1)


class InternalAdaptRegistrationPathTest(unittest.TestCase):
    """OVOSSkill._register_adapt_intent must not self-inflict a deprecation warning."""

    def setUp(self):
        self.bus = CapturingBus()
        self.iface = IntentServiceInterface(self.bus)
        self.iface.set_id("internal.skill")
        self.iface.register_keyword("kw", "hello", lang="en-US")

    def test_munge_and_register_intent_emits_no_deprecation_warning(self):
        import warnings
        parser = IntentBuilder("greet").require("kw").build()
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            self.iface._adapt.munge_intent_parser(parser, "greet",
                                                   self.iface.skill_id)
            self.iface.register_intent("greet", parser)
        deprecation_warnings = [w for w in caught
                                if issubclass(w.category, DeprecationWarning)]
        self.assertEqual(deprecation_warnings, [])

    def test_munge_and_register_intent_still_spec_emits_keyword(self):
        parser = IntentBuilder("greet").require("kw").build()
        self.iface._adapt.munge_intent_parser(parser, "greet",
                                              self.iface.skill_id)
        self.iface.register_intent("greet", parser)
        payloads = self.bus.of_type(SpecMessage.INTENT_REGISTER_KEYWORD)
        self.assertEqual(len(payloads), 1)
        data, _ = payloads[0]
        self.assertEqual(data["required"], [{"name": "kw", "samples": ["hello"]}])


class RegexRegistrationTest(unittest.TestCase):
    """Regex intents are adapt-engine only; the surviving registration name
    is register_adapt_regex."""

    def setUp(self):
        self.bus = CapturingBus()
        self.iface = IntentServiceInterface(self.bus)
        self.iface.set_id("re.skill")

    def test_register_adapt_regex_munges_named_groups(self):
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            self.iface.register_adapt_regex("(?P<name>.*)", lang="en-US")
        data, context = self.bus.of_type("register_vocab")[0]
        self.assertEqual(data["lang"], "en-US")
        # the skill_id-derived prefix is applied to the named group
        self.assertIn("name", data["regex"])
        self.assertEqual(context["skill_id"], "re.skill")


class MalformedRegistrationTests(unittest.TestCase):
    """INTENT-4 §6.3 / §7.2: a registration whose samples are all empty
    carries nothing indexable, so the producer never puts it on the bus."""

    def setUp(self):
        self.bus = CapturingBus()
        self.iface = IntentServiceInterface(self.bus)
        self.iface.set_id("empty.skill")

    def test_template_with_no_valid_samples_is_not_registered(self):
        self.iface.register_template("empty.skill:play.intent", ["", "   "],
                                     "en-US")
        self.assertEqual(self.bus.captured, [])

    def test_entity_with_no_valid_samples_is_not_registered(self):
        self.iface.register_entity("empty.skill:engine", [], "en-US")
        self.assertEqual(self.bus.captured, [])

    def test_blank_samples_are_dropped_from_valid_registration(self):
        self.iface.register_template("empty.skill:play.intent",
                                     ["play {thing}", "  ", ""], "en-US")
        data, _ = self.bus.of_type(SpecMessage.INTENT_REGISTER_TEMPLATE)[0]
        self.assertEqual(data["samples"], ["play {thing}"])


if __name__ == "__main__":
    unittest.main()


class ContextOnlyRequireTest(unittest.TestCase):
    """A `require()` naming a context keyword must not be dropped on the wire.

    OVOS-CONTEXT-1 gating is expressed in adapt by requiring an entity that
    only the intent-context injection can supply, so that vocabulary has no
    samples. Emitting the INTENT-4 payload without it registers an ungated
    copy of the intent, which then matches with no context set.
    """

    def setUp(self):
        self.bus = CapturingBus()
        self.iface = IntentServiceInterface(self.bus)
        self.iface.set_id("test.skill")

    def test_context_only_require_suppresses_spec_emit(self):
        self.iface.register_adapt_keyword("TellMeMoreKW", "tell me more",
                                          lang="en-US")
        parser = (IntentBuilder("tell_me_more")
                  .require("prev_dialog")      # context keyword, no vocab
                  .require("TellMeMoreKW")
                  .build())

        self.iface.register_adapt_intent("tell_me_more", parser)

        # legacy registration still carries the full definition
        self.assertEqual(len(self.bus.of_type("register_intent")), 1)
        # ... and no weakened spec registration is emitted
        self.assertEqual(self.bus.of_type(SpecMessage.INTENT_REGISTER_KEYWORD), [])

    def test_context_only_exclude_suppresses_spec_emit(self):
        self.iface.register_adapt_keyword("HelloKW", "hello", lang="en-US")
        parser = (IntentBuilder("greet")
                  .require("HelloKW")
                  .exclude("said_hello")       # context keyword, no vocab
                  .build())

        self.iface.register_adapt_intent("greet", parser)

        self.assertEqual(self.bus.of_type(SpecMessage.INTENT_REGISTER_KEYWORD), [])

    def test_context_only_optional_suppresses_spec_emit(self):
        """An `optionally()` naming a context keyword must also suppress the
        spec emit: dropping it silently would still register a *stronger*
        matcher on the wire than the legacy path (missing the optional
        context slot in match data), and the twin parser would win the
        match, robbing the skill of that slot.
        """
        self.iface.register_adapt_keyword("TellMeMoreKW", "tell me more",
                                          lang="en-US")
        parser = (IntentBuilder("tell_me_more")
                  .require("TellMeMoreKW")
                  .optionally("prev_dialog")   # context keyword, no vocab
                  .build())

        self.iface.register_adapt_intent("tell_me_more", parser)

        # legacy registration still carries the full definition
        self.assertEqual(len(self.bus.of_type("register_intent")), 1)
        # ... and no weakened spec registration is emitted
        self.assertEqual(self.bus.of_type(SpecMessage.INTENT_REGISTER_KEYWORD), [])

    def test_fully_sampled_intent_still_emits(self):
        self.iface.register_adapt_keyword("HelloKW", "hello", lang="en-US")
        parser = IntentBuilder("greet").require("HelloKW").build()

        self.iface.register_adapt_intent("greet", parser)

        emitted = self.bus.of_type(SpecMessage.INTENT_REGISTER_KEYWORD)
        self.assertEqual(len(emitted), 1)
        self.assertEqual([d["name"] for d in emitted[0][0]["required"]],
                         ["HelloKW"])
