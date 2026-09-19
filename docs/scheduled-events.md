# Scheduled Events

A skill asks for a handler to be called later — once, or over and over — and the scheduler calls it, whether or not the skill is still loaded and whether or not the device stayed on.

**Module:** `ovos_workshop.skills.ovos`

## The six methods

```python
self.schedule_event(handler, when, data=None, name=None, context=None)
self.schedule_repeating_event(handler, when, frequency, data=None, name=None, context=None)
self.update_scheduled_event(name, data=None)
self.cancel_scheduled_event(name)
self.cancel_all_repeating_events()
self.get_scheduled_event_status(name)
```

`when` is a `datetime`, or a number of seconds from now. `frequency` is the period in seconds. `data` is delivered as the fired message's `data`, and `context` as its context. `handler` takes the fired `Message`.

```python
class AlarmSkill(OVOSSkill):

    @intent_handler("set.alarm.intent")
    def handle_set_alarm(self, message):
        self.schedule_event(self.ring, 300, {"label": "eggs"}, name="kitchen")
        self.speak("Alarm set for five minutes from now.")

    def ring(self, message):
        self.speak(f"Your {message.data['label']} timer is up.")
```

## Naive datetimes are read in the configured timezone

A `datetime` without a `tzinfo` is stamped with the timezone from the assistant's configuration — the user's home timezone, from `location.timezone.code` — and not the timezone the process happens to run in. That is the right reading for a voice assistant: "wake me at seven" means seven where the user lives, and a server, a container and a Raspberry Pi with a stale `/etc/localtime` must all agree about when that is.

The consequence to know is that a device running the stock configuration is in Lawrence, Kansas until someone sets its location. Schedule `datetime(2031, 3, 29, 7, 30)` on an unconfigured device and it fires at 07:30 America/Chicago, which is not 07:30 wherever the device is sitting. Set the device location, or pass an aware datetime and leave nothing to interpretation:

```python
from datetime import datetime
from zoneinfo import ZoneInfo

self.schedule_event(self.ring, datetime(2031, 3, 29, 7, 30, tzinfo=ZoneInfo("Europe/Lisbon")))
```

## A name is an identity

`name` is how a schedule is known: it is what `update_scheduled_event`, `cancel_scheduled_event` and `get_scheduled_event_status` take, and it is the schedule's identity. Scheduling a name that already has a pending one-shot replaces it rather than leaving two to fire, so a skill that re-creates its schedules every time it loads does not accumulate them.

Without a `name` one is derived from the handler's own name. Rename the handler and the old schedule is orphaned, so name anything you intend to cancel later.

`schedule_repeating_event` ignores a name that is already repeating. Cancel it first to replace it.

## Updating changes the payload, not the clock

`update_scheduled_event(name, data)` changes the data the handler will receive and leaves the timing exactly where it was. An hourly job keeps its hour; a countdown keeps counting down to the instant it was already counting down to instead of starting over.

## Asking whether something is still coming

`get_scheduled_event_status(name)` answers the seconds until the event fires, or `None` when nothing by that name is scheduled any more — because it fired, because it was cancelled, or because it never existed. So the natural guard reads the way it looks:

```python
if self.get_scheduled_event_status("kitchen"):
    self.speak("Your timer is still running.")
```

An event due this very second answers `0`, which is falsy for the same reason it is small; compare against `None` if that distinction matters to you. Only a scheduler that does not answer at all raises.

This is also the one scheduling call that waits for the scheduler.

## Scheduling does not block and does not raise

The other five hand their request to the skill's own sending thread and return. Requests go out in the order they were made, and a scheduler that refuses one or never answers is reported in the log rather than raised at the skill — a handler that sets a timer should not have to guard the call. Bad arguments are still rejected immediately: a negative delay raises `ValueError`, and a `when` that is neither a datetime nor a number raises `TypeError`.

An unloading skill flushes what it has queued and stops the thread before it goes, so a cancellation made just before shutdown still happens.

## Repeating schedules outlive the skill

A schedule belongs to the skill id, not to the process. A repeating schedule keeps running when the skill is unloaded and is still there when it comes back, which is what makes a daily briefing survive a restart or an update.

The skill's own record of its repeats does not survive that trip, so after a reload `cancel_all_repeating_events` only reaches the ones scheduled since. Cancel by name, or re-create the schedule and rely on replacement.

A skill that wants the older behaviour instead sets a class attribute, and its repeats are cancelled when it shuts down:

```python
class MySkill(OVOSSkill):
    repeating_schedules_outlive_the_skill = False
```

## What the handler receives

The handler is called with a `Message` carrying the `data` the schedule was created with, the `context` it was scheduled with, and a `scheduler` entry describing the occurrence:

```python
def ring(self, message):
    message.context["scheduler"]  # {"id", "owner", "due", "fired", "remaining"}
```

The context is the one the schedule was made with, kept by the scheduler and handed back unchanged — so a handler that speaks when the alarm rings speaks to the device the alarm was set on, without arranging anything. Pass `context=` to say otherwise; leave it out and the message being handled supplies it.

Whether that routing is still worth following is the handler's judgement. A session captured when the alarm was set may be long finished by the time it rings, and a handler that cares checks. Anything else the handler needs at fire time belongs in `data`.
