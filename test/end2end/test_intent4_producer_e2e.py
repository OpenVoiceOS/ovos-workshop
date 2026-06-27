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
"""Real-bus end-to-end test of the OVOS-INTENT-4 producer.

This is the end-to-end counterpart of ``test/unittests/test_intent4_producer.py``.
The unit test pokes ``IntentServiceInterface`` methods directly on a FakeBus to
assert the spec payloads are *hand-built* correctly. This test instead boots a
real (mini) OVOS stack via ovoscope's ``MiniCroft`` and loads a real fixture
``OVOSSkill`` (``intent4_test_skill``). On skill load the skill's registration
calls flow through the full real path — ``register_vocabulary`` ->
``munge_intent_parser`` -> ``register_adapt_intent`` and
``register_intent_file`` / ``register_entity_file`` -> the producer — so we
prove the INTENT-4 topics actually appear *on the bus* end-to-end, not merely
that a method hand-emits them.

Namespace bridging is disabled on the harness bus (``modernize=False``,
``emit_legacy=False``) so the spec topics cannot be synthesized by the bus's
``MIGRATION_MAP`` bridge — if ``ovos.intent.register.keyword`` / ``.template``
/ ``ovos.entity.register`` appear, the producer (and only the producer) put
them there. ``register_vocab`` / ``register_intent`` /
``padatious:register_intent`` / ``padatious:register_entity`` are NOT in the
MIGRATION_MAP, so the legacy dual-emit is likewise genuinely the producer's.
For §8.2 ``ovos.intent.deregister`` the opposite holds: ``detach_intent`` *is*
in the MIGRATION_MAP, so with bridging off we can assert the producer emits the
spec topic and does NOT itself hand-emit the legacy one.

The real munged path exposes two §5/§6/§7 divergences the unit test (which
bypasses ``munge_intent_parser`` and skill-level resource loading) does not —
these are marked ``xfail``; everything else is expected green.
"""
import sys
from os.path import dirname

import pytest

try:
    from ovoscope import get_minicroft
    HAS_OVOSCOPE = True
except ImportError:
    HAS_OVOSCOPE = False

from ovos_spec_tools import SpecMessage

# the fixture skill lives next to this file in its own package directory so its
# `root_dir` resolves there and its locale/en-us resources are discoverable.
sys.path.insert(0, dirname(__file__))

SKILL_ID = "intent4.e2e.test"

pytestmark = pytest.mark.skipif(not HAS_OVOSCOPE,
                                reason="ovoscope not installed")


def _boot():
    """Boot a real MiniCroft with the INTENT-4 fixture skill, bridging off."""
    from intent4_test_skill import Intent4TestSkill
    return get_minicroft([SKILL_ID],
                         extra_skills={SKILL_ID: Intent4TestSkill},
                         # isolate namespaces: no MIGRATION_MAP bridging, so any
                         # spec topic on the bus was emitted by the producer.
                         modernize=False, emit_legacy=False)


def _of_type(mc, msg_type):
    """All boot messages of a given type (data, context) tuples."""
    return [(m.data, m.context) for m in mc.boot_messages
            if m.msg_type == str(msg_type)]


class TestIntent4ProducerE2E:
    """The fixture skill is loaded once; assertions inspect the registration
    topics captured during boot."""

    @classmethod
    def setup_class(cls):
        from ovos_utils.log import LOG
        LOG.set_level("ERROR")
        cls.mc = _boot()

    @classmethod
    def teardown_class(cls):
        if getattr(cls, "mc", None) is not None:
            cls.mc.stop()

    # ------------------------------------------------------------------ §5

    def test_keyword_topic_flows_on_real_bus(self):
        """§5: loading a skill with an adapt keyword intent puts exactly one
        ``ovos.intent.register.keyword`` on the bus, alongside the legacy
        ``register_intent`` (dual-emit)."""
        kw = _of_type(self.mc, SpecMessage.INTENT_REGISTER_KEYWORD)
        assert len(kw) == 1, "spec keyword topic did not flow on the real bus"
        # legacy register_intent dual-emitted (NOT bridged: not in MIGRATION_MAP)
        assert len(_of_type(self.mc, "register_intent")) >= 1
        # legacy register_vocab also went out for the adapt vocab
        assert len(_of_type(self.mc, "register_vocab")) >= 1

    def test_keyword_identity_and_descriptors(self):
        """§3.2 identity + §5.1/§5.2 inlined ``{name, samples}`` descriptors,
        with the producer's ``to_alnum(skill_id)`` munge prefix stripped on the
        wire (real ``munge_intent_parser`` path)."""
        data, context = _of_type(self.mc, SpecMessage.INTENT_REGISTER_KEYWORD)[0]

        # §3.2 identity
        assert data["skill_id"] == SKILL_ID
        assert data["intent_name"] == "set_brightness"
        assert data["lang"] == "en-US"
        assert context["skill_id"] == SKILL_ID

        # §5.2 all four role keys present
        for key in ("required", "optional", "one_of", "excluded"):
            assert key in data

        # required descriptors: skill-prefix munge stripped, samples inlined
        req = {d["name"]: d["samples"] for d in data["required"]}
        assert req["setKW"] == ["set", "change", "adjust"]
        assert req["brightnessKW"] == ["brightness", "light level"]

        # one_of is an array of groups; the single group carries both members
        assert len(data["one_of"]) == 1
        group = {d["name"]: d["samples"] for d in data["one_of"][0]}
        assert group["upKW"] == ["up", "higher"]
        assert group["downKW"] == ["down", "lower"]

        # optional descriptor inlined
        opt = {d["name"]: d["samples"] for d in data["optional"]}
        assert opt["politeKW"] == ["please"]

    @pytest.mark.xfail(reason="INTENT-4 §5.2: 'excluded' carries the excluded "
                              "vocabulary descriptors; on the real stack "
                              "munge_intent_parser does NOT munge "
                              "intent_parser.excludes (stays 'questionKW') while "
                              "register_vocabulary caches samples under the "
                              "munged key ('<alnum_skill_id>questionKW'), so "
                              "_spec_keyword_descriptors finds no samples and the "
                              "producer emits excluded=[] (excluded vocab silently "
                              "dropped on the munged e2e path)",
                       strict=False)
    def test_excluded_descriptor_present(self):
        data, _ = _of_type(self.mc, SpecMessage.INTENT_REGISTER_KEYWORD)[0]
        exc = {d["name"]: d["samples"] for d in data["excluded"]}
        assert exc["questionKW"] == ["what is"]

    # ------------------------------------------------------------------ §6

    def test_template_topic_flows_on_real_bus(self):
        """§6: the padatious intent file registration puts exactly one
        ``ovos.intent.register.template`` on the bus, alongside legacy
        ``padatious:register_intent``."""
        tmpl = _of_type(self.mc, SpecMessage.INTENT_REGISTER_TEMPLATE)
        assert len(tmpl) == 1, "spec template topic did not flow on the real bus"
        assert len(_of_type(self.mc, "padatious:register_intent")) == 1

        data, context = tmpl[0]
        assert data["skill_id"] == SKILL_ID
        assert data["lang"] == "en-US"
        # §6: samples inlined from the .intent file (file path dropped)
        assert data["samples"] == ["(play|put on) {query}",
                                   "i want to listen to {query}"]
        # §6: blacklist defaults empty
        assert data["blacklist"] == []
        assert context["skill_id"] == SKILL_ID

    @pytest.mark.xfail(reason="INTENT-4 §6: 'intent_name' is the skill-local "
                              "intent name; on the real stack a skill registers "
                              "a padatious intent by its resource *filename* "
                              "('play.intent'), and the producer's "
                              "intent_name.split(':')[-1] keeps the '.intent' "
                              "suffix, so the wire intent_name is 'play.intent' "
                              "rather than the clean 'play'",
                       strict=False)
    def test_template_intent_name_clean(self):
        data, _ = _of_type(self.mc, SpecMessage.INTENT_REGISTER_TEMPLATE)[0]
        assert data["intent_name"] == "play"

    # ------------------------------------------------------------------ §7

    def test_entity_topic_flows_on_real_bus(self):
        """§7: the padatious entity file registration puts exactly one
        ``ovos.entity.register`` on the bus, alongside legacy
        ``padatious:register_entity``."""
        ent = _of_type(self.mc, SpecMessage.ENTITY_REGISTER)
        assert len(ent) == 1, "spec entity topic did not flow on the real bus"
        assert len(_of_type(self.mc, "padatious:register_entity")) == 1

        data, context = ent[0]
        assert data["skill_id"] == SKILL_ID
        assert data["lang"] == "en-US"
        # §7: samples inlined from the .entity file (file path dropped)
        assert data["samples"] == ["spotify", "youtube music"]
        assert context["skill_id"] == SKILL_ID

    @pytest.mark.xfail(reason="INTENT-4 §7: 'entity_name' is the skill-local "
                              "entity name; on the real stack the skill-level "
                              "register_entity_file munges the entity name with a "
                              "hash (e.g. 'engine_<md5>'), and the producer's "
                              "entity_name.split(':')[-1] preserves that munged "
                              "name rather than the clean 'engine'",
                       strict=False)
    def test_entity_name_clean(self):
        data, _ = _of_type(self.mc, SpecMessage.ENTITY_REGISTER)[0]
        assert data["entity_name"] == "engine"

    # ------------------------------------------------------------------ §8.2

    def test_deregister_topic_flows_spec_only(self):
        """§8.2: detaching an intent on the real stack puts exactly one
        ``ovos.intent.deregister`` on the bus; the producer does NOT itself
        hand-emit the legacy ``detach_intent`` (that rename IS in the
        MIGRATION_MAP, so the bus bridges it — and with bridging off here, no
        legacy topic appears, proving the producer is spec-only)."""
        inst = self.mc.plugin_skills[SKILL_ID].instance

        captured = []
        real_emit = self.mc.bus.emit

        def _cap(msg):
            captured.append((msg.msg_type, dict(msg.data), dict(msg.context)))
            return real_emit(msg)

        self.mc.bus.emit = _cap
        try:
            inst.intent_service.remove_intent("set_brightness")
        finally:
            self.mc.bus.emit = real_emit

        dereg = [(d, c) for t, d, c in captured
                 if t == str(SpecMessage.INTENT_DEREGISTER)]
        assert len(dereg) == 1, "spec deregister topic did not flow"
        data, context = dereg[0]
        assert data["skill_id"] == SKILL_ID
        assert data["intent_name"] == "set_brightness"
        assert context["skill_id"] == SKILL_ID

        # producer must NOT hand-emit the legacy topic (bus MIGRATION_MAP owns
        # that bridge); with bridging off, none should appear
        legacy = [t for t, _, _ in captured if t == "detach_intent"]
        assert legacy == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
