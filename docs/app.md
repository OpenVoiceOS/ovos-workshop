# OVOSAbstractApplication

`OVOSAbstractApplication` is a skill-like class designed to run **without** an intent service. Use it for standalone GUI apps, HiveMind-attached services, or any program that needs access to TTS, the MessageBus, and settings, but does not need to register intents with `ovos-core`.

**Source:** `ovos_workshop/app.py`

---

## When to Use OVOSAbstractApplication vs OVOSSkill

| Concern | `OVOSSkill` | `OVOSAbstractApplication` |
|---|---|---|
| Loaded by `ovos-core` | Yes | No |
| Registers intents | Yes | Optional |
| Needs running intent service | Yes | No |
| Creates its own bus connection | No | Yes (if no bus passed) |
| Settings path | `skills/<id>/settings.json` | `apps/<id>/settings.json` |
| Suitable for standalone execution | No | Yes |

---

## Class Signature

```python
class OVOSAbstractApplication(OVOSSkill):
    def __init__(
        self,
        skill_id: str,
        bus: Optional[MessageBusClient] = None,
        resources_dir: Optional[str] = None,
        gui: Optional[GUIInterface] = None,
        **kwargs,
    ): ...
```

`OVOSAbstractApplication.__init__` is defined in `ovos_workshop/app.py:13`.
### Parameters

| Parameter | Type | Description |
|---|---|---|
| `skill_id` | `str` | Unique identifier for this application (required). |
| `bus` | `MessageBusClient \| None` | Existing bus connection. If `None`, one is created via `get_mycroft_bus()`. |
| `resources_dir` | `str \| None` | Root directory for locale/dialog resources. Defaults to the application's own directory. |
| `gui` | `GUIInterface \| None` | GUI interface to bind. If `None`, one is created automatically. |

---

## `_dedicated_bus` Flag

`OVOSAbstractApplication._dedicated_bus` is defined in `ovos_workshop/app.py:25`.
Set to `True` when the application created its own bus connection (i.e., `bus=None` was passed to `__init__`). The flag is used in `default_shutdown()` to decide whether to close the bus on exit.

```python
self._dedicated_bus = False
if bus:
    self._dedicated_bus = False
else:
    self._dedicated_bus = True
    bus = get_mycroft_bus()
```

---

## `settings_path` Property

`OVOSAbstractApplication.settings_path` is defined in `ovos_workshop/app.py:36`.
Returns the path where this application's settings file is stored. Unlike `OVOSSkill`, which stores settings under `~/.config/ovos/skills/`, applications store settings under `apps/`:

```
~/.config/ovos/apps/<skill_id>/settings.json
```

This separation prevents skill managers from scanning and accidentally loading app settings.

---

## `default_shutdown()`

`OVOSAbstractApplication.default_shutdown` is defined in `ovos_workshop/app.py:43`.
Gracefully shuts down the application:

1. Calls `self.clear_intents()` to remove all bus handlers and detach from the intent service.
2. Calls `super().default_shutdown()` to run the base skill shutdown sequence.
3. If `self._dedicated_bus` is `True`, closes the bus connection with `self.bus.close()`.

```python
def default_shutdown(self):
    self.clear_intents()
    super().default_shutdown()
    if self._dedicated_bus:
        self.bus.close()
```

---

## `get_language_dir()`

`OVOSAbstractApplication.get_language_dir` is defined in `ovos_workshop/app.py:52`.
Returns the best-matched language resource directory for the requested language, with **dialect fallback**. For example, if `lang="pt-pt"` is requested but only `pt-br` resources exist, the `pt-br` path is returned.

```python
def get_language_dir(
    self,
    base_path: Optional[str] = None,
    lang: Optional[str] = None,
) -> Optional[str]:
```

| Parameter | Default | Description |
|---|---|---|
| `base_path` | `self.res_dir` | Root path to search for resources. |
| `lang` | `self.lang` | Language tag to look up. |

**Lookup order** (`ovos_workshop/app.py:69`):

1. `<base_path>/<lang>`: exact match with region in upper case (e.g. `en-US`)
2. `<base_path>/<lang.lower()>`: exact match lower-cased (e.g. `en-us`)
3. Dialect siblings via `locate_lang_directories()`: sorted by similarity, first match wins.

Returns `None` if no matching directory is found.

---

## `clear_intents()`

`OVOSAbstractApplication.clear_intents` is defined in `ovos_workshop/app.py:83`.
Removes all registered event handlers for this application's intents and detaches the application from the intent service. This prevents duplicate handlers if the application is re-initialized without a full process restart.

```python
def clear_intents(self):
    for intent_name, _ in self.intent_service:
        event_name = f'{self.skill_id}:{intent_name}'
        self.remove_event(event_name)
    self.intent_service.detach_all()
```

---

## Minimal Application Example

```python
from ovos_workshop.app import OVOSAbstractApplication


class MyClockApp(OVOSAbstractApplication):
    """A minimal standalone clock application."""

    def __init__(self, **kwargs):
        super().__init__(skill_id="my-clock-app.example", **kwargs)

    def initialize(self):
        """Called after the bus is connected and the app is ready."""
        self.log.info("Clock app started")
        self.speak("Clock application is ready.")

    def default_shutdown(self):
        self.log.info("Clock app shutting down")
        super().default_shutdown()


if __name__ == "__main__":
    app = MyClockApp()
    # The app creates its own bus connection automatically.
    # Call default_shutdown() to stop cleanly.
```

To pass an existing bus (e.g. in tests or when composing multiple apps):

```python
from ovos_bus_client import MessageBusClient
from ovos_workshop.app import OVOSAbstractApplication

bus = MessageBusClient()
bus.run_in_thread()

app = MyClockApp(bus=bus)
# _dedicated_bus is False: shutdown will NOT close the bus.
```

---
[← decorators](decorators.md) · [Home](index.md) · [game-skill →](game-skill.md)
