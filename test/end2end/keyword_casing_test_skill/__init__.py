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
"""Fixture skill for the vocab-casing regression test (PR #485).

Loads a CamelCase-named ``.voc`` file (``HelloWorldKeyword.voc``) purely via
the normal skill-loading path (``load_data_files`` -> ``load_skill_vocabulary``),
never via ``self.register_vocabulary``, so the on-disk basename casing is what
determines the vocab_type used by the INTENT-4 keyword-sample cache.
"""
from ovos_workshop.intents import IntentBuilder
from ovos_workshop.skills.ovos import OVOSSkill


class KeywordCasingTestSkill(OVOSSkill):
    """Registers one adapt intent that requires a keyword loaded from a
    CamelCase ``.voc`` file, to guard against the .title() casing bug."""

    def initialize(self):
        # NOTE: no self.register_vocabulary() call here on purpose - the
        # keyword samples must come exclusively from the .voc file on disk
        # via the automatic load_data_files() -> load_skill_vocabulary() path.
        adapt_intent = (IntentBuilder("greet")
                        .require("HelloWorldKeyword")
                        .build())
        self.register_intent(adapt_intent, self.handle_greet)

    def handle_greet(self, message):
        pass


def create_skill():
    return KeywordCasingTestSkill()
