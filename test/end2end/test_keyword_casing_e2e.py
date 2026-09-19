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
"""Real-bus end-to-end regression guard for the vocab-casing bug fixed by
PR #485.

``load_skill_vocabulary`` used to run ``.title()`` on ``.voc`` basenames, so a
CamelCase file like ``HelloWorldKeyword.voc`` became the vocab_type
``Helloworldkeyword`` on the wire, breaking the INTENT-4 exact-string keyword
sample cache (``_adapt_keyword_samples``) and causing
``ovos.intent.register.keyword`` to be emitted with an empty ``samples`` list
for that keyword. Adapt utterance matching itself is case-insensitive, so the
casing bug is invisible there - the *only* observable discriminator is this
spec keyword-emit carrying non-empty samples.

Boots a real (mini) OVOS stack via ovoscope's ``MiniCroft``, loads the
``keyword_casing_test_skill`` fixture (a CamelCase ``.voc`` file loaded purely
through the normal skill-loading path, never via ``register_vocabulary``), and
asserts the ``ovos.intent.register.keyword`` message carries the expected
non-empty samples for that keyword.
"""
import sys
from os.path import dirname

import pytest

from ovoscope import get_minicroft

from ovos_bus_client.session import SessionManager
from ovos_spec_tools import SpecMessage

# the fixture skill lives next to this file in its own package directory so its
# `root_dir` resolves there and its locale/en-us resources are discoverable.
sys.path.insert(0, dirname(__file__))

SKILL_ID = "keyword.casing.e2e.test"

EXPECTED_SAMPLES = ["hello world", "hi there", "greetings"]


def _boot():
    """Boot a real MiniCroft with the keyword-casing fixture skill."""
    from keyword_casing_test_skill import KeywordCasingTestSkill
    return get_minicroft([SKILL_ID],
                         extra_skills={SKILL_ID: KeywordCasingTestSkill},
                         modernize=False, emit_legacy=False)


def _of_type(mc, msg_type):
    """All boot messages of a given type (data, context) tuples."""
    return [(m.data, m.context) for m in mc.boot_messages
            if m.msg_type == str(msg_type)]


class TestKeywordCasingE2E:
    """The fixture skill is loaded once; assertions inspect the registration
    topics captured during boot."""

    mc = None

    @classmethod
    def setup_class(cls):
        from ovos_utils.log import LOG
        LOG.set_level("ERROR")
        # booting a real MiniCroft runs a real IntentService, whose
        # startup calls SessionManager.connect_to_bus(mc.bus) - this
        # mutates the process-wide SessionManager.bus class attribute.
        # Save/restore it so later tests don't inherit a bus pointing at
        # this (now-stopped) MiniCroft instance.
        cls._saved_bus = SessionManager.bus
        cls.mc = _boot()

    @classmethod
    def teardown_class(cls):
        cls.mc.stop()
        SessionManager.bus = cls._saved_bus

    def test_keyword_topic_flows_on_real_bus(self):
        """Exactly one ``ovos.intent.register.keyword`` for the CamelCase
        keyword's adapt intent."""
        kw = _of_type(self.mc, SpecMessage.INTENT_REGISTER_KEYWORD)
        assert len(kw) == 1, "spec keyword topic did not flow on the real bus"

    def test_camelcase_keyword_has_nonempty_samples(self):
        """Regression guard for PR #485: the CamelCase-named keyword must
        carry its real, non-empty samples from the .voc file - not an empty
        list caused by a mismatched, `.title()`-mangled vocab_type."""
        data, context = _of_type(self.mc, SpecMessage.INTENT_REGISTER_KEYWORD)[0]

        assert data["skill_id"] == SKILL_ID
        assert data["intent_name"] == "greet"
        assert context["skill_id"] == SKILL_ID

        assert "required" in data
        req = {d["name"]: d["samples"] for d in data["required"]}

        # the exact CamelCase name must be present - not "Helloworldkeyword"
        assert "HelloWorldKeyword" in req, (
            f"expected CamelCase keyword name preserved on the wire, got: "
            f"{list(req.keys())}"
        )
        samples = req["HelloWorldKeyword"]
        assert samples, "keyword samples must not be empty"
        assert samples == EXPECTED_SAMPLES


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
