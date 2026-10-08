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

Handling one padacioso template intent calls the real
``OVOSSkill.set_cross_skill_context`` API - the producer under test - with
the bare shared key ``person``.
"""
from threading import Event

from ovos_workshop.skills.ovos import OVOSSkill


class Context1SetterTestSkill(OVOSSkill):
    """Registers one template intent whose handler publishes a
    shared-scope context entry for a different skill to pick up."""

    def initialize(self):
        self.handled = Event()
        self.register_intent_file("remember.intent", self.handle_remember)

    def handle_remember(self, message):
        self.set_cross_skill_context("person", "Bob")
        self.handled.set()


def create_skill():
    return Context1SetterTestSkill()
