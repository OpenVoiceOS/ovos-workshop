# Skill Launcher

**Module:** `ovos_workshop.skill_launcher`

The skill launcher handles loading skill classes from plugins or files, connecting them to the bus, and managing their lifecycle.

## Skill Base Classes Registry

```python
from ovos_workshop.skill_launcher import SKILL_BASE_CLASSES

# [OVOSSkill, OVOSCommonPlaybackSkill, CommonQuerySkill, ActiveSkill,
#  FallbackSkill, UniversalSkill, UniversalFallback, OVOSGameSkill,
#  ConversationalGameSkill]
```

This list is used to detect which class in a loaded module is the skill class.

## PluginSkillLoader

Used by `SkillManager` to load plugin-based skills (installed via pip, discovered via entry points).

```python
from ovos_workshop.skill_launcher import PluginSkillLoader

loader = PluginSkillLoader(bus, skill_id)
loader.skill_class = MySkillClass    # or set via entry point discovery
loader.load(MySkillClass)            # instantiates and calls _startup
```

Key attributes:
- `loader.instance` — the live skill instance (or `None` if not loaded)
- `loader.loaded` — `True` if the skill is currently loaded
- `loader.active` — `True` if the skill is active (not deactivated)
- `loader.skill_id` — unique skill identifier
- `loader.runtime_requirements` — `RuntimeRequirements` from the skill class

Key methods:
- `loader.load(skill_class)` — load and start the skill
- `loader.reload()` — unload and reload the skill
- `loader.activate()` — re-enable a deactivated skill
- `loader.deactivate()` — deactivate (unload) a skill

## Loading from a File (legacy)

Skills that are directories with an `__init__.py` can be loaded with `load_skill_module`:

```python
from ovos_workshop.skill_launcher import load_skill_module

module = load_skill_module("/path/to/skill/__init__.py", "my-skill-id")
```

## Standalone Skill Launcher

Skills can be run as standalone processes without `ovos-core`:

```bash
ovos-skill-launcher my_skill_package_name
```

The `ovos-skill-launcher` console script connects to the bus and loads a single skill by entry point or module path. This is the recommended approach for running skills in Docker containers.

Programmatic equivalent:

```python
from ovos_bus_client import MessageBusClient
from ovos_workshop.skill_launcher import PluginSkillLoader
from ovos_utils import wait_for_exit_signal

bus = MessageBusClient()
bus.run_in_thread()
bus.connected_event.wait()

loader = PluginSkillLoader(bus, "my-skill-id")
loader.load(MySkillClass)

wait_for_exit_signal()
loader.deactivate()
```

## Hot Reload

If `skill.reload_skill` is `True` (the default), the skill can be reloaded when its source files change. Set `self.reload_skill = False` in `__init__` to disable this.

## File Watching for Settings

Each `PluginSkillLoader` watches the skill's `settings.json` for external changes. When a change is detected, `ovos.skills.settings_changed` is emitted with the `skill_id`.

## Testing Skills with ovoscope

`PluginSkillLoader` is how both `ovos-core` (production) and `ovoscope` (testing) load skills.
ovoscope wraps `SkillManager` in a lightweight `MiniCroft` that uses `FakeBus` instead of a real
WebSocket bus — skills are loaded identically, so tests exercise the exact same loader path.

```python
from ovoscope import End2EndTest, get_minicroft
from ovos_bus_client.message import Message
from ovos_bus_client.session import Session

SKILL_ID = "my-skill.author"

minicroft = get_minicroft([SKILL_ID])    # loads skill via PluginSkillLoader, waits for READY

session = Session("test-1")
message = Message(
    "recognizer_loop:utterance",
    {"utterances": ["trigger phrase"], "lang": "en-US"},
    {"session": session.serialize(), "source": "A", "destination": "B"},
)

test = End2EndTest(
    minicroft=minicroft,
    skill_ids=[SKILL_ID],
    source_message=message,
    expected_messages=[...],
)
test.execute(timeout=10)
minicroft.stop()
```

For a full tutorial including 8 test patterns and CI integration, see
[ovoscope/docs/usage-guide.md](../../ovoscope/docs/usage-guide.md).
