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

    def can_answer(self, message):
        return True

    @fallback_handler
    def handle_fallback(self, message):
        pass

    @fallback_handler(10)
    def high_prio_fallback(self, message):
        pass



class _ConcreteFallback(FallbackSkill):
    """FallbackSkill is abstract, so tests need a class that satisfies the
    can_answer contract the same way a real skill does."""

    def can_answer(self, message):
        return False


class TestFallbackSkillV2(TestCase):
    fallback_skill = _ConcreteFallback(FakeBus(), "test_fallback_v2")

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

    def test_handle_fallback_request_emits_handled_once_per_sweep(self):
        """PIPELINE-1 §9.5 legacy shim (core < 2.3.0): the fallback sweep may
        span several registered fallback skills, each with its own
        `ovos.skills.fallback.<skill_id>.request` handler. A declined attempt
        is not the end of the sweep - only the skill that actually handles
        the utterance (or, absent one, the orchestrator) should emit the
        `ovos.utterance.handled` end-marker."""
        bus = FakeBus()
        events = []
        bus.on("ovos.utterance.handled", lambda m: events.append(m))

        declining = _ConcreteFallback(bus, "declining.fallback")
        handling = _ConcreteFallback(bus, "handling.fallback")

        declining._fallback_handlers = [(1, lambda message: False)]
        handling._fallback_handlers = [(2, lambda message: True)]

        with patch("ovos_workshop.skills.fallback._core_owns_utterance_handled",
                  return_value=False):
            # legacy fallback service tries skills in priority order
            declining._handle_fallback_request(Message("test"))
            time.sleep(0.2)
            self.assertEqual(len(events), 0,
                             "a declined attempt must not emit the end-marker")

            handling._handle_fallback_request(Message("test"))
            time.sleep(0.2)
            self.assertEqual(len(events), 1,
                             "the handling attempt must emit exactly once")

        declining._fallback_handlers = []
        handling._fallback_handlers = []

    def test_handle_fallback_request_all_decline_emits_none(self):
        """When every fallback skill in the sweep declines, the legacy shim
        must not emit `ovos.utterance.handled` itself - mirroring core >=
        2.3.0, where the per-attempt path never owns the no-match terminal
        (that is `IntentService.send_complete_intent_failure`'s job, once,
        at the end of the whole utterance-handling loop)."""
        bus = FakeBus()
        events = []
        bus.on("ovos.utterance.handled", lambda m: events.append(m))

        first = _ConcreteFallback(bus, "first.declining.fallback")
        second = _ConcreteFallback(bus, "second.declining.fallback")
        first._fallback_handlers = [(1, lambda message: False)]
        second._fallback_handlers = [(2, lambda message: False)]

        with patch("ovos_workshop.skills.fallback._core_owns_utterance_handled",
                  return_value=False):
            first._handle_fallback_request(Message("test"))
            second._handle_fallback_request(Message("test"))
            time.sleep(0.2)
            self.assertEqual(len(events), 0)

        first._fallback_handlers = []
        second._fallback_handlers = []

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


class TestFallbackIsAbstract(TestCase):
    """can_answer is declared abstract, but FallbackSkill used the default
    metaclass, so the declaration was inert: a skill without can_answer loaded
    fine and then raised NotImplementedError inside the ping handler, which is
    registered with speak_errors=False. The skill silently never answered."""

    def test_a_skill_without_can_answer_cannot_be_created(self):
        class Incomplete(FallbackSkill):
            @fallback_handler
            def handle_fallback(self, message):
                pass

        with self.assertRaises(TypeError):
            Incomplete(FakeBus(), "incomplete.test")

    def test_a_skill_with_can_answer_is_created(self):
        class Complete(FallbackSkill):
            def can_answer(self, message):
                return True

        skill = Complete(FakeBus(), "complete.test")
        self.assertTrue(skill.can_answer(Message("")))
