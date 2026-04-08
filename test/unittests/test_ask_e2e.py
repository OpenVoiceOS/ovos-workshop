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
"""Ovoscope end-to-end tests for ask_yesno and ask_selection."""
import threading
import unittest

from ovos_bus_client.message import Message
from ovos_bus_client.session import SessionManager, Session
from ovos_utils.log import LOG
from ovos_workshop.skills.ovos import OVOSSkill

from ovoscope import get_minicroft, CaptureSession

# ---------------------------------------------------------------------------
# Shared skill IDs
# ---------------------------------------------------------------------------
YESNO_SKILL_ID = "test.ask.yesno.skill"
SELECT_SKILL_ID = "test.ask.selection.skill"


# ---------------------------------------------------------------------------
# Inline test skills
# ---------------------------------------------------------------------------

class AskYesNoSkill(OVOSSkill):
    """Handles 'test.ask.yesno': calls ask_yesno and emits the result."""

    def initialize(self):
        self.add_event("test.ask.yesno", self.handle_yesno)

    def handle_yesno(self, message: Message):
        answer = self.ask_yesno("do you want tea")
        self.bus.emit(message.forward("test.yesno.result", {"answer": answer}))
        self.bus.emit(message.forward("ovos.utterance.handled"))


class AskSelectionSkill(OVOSSkill):
    """Handles 'test.ask.selection': calls ask_selection and emits the result."""

    def initialize(self):
        self.add_event("test.ask.selection", self.handle_selection)

    def handle_selection(self, message: Message):
        options = message.data.get("options", ["alpha", "beta", "gamma"])
        answer = self.ask_selection(options, numeric=True)
        self.bus.emit(message.forward("test.selection.result", {"answer": answer}))
        self.bus.emit(message.forward("ovos.utterance.handled"))


# ---------------------------------------------------------------------------
# Helper — inject a user response after the skill starts listening
# ---------------------------------------------------------------------------

def _inject_response_after_speak(mc, skill_id: str, utterance: str,
                                  session: Session, delay: float = 0.3):
    """Wait for the skill to speak (prompt), then inject user utterance.

    Emits directly to ``{skill_id}.converse.get_response`` which is the
    internal bus event that ``_wait_response`` reads from.
    """
    spoken = threading.Event()

    def on_speak(msg: str):
        spoken.set()

    mc.bus.on("speak", on_speak)

    def _inject():
        spoken.wait(timeout=10)
        mc.bus.remove("speak", on_speak)
        import time; time.sleep(delay)
        mc.bus.emit(Message(
            f"{skill_id}.converse.get_response",
            {"utterances": [utterance], "lang": "en-us"},
            {"session": session.serialize(), "skill_id": skill_id},
        ))

    t = threading.Thread(target=_inject, daemon=True)
    t.start()
    return t


def _make_trigger(msg_type: str, skill_id: str,
                  data: dict = None, session_id: str = "e2e-test") -> Message:
    sess = Session(session_id)
    sess.lang = "en-us"
    return Message(msg_type, data or {},
                   {"session": sess.serialize(),
                    "skill_id": skill_id,
                    "source": "test", "destination": skill_id})


# ---------------------------------------------------------------------------
# Tests: ask_yesno
# ---------------------------------------------------------------------------

class TestAskYesnoE2E(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        LOG.set_level("ERROR")
        cls.mc = get_minicroft([YESNO_SKILL_ID],
                               extra_skills={YESNO_SKILL_ID: AskYesNoSkill})

    @classmethod
    def tearDownClass(cls):
        cls.mc.stop()

    def _run(self, user_says: str, session_id: str = "e2e-yesno") -> list:
        """Trigger ask_yesno, inject a user reply, return captured messages."""
        trigger = _make_trigger("test.ask.yesno", YESNO_SKILL_ID,
                                session_id=session_id)
        sess = SessionManager.get(trigger)
        _inject_response_after_speak(self.mc, YESNO_SKILL_ID,
                                     user_says, sess)
        cap = CaptureSession(self.mc)
        cap.capture(trigger, timeout=15)
        return cap.finish()

    def test_yes_response(self):
        msgs = self._run("yes", session_id="e2e-yesno-yes")
        results = [m for m in msgs if m.msg_type == "test.yesno.result"]
        self.assertTrue(results, "test.yesno.result not emitted")
        self.assertEqual(results[0].data["answer"], "yes")

    def test_no_response(self):
        msgs = self._run("nope", session_id="e2e-yesno-no")
        results = [m for m in msgs if m.msg_type == "test.yesno.result"]
        self.assertTrue(results, "test.yesno.result not emitted")
        self.assertEqual(results[0].data["answer"], "no")

    def test_unmatched_response_returns_raw(self):
        msgs = self._run("maybe later", session_id="e2e-yesno-maybe")
        results = [m for m in msgs if m.msg_type == "test.yesno.result"]
        self.assertTrue(results, "test.yesno.result not emitted")
        self.assertEqual(results[0].data["answer"], "maybe later")


# ---------------------------------------------------------------------------
# Tests: ask_selection
# ---------------------------------------------------------------------------

class TestAskSelectionE2E(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        LOG.set_level("ERROR")
        cls.mc = get_minicroft([SELECT_SKILL_ID],
                               extra_skills={SELECT_SKILL_ID: AskSelectionSkill})

    @classmethod
    def tearDownClass(cls):
        cls.mc.stop()

    def _run(self, user_says: str, options: list = None,
             session_id: str = "e2e-select") -> list:
        trigger = _make_trigger("test.ask.selection", SELECT_SKILL_ID,
                                data={"options": options or ["alpha", "beta", "gamma"]},
                                session_id=session_id)
        sess = SessionManager.get(trigger)
        _inject_response_after_speak(self.mc, SELECT_SKILL_ID,
                                     user_says, sess)
        cap = CaptureSession(self.mc)
        cap.capture(trigger, timeout=15)
        return cap.finish()

    def test_fuzzy_match(self):
        msgs = self._run("beta", session_id="e2e-select-beta")
        results = [m for m in msgs if m.msg_type == "test.selection.result"]
        self.assertTrue(results, "test.selection.result not emitted")
        self.assertEqual(results[0].data["answer"], "beta")

    def test_first_option(self):
        msgs = self._run("alpha", session_id="e2e-select-alpha")
        results = [m for m in msgs if m.msg_type == "test.selection.result"]
        self.assertTrue(results, "test.selection.result not emitted")
        self.assertEqual(results[0].data["answer"], "alpha")


if __name__ == "__main__":
    unittest.main()
