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
"""Fixture skill for the OVOS-INTENT-4 producer end-to-end test.

This is a *real* OVOSSkill (it lives in its own package directory, so its
``root_dir`` resolves here and its ``locale/en-us/`` resources — ``play.intent``
and ``engine.entity`` — are found by the real ``register_intent_file`` /
``register_entity_file`` machinery). Loading it on an ovoscope ``MiniCroft``
exercises the real registration path on a real bus:

- an **adapt** keyword intent (``set_brightness``) built from
  ``register_vocabulary`` + ``IntentBuilder`` covering every §5.2 role
  (``required`` / ``one_of`` / ``optional`` / ``excluded``);
- a **padatious** template intent (``play``) registered from
  ``play.intent`` (§6); and
- a padatious **entity** registered from ``engine.entity`` (§7).

When loaded, ``IntentServiceInterface`` (the INTENT-4 producer under test)
dual-emits the spec registration topics alongside the legacy ones.
"""
from ovos_workshop.intents import IntentBuilder
from ovos_workshop.skills.ovos import OVOSSkill


class Intent4TestSkill(OVOSSkill):
    """Registers one adapt keyword intent, one padatious template intent, and
    one padatious entity — covering INTENT-4 §5/§6/§7 on a real stack."""

    def initialize(self):
        # --- adapt vocab (§5.1 samples that get inlined into the keyword msg) ---
        # required: setKW (primary + aliases) and brightnessKW
        self.register_vocabulary("set", "setKW")
        self.register_vocabulary("change", "setKW")
        self.register_vocabulary("adjust", "setKW")
        self.register_vocabulary("brightness", "brightnessKW")
        self.register_vocabulary("light level", "brightnessKW")
        # one_of group members
        self.register_vocabulary("up", "upKW")
        self.register_vocabulary("higher", "upKW")
        self.register_vocabulary("down", "downKW")
        self.register_vocabulary("lower", "downKW")
        # optional
        self.register_vocabulary("please", "politeKW")
        # excluded
        self.register_vocabulary("what is", "questionKW")

        # --- adapt keyword intent exercising every §5.2 role ---
        adapt_intent = (IntentBuilder("set_brightness")
                        .require("setKW")
                        .require("brightnessKW")
                        .one_of("upKW", "downKW")
                        .optionally("politeKW")
                        .exclude("questionKW")
                        .build())
        self.register_intent(adapt_intent, self.handle_set_brightness)

        # --- padatious template intent (§6) + entity (§7) from /locale ---
        self.register_intent_file("play.intent", self.handle_play)
        self.register_entity_file("engine.entity")

    def handle_set_brightness(self, message):
        pass

    def handle_play(self, message):
        pass


def create_skill():
    return Intent4TestSkill()
