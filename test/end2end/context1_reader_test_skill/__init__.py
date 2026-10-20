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
"""Fixture skill for the OVOS-CONTEXT-1 §5.0 cross-skill-context
end-to-end test.

Registers one template intent gated by a §6 ``requires_context``
declaration on the SHARED (bare, owner-less) key ``person`` - a DIFFERENT
skill (``context1_setter_test_skill``) is the one that publishes it.
"""
from threading import Event

from ovos_workshop.skills.ovos import OVOSSkill


class Context1ReaderTestSkill(OVOSSkill):
    """Registers one template intent that only matches while a different
    skill's shared context entry is live."""

    def initialize(self):
        self.handled = Event()
        self.last_message = None
        self.register_intent_file(
            "height.intent", self.handle_height,
            requires_context=[{"key": "person", "scope": "shared"}])

    def handle_height(self, message):
        self.last_message = message
        self.handled.set()


def create_skill():
    return Context1ReaderTestSkill()
