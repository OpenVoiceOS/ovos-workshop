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
    developer-facing adapt-context helper). Per CONTEXT-1 §5.0 (architecture#161)
    the session is the only context write path: the wrapper now delegates to
    ``Session.set_intent_context`` on the SAME session object the handler holds,
    so this mutation rides forward on the handler-complete message exactly like
    the raw path does - the legacy async ``add_context`` bus message is still
    emitted alongside it as a compat dual-write, but no longer the only carrier.
    This test was xfail (architecture#161 workshop#532); it is now a passing
    regression guard for the finding-29 fix.
"""
import time
import unittest
from unittest import mock

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

    def test_wrapper_set_context_is_flushed(self):
        """Handler mutates context via the skill.set_context() wrapper - the
        contract under test (finding 29 / CONTEXT-1 §5.0): this mutation
        must ALSO land in the handler-complete snapshot, deterministically,
        not via a subsequent async bus round-trip.

        Formerly xfail (workshop#532). Fixed by delegating set_context() to
        Session.set_intent_context on the live session (architecture#161,
        workshop fix/set-context-via-session): the wrapper no longer relies
        solely on the async add_context bus message to reach the session.
        """
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

    def test_wrapper_set_context_stamps_expires_at(self):
        """Regression for the reviewer-confirmed defect: the skill-side
        registry write via ``set_context()`` must carry the SAME decay
        stamp ovos-core's ``handle_add_context`` computes
        (``Configuration()['context']['timeout']`` minutes, default 2),
        not an immortal (missing ``expires_at``) entry - an omitted stamp
        here folds back into ovos-core's registry and strips core's own
        decay for that key. One decay policy, same as core.
        """
        def handler(message):
            self.skill.set_context("probe", "wrapper-value", "flush.test")

        before = time.time()
        with mock.patch("ovos_workshop.intents.Configuration") as mock_cfg:
            mock_cfg.return_value.get.return_value = {"timeout": 2}
            self._dispatch(handler)
        after = time.time()

        stored_key = f"{self.skill_id}:probe"
        ctx = self.captured[0].context.get("session", {}).get(
            "intent_context") or {}
        self.assertIn(stored_key, ctx)
        entry = ctx[stored_key]
        self.assertIn("expires_at", entry,
                      f"positive-timeout write must carry expires_at: {entry}")
        self.assertIsInstance(entry["expires_at"], float)
        self.assertGreater(entry["expires_at"], before)
        self.assertLessEqual(entry["expires_at"], after + 2 * 60 + 1)

    def test_wrapper_set_context_immortal_when_timeout_disabled(self):
        """Timeout <= 0 is the deliberate immortal-entry opt-out (mirrors
        ovos-core's convention) - `expires_at` must be absent/None only in
        that explicit case, never by default."""
        self.captured.clear()

        def handler(message):
            self.skill.set_context("probe", "wrapper-value", "flush.test")

        with mock.patch("ovos_workshop.intents.Configuration") as mock_cfg:
            mock_cfg.return_value.get.return_value = {"timeout": 0}
            self._dispatch(handler)

        stored_key = f"{self.skill_id}:probe"
        ctx = self.captured[0].context.get("session", {}).get(
            "intent_context") or {}
        self.assertIn(stored_key, ctx)
        entry = ctx[stored_key]
        self.assertIsNone(entry.get("expires_at"))


if __name__ == "__main__":
    unittest.main()
