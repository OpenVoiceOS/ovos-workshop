import time
from unittest import TestCase
from unittest.mock import patch, Mock

from threading import Event
from ovos_utils.fakebus import FakeBus
from ovos_bus_client.message import Message
from ovos_workshop.decorators import fallback_handler
from ovos_workshop.skills.fallback import   FallbackSkill


class V2FallbackSkill(FallbackSkill):
    def __init__(self):
        super().__init__(FakeBus(), "fallback_v2")

    @fallback_handler
    def handle_fallback(self, message):
        pass

    @fallback_handler(10)
    def high_prio_fallback(self, message):
        pass



class TestFallbackSkillV2(TestCase):
    fallback_skill = FallbackSkill(FakeBus(), "test_fallback_v2")
    fallback_skill.can_answer = lambda message: False

    def test_class_inheritance(self):
        from ovos_workshop.skills.ovos import OVOSSkill
        self.assertIsInstance(self.fallback_skill, OVOSSkill)
        self.assertIsInstance(self.fallback_skill, FallbackSkill)

    def test_00_init(self):
        from ovos_workshop.skills.ovos import OVOSSkill
        self.assertIsInstance(self.fallback_skill, FallbackSkill)
        self.assertIsInstance(self.fallback_skill, OVOSSkill)

    def test_priority(self):
        FallbackSkill.fallback_config = {}

        # No config or handlers
        self.assertEqual(self.fallback_skill.priority, 101)
        # Config override
        FallbackSkill.fallback_config = \
            {"fallback_priorities": {"test_fallback_v2": 10}}
        self.assertEqual(self.fallback_skill.priority, 10,
                         self.fallback_skill.fallback_config)

        fallback_skill = V2FallbackSkill()

        # Minimum handler
        self.assertEqual(fallback_skill.priority, 10)
        # Config override
        FallbackSkill.fallback_config['fallback_priorities'][
            fallback_skill.skill_id] = 80
        self.assertEqual(fallback_skill.priority, 80)

        FallbackSkill.fallback_config = {}

    def test_can_answer(self):
        self.assertFalse(self.fallback_skill.can_answer(Message("")))

    def test_register_system_event_handlers(self):
        self.assertTrue(any(["ovos.skills.fallback.ping" in tup
                             for tup in self.fallback_skill.events]))
        self.assertTrue(any([f"ovos.skills.fallback.{self.fallback_skill.skill_id}.request"
                             in tup for tup in self.fallback_skill.events]))

    def test_handle_fallback_ack(self):
        def mock_pong(message: Message):
            self.assertEqual(message.data["skill_id"],
                             self.fallback_skill.skill_id)
            self.assertEqual(message.context["skill_id"],
                             self.fallback_skill.skill_id)
            self.assertEqual(message.data["can_handle"], "test")
        
        orig_can_answer = self.fallback_skill.can_answer
        self.fallback_skill.can_answer = Mock(return_value="test")
        self.fallback_skill.bus.once("ovos.skills.fallback.pong", mock_pong)

        self.fallback_skill._handle_fallback_ack(Message("test"))
        self.fallback_skill.can_answer = orig_can_answer
        

    def test_handle_fallback_request(self):
        start_event = Event()
        handler_event = Event()

        def mock_start(message: Message):
            start_event.set()
        
        def mock_handler(message: Message):
            handler_event.set()
            return True
        
        def mock_resonse(message: Message):
            self.assertTrue(message.data["result"])
            self.assertEqual(message.data["fallback_handler"],
                             "mock_handler")
        
        self.fallback_skill.bus.once(
            f"ovos.skills.fallback.{self.fallback_skill.skill_id}.start",
            mock_start
        )
        self.fallback_skill.bus.once(
            f"ovos.skills.fallback.{self.fallback_skill.skill_id}.response",
            mock_resonse
        )
        self.fallback_skill._fallback_handlers = [(100, mock_handler)]

        self.fallback_skill._handle_fallback_request(Message("test"))
        time.sleep(0.2)  # above runs in a killable thread

        self.assertTrue(start_event.is_set())
        self.assertTrue(handler_event.is_set())

        self.fallback_skill._fallback_handlers = []

    def test_register_fallback(self):
        priority = 75

        def fallback_service_register(message: Message):
            self.assertEqual(message.data["skill_id"],
                             self.fallback_skill.skill_id)
            self.assertEqual(message.data["priority"], priority)
        
        # test with f"ovos.skills.fallback.{self.skill_id}"
        def mock_handler(_: Message):
            return True
            
        self.fallback_skill.bus.once(
            f"ovos.skills.fallback.register", fallback_service_register
        )
        self.fallback_skill.register_fallback(mock_handler, priority)
        self.assertEqual(len(self.fallback_skill._fallback_handlers), 1)
        self.assertEqual(self.fallback_skill._fallback_handlers[0][0],
                         priority)
        self.assertEqual(self.fallback_skill._fallback_handlers[0][1],
                         mock_handler)
        
        self.fallback_skill._fallback_handlers = []
    
    def test_remove_fallback(self):

        def mock_handler(_: Message):
            return True
        
        def fallback_service_deregister(message: Message):
            deregister_event.set()
            self.assertEqual(message.data["skill_id"],
                             self.fallback_skill.skill_id)
        
        deregister_event = Event()
        self.fallback_skill.bus.once(
            f"ovos.skills.fallback.deregister", fallback_service_deregister
        )
        self.fallback_skill._fallback_handlers = [(50, mock_handler)]
        self.assertEqual(len(self.fallback_skill._fallback_handlers), 1)
        self.fallback_skill.remove_fallback(mock_handler)
        self.assertEqual(len(self.fallback_skill._fallback_handlers), 0)
        self.assertTrue(deregister_event.is_set())
        deregister_event.clear()
        self.assertFalse(deregister_event.is_set())

        self.fallback_skill.bus.once(
            f"ovos.skills.fallback.deregister", fallback_service_deregister
        )
        self.fallback_skill._fallback_handlers = [(100, mock_handler), (50, mock_handler)]
        self.fallback_skill.remove_fallback()
        self.assertEqual(len(self.fallback_skill._fallback_handlers), 0)
        self.assertTrue(deregister_event.is_set())

        self.fallback_skill._fallback_handlers = []

    def test_default_shutdown(self):
        # TODO
        pass

    def test_register_decorated(self):
        # TODO
        pass
