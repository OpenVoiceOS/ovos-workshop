from unittest.mock import MagicMock

from ovos_bus_client.message import Message
from ovos_utils.fakebus import FakeBus

from ovos_workshop.skills.fallback import FallbackSkill


def _make_skill():
    skill = FallbackSkill.__new__(FallbackSkill)
    skill.skill_id = "test.skill"
    skill.bus = FakeBus()
    skill.bus.emit = MagicMock()
    skill.can_answer = MagicMock(return_value=True)
    return skill


def test_fallback_ack_echoes_request_id():
    skill = _make_skill()

    skill._handle_fallback_ack(Message(
        "ovos.skills.fallback.ping",
        {"fallback_request_id": "req-1"},
        {"fallback_request_id": "req-1"},
    ))

    emitted = skill.bus.emit.call_args[0][0]
    assert emitted.msg_type == "ovos.skills.fallback.pong"
    assert emitted.data["skill_id"] == "test.skill"
    assert emitted.data["can_handle"] is True
    assert emitted.data["fallback_request_id"] == "req-1"
    assert emitted.context["fallback_request_id"] == "req-1"


def test_fallback_ack_keeps_legacy_shape_without_request_id():
    skill = _make_skill()

    skill._handle_fallback_ack(Message("ovos.skills.fallback.ping"))

    emitted = skill.bus.emit.call_args[0][0]
    assert emitted.msg_type == "ovos.skills.fallback.pong"
    assert emitted.data == {"skill_id": "test.skill", "can_handle": True}
    assert emitted.context == {"skill_id": "test.skill"}
