"""Runtime metric coverage for skill handlers and dialog rendering."""

from unittest.mock import MagicMock, PropertyMock, patch

from ovos_bus_client.message import Message
from ovos_utils.events import EventContainer
from ovos_utils.fakebus import FakeBus

from ovos_workshop._metrics import DIALOG_RENDER, SKILL_HANDLER
from ovos_workshop._performance_trace import (
    message_request_id,
    trace_performance_stage,
)
from ovos_workshop.skills import ovos as ovos_skill_module
from ovos_workshop.skills.ovos import OVOSSkill


def _skill() -> OVOSSkill:
    skill = OVOSSkill.__new__(OVOSSkill)
    skill.skill_id = "test.skill"
    skill.bus = FakeBus()
    skill.events = EventContainer(skill.bus)
    skill.log = MagicMock()
    skill._on_event_start = MagicMock()
    skill._on_event_end = MagicMock()
    skill._on_event_error = MagicMock()
    return skill


def test_handler_info_events_measure_handler_execution():
    skill = _skill()
    calls = MagicMock()

    def handler(message):
        calls(message)

    before = SKILL_HANDLER.snapshot()["count"]
    skill.add_event(
        "test.intent",
        handler,
        handler_info="mycroft.skill.handler",
        is_intent=True,
    )

    message = Message("test.intent")
    skill.bus.emit(message)

    calls.assert_called_once_with(message)
    assert SKILL_HANDLER.snapshot()["count"] == before + 1


def test_internal_events_do_not_pollute_skill_handler_metric():
    skill = _skill()
    before = SKILL_HANDLER.snapshot()["count"]

    def handler(_message):
        return None

    skill.add_event("internal.event", handler)

    skill.bus.emit(Message("internal.event"))

    assert SKILL_HANDLER.snapshot()["count"] == before


def test_speak_dialog_measures_only_renderer_work():
    skill = _skill()
    renderer = MagicMock()
    renderer.render.return_value = "It is sunny."
    skill.speak = MagicMock()
    before = DIALOG_RENDER.snapshot()["count"]

    with patch.object(
        OVOSSkill,
        "dialog_renderer",
        new_callable=PropertyMock,
        return_value=renderer,
    ):
        skill.speak_dialog("weather.answer", {"summary": "sunny"})

    renderer.render.assert_called_once_with(
        "weather.answer", {"summary": "sunny"}
    )
    skill.speak.assert_called_once()
    assert DIALOG_RENDER.snapshot()["count"] == before + 1


def test_trace_extracts_nested_query_id():
    message = Message(
        "speak",
        {},
        {"metadata": {"qa_query_id": "request-skill"}},
    )

    assert message_request_id(message) == "request-skill"


def test_speak_emits_correlated_stage_without_changing_message(
        monkeypatch):
    skill = _skill()
    trigger = Message(
        "test.intent",
        {},
        {"query_id": "request-skill"},
    )
    traces = []
    emitted = []
    skill.bus.on("speak", emitted.append)
    monkeypatch.setattr(
        ovos_skill_module,
        "dig_for_message",
        lambda: trigger,
    )
    monkeypatch.setattr(
        ovos_skill_module,
        "trace_performance_stage",
        lambda stage, **values: traces.append((
            stage,
            values["message"].context.get("query_id"),
            set(values["message"].data),
        )),
    )

    with patch.object(
        OVOSSkill,
        "lang",
        new_callable=PropertyMock,
        return_value="en-US",
    ):
        skill.speak("It is sunny.")

    assert len(emitted) == 1
    assert emitted[0].context["query_id"] == "request-skill"
    assert traces == [(
        "skill_reply_emit",
        "request-skill",
        {"utterance", "expect_response", "meta", "lang"},
    )]


def test_skill_trace_is_silent_without_opt_in(monkeypatch):
    monkeypatch.delenv("OVOS_PERFORMANCE_TRACE", raising=False)
    log_info = MagicMock()
    monkeypatch.setattr(
        "ovos_workshop._performance_trace._LOG.info",
        log_info,
    )

    trace_performance_stage("skill_reply_emit", request_id="request-silent")
    log_info.assert_not_called()
