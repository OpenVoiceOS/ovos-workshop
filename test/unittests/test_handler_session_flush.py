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
"""Reproducer for HANDOFF finding 29: handler-scoped session mutations must be
flushed into the session snapshot the handler-complete signal carries.

Two write paths are exercised:
  * the "raw" path - a handler calling ``SessionManager.get().set_intent_context``
    directly (already synchronous in-process; expected to already be green via
    ovos-bus-client's ``Message.forward``/``sync_message_session`` re-stamp).
  * the "wrapper" path - a handler calling ``self.set_context()`` (the
    developer-facing adapt-context helper), which historically only emitted an
    async ``add_context`` bus message for core to apply - never touching the
    skill process's own local session singleton, so the handler-complete
    message's re-stamped snapshot never contained the mutation.

Both tests use a real ``OVOSSkill`` + ``FakeBus`` + ``add_event`` dispatch (no
mocked peers) and inspect the actual ``mycroft.skill.handler.complete``
message emitted on the bus.
"""
import unittest

from ovos_bus_client import Message
from ovos_bus_client.session import Session, SessionManager
from ovos_utils.fakebus import FakeBus

from ovos_workshop.skills.ovos import OVOSSkill


class TestHandlerSessionFlush(unittest.TestCase):
    def setUp(self):
        self.bus = FakeBus()
        self.captured = []
        self.bus.on("mycroft.skill.handler.complete",
                    lambda m: self.captured.append(m))
        self.skill_id = "flush.test.skill"
        self.skill = OVOSSkill(bus=self.bus, skill_id=self.skill_id)
        # isolate from any singleton state a previous test left behind
        sess = Session(session_id="flush-test-session")
        SessionManager.sessions[sess.session_id] = sess
        SessionManager.default_session = SessionManager.default_session
        self.session_id = sess.session_id

    def _dispatch(self, handler):
        msg = Message("test.event",
                       {},
                       {"skill_id": self.skill_id,
                        "session": Session(session_id=self.session_id).serialize()})
        self.skill.add_event("test.event", handler, "mycroft.skill.handler",
                             is_intent=False)
        self.bus.emit(msg)

    def test_raw_session_write_is_flushed(self):
        """Handler mutates the session directly via SessionManager - already
        synchronous in-process, so the re-stamped handler-complete snapshot
        must already contain it."""
        def handler(message):
            sess = SessionManager.get(message)
            sess.set_intent_context("probe", "raw-value",
                                    scope="private", owner_id=self.skill_id)

        self._dispatch(handler)

        self.assertEqual(len(self.captured), 1)
        snapshot = self.captured[0].context.get("session") or {}
        stored_key = f"{self.skill_id}:probe"
        ctx = snapshot.get("intent_context") or {}
        self.assertIn(stored_key, ctx,
                      f"raw session mutation missing from handler-complete "
                      f"snapshot: {ctx}")
        self.assertEqual(ctx[stored_key]["value"], "raw-value")

    @unittest.expectedFailure
    def test_wrapper_set_context_is_flushed(self):
        """Handler mutates context via the skill.set_context() wrapper - the
        contract under test (finding 29): this mutation must ALSO land in the
        handler-complete snapshot, deterministically, not via a subsequent
        async bus round-trip.

        RED, left as an open contract gap (xfail), NOT fixed by this test
        file. An attempted workshop-local fix (mirroring the write onto
        ``SessionManager.get(msg).set_intent_context(...)`` before forwarding
        the handler-complete signal) was built and verified to close this gap
        in isolation, but it regressed
        ``test/unittests/skills/test_intent_layers_e2e.py`` -
        ``test_layers_advance_in_sequence_and_gate_intents`` went from 2/2
        green to consistently matching the PREVIOUS layer's intent one step
        late. That e2e test exercises the real ovos-core intent-matching path
        (ovos-adapt's context-gated matching), which apparently does not
        (only) consult ``Session.intent_context`` the way the OVOS-CONTEXT-1
        read/write contract on ``Session`` implies - or consults it in a way
        a second, workshop-local write into the same map desyncs from the
        write ovos-core itself performs when it processes the async
        ``add_context`` bus message. Duplicating the write locally is not
        safe without knowing exactly what ovos-core's ``add_context`` handler
        does with it; that lives outside this repo. See the HANDOFF finding
        29 PR discussion for the full investigation - this contract needs
        core-side cooperation (or an ovos-core-verified fix), not a
        workshop-only patch."""
        def handler(message):
            self.skill.set_context("probe", "wrapper-value", "flush.test")

        self._dispatch(handler)

        self.assertEqual(len(self.captured), 1)
        snapshot = self.captured[0].context.get("session") or {}
        stored_key = f"{self.skill_id}:probe"
        ctx = snapshot.get("intent_context") or {}
        self.assertIn(stored_key, ctx,
                      f"set_context() wrapper mutation missing from "
                      f"handler-complete snapshot (finding 29): {ctx}")
        self.assertEqual(ctx[stored_key]["value"], "wrapper-value")


if __name__ == "__main__":
    unittest.main()
