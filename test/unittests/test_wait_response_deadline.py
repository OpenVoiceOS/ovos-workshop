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
"""Regression test for the unbounded busy-wait in OVOSSkill._wait_response.

Field evidence: OpenVoiceOS/ovos-skill-alerts#138 "Update 3" captured a live
py-spy stack showing `ask_yesno -> get_response -> _wait_response` blocked
forever in `while not ans: time.sleep(0.1)` because the killable background
thread (`_real_wait_response`) never populated `__validated_responses` for
the session (bus/TTS handshake stalled). This hung a CI job to the 30-minute
job kill instead of returning the documented "no response" (`None`) outcome.
"""
import time
import unittest
from unittest.mock import patch

import pytest
from ovos_bus_client.message import Message
from ovos_utils.fakebus import FakeBus

from ovos_workshop.skills.ovos import OVOSSkill


class TestWaitResponseDeadline(unittest.TestCase):

    def setUp(self):
        self.bus = FakeBus()
        self.skill = OVOSSkill(bus=self.bus,
                               skill_id="test.wait.response.deadline")
        # small timeout so the test runs fast; this is the same
        # skills.get_response_timeout config _wait_response derives its
        # deadline from
        self.skill.config_core = {"skills": {"get_response_timeout": 0.2}}

    @pytest.mark.timeout(30)
    def test_wait_response_returns_none_when_background_thread_never_answers(self):
        """If the killable thread never writes a result, _wait_response must
        give up and return None instead of blocking forever."""
        message = Message("test.trigger", {},
                          {"skill_id": self.skill.skill_id})

        # simulate the stalled killable thread: real code initializes
        # __validated_responses[session_id] = [] as soon as the thread
        # starts (ovos.py ~line 1975), then stalls inside its own
        # __get_response wait (bus/TTS handshake never completes), so the
        # dict entry stays `[]` -- present but never truthy and never None
        def _stalled_thread(is_cancel, validator, on_fail, num_retries,
                            msg):
            from ovos_bus_client.session import SessionManager
            s = SessionManager.get(msg)
            self.skill._OVOSSkill__validated_responses[s.session_id] = []
            # thread "hangs" here forever in real life; test just returns
            # without ever setting a truthy/None value

        with patch.object(self.skill, "_real_wait_response",
                          _stalled_thread):
            start = time.time()
            ans = self.skill._wait_response(
                is_cancel=lambda u: False,
                validator=lambda u: True,
                on_fail=lambda u: "",
                num_retries=0,
                message=message,
            )
            elapsed = time.time() - start

        self.assertIsNone(ans, "get_response's documented 'no response' "
                               "outcome is None, not an unbounded hang")
        # deadline is derived from the (patched) get_response_timeout=0.2s
        # config, so this must return in a handful of seconds, not hang
        self.assertLess(elapsed, 25,
                        "_wait_response blocked far longer than its "
                        "configured deadline allows")


if __name__ == "__main__":
    unittest.main()
