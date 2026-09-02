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
"""How the skill scheduling methods map onto the schedules they create.

The methods themselves are unchanged; what is checked here is the record each
one produces when the attached scheduler speaks SCHEDULER-1, and the fallback
to the pre-specification protocol when it does not.
"""
import os
import tempfile
import threading
import time
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock
from zoneinfo import ZoneInfo

from ovos_config.config import Configuration
from ovos_utils.fakebus import FakeBus

from ovos_bus_client.apis.events import EventSchedulerInterface
from ovos_bus_client.message import Message
from ovos_workshop.skills.ovos import OVOSSkill, SchedulerClient

try:
    from ovos_bus_client.util.scheduled_events import ScheduledEventService
except ImportError:
    ScheduledEventService = None

speaks_the_specification = unittest.skipIf(
    SchedulerClient is None or ScheduledEventService is None,
    "the installed ovos-bus-client has no SCHEDULER-1 scheduler")


def configured_zone() -> ZoneInfo:
    """The timezone a naive datetime is meant to be read in."""
    return ZoneInfo(Configuration()["location"]["timezone"]["code"])


class TestLegacyFallback(unittest.TestCase):
    """With a scheduler that is not a SCHEDULER-1 client, the old calls go out
    unchanged."""

    def setUp(self):
        self.skill = OVOSSkill(bus=FakeBus(), skill_id="test.fallback")
        self.scheduler = Mock(spec=["schedule_event", "schedule_repeating_event",
                                    "update_scheduled_event",
                                    "cancel_scheduled_event",
                                    "get_scheduled_event_status",
                                    "cancel_all_repeating_events"])
        self.skill.event_scheduler = self.scheduler
        self.addCleanup(self.skill._stop_sending_to_scheduler, 2)

    def settle(self):
        """Wait for the requests made so far to reach the scheduler.

        The scheduling calls hand their request to a sending thread and
        return; a test that wants to see the request has to wait for it.
        """
        self.skill._scheduler_requests_sent()

    def test_a_mock_scheduler_is_not_taken_for_a_specification_client(self):
        self.assertFalse(self.skill._use_spec_scheduler)

    def test_a_one_shot_event_is_handed_to_the_old_interface(self):
        handler = Mock()
        self.skill.schedule_event(handler, 60, {"k": 1}, "ring")
        self.settle()
        self.scheduler.schedule_event.assert_called_once_with(
            handler, 60, {"k": 1}, "ring", context={"skill_id": "test.fallback"})

    def test_a_repeating_event_is_handed_to_the_old_interface(self):
        handler = Mock()
        self.skill.schedule_repeating_event(handler, None, 300, {"k": 1}, "tick")
        self.settle()
        self.scheduler.schedule_repeating_event.assert_called_once_with(
            handler, None, 300, {"k": 1}, "tick",
            context={"skill_id": "test.fallback"})

    def test_the_other_four_calls_are_handed_over_unchanged(self):
        self.skill.update_scheduled_event("ring", {"k": 2})
        self.settle()
        self.scheduler.update_scheduled_event.assert_called_once_with("ring", {"k": 2})
        self.skill.cancel_scheduled_event("ring")
        self.settle()
        self.scheduler.cancel_scheduled_event.assert_called_once_with("ring")
        self.skill.get_scheduled_event_status("ring")
        self.settle()
        self.scheduler.get_scheduled_event_status.assert_called_once_with("ring")
        self.skill.cancel_all_repeating_events()
        self.settle()
        self.scheduler.cancel_all_repeating_events.assert_called_once_with()

    def test_an_event_the_old_scheduler_does_not_know_reads_as_nothing(self):
        # its reply for an unknown name carries no schedule, and its own
        # client reads off the end of that empty payload
        self.scheduler.get_scheduled_event_status.side_effect = KeyError(0)
        self.assertIsNone(self.skill.get_scheduled_event_status("gone"))

    def test_a_context_given_with_no_message_in_flight_is_kept(self):
        self.skill.schedule_event(Mock(), 60, name="ring", context={"mine": True})
        self.settle()
        context = self.scheduler.schedule_event.call_args.kwargs["context"]
        self.assertTrue(context["mine"])
        self.assertEqual(context["skill_id"], "test.fallback")

    def test_a_context_given_beats_the_message_being_handled(self):
        def handling(message):
            self.skill.schedule_event(Mock(), 60, name="ring",
                                      context={"mine": True})

        handling(Message("something", context={"theirs": True}))
        self.settle()
        context = self.scheduler.schedule_event.call_args.kwargs["context"]
        self.assertTrue(context["mine"])
        self.assertNotIn("theirs", context)

    def test_with_no_context_given_the_handled_message_supplies_it(self):
        def handling(message):
            self.skill.schedule_event(Mock(), 60, name="ring")

        handling(Message("something", context={"theirs": True}))
        self.settle()
        context = self.scheduler.schedule_event.call_args.kwargs["context"]
        self.assertTrue(context["theirs"])


@speaks_the_specification
class TestSpecificationDelegation(unittest.TestCase):
    skill_id = "test.scheduler"

    def setUp(self):
        self.bus = FakeBus()
        handle, self.store = tempfile.mkstemp(suffix=".json")
        os.close(handle)
        os.unlink(self.store)
        self.service = ScheduledEventService(self.bus, store_path=self.store,
                                             autostart=False)
        self.skill = OVOSSkill(bus=self.bus, skill_id=self.skill_id)

    def tearDown(self):
        self.skill._stop_sending_to_scheduler(2)
        self.service.shutdown()
        for path in (self.store, f"{self.store}.tmp"):
            if os.path.isfile(path):
                os.unlink(path)

    def settle(self):
        """Wait for the requests made so far to reach the scheduler."""
        self.skill._scheduler_requests_sent()

    def stored(self, name: str):
        """One schedule as the scheduler holds it, or None."""
        self.settle()
        return self.skill.event_scheduler.get(name)

    def schedules(self) -> list:
        """Every schedule this skill owns."""
        self.settle()
        return self.skill.event_scheduler.list()

    def record(self, name: str) -> dict:
        return self.stored(name)["record"]

    def in_an_hour(self) -> datetime:
        return datetime.now(timezone.utc) + timedelta(hours=1)

    def just_now(self) -> datetime:
        """An instant already due, so the next evaluation fires it."""
        return datetime.now(timezone.utc) - timedelta(seconds=1)

    def fire(self, name: str, data: dict = None):
        """Emit the event a schedule fires, as the scheduler emits it."""
        self.settle()
        self.bus.emit(Message(f"{self.skill_id}.{name}", data or {},
                              {"scheduler": {"id": name}}))

    # --- what each legacy argument becomes --------------------------------

    def test_a_delay_in_seconds_becomes_a_relative_timing(self):
        self.skill.schedule_event(Mock(), 60, {"k": 1}, "ring")
        record = self.record("ring")
        self.assertEqual(record["in"], {"seconds": 60})
        self.assertEqual(record["event"], "test.scheduler.ring")
        self.assertEqual(record["owner"], self.skill_id)
        self.assertEqual(record["data"], {"k": 1})

    def test_an_aware_datetime_becomes_the_instant_it_names(self):
        when = self.in_an_hour()
        self.skill.schedule_event(Mock(), when, name="ring")
        self.assertEqual(self.record("ring")["at"], when.isoformat())

    def test_a_naive_datetime_is_read_in_the_configured_zone(self):
        naive = datetime.now() + timedelta(hours=1)
        self.skill.schedule_event(Mock(), naive, name="ring")
        expected = naive.replace(tzinfo=configured_zone())
        self.assertEqual(self.record("ring")["at"], expected.isoformat())

    def test_a_negative_delay_is_refused_before_it_reaches_the_bus(self):
        with self.assertRaises(ValueError):
            self.skill.schedule_event(Mock(), -1, name="ring")
        self.assertIsNone(self.stored("ring"))

    def test_a_repeat_with_a_bad_time_is_refused_before_it_is_queued(self):
        with self.assertRaises(ValueError):
            self.skill.schedule_repeating_event(Mock(), -1, 300, name="tick")
        with self.assertRaises(TypeError):
            self.skill.schedule_repeating_event(Mock(), "soon", 300, name="tick")
        self.assertIsNone(self.stored("tick"))

    def test_a_time_of_the_wrong_type_is_refused(self):
        with self.assertRaises(TypeError):
            self.skill.schedule_event(Mock(), "tomorrow", name="ring")

    def test_a_caller_context_is_not_modified(self):
        given = {"mine": True}
        self.skill.schedule_event(Mock(), 60, name="ring", context=given)
        self.settle()
        self.assertEqual(given, {"mine": True})

    def test_the_handler_name_identifies_an_unnamed_schedule(self):
        def wake_up(message):
            pass

        self.skill.schedule_event(wake_up, 60)
        self.assertEqual(self.record("wake_up")["event"],
                         "test.scheduler.wake_up")

    def test_a_repeat_becomes_a_period_anchored_on_the_first_call(self):
        when = self.in_an_hour()
        self.skill.schedule_repeating_event(Mock(), when, 300, name="tick")
        self.assertEqual(self.record("tick")["every"],
                         {"seconds": 300, "start": when.isoformat()})

    def test_a_repeat_with_no_time_starts_one_period_from_now(self):
        self.skill.schedule_repeating_event(Mock(), None, 300, name="tick")
        start = datetime.fromisoformat(self.record("tick")["every"]["start"])
        expected = datetime.now(timezone.utc) + timedelta(seconds=300)
        self.assertLess(abs((start - expected).total_seconds()), 5)

    def test_a_repeat_scheduled_twice_keeps_the_first_one(self):
        self.skill.schedule_repeating_event(Mock(), None, 300, name="tick")
        first = self.record("tick")["every"]["start"]
        self.skill.schedule_repeating_event(Mock(), self.in_an_hour(), 300,
                                            name="tick")
        self.assertEqual(self.record("tick")["every"]["start"], first)

    # --- the behaviours the delegation fixes ------------------------------

    def test_scheduling_a_name_again_replaces_the_pending_event(self):
        self.skill.schedule_event(Mock(), 60, name="ring")
        self.skill.schedule_event(Mock(), 120, name="ring")
        self.assertEqual(len(self.schedules()), 1)
        self.assertEqual(self.record("ring")["in"], {"seconds": 120})

    def test_scheduling_a_name_again_leaves_one_handler_behind(self):
        calls = []
        self.skill.schedule_event(lambda m: calls.append("first"), 60, name="ring")
        self.skill.schedule_event(lambda m: calls.append("second"), 60, name="ring")
        self.fire("ring")
        self.assertEqual(calls, ["second"])

    def test_cancelling_works_without_a_handler_of_our_own(self):
        self.skill.schedule_event(Mock(), 60, name="ring")
        # as after a restart: the schedule outlives the process that made it
        self.settle()
        self.skill.event_scheduler.events.clear()
        self.skill.event_scheduler._handled_events.clear()
        self.skill.cancel_scheduled_event("ring")
        self.assertIsNone(self.stored("ring"))

    def test_a_handler_is_called_with_the_context_it_was_scheduled_with(self):
        # the real scheduler fires this one: the context comes back over the
        # wire, stored with the schedule, not from anything held in memory
        seen = []
        self.skill.schedule_event(lambda m: seen.append(m.context),
                                  self.just_now(), name="ring",
                                  context={"mine": True})
        self.settle()
        self.service._evaluate()
        self.assertTrue(seen[0]["mine"])
        self.assertEqual(seen[0]["skill_id"], self.skill_id)
        self.assertEqual(seen[0]["scheduler"]["id"], "ring")

    def test_the_context_is_stored_with_the_schedule(self):
        self.skill.schedule_event(Mock(), 60, name="ring",
                                  context={"mine": True})
        stored = self.record("ring")["context"]
        self.assertTrue(stored["mine"])
        self.assertEqual(stored["skill_id"], self.skill_id)

    # --- reading and changing a schedule ----------------------------------

    def test_updating_a_delayed_event_does_not_restart_its_delay(self):
        self.skill.schedule_event(Mock(), 3600, {"k": 1}, "ring")
        due = datetime.fromisoformat(self.stored("ring")["state"]["next"])
        time.sleep(1.1)
        self.skill.update_scheduled_event("ring", {"k": 2})
        moved = datetime.fromisoformat(self.stored("ring")["state"]["next"])
        self.assertLess(abs((moved - due).total_seconds()), 0.5)
        self.assertEqual(self.record("ring")["data"], {"k": 2})

    def test_the_status_of_an_event_is_the_seconds_left_until_it_fires(self):
        self.skill.schedule_event(Mock(), self.in_an_hour(), name="ring")
        left = self.skill.get_scheduled_event_status("ring")
        self.assertAlmostEqual(left, 3600, delta=5)

    def test_the_status_of_an_event_that_never_existed_is_nothing(self):
        # the scheduler answers, and its answer is that there is no schedule
        self.assertIsNone(
            self.skill.get_scheduled_event_status("never-scheduled"))

    def test_the_status_of_an_event_that_already_fired_is_nothing(self):
        self.skill.schedule_event(Mock(), self.just_now(), name="ring")
        self.settle()
        self.service._evaluate()
        self.assertIsNone(self.skill.get_scheduled_event_status("ring"))

    def test_a_pending_event_reads_as_still_coming(self):
        self.skill.schedule_event(Mock(), self.in_an_hour(), name="ring")
        self.assertTrue(self.skill.get_scheduled_event_status("ring"))
        self.skill.cancel_scheduled_event("ring")
        self.assertFalse(self.skill.get_scheduled_event_status("ring"))

    def test_updating_an_event_changes_its_data_and_keeps_its_time(self):
        when = self.in_an_hour()
        self.skill.schedule_event(Mock(), when, {"k": 1}, "ring")
        self.skill.update_scheduled_event("ring", {"k": 2})
        record = self.record("ring")
        self.assertEqual(record["data"], {"k": 2})
        self.assertEqual(record["at"], when.isoformat())

    def test_updating_an_event_keeps_the_handler_subscribed(self):
        calls = []
        self.skill.schedule_event(lambda m: calls.append(m.data), 3600,
                                  {"k": 1}, "ring")
        self.skill.update_scheduled_event("ring", {"k": 2})
        self.fire("ring", {"k": 2})
        self.assertEqual(calls, [{"k": 2}])

    def test_updating_an_unknown_event_does_nothing(self):
        self.skill.update_scheduled_event("never-scheduled", {"k": 1})
        self.assertEqual(self.schedules(), [])

    def test_a_repeating_period_survives_an_update(self):
        self.skill.schedule_repeating_event(Mock(), None, 300, {"k": 1}, "tick")
        start = self.record("tick")["every"]["start"]
        self.skill.update_scheduled_event("tick", {"k": 2})
        record = self.record("tick")
        self.assertEqual(record["every"], {"seconds": 300, "start": start})
        self.assertEqual(record["data"], {"k": 2})

    # --- cancelling in bulk -----------------------------------------------

    def test_cancelling_every_repeat_leaves_one_shot_events_alone(self):
        self.skill.schedule_repeating_event(Mock(), None, 300, name="tick")
        self.skill.schedule_event(Mock(), 60, name="ring")
        self.skill.cancel_all_repeating_events()
        self.assertIsNone(self.stored("tick"))
        self.assertIsNotNone(self.stored("ring"))

    def test_the_caller_is_not_blocked_and_a_refusal_does_not_reach_it(self):
        # the scheduler refuses this one; the skill hears about it in the log
        started = time.monotonic()
        self.skill.update_scheduled_event("never-scheduled", {"k": 1})
        self.assertLess(time.monotonic() - started, 0.5)
        self.settle()

    def test_a_repeat_outlives_the_skill_that_scheduled_it(self):
        # a schedule belongs to the skill id, not to the process: an unloaded
        # skill finds its own repeats again when it comes back
        self.skill.schedule_repeating_event(Mock(), None, 300, name="tick")
        self.skill.default_shutdown()
        self.assertIsNotNone(self.skill.event_scheduler.get("tick"))

    def test_the_flag_can_have_repeats_cancelled_on_shutdown_instead(self):
        self.skill.repeating_schedules_outlive_the_skill = False
        self.skill.schedule_repeating_event(Mock(), None, 300, name="tick")
        self.skill.default_shutdown()
        # read without settling: an unloaded skill's process may exit here,
        # and nothing in production waits for the queue on its behalf
        self.assertIsNone(self.skill.event_scheduler.get("tick"))

    def test_shutdown_stops_the_thread_that_sends_the_requests(self):
        self.skill.schedule_event(Mock(), 60, name="ring")
        sender = self.skill._scheduler_sender
        self.assertEqual(sender.name, f"{self.skill_id}-scheduler")
        self.skill.default_shutdown()
        self.assertNotIn(sender, threading.enumerate())

    def test_shutdown_gives_up_on_a_scheduler_that_never_answers(self):
        self.skill.schedule_event(Mock(), 60, name="ring")
        self.skill._send_to_scheduler("slow", lambda: time.sleep(2))
        started = time.monotonic()
        self.skill._stop_sending_to_scheduler(0.2)
        self.assertLess(time.monotonic() - started, 1.5)

    def test_a_cancelled_repeat_can_be_scheduled_again(self):
        self.skill.schedule_repeating_event(Mock(), None, 300, name="tick")
        self.skill.cancel_scheduled_event("tick")
        self.skill.schedule_repeating_event(Mock(), self.in_an_hour(), 300,
                                            name="tick")
        self.assertIsNotNone(self.stored("tick"))


@speaks_the_specification
class TestNoSchedulerOnTheBus(unittest.TestCase):
    """A client is installed but nothing is answering: the old topics."""

    def setUp(self):
        self.bus = FakeBus()
        self.seen = []
        self.bus.on("mycroft.scheduler.schedule_event", self.seen.append)
        self.skill = OVOSSkill(bus=self.bus, skill_id="test.lonely")
        self.addCleanup(self.skill._stop_sending_to_scheduler, 2)

    def test_scheduling_falls_back_to_the_old_topic(self):
        self.skill.schedule_event(Mock(), 60, name="ring")
        self.skill._scheduler_requests_sent()
        self.assertEqual(len(self.seen), 1)
        self.assertEqual(self.seen[0].data["event"], "test.lonely:ring")

    def test_the_caller_waits_for_nothing_and_is_not_raised_at(self):
        started = time.monotonic()
        for name in ("one", "two", "three"):
            self.skill.schedule_repeating_event(Mock(), None, 300, name=name)
        self.skill.cancel_all_repeating_events()
        self.assertLess(time.monotonic() - started, 0.5)
        self.skill._scheduler_requests_sent()

    def test_an_unnamed_schedule_keeps_the_pre_specification_name(self):
        def wake_up(message):
            pass

        self.skill.schedule_event(wake_up, 60)
        self.skill._scheduler_requests_sent()
        # a schedule an older release persisted is stored under this name;
        # any other name here leaves it running with nothing able to cancel it
        self.assertEqual(self.seen[0].data["event"],
                         "test.lonely:test.lonelywake_up")

    def test_an_unnamed_schedule_lands_where_the_old_interface_put_it(self):
        def wake_up(message):
            pass

        interface = EventSchedulerInterface(bus=self.bus, skill_id="test.lonely")
        with self.assertWarns(DeprecationWarning):
            interface.schedule_repeating_event(wake_up, None, 300)
        self.skill.schedule_repeating_event(wake_up, None, 300)
        self.skill._scheduler_requests_sent()
        self.assertEqual(self.seen[1].data["event"], self.seen[0].data["event"])


if __name__ == "__main__":
    unittest.main()
