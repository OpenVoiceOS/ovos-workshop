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
"""Owner ruling: "when a .intent names a slot we have an .entity for, that
should be automatically picked up... i see no reason to not register every
.entity file." These tests cover the auto-discovery added to
`OVOSSkill.load_lang` / `OVOSSkill._auto_register_entity_files`:

- every shipped ``.entity`` file gets registered, not just the ones a
  ``.intent`` happens to name a slot for
- ordering: entity registrations reach the bus before/with the first
  intent template for the same lang (never after - the ggwave/pokepedia
  bug class)
- idempotency: reloading resources / calling the explicit
  `register_entity_file` API for an already auto-registered file does not
  double-register
- the ``skills.auto_register_entity_files`` config gate disables it
- a bare '#' placeholder line is flagged as dead (comment-stripped, not a
  digit wildcard) rather than silently doing nothing
"""
import json
import unittest
from os.path import dirname

from ovos_workshop.skills.ovos import OVOSSkill
from ovos_utils.fakebus import FakeBus

RES_DIR = f"{dirname(__file__)}/ovos_tskill_autoentity"


def _make_bus():
    bus = FakeBus()
    bus.emitted_msgs = []

    def get_msg(msg):
        bus.emitted_msgs.append(json.loads(msg))

    bus.on("message", get_msg)
    return bus


def _make_skill(bus, skill_id="autoentity.test"):
    return OVOSSkill(skill_id=skill_id, bus=bus, resources_dir=RES_DIR)


class TestAutoEntityDiscovery(unittest.TestCase):
    """Every ``.entity`` file under locale resources is registered, with no
    filtering by whether some ``.intent`` declares a matching slot name."""

    def setUp(self):
        self.bus = _make_bus()
        self.skill = _make_skill(self.bus)

    def _entity_regs(self):
        return [m["data"] for m in self.bus.emitted_msgs
                if m["type"] == "ovos.entity.register"]

    def test_entity_auto_registered_on_first_resource_load(self):
        # touching resources for the first time (e.g. via register_intent_file,
        # or any other resource access) must auto-register every .entity file
        self.skill.load_lang(RES_DIR, "en-US")
        names = {d["entity_name"] for d in self._entity_regs()}
        self.assertIn("game", names)

    def test_unreferenced_entity_file_is_still_registered(self):
        """unused.entity is not named by any {slot} in play.intent - the
        owner ruling is explicit that every shipped .entity file is
        registered regardless of whether a slot references it."""
        self.skill.load_lang(RES_DIR, "en-US")
        names = {d["entity_name"] for d in self._entity_regs()}
        self.assertIn("unused", names)

    def test_entity_samples_match_file_contents(self):
        self.skill.load_lang(RES_DIR, "en-US")
        data = next(d for d in self._entity_regs() if d["entity_name"] == "game")
        self.assertEqual(set(data["samples"]), {"chess", "poker"})

    def test_nested_entity_file_is_registered(self):
        """subdir/pet.entity is discovered by the recursive rglob, but
        ResourceFile._locate() (resource_files.py) matches candidates by
        BASENAME against os.walk's file list - re-searching for it by the
        subfolder-qualified name "subdir/pet" never matches anything, so a
        naive re-lookup silently fails to register it. Auto-discovery must
        pass the already-resolved path through instead of re-deriving one."""
        self.skill.load_lang(RES_DIR, "en-US")
        names = {d["entity_name"] for d in self._entity_regs()}
        self.assertIn("pet", names,
                      f"nested entity file was not registered, saw: {names}")
        data = next(d for d in self._entity_regs() if d["entity_name"] == "pet")
        self.assertEqual(set(data["samples"]), {"cat", "dog"})


class TestAutoEntityOrdering(unittest.TestCase):
    """Entities must reach the bus before/with the intent template that
    names their slot - never after (the ggwave/pokepedia bug class was
    register-after-train)."""

    def setUp(self):
        self.bus = _make_bus()
        self.skill = _make_skill(self.bus)

    def test_entity_registered_before_intent_template(self):
        self.skill.register_intent_file("play.intent", None)
        types = [m["type"] for m in self.bus.emitted_msgs]
        entity_idx = types.index("ovos.entity.register")
        template_idx = types.index("ovos.intent.register.template")
        self.assertLess(entity_idx, template_idx,
                        "entity registration must precede the intent "
                        "template registration on the bus")


class TestAutoEntityIdempotency(unittest.TestCase):
    """Loading resources twice / mixing auto-discovery with an explicit
    register_entity_file() call for the same file must register once,
    not stack duplicate bus registrations."""

    def setUp(self):
        self.bus = _make_bus()
        self.skill = _make_skill(self.bus)

    def _entity_regs(self, name):
        return [m["data"] for m in self.bus.emitted_msgs
                if m["type"] == "ovos.entity.register"
                and m["data"]["entity_name"] == name]

    def test_repeated_load_lang_does_not_double_register(self):
        self.skill.load_lang(RES_DIR, "en-US")
        self.skill.load_lang(RES_DIR, "en-US")
        self.skill.load_lang(RES_DIR, "en-US")
        self.assertEqual(len(self._entity_regs("game")), 1)

    def test_explicit_register_after_auto_discovery_does_not_double_register(self):
        # first touch triggers auto-discovery (e.g. via an intent file load)
        self.skill.register_intent_file("play.intent", None)
        self.assertEqual(len(self._entity_regs("game")), 1)
        # a skill author who still explicitly calls register_entity_file()
        # for the same file must not get a second registration
        self.skill.register_entity_file("game.entity")
        self.assertEqual(len(self._entity_regs("game")), 1)

    def test_direct_auto_register_call_is_idempotent(self):
        self.skill.load_lang(RES_DIR, "en-US")
        # calling the internal discovery method again directly (e.g. a
        # future reload path) must not re-emit
        self.skill._auto_register_entity_files("en-US")
        self.assertEqual(len(self._entity_regs("game")), 1)


class TestAutoEntityConfigGate(unittest.TestCase):
    """skills.auto_register_entity_files=false trivially disables the
    feature, protecting deployments that need to opt out."""

    def test_disabled_via_config(self):
        # config_core is a process-wide Configuration() singleton shared by
        # every skill instance, and skill construction itself triggers the
        # first load_lang() (via load_data_files -> _startup) - so the gate
        # must be set BEFORE construction, and restored right after so it
        # can't leak "disabled" into other tests' skills.
        from ovos_config.config import Configuration
        original = Configuration().get("skills", {}).get(
            "auto_register_entity_files", True)
        Configuration().setdefault("skills", {})[
            "auto_register_entity_files"] = False
        try:
            bus = _make_bus()
            skill = _make_skill(bus, skill_id="autoentity.disabled.test")
            names = {m["data"]["entity_name"] for m in bus.emitted_msgs
                    if m["type"] == "ovos.entity.register"}
            self.assertNotIn("game", names)
            self.assertNotIn("unused", names)
        finally:
            Configuration().setdefault("skills", {})[
                "auto_register_entity_files"] = original

    def test_enabled_by_default(self):
        bus = _make_bus()
        skill = _make_skill(bus, skill_id="autoentity.default.test")
        skill.load_lang(RES_DIR, "en-US")
        names = {m["data"]["entity_name"] for m in bus.emitted_msgs
                if m["type"] == "ovos.entity.register"}
        self.assertIn("game", names)


class TestHashPlaceholderDeprecation(unittest.TestCase):
    """A bare '#' line in an .entity file is a dead mycroft-core convention:
    `read_resource_file` drops any line starting with '#' as a COMMENT, so
    it is never registered as a digit wildcard (or anything else). Flag it
    rather than silently shipping a no-op entity file."""

    def test_hash_placeholder_file_yields_no_samples(self):
        from ovos_spec_tools.resources import read_resource_file
        from pathlib import Path
        samples = read_resource_file(Path(f"{RES_DIR}/locale/en-US/offset.entity"))
        # executed evidence: '#' is comment syntax, not a wildcard token -
        # it never reaches the samples list at all
        self.assertEqual(samples, [])

    def test_hash_placeholder_entity_is_not_registered(self):
        bus = _make_bus()
        skill = _make_skill(bus, skill_id="autoentity.hash.test")
        skill.load_lang(RES_DIR, "en-US")
        names = {m["data"]["entity_name"] for m in bus.emitted_msgs
                if m["type"] == "ovos.entity.register"}
        # no valid samples survive comment-stripping -> register_entity()
        # itself refuses to register an empty entity
        self.assertNotIn("offset", names)

    def test_hash_placeholder_logs_deprecation_warning(self):
        from unittest.mock import patch
        bus = _make_bus()
        # construction itself triggers the first load_lang() (via
        # load_data_files -> _startup), so the patch must be in place
        # BEFORE the skill is built, not just around an explicit call
        with patch("ovos_workshop.skills.ovos.log_deprecation") as mock_dep:
            _make_skill(bus, skill_id="autoentity.hash.warn.test")
        messages = [c.args[0] for c in mock_dep.call_args_list]
        self.assertTrue(any("placeholder" in m for m in messages),
                        f"no '#' placeholder deprecation warning logged, "
                        f"saw: {messages}")


if __name__ == '__main__':
    unittest.main()
