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
"""Re-registration of intents/vocab after the matchers lose compiled state.

The intent matchers (pipeline plugins) hold skill registrations in memory,
built from ``register_vocab`` / ``register_intent`` / ``padatious:*``
broadcasts. Those broadcasts are load-time announcements (OVOS-INTENT-4 §10):
a matcher (re)constructed after the skill loaded has missed them and matches
nothing until the skill re-emits. Re-registration is implicit replacement
(OVOS-INTENT-4 §8.1), so replaying is always safe.

Skills must therefore re-drive their registrations when:
- the intent service announces its pipeline plugins were (re)loaded
  (``intent.service.pipelines.loaded``), e.g. after the intent service
  process restarted while the skill process kept running;
- the websocket to the messagebus is re-established after a drop
  (the bus client's ``open`` event), so a messagebus restart can never
  leave matchers without the skill's registrations.
"""
import os
import tempfile
import unittest

from ovos_bus_client.message import Message
from ovos_utils.fakebus import FakeBus

from ovos_workshop.intents import IntentBuilder, IntentServiceInterface
from ovos_workshop.skills.fallback import FallbackSkill
from ovos_workshop.skills.ovos import OVOSSkill


REGISTRATION_TOPICS = ("register_vocab", "register_intent",
                       "padatious:register_intent",
                       "padatious:register_entity")


class BusCapture:
    """Record registration traffic emitted on a FakeBus."""

    def __init__(self, bus, topics=REGISTRATION_TOPICS):
        self.messages = []
        bus.on("message", self._capture)
        self._topics = topics

    def _capture(self, serialized):
        message = Message.deserialize(serialized)
        if message.msg_type in self._topics:
            self.messages.append(message)

    def clear(self):
        self.messages.clear()

    def types(self):
        return [m.msg_type for m in self.messages]


def _make_intent_file(content="hello world"):
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".intent", delete=False)
    f.write(content)
    f.close()
    return f.name


class TestReregisterAll(unittest.TestCase):
    """IntentServiceInterface.reregister_all replays recorded registrations."""

    def setUp(self):
        self.bus = FakeBus()
        self.capture = BusCapture(self.bus)
        self.interface = IntentServiceInterface(self.bus)
        self.interface.set_id("test-skill.test")
        self.intent_file = _make_intent_file()
        self.entity_file = _make_intent_file("thing")

    def tearDown(self):
        for f in (self.intent_file, self.entity_file):
            if os.path.exists(f):
                os.remove(f)

    def _register_everything(self):
        self.interface.register_adapt_keyword(
            "test_skillHelloKeyword", "hello", ["hi", "hey"], lang="en-US")
        self.interface.register_adapt_regex(
            "(?P<TestThing>.*)", lang="en-US")
        adapt_intent = IntentBuilder("test-skill.test:hello.intent").require(
            "test_skillHelloKeyword").build()
        self.interface.register_adapt_intent(
            "hello.intent", adapt_intent)
        self.interface.register_padatious_intent(
            "test-skill.test:file.intent", self.intent_file, "en-US")
        self.interface.register_padatious_entity(
            "test-skill.test:thing.entity", self.entity_file, "en-US")

    def test_reregister_all_replays_everything(self):
        self._register_everything()
        original = sorted((m.msg_type, str(sorted(m.data.items())))
                          for m in self.capture.messages)
        self.capture.clear()

        self.interface.reregister_all()

        replayed = sorted((m.msg_type, str(sorted(m.data.items())))
                          for m in self.capture.messages
                          if m.msg_type != "detach_intent")
        self.assertEqual(original, replayed)

    def test_reregister_detaches_adapt_intent_before_replay(self):
        # legacy adapt consumers append parsers instead of replacing, so the
        # replay must be preceded by a detach of the same intent
        self._register_everything()
        capture = BusCapture(self.bus, topics=("detach_intent",
                                               "register_intent"))
        self.interface.reregister_all()
        types = [m.msg_type for m in capture.messages]
        self.assertIn("detach_intent", types)
        self.assertLess(types.index("detach_intent"),
                        types.index("register_intent"))
        detach = [m for m in capture.messages
                  if m.msg_type == "detach_intent"][0]
        register = [m for m in capture.messages
                    if m.msg_type == "register_intent"][0]
        self.assertEqual(detach.data["intent_name"], register.data["name"])

    def test_reregister_skips_detached_intents(self):
        self._register_everything()
        self.interface.remove_intent("hello.intent")
        self.capture.clear()

        self.interface.reregister_all()

        registered_names = [m.data.get("name") for m in self.capture.messages
                            if m.msg_type == "register_intent"]
        self.assertNotIn("test-skill.test:hello.intent", registered_names)
        # padatious intent is still in effect and must be replayed
        self.assertIn("padatious:register_intent", self.capture.types())

    def test_carries_skill_id_context(self):
        self._register_everything()
        self.capture.clear()
        self.interface.reregister_all()
        for message in self.capture.messages:
            self.assertEqual(message.context.get("skill_id"),
                             "test-skill.test")


class ReconnectTestSkill(OVOSSkill):
    def initialize(self):
        self.register_vocabulary("hello", "HelloKeyword", lang="en-US")
        self.register_intent(
            IntentBuilder("HelloIntent").require("HelloKeyword"),
            self.handle_hello)

    def handle_hello(self, message):
        pass


class TestSkillReregisterTriggers(unittest.TestCase):

    def setUp(self):
        self.bus = FakeBus()
        self.capture = BusCapture(self.bus)
        self.skill = ReconnectTestSkill(
            bus=self.bus, skill_id="reconnect-test.test")

    def tearDown(self):
        self.skill.default_shutdown()

    def test_registers_on_load(self):
        self.assertIn("register_vocab", self.capture.types())
        self.assertIn("register_intent", self.capture.types())

    def test_reregisters_on_bus_reconnect(self):
        self.capture.clear()
        # the bus client re-emits its "open" event on every reconnect
        self.bus.ee.emit("open")
        self.assertIn("register_vocab", self.capture.types())
        self.assertIn("register_intent", self.capture.types())

    def test_reregisters_when_pipelines_reload(self):
        self.capture.clear()
        self.bus.emit(Message("intent.service.pipelines.loaded"))
        self.assertIn("register_vocab", self.capture.types())
        self.assertIn("register_intent", self.capture.types())

    def test_replayed_registrations_match_originals(self):
        original = sorted((m.msg_type, str(sorted(m.data.items())))
                          for m in self.capture.messages)
        self.capture.clear()
        self.bus.ee.emit("open")
        replayed = sorted((m.msg_type, str(sorted(m.data.items())))
                          for m in self.capture.messages
                          if m.msg_type != "detach_intent")
        self.assertEqual(original, replayed)


class ReconnectFallbackSkill(FallbackSkill):
    def initialize(self):
        self.register_fallback(self.handle_fallback, 80)

    def handle_fallback(self, message):
        return False


class TestFallbackReregister(unittest.TestCase):

    def setUp(self):
        self.bus = FakeBus()
        self.messages = []
        self.bus.on("message", self._capture)
        self.skill = ReconnectFallbackSkill(
            bus=self.bus, skill_id="reconnect-fallback.test")

    def _capture(self, serialized):
        message = Message.deserialize(serialized)
        if message.msg_type == "ovos.skills.fallback.register":
            self.messages.append(message)

    def tearDown(self):
        self.skill.default_shutdown()

    def test_reregisters_fallback_on_reconnect(self):
        self.assertEqual(len(self.messages), 1)
        self.bus.ee.emit("open")
        self.assertEqual(len(self.messages), 2)
        self.assertEqual(self.messages[-1].data["skill_id"],
                         "reconnect-fallback.test")


if __name__ == "__main__":
    unittest.main()
