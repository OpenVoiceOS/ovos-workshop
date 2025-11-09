import json
import unittest
from unittest.mock import Mock

from ovos_bus_client import Message

from ovos_workshop.skills.ovos import OVOSSkill
from ovos_utils.fakebus import FakeBus
from os.path import dirname
from ovos_workshop.skill_launcher import SkillLoader


class SpecificArgsSkill(OVOSSkill):
    def __init__(self, skill_id="SpecificArgsSkill", bus=None, **kwargs):
        self.inited = True
        self.initialized = False
        self.startup_called = False
        super().__init__(skill_id=skill_id, bus=bus, **kwargs)
        self.kwargs = kwargs

    def initialize(self):
        self.initialized = True

    def _startup(self, bus, skill_id=""):
        self.startup_called = True
        self.initialize()


class KwargSkill(OVOSSkill):
    def __init__(self, **kwargs):
        self.inited = True
        self.initialized = False
        self.startup_called = False
        super().__init__(**kwargs)

    def initialize(self):
        self.initialized = True

    def _startup(self, bus, skill_id=""):
        self.startup_called = True
        self.initialize()


class TestSkill(unittest.TestCase):
    def setUp(self):
        self.bus = FakeBus()
        self.bus.emitted_msgs = []

        def get_msg(msg):
            msg = json.loads(msg)
            self.bus.emitted_msgs.append(msg)

        self.bus.on("message", get_msg)

        self.skill = SkillLoader(self.bus, f"{dirname(__file__)}/ovos_tskill_abort")
        self.skill.skill_id = "abort.test"
        self.bus.emitted_msgs = []

        self.skill.load()

    def test_skill_id(self):
        self.assertTrue(isinstance(self.skill.instance, OVOSSkill))

        self.assertEqual(self.skill.skill_id, "abort.test")

        # if running in ovos-core every message will have the skill_id in context
        for msg in self.bus.emitted_msgs:
            if msg["type"] == 'mycroft.skills.loaded': # emitted by SkillLoader, not by skill
                continue
            self.assertEqual(msg["context"]["skill_id"], "abort.test")

    def test_intent_register(self):
        padatious_intents = ["abort.test:test.intent",
                             "abort.test:test2.intent",
                             "abort.test:test3.intent"]
        for msg in self.bus.emitted_msgs:
            if msg["type"] == "padatious:register_intent":
                self.assertTrue(msg["data"]["name"] in padatious_intents)

    def test_registered_events(self):
        registered_events = [e[0] for e in self.skill.instance.events]

        # intent events
        intent_triggers = [f"{self.skill.skill_id}:test.intent",
                           f"{self.skill.skill_id}:test2.intent",
                           f"{self.skill.skill_id}:test3.intent"
                           ]
        for event in intent_triggers:
            self.assertTrue(event in registered_events)

        # base skill class events shared with mycroft-core
        default_skill = ["mycroft.skill.enable_intent",
                         "mycroft.skill.disable_intent",
                         "mycroft.skill.set_cross_context",
                         "mycroft.skill.remove_cross_context",
                         "mycroft.skills.settings.changed"]
        for event in default_skill:
            self.assertTrue(event in registered_events)

        # because its a ConversationalSkill class
        converse_ovos = [f"{self.skill.skill_id}.converse.ping",
                        f"{self.skill.skill_id}.converse.request",
                        "intent.service.skills.activated",
                        "intent.service.skills.deactivated",
                        f"{self.skill.skill_id}.activate",
                        f"{self.skill.skill_id}.deactivate"]
        for event in converse_ovos:
            self.assertTrue(event in registered_events)

    @unittest.skip("Mocks are causing issues, rewrite test")
    def test_stop(self):
        # TODO - someone figure this one out
        # 2025-01-09 19:17:20.473 - abort.test - ERROR - Type is not JSON serializable: Mock
        # Traceback (most recent call last):
        #   File "/home/miro/PycharmProjects/OVOS/ovos-utils/ovos_utils/events.py", line 78, in wrapper
        #     handler(message)
        #   File "/home/miro/PycharmProjects/OVOS/ovos-workshop/ovos_workshop/skills/ovos.py", line 1357, in _handle_session_stop
        #     self.bus.emit(message.reply(f"{self.skill_id}.stop.response", data))
        #   File "/home/miro/PycharmProjects/OVOS/ovos-utils/ovos_utils/fakebus.py", line 48, in emit
        #     self.ee.emit("message", message.serialize())
        #   File "/home/miro/PycharmProjects/OVOS/ovos-bus-client/ovos_bus_client/message.py", line 83, in serialize
        #     msg = orjson.dumps({'type': self.msg_type, 'data': data, 'context': ctxt}).decode("utf-8")
        # TypeError: Type is not JSON serializable: Mock

        skill = self.skill.instance
        handle_stop = Mock()
        real_stop = skill.stop
        skill.stop = Mock()
        self.bus.once(f"{self.skill.skill_id}.stop", handle_stop)
        self.bus.emit(Message("mycroft.stop"))
        handle_stop.assert_called_once()
        self.assertEqual(handle_stop.call_args[0][0].context['skill_id'],
                         skill.skill_id)
        skill.stop.assert_called_once()

        skill.stop = real_stop

    def tearDown(self) -> None:
        self.skill.unload()


class TestSkillNew(unittest.TestCase):

    def test_load(self):
        bus = FakeBus()
        kwarg = KwargSkill(skill_id="kwarg", bus=bus)
        self.assertTrue(kwarg.inited)
        self.assertTrue(kwarg.initialized)
        self.assertTrue(kwarg.startup_called)
        self.assertEqual(kwarg.skill_id, "kwarg")
        self.assertEqual(kwarg.bus, bus)

        gui = Mock()
        args = SpecificArgsSkill("args", bus, gui=gui)
        self.assertTrue(args.inited)
        self.assertTrue(args.initialized)
        self.assertTrue(args.startup_called)
        self.assertEqual(args.skill_id, "args")
        self.assertEqual(args.bus, bus)
        self.assertEqual(args.gui, gui)
