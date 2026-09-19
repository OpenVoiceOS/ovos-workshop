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
"""Real-bus end-to-end test proving a skill's shipped ``.entity`` file is
registered automatically - and reaches the bus before the ``.intent``
template that names its slot - without the skill ever calling
``register_entity_file`` itself.

Boots a real (mini) OVOS stack via ovoscope's ``MiniCroft``, loads the
``auto_entity_test_skill`` fixture (ships ``game.entity``, references
``{game}`` in ``play.intent``, never calls ``register_entity_file``), and
inspects the bus messages captured during boot.
"""
import sys
from os.path import dirname

from ovoscope import get_minicroft

from ovos_bus_client.session import SessionManager
from ovos_spec_tools import SpecMessage

sys.path.insert(0, dirname(__file__))

SKILL_ID = "auto.entity.e2e.test"


def _boot():
    from auto_entity_test_skill import AutoEntityTestSkill
    return get_minicroft([SKILL_ID],
                         extra_skills={SKILL_ID: AutoEntityTestSkill},
                         modernize=False, emit_legacy=False)


def _of_type(mc, msg_type):
    return [(m.data, m.context) for m in mc.boot_messages
            if m.msg_type == str(msg_type)]


def _index_of_first(mc, msg_type):
    for i, m in enumerate(mc.boot_messages):
        if m.msg_type == str(msg_type):
            return i
    return None


class TestAutoEntityRegistrationE2E:
    mc = None

    @classmethod
    def setup_class(cls):
        from ovos_utils.log import LOG
        LOG.set_level("ERROR")
        cls._saved_bus = SessionManager.bus
        cls.mc = _boot()

    @classmethod
    def teardown_class(cls):
        cls.mc.stop()
        SessionManager.bus = cls._saved_bus

    def test_entity_auto_registered_without_explicit_call(self):
        """The skill never calls register_entity_file - the entity must
        still reach the bus, discovered from locale/en-us/game.entity."""
        ent = _of_type(self.mc, SpecMessage.ENTITY_REGISTER)
        names = [d["entity_name"] for d, _ in ent]
        assert "game" in names, \
            f"game.entity was not auto-registered, saw: {names}"

        data, context = next((d, c) for d, c in ent if d["entity_name"] == "game")
        assert data["skill_id"] == SKILL_ID
        assert data["lang"] == "en-US"
        assert set(data["samples"]) == {"chess", "poker", "solitaire"}
        assert context["skill_id"] == SKILL_ID

    def test_entity_registered_before_intent_template(self):
        """Ordering guarantee: the auto-registered entity must reach the bus
        at or before the intent template that names its slot - never after
        (the ggwave/pokepedia bug class was register-after-train)."""
        entity_idx = _index_of_first(self.mc, SpecMessage.ENTITY_REGISTER)
        template_idx = _index_of_first(self.mc, SpecMessage.INTENT_REGISTER_TEMPLATE)
        assert entity_idx is not None, "no entity registration observed"
        assert template_idx is not None, "no intent template registration observed"
        assert entity_idx < template_idx, (
            "entity registration must precede the intent template "
            f"registration on the bus (entity@{entity_idx}, "
            f"template@{template_idx})")

    def test_intent_template_present(self):
        tmpl = _of_type(self.mc, SpecMessage.INTENT_REGISTER_TEMPLATE)
        assert len(tmpl) == 1
        data, _ = tmpl[0]
        assert data["skill_id"] == SKILL_ID
        assert any("game" in s or "{game}" in s for s in ["play {game}"])
