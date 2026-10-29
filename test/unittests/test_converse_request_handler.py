import json
import time
import unittest
from os.path import dirname
from unittest.mock import patch

from ovos_utils.fakebus import FakeBus, Message

from ovos_workshop.skill_launcher import SkillLoader


class TestConverseRequestHandler(unittest.TestCase):
    """A converse request over the bus must reach converse() and answer
    without an error payload.

    Regression guard: the import swap in ovos_workshop/skills/converse.py
    left _handle_converse_request calling a name that was no longer
    imported. The resulting NameError was swallowed by the handler's own
    except-clause and returned as {"result": false, "error": "NameError(...)"},
    so converse() silently never ran for every live converse round trip
    while the unit suite stayed green — nothing exercised the handler with
    a real lang payload.
    """

    def setUp(self):
        self.bus = FakeBus()
        self.skill = SkillLoader(self.bus, f"{dirname(__file__)}/ovos_tskill_abort")
        self.skill.skill_id = "abort.test"
        self.skill.load()

    def tearDown(self) -> None:
        self.skill.unload()

    def test_converse_request_reaches_converse_and_reports_no_error(self):
        responses = []
        self.bus.on("skill.converse.response",
                    lambda m: responses.append(json.loads(m) if isinstance(m, str) else m.serialize()))

        with patch.object(self.skill.instance.__class__, "converse",
                          return_value=True) as converse:
            self.bus.emit(Message(f"{self.skill.skill_id}.converse.request",
                                  {"utterances": ["hello there"],
                                   "lang": "en-US"},
                                  {"skill_id": self.skill.skill_id}))

            # the handler runs on a killable_event worker thread; wait for
            # the response to land instead of asserting mid-flight
            deadline = time.monotonic() + 5
            while not responses and time.monotonic() < deadline:
                time.sleep(0.05)

            self.assertTrue(converse.called,
                            "converse() was never invoked by the converse.request handler")

        self.assertTrue(responses, "no skill.converse.response was emitted")
        payload = json.loads(responses[-1]) if isinstance(responses[-1], str) else responses[-1]
        data = payload["data"] if "data" in payload else payload
        self.assertNotIn("error", data,
                         f"converse.request handler answered with an error: {data.get('error')}")
        self.assertTrue(data["result"],
                        "converse() returned True but the response carried result=False")
