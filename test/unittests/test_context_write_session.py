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
"""OVOS-CONTEXT-1 §5.3: a context write rides forward on the session bound
to the current dispatch Message. ``set_context``/``remove_context`` used to
resolve the session to mutate by first checking
``SessionManager.sessions`` for a live entry keyed on the named session id.
Per OVOS-SESSION-2 §2.2 that registry never holds a named id's canonical
state - a named session is whatever the CURRENT message's carrier says -
but nothing stopped some *other* stale entry from having been left there
(e.g. a leftover from an earlier turn). When that happened the write landed
on the orphan registry object instead of the session the current message
actually carries, silently discarding whatever that carrier held and
leaving the mutation invisible on the message the handler emits.
"""
import unittest
from unittest import mock

from ovos_bus_client import Message
from ovos_bus_client.session import Session, SessionManager
from ovos_utils.fakebus import FakeBus

from ovos_workshop.intents import IntentServiceInterface


class TestContextWriteThroughDispatchSession(unittest.TestCase):
    def setUp(self):
        self.bus = FakeBus()
        self.captured = []
        self.bus.on("add_context", lambda m: self.captured.append(m))
        self.skill_id = "orphan.test.skill"
        self.iface = IntentServiceInterface(self.bus)
        self.iface.set_id(self.skill_id)
        self.session_id = "orphan-probe-session"
        SessionManager.sessions.pop(self.session_id, None)

    def tearDown(self):
        SessionManager.sessions.pop(self.session_id, None)

    def _fresh_carrier_message(self, msg_type="test.intent"):
        fresh = Session(session_id=self.session_id)
        fresh.set_intent_context("fresh_key", "fresh-value", scope="shared")
        return Message(msg_type, {}, {"session": fresh.serialize()})

    def test_set_context_writes_through_current_message_not_a_stale_registry_entry(self):
        stale = Session(session_id=self.session_id)
        stale.set_intent_context("old_key", "stale-value", scope="shared")
        SessionManager.sessions[self.session_id] = stale

        msg = self._fresh_carrier_message()
        forwarded = []
        with mock.patch("ovos_workshop.intents.dig_for_message", return_value=msg):
            self.iface._adapt.set_context("probe", "value", "orphan.test",
                                           original_key="probe")
            forwarded.append(msg.forward("some.derived.event"))

        ctx = forwarded[0].context.get("session", {}).get("intent_context") or {}
        # the fresh carrier's own entry must survive the write
        self.assertIn("fresh_key", ctx,
                       f"write discarded the current message's own session "
                       f"content: {ctx}")
        # the stale orphan's unrelated entry must NOT leak onto this message
        self.assertNotIn("old_key", ctx,
                          f"write landed on a stale registry object instead "
                          f"of the current message's session: {ctx}")
        # the new private entry itself must be present
        stored_key = f"{self.skill_id}:probe"
        self.assertIn(stored_key, ctx)
        self.assertEqual(ctx[stored_key]["value"], "value")

    def test_remove_context_removal_rides_the_same_message(self):
        # Same stale-registry-entry trap as the set_context test above: a
        # DIFFERENT object under this session id sits in the registry
        # (unrelated content, no "probe" key at all), so a fix that mutates
        # the registry object instead of the current message's own session
        # would find nothing to remove and never emit the tombstone.
        stale = Session(session_id=self.session_id)
        stale.set_intent_context("old_key", "stale-value", scope="shared")
        SessionManager.sessions[self.session_id] = stale

        fresh = Session(session_id=self.session_id)
        fresh.set_intent_context("probe", "value", scope="private",
                                  owner_id=self.skill_id)
        msg = Message("test.intent", {}, {"session": fresh.serialize()})

        with mock.patch("ovos_workshop.intents.dig_for_message", return_value=msg):
            self.iface._adapt.remove_context("probe", original_key="probe")
            forwarded = msg.forward("some.derived.event")

        ctx = forwarded.context.get("session", {}).get("intent_context") or {}
        stored_key = f"{self.skill_id}:probe"
        # the stale orphan's unrelated entry must NOT leak onto this message
        self.assertNotIn("old_key", ctx,
                          f"removal landed on a stale registry object "
                          f"instead of the current message's session: {ctx}")
        # OVOS-SESSION-2 §5.1: a removal rides out as an explicit `null`
        # entry (the tombstone), not an absent key - the merge step is what
        # turns that into deletion downstream.
        self.assertIn(stored_key, ctx, f"removal tombstone missing: {ctx}")
        self.assertIsNone(ctx[stored_key],
                           f"removed entry must serialize as null, not a "
                           f"live entry: {ctx}")

    def test_set_context_shared_scope_uses_bare_key(self):
        msg = self._fresh_carrier_message()
        with mock.patch("ovos_workshop.intents.dig_for_message", return_value=msg):
            session = SessionManager.get(msg)
        # exercise the raw Session API the shared-scope wrapper would need to
        # match, so a scope regression in set_intent_context is also caught
        session.set_intent_context("shared_probe", "v", scope="shared")
        self.assertIn("shared_probe", session.intent_context)
        self.assertNotIn(f"{self.skill_id}:shared_probe", session.intent_context)

    def test_set_context_with_no_message_in_hand_does_not_raise(self):
        """No dispatch Message to bind to - the session write falls back to
        the default session (SessionManager.get(None) semantics) and the
        legacy topic still fires from a bare Message, exactly as a
        called-outside-a-handler `set_context()` always has."""
        with mock.patch("ovos_workshop.intents.dig_for_message", return_value=None):
            self.iface._adapt.set_context("probe", "value", "orphan.test",
                                           original_key="probe")
        self.assertEqual(len(self.captured), 1)

    def test_legacy_add_context_wire_shape_is_pinned(self):
        """Pre-spec cores still read this topic for the adapt-engine
        `session.context` field; its wire shape must not drift."""
        msg = self._fresh_carrier_message()
        with mock.patch("ovos_workshop.intents.dig_for_message", return_value=msg):
            self.iface._adapt.set_context("orphan_test_skillprobe", "value",
                                           "orphan.test", original_key="probe")
        self.assertEqual(len(self.captured), 1)
        data = self.captured[0].data
        self.assertEqual(data["context"], "orphan_test_skillprobe")
        self.assertEqual(data["word"], "value")
        self.assertEqual(data["origin"], "orphan.test")
        self.assertEqual(data["key"], "probe")


if __name__ == "__main__":
    unittest.main()
