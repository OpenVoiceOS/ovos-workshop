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
"""Real-stack end-to-end proof of OVOS-CONTEXT-1 §5.0 for the SHARED
(cross-skill) scope.

    §5.0: "A component writes intent context by mutating the `session` it
    carries or replies with... There is no context-mutation topic: no
    participant emits a Message whose purpose is to announce a context
    change to the orchestrator or to another component."

Boots a real (mini) OVOS stack via ovoscope's ``MiniCroft`` with TWO real
skills: ``context1_setter_test_skill`` calls the real
``OVOSSkill.set_cross_skill_context`` API while handling one template
intent; ``context1_reader_test_skill`` registers a DIFFERENT template
intent gated by a §6 ``requires_context`` declaration on the same bare,
owner-less shared key. Two utterances are driven through the real
padacioso pipeline in the same session: the setter's intent, then the
reader's. The reader's intent must match only because the setter's
handler put the entry on the SESSION - the test disables the legacy
``mycroft.skill.set_cross_context`` compat broadcast for its whole
duration (drops it before it reaches the bus), so a bug that made the
broadcast the only real mutation path could never pass this test even if
some other component happened to still listen for it.

Adapt is deliberately excluded from this run's pipeline: an unrelated,
pre-existing ovos-core bug (``IntentManifest.get_slot_names`` treats the
INTENT-4 §5.2 ``required``/``optional`` descriptor dicts as bare slot
names) crashes the §7 context-supplied-slot step for ANY adapt intent
that combines keyword requirements with a `requires_context` declaration,
independently of this PR's change. Padacioso intents don't populate those
manifest fields and are unaffected - and the padatious engine is never
used in this repo's tests.
"""
import sys
from os.path import dirname

import pytest

from ovoscope import (get_minicroft, wait_for_match, make_utterance_message,
                      PADACIOSO_PIPELINE)

from ovos_bus_client.session import Session, SessionManager
from ovos_spec_tools import SpecMessage

sys.path.insert(0, dirname(__file__))

SETTER_ID = "context1.setter.e2e.test"
READER_ID = "context1.reader.e2e.test"

DROPPED_LEGACY_TOPICS = {"mycroft.skill.set_cross_context",
                         "mycroft.skill.remove_cross_context"}


def _boot():
    """Boot a real MiniCroft with both CONTEXT-1 fixture skills, padacioso-only."""
    from context1_setter_test_skill import Context1SetterTestSkill
    from context1_reader_test_skill import Context1ReaderTestSkill
    return get_minicroft([SETTER_ID, READER_ID],
                         extra_skills={SETTER_ID: Context1SetterTestSkill,
                                       READER_ID: Context1ReaderTestSkill},
                         default_pipeline=PADACIOSO_PIPELINE,
                         wait_for_trained=False)


class TestContext1CrossSkillE2E:
    """Skill A's `set_cross_skill_context` must open skill B's
    `requires_context` gate purely through the session write - the legacy
    broadcast is dropped before it ever reaches the bus for this whole
    test class."""

    mc = None

    @classmethod
    def setup_class(cls):
        from ovos_utils.log import LOG
        LOG.set_level("ERROR")
        # booting a real MiniCroft runs a real IntentService, whose startup
        # calls SessionManager.connect_to_bus(mc.bus) - this mutates the
        # process-wide SessionManager.bus class attribute. Save/restore it
        # so later tests don't inherit a bus pointing at this (now-stopped)
        # MiniCroft instance.
        cls._saved_bus = SessionManager.bus
        cls.mc = _boot()

        # Drop the legacy compat broadcast before it reaches the bus, for
        # the whole class: if the gate below only opened because some
        # listener still reacted to `mycroft.skill.set_cross_context`, this
        # makes that impossible - the session write is the only thing left
        # that could satisfy the reader's gate.
        real_emit = cls.mc.bus.emit

        def _emit_dropping_legacy_cross_context(message):
            if message.msg_type in DROPPED_LEGACY_TOPICS:
                return
            return real_emit(message)

        cls._real_emit = real_emit
        cls.mc.bus.emit = _emit_dropping_legacy_cross_context

    @classmethod
    def teardown_class(cls):
        cls.mc.bus.emit = cls._real_emit
        cls.mc.stop()
        SessionManager.bus = cls._saved_bus

    def test_shared_context_gate_opens_across_skills_in_same_session(self):
        setter = self.mc.plugin_skills[SETTER_ID].instance
        reader = self.mc.plugin_skills[READER_ID].instance
        setter.handled.clear()
        reader.handled.clear()
        reader.last_message = None

        session = Session("context1-cross-skill-e2e")

        # Turn 1: the setter's intent, publishing the shared "person" entry.
        # Wait for the TERMINAL event, not the match event - the match fires
        # before the handler (and its set_cross_skill_context call) runs;
        # only a forward-derived message emitted AFTER the handler completes
        # is guaranteed to carry the mutated session (OVOS-SESSION-2 §2.6).
        set_msg = make_utterance_message("remember bob", session=session)
        handled = wait_for_match(
            self.mc.bus, [str(SpecMessage.UTTERANCE_HANDLED)],
            timeout=10, emit=set_msg)
        assert handled is not None, "setter intent never matched/completed"
        assert setter.handled.wait(5), "setter handler never ran"

        # OVOS-SESSION-2 §2.2: a NAMED session carries no state of its own
        # in the registry - the working session travels on the Messages of
        # the utterance flow that holds it. Read it back from the terminal
        # event's own session (SESSION-2's "the client declares the session
        # on every message" discipline), never from a private local
        # reference to the `session` object built above.
        live = Session.deserialize(handled.context["session"])
        assert "person" in (live.intent_context or {}), (
            "shared 'person' entry never landed in session.intent_context - "
            "set_cross_skill_context did not write through the session")
        entry = live.intent_context["person"]
        assert entry["value"] == "Bob"

        # Turn 2: the reader's intent, same session - only satisfiable while
        # the shared "person" entry set above is live.
        ask_msg = make_utterance_message("tall he", session=live)
        matched = wait_for_match(
            self.mc.bus, [f"{READER_ID}:height"],
            timeout=10, emit=ask_msg)
        assert matched is not None, (
            "OVOS-CONTEXT-1 §5.0: the reader skill's requires_context-gated "
            "intent did not match after the setter skill's real "
            "set_cross_skill_context() call, with the legacy "
            "mycroft.skill.set_cross_context broadcast dropped before it "
            "reached the bus - the session write is not reaching the real "
            "pipeline's gate")
        assert reader.handled.wait(5), "reader handler never ran"
        assert reader.last_message is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
