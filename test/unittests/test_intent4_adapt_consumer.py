"""Producer -> consumer regression: a real ``AdaptPipeline`` (from
ovos-adapt-parser / ovos-adapt-pipeline-plugin) wired to a real
``IntentServiceInterface``.

The bug class this guards against: when the INTENT-4 producer (this repo)
hand-emits ``ovos.intent.register.keyword`` for an intent that names a
context-only keyword (an adapt ``.require()``/``.optionally()`` naming a
keyword with no registered vocab samples, e.g. OVOS-CONTEXT-1 gating), the
*consumer* (the real adapt pipeline) ends up holding TWO parsers for the same
intent name: the legacy one (full definition, context-gated) and an ungated
spec-side twin built from the (necessarily incomplete) payload. adapt's
``determine_intent`` iterates parsers and the ungated twin can shadow the
legacy one, matching with the gate (or optional slot) silently dropped.

This test wires the two real components together (no mocked pipeline) and
asserts the parser COUNT the consumer ends up holding, for both the
`require()` and `optionally()` context-only cases.
"""
import unittest
from unittest import mock

import pytest
from ovos_bus_client.message import Message

from ovos_workshop.intents import IntentServiceInterface, IntentBuilder

# Deliberate legacy-coverage suite: exercises the deprecated
# register_adapt_* facade on purpose to guard the producer/consumer
# double-registration regression.
pytestmark = pytest.mark.filterwarnings(
    "ignore:(IntentServiceInterface\\.)?register_(adapt|padatious)_\\w+ "
    "is deprecated:DeprecationWarning"
)

try:
    from ovos_adapt.opm import AdaptPipeline
    _HAVE_ADAPT_PIPELINE = True
except ImportError:  # pragma: no cover - guarded skip, not expected in CI
    _HAVE_ADAPT_PIPELINE = False

SKILL_ID = "consumer.test.skill"


class _WireBus:
    """Minimal bus that forwards producer emits into a real AdaptPipeline,
    the way the real OVOS message bus + adapt plugin do in production."""

    def __init__(self):
        self.pipeline = AdaptPipeline(mock.Mock())
        self.seen = []

    def emit(self, msg):
        self.seen.append(msg.msg_type)
        if msg.msg_type == "register_vocab":
            self.pipeline.handle_register_vocab(msg)
        elif msg.msg_type == "register_intent":
            self.pipeline.handle_register_intent(msg)
        elif msg.msg_type == "ovos.intent.register.keyword":
            self.pipeline.handle_spec_register_keyword(msg)

    def on(self, *_a, **_k):
        pass


def _parsers_for(pipeline, intent_name):
    """All adapt IntentParser objects registered under ``intent_name``
    across every language engine the pipeline holds."""
    full_name = f"{SKILL_ID}:{intent_name}"
    return [p for engine in pipeline.engines.values()
            for p in engine.intent_parsers if p.name == full_name]


@unittest.skipUnless(_HAVE_ADAPT_PIPELINE,
                     "ovos-adapt-parser (ovos_adapt.opm.AdaptPipeline) not installed")
class RealAdaptConsumerTest(unittest.TestCase):
    """Wires a real IntentServiceInterface producer to a real AdaptPipeline
    consumer and asserts on the consumer's resulting parser table."""

    def setUp(self):
        self.bus = _WireBus()
        self.iface = IntentServiceInterface(self.bus)
        self.iface.set_id(SKILL_ID)

    def test_context_only_require_yields_exactly_one_consumer_parser(self):
        self.iface.register_adapt_keyword("TellMeMoreKW", "tell me more",
                                          lang="en-US")
        parser = (IntentBuilder("tell_me_more")
                  .require("TellMeMoreKW")
                  .require("prev_dialog")      # context keyword, no vocab
                  .build())
        self.iface.register_adapt_intent("tell_me_more", parser)

        # exactly one emit reached the pipeline as a parser: the legacy one.
        self.assertEqual(self.bus.seen.count("register_intent"), 1)
        self.assertEqual(
            self.bus.seen.count("ovos.intent.register.keyword"), 0,
            "producer must not emit the spec keyword topic for a "
            "context-only require()")

        parsers = _parsers_for(self.bus.pipeline, "tell_me_more")
        self.assertEqual(len(parsers), 1,
                         "consumer must hold exactly one parser for the "
                         "intent: the legacy, context-gated one")
        # munged skill-prefix names both required keywords; the gate survives.
        self.assertEqual(len(parsers[0].requires), 2)
        self.assertTrue(any(r[0].endswith("prev_dialog")
                            for r in parsers[0].requires),
                        "the context-gating keyword must still be a require()")

    def test_context_only_optional_yields_exactly_one_consumer_parser(self):
        self.iface.register_adapt_keyword("TellMeMoreKW", "tell me more",
                                          lang="en-US")
        parser = (IntentBuilder("tell_me_more")
                  .require("TellMeMoreKW")
                  .optionally("prev_dialog")   # context keyword, no vocab
                  .build())
        self.iface.register_adapt_intent("tell_me_more", parser)

        self.assertEqual(self.bus.seen.count("register_intent"), 1)
        self.assertEqual(
            self.bus.seen.count("ovos.intent.register.keyword"), 0,
            "producer must not emit the spec keyword topic for a "
            "context-only optionally()")

        parsers = _parsers_for(self.bus.pipeline, "tell_me_more")
        self.assertEqual(len(parsers), 1,
                         "consumer must hold exactly one parser for the "
                         "intent: the legacy one, carrying the optional slot")
        self.assertEqual(len(parsers[0].optional), 1)
        self.assertTrue(parsers[0].optional[0][0].endswith("prev_dialog"),
                        "the optional context slot must still be present")


if __name__ == "__main__":
    unittest.main()
