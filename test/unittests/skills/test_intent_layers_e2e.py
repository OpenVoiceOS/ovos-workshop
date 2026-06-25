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
"""End-to-end test of intent-context gated layers on a real (mini) OVOS stack.

A purpose-built 4-layer demo skill is loaded on an ovoscope MiniCroft harness
(FakeBus). The test drives utterances that advance layer0 -> layer1 -> layer2
-> layer3 and asserts, via the live adapt pipeline, that at each step ONLY the
active layer's intent matches and the other layers' intents do NOT (because
their gating context is not set). It also asserts that reset removes the
context so the layer intents stop matching.

The demo skill is built entirely with adapt IntentBuilders; the layer context
mechanism injects each layer's context token as an additional `.require()` on
the intent, so the intent can only match while that layer is active.
"""
import time
import unittest

import pytest
from ovos_bus_client.message import Message
from ovos_bus_client.session import SessionManager

try:
    from ovoscope import MiniCroft, ADAPT_PIPELINE
    HAS_OVOSCOPE = True
except ImportError:
    HAS_OVOSCOPE = False

from ovos_workshop.intents import IntentBuilder
from ovos_workshop.decorators import layer_intent, enables_layer, disables_layer, resets_layers
from ovos_workshop.decorators.layers import layer_context_token
from ovos_workshop.skills.ovos import OVOSSkill

SKILL_ID = "demo-layers.test"


class FourLayerDemoSkill(OVOSSkill):
    """Minimal skill with exactly 4 intent layers (layer0..layer3) plus two
    always-on intents (start / status) that are NOT gated by any layer."""

    def initialize(self):
        self.reached = []  # ordered record of which layer handlers fired
        # start with all layers off
        self.intent_layers.reset()

    # always-on "begin" / "status" intents are wired onto the class below via
    # the standard intent_handler decorator (they must match regardless of
    # which layer, if any, is active).

    # --- layer 0 (activated by the always-on "begin" intent) ---------------
    @layer_intent(IntentBuilder("Step0Intent").require("step"), "layer0")
    @enables_layer("layer1")
    @disables_layer("layer0")
    def handle_step0(self, message=None):
        self.reached.append("layer0")

    @layer_intent(IntentBuilder("Step1Intent").require("step"), "layer1")
    @enables_layer("layer2")
    @disables_layer("layer1")
    def handle_step1(self, message=None):
        self.reached.append("layer1")

    @layer_intent(IntentBuilder("Step2Intent").require("step"), "layer2")
    @enables_layer("layer3")
    @disables_layer("layer2")
    def handle_step2(self, message=None):
        self.reached.append("layer2")

    @layer_intent(IntentBuilder("Step3Intent").require("step"), "layer3")
    @resets_layers()
    def handle_step3(self, message=None):
        self.reached.append("layer3")


# always-on intents wired with the standard intent decorator
from ovos_workshop.decorators import intent_handler


def _begin_handler(self, message=None):
    self.reached.append("begin")
    self.intent_layers.activate_layer("layer0")


def _status_handler(self, message=None):
    self.reached.append("status")


FourLayerDemoSkill.handle_begin = intent_handler(
    IntentBuilder("BeginIntent").require("begin"))(_begin_handler)
FourLayerDemoSkill.handle_status = intent_handler(
    IntentBuilder("StatusIntent").require("status"))(_status_handler)


@pytest.mark.skipif(not HAS_OVOSCOPE, reason="ovoscope not installed")
class IntentLayersE2ETest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.core = MiniCroft(
            [],
            extra_skills={SKILL_ID: FourLayerDemoSkill},
            default_pipeline=ADAPT_PIPELINE,
        )
        cls.core.start()
        cls.core.wait_for_intent_service()
        time.sleep(1)
        cls.bus = cls.core.bus
        cls.skill = cls.core.plugin_skills[SKILL_ID].instance
        # register the vocab the intents require (no .voc files in this test)
        for kw, words in (("begin", ["begin", "start"]),
                          ("status", ["status", "where am i"]),
                          ("step", ["step", "next", "advance", "go"])):
            for w in words:
                cls.skill.register_vocabulary(w, kw, lang="en-US")
        cls.bus.emit(Message("mycroft.skills.train"))
        time.sleep(1)

    @classmethod
    def tearDownClass(cls):
        try:
            cls.core.stop()
        except Exception:
            pass

    def setUp(self):
        self.skill.intent_layers.reset()
        SessionManager.default_session.context.clear_context()
        self.skill.reached = []
        time.sleep(0.3)

    # helpers ----------------------------------------------------------------
    def _utter(self, text):
        handlers = []
        self.bus.on("mycroft.skill.handler.start",
                    lambda m: handlers.append(m.data.get("name", "")))
        self.bus.emit(Message("recognizer_loop:utterance",
                              {"utterances": [text], "lang": "en-US"}))
        time.sleep(1.5)
        return handlers

    def _matched_intent(self, text):
        """What intent (if any) the live pipeline selects for `text`."""
        r = self.bus.wait_for_response(
            Message("intent.service.intent.get",
                    {"utterance": text, "lang": "en-US"}),
            "intent.service.intent.reply", timeout=3)
        if not r:
            return None
        intent = r.data.get("intent")
        return intent.get("intent_name") if intent else None

    def _active(self):
        return [l for l in ("layer0", "layer1", "layer2", "layer3")
                if self.skill.intent_layers.is_active(l)]

    def _tokens(self):
        return [c["key"] for c in
                SessionManager.default_session.context.get_context()]

    # tests ------------------------------------------------------------------
    def test_layers_advance_in_sequence_and_gate_intents(self):
        skill = self.skill

        # nothing active yet: a layer "step" intent must NOT match
        self.assertEqual(self._active(), [])
        self.assertIsNone(self._matched_intent("step"),
                          "step matched with no active layer - gating failed")

        # always-on intents work regardless of layer state
        self.assertEqual(self._matched_intent("begin"),
                         f"{SKILL_ID}:BeginIntent")
        self.assertEqual(self._matched_intent("status"),
                         f"{SKILL_ID}:StatusIntent")

        # --- begin -> layer0 active --------------------------------------
        self._utter("begin")
        self.assertEqual(self._active(), ["layer0"])
        self.assertIn(layer_context_token("layer0"), self._tokens())
        # only layer0's step intent matches now
        self.assertEqual(self._matched_intent("step"),
                         f"{SKILL_ID}:Step0Intent")

        # advance through each layer; assert the matched intent is the active
        # layer's, and that exactly one layer is active at a time
        expected = [
            ("layer1", "Step1Intent"),
            ("layer2", "Step2Intent"),
            ("layer3", "Step3Intent"),
        ]
        # fire layer0 -> activates layer1
        self._utter("step")
        for layer_name, intent_name in expected:
            self.assertEqual(self._active(), [layer_name],
                             f"expected only {layer_name} active, got {self._active()}")
            # the active layer's step intent matches
            self.assertEqual(self._matched_intent("step"),
                             f"{SKILL_ID}:{intent_name}")
            # always-on intents still match while a layer is active
            self.assertEqual(self._matched_intent("status"),
                             f"{SKILL_ID}:StatusIntent")
            # advance
            self._utter("step")

        # after firing layer3's handler, resets_layers cleared everything
        self.assertEqual(self._active(), [])
        for tok in self._tokens():
            self.assertFalse(tok.startswith(layer_context_token("")[:5]),
                             f"stale layer token after reset: {tok}")
        # and the step intent no longer matches
        self.assertIsNone(self._matched_intent("step"),
                          "step still matched after reset - context not removed")

        # full ordered playthrough was recorded
        self.assertEqual(skill.reached,
                         ["begin", "layer0", "layer1", "layer2", "layer3"])

    def test_inactive_layer_intents_do_not_match(self):
        """With only layer0 active, layer1/2/3 intents must not be selectable."""
        skill = self.skill
        self._utter("begin")
        self.assertEqual(self._active(), ["layer0"])
        # the matched step intent is layer0's, never a deeper layer's
        self.assertEqual(self._matched_intent("step"), f"{SKILL_ID}:Step0Intent")
        # manually set ONLY layer2 context and confirm layer2 (not layer0) wins
        skill.intent_layers.deactivate_layer("layer0")
        skill.intent_layers.activate_layer("layer2")
        time.sleep(0.3)
        self.assertEqual(self._active(), ["layer2"])
        self.assertEqual(self._matched_intent("step"), f"{SKILL_ID}:Step2Intent")
        # deactivate -> nothing matches
        skill.intent_layers.deactivate_layer("layer2")
        time.sleep(0.3)
        self.assertIsNone(self._matched_intent("step"))


if __name__ == "__main__":
    unittest.main()
