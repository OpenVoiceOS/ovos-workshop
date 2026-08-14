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
"""Fixture skill for the auto-register-entity-files end-to-end test.

Ships a ``game.entity`` file that ``play.intent`` references via the
``{game}`` slot, but NEVER calls ``register_entity_file`` explicitly - the
entity must reach the matcher purely from the automatic locale-resource
discovery (see ``OVOSSkill._auto_register_entity_files``).
"""
from ovos_workshop.skills.ovos import OVOSSkill


class AutoEntityTestSkill(OVOSSkill):
    """Registers one padatious template intent whose slot is filled by a
    shipped-but-never-explicitly-registered ``.entity`` file."""

    def initialize(self):
        # NOTE: no self.register_entity_file("game.entity") call - that is
        # the point of this fixture.
        self.register_intent_file("play.intent", self.handle_play)

    def handle_play(self, message):
        pass


def create_skill():
    return AutoEntityTestSkill()
