# OVOSSkill

**Module:** `ovos_workshop.skills.ovos.OVOSSkill`

`OVOSSkill` is the base class that all OVOS skills inherit from. It handles startup, intent registration, resource loading, settings, event management, GUI, and shutdown.

## Constructor

```python
OVOSSkill(
    name: str = None,          # DEPRECATED, use skill_id
    bus: MessageBusClient = None,
    resources_dir: str = None,
    settings: dict = None,     # initial default settings
    gui: GUIInterface = None,
    skill_id: str = "",        # set by SkillLoader
)
```

Modern skills should always accept `**kwargs` and pass them to `super().__init__`:

```python
class MySkill(OVOSSkill):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
```

## Lifecycle Methods

Override these in your skill class:

| Method | When called | Notes |
|---|---|---|
| `initialize()` | After full startup | Legacy. Prefer `__init__`. |
| `get_intro_message()` | First run only | Return a dialog name or string to speak on first install |
| `stop()` | User/system stop | Return `True` if the skill handled the stop |
| `stop_session(session)` | Per-session stop | Called before `stop()`; return `True` to prevent global `stop()` |
| `can_stop(message)` | Before stop | Must be implemented if `stop()` or `stop_session()` is defined |
| `shutdown()` | Skill unload | Final cleanup after all other shutdown steps |

### Startup Sequence (`_startup`)

1. Set `skill_id`
2. Init settings (`_init_settings`)
3. Bind bus (`bind`)
4. Init GUI
5. Load resource files (`load_data_files`)
6. Register decorated intents (`_register_decorated`)
7. Register homescreen app if `@homescreen_app` used
8. Register resting screen if `@resting_screen_handler` used
9. Call `initialize()`
10. Check first run
11. Set status to `ready`

### Shutdown Sequence (`default_shutdown`)

1. `stop()`
2. Store settings
3. Shutdown GUI
4. Shutdown event scheduler, clear events
5. Call `shutdown()`
6. Emit `detach_skill`

## Key Properties

### Session-aware (read from current Session)

| Property | Type | Description |
|---|---|---|
| `lang` | `str` | BCP-47 language of the current request |
| `core_lang` | `str` | Default configured language |
| `secondary_langs` | `list` | Configured secondary languages |
| `native_langs` | `list` | `core_lang` + `secondary_langs` |
| `location` | `dict` | Location preferences |
| `location_pretty` | `str` | City name |
| `location_timezone` | `str` | Timezone code |
| `system_unit` | `str` | `"metric"` or `"imperial"` |
| `date_format` | `str` | `"DMY"`, `"MDY"`, or `"YMD"` |
| `time_format` | `str` | `"half"` or `"full"` |

### Infrastructure

| Property | Type | Description |
|---|---|---|
| `settings` | `JsonStorage` | Persistent skill settings |
| `bus` | `MessageBusClient` | MessageBus connection |
| `gui` | `SkillGUI` | GUI interface |
| `enclosure` | `EnclosureAPI` | Hardware interface |
| `file_system` | `FileSystemAccess` | Managed local file access |
| `resources` | `SkillResources` | Resource files for `self.lang` |
| `dialog_renderer` | `MustacheDialogRenderer` | Render dialog templates |
| `event_scheduler` | `EventSchedulerInterface` | Schedule future bus events |
| `intent_service` | `IntentServiceInterface` | Register/manage intents |
| `intent_layers` | `IntentLayers` | Manage intent layer sets |
| `audio_service` | `OCPInterface` | Control audio/OCP playback |
| `translator` | `OVOSLangTranslation` | Language translation (lazy init) |
| `lang_detector` | `OVOSLangDetection` | Language detection (lazy init) |
| `is_fully_initialized` | `bool` | True after `_startup` completes |
| `reload_skill` | `bool` | Set to `False` to prevent hot-reload |

## Speaking

```python
self.speak("Hello world")
self.speak_dialog("my.dialog.file")            # uses locale/lang/dialog/my.dialog.file
self.speak_dialog("my.dialog", data={"name": "Alice"})  # Mustache templating
```

## Getting User Input

```python
response = self.get_response("What is your name?")

# Yes/No question
answer = self.ask_yesno("Do you want to continue?")   # returns "yes" / "no" / None

# Selection from list
choice = self.ask_selection(["A", "B", "C"], "Pick one")
```

`get_response` suspends the converse channel for this skill until the user responds or a timeout is hit. Raise `AbortQuestion` to cancel gracefully.

`ask_yesno` and `ask_selection` are backed by pluggable engine plugins. The active plugin can be set per-skill via `settings.json` (`ask_yesno_plugin`, `ask_selection_plugin`) or system-wide in `mycroft.conf` under the `skills` block. Defaults are `ovos-solver-yes-no-plugin` and `ovos-option-matcher-fuzzy-plugin`, both installed as runtime dependencies. See [skill-interaction.md](skill-interaction.md) for full configuration reference.

## Intent Registration

```python
# Padatious (intent file)
self.register_intent_file("my.intent", self.handler)

# Adapt (vocab-based)
from ovos_workshop.intents import IntentBuilder
intent = IntentBuilder("MyIntent").require("Keyword").build()
self.register_intent(intent, self.handler)

# Vocabulary keywords
self.register_vocabulary("hello", "HelloKeyword")
self.register_entity_file("food.entity")
```

## Context Management

```python
self.set_context("MyContext", "value")
self.remove_context("MyContext")
```

## Public Skill API

Decorate a method with `@skill_api_method` to expose it over the bus. Other skills or tools can call it via `SkillApi`.

## RuntimeRequirements

Override the class property to declare connectivity needs:

```python
from ovos_utils.process_utils import RuntimeRequirements

@classproperty
def runtime_requirements(cls):
    return RuntimeRequirements(
        internet_before_load=False,
        network_before_load=False,
        requires_internet=False,
        requires_network=False,
    )
```

This is used by `SkillManager` to defer loading until the required connectivity is available.

## System Bus Events Handled (per skill)

| Event | Description |
|---|---|
| `mycroft.stop` | Trigger stop flow |
| `{skill_id}.stop` | Skill-specific stop |
| `{skill_id}.stop.ping` | Check if skill can stop |
| `{skill_id}.converse.get_response` | Feed user response to `get_response` |
| `mycroft.skill.enable_intent` | Enable a disabled intent |
| `mycroft.skill.disable_intent` | Disable an active intent |
| `mycroft.skill.set_cross_context` | Set cross-skill context |
| `mycroft.skill.remove_cross_context` | Remove cross-skill context |
| `mycroft.skills.settings.changed` | Remote settings update |
| `ovos.skills.settings_changed` | Local settings file changed |
| `question:query` | Common query pipeline request |
| `ovos.common_query.ping` | Common query service discovery |
| `question:action.{skill_id}` | Common query callback |
| `homescreen.metadata.get` | Homescreen requesting metadata |
| `{skill_id}.public_api` | Skill API introspection |
