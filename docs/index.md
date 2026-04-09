# ovos-workshop Documentation

`ovos-workshop` provides all base classes, decorators, and helpers needed to write skills and applications for OpenVoiceOS.

**Package:** `ovos-workshop`
**Source:** `ovos_workshop/`
**Entry point group:** `opm.skills`

---

## Quick-Start: Minimal Skill in 20 Lines

```python
from ovos_workshop.skills.ovos import OVOSSkill
from ovos_workshop.decorators import intent_handler


class HelloWorldSkill(OVOSSkill):
    """A minimal OVOS skill."""

    @intent_handler("hello.intent")
    def handle_hello(self, message):
        """Respond to a greeting."""
        self.speak_dialog("hello.response")


def create_skill():
    return HelloWorldSkill()
```

`pyproject.toml` entry point:

```toml
[project.entry-points."opm.skills"]
hello-world-skill = "hello_world_skill:HelloWorldSkill"
```

---

## Full Class Hierarchy

```
OVOSSkill                             ovos_workshop/skills/ovos.py
├── ConversationalSkill               ovos_workshop/skills/converse.py
│   └── ActiveSkill                   ovos_workshop/skills/active.py
├── FallbackSkill                     ovos_workshop/skills/fallback.py
├── CommonQuerySkill                  ovos_workshop/skills/common_query_skill.py
├── OVOSCommonPlaybackSkill           ovos_workshop/skills/common_play.py
│   └── OVOSGameSkill                 ovos_workshop/skills/game_skill.py
│       └── ConversationalGameSkill   ovos_workshop/skills/game_skill.py
├── UniversalSkill                    ovos_workshop/skills/auto_translatable.py
│   ├── UniversalFallback             ovos_workshop/skills/auto_translatable.py
│   └── UniversalCommonQuerySkill     ovos_workshop/skills/auto_translatable.py
│       (deprecated)
└── OVOSAbstractApplication           ovos_workshop/app.py
    (not loaded by ovos-core)
```

---

## Navigation

| Document | Key Classes | Description |
|---|---|---|
| [skill-classes.md](skill-classes.md) | `OVOSSkill`, `FallbackSkill`, `CommonQuerySkill`, `OVOSCommonPlaybackSkill`, `ActiveSkill`, `OVOSGameSkill`, `ConversationalGameSkill`, `UniversalSkill`, `UniversalFallback` | Full class reference and when to use each |
| [ovos-skill.md](ovos-skill.md) | `OVOSSkill` | Base class: intent registration, settings, resources, GUI, lifecycle |
| [decorators.md](decorators.md) | `intent_handler`, `killable_intent`, `ocp_search`, `layer_intent`, `skill_api_method` | All intent and utility decorators with source citations |
| [app.md](app.md) | `OVOSAbstractApplication` | Skill-like app that runs without the intent service |
| [game-skill.md](game-skill.md) | `OVOSGameSkill`, `ConversationalGameSkill` | OCP-integrated game loop with converse and auto-save |
| [auto-translatable.md](auto-translatable.md) | `UniversalSkill`, `UniversalFallback` | Auto-translate input/output for any language |
| [skill-interaction.md](skill-interaction.md) | `OVOSSkill.ask_yesno`, `OVOSSkill.ask_selection` | Pluggable yes/no and option-selection engines |
| [skill-api.md](skill-api.md) | `SkillApi`, `skill_api_method` | Inter-skill RPC over the MessageBus |
| [filesystem.md](filesystem.md) | `FileSystemAccess` | Sandboxed, XDG-compliant file storage for skills |
| [resource-files.md](resource-files.md) | `SkillResources` | Locale, dialog, vocab, regex, and other resource files |
| [settings.md](settings.md) | `SkillSettingsManager` | Skill settings — persistence, change callbacks, file watching |
| [intent-layers.md](intent-layers.md) | `IntentLayers` | Enable/disable intent sets at runtime |
| [skill-launcher.md](skill-launcher.md) | `SkillLoader`, `PluginSkillLoader` | Loading skills as plugins or in standalone mode |
| [permissions.md](permissions.md) | `ConverseMode`, `FallbackMode` | Converse and fallback permission modes |

---

## Key Concepts

### MessageBus

OVOS uses a WebSocket publish/subscribe bus. Every message has three fields:

```python
Message(
    msg_type="my.event.type",   # str — event name
    data={"key": "value"},      # dict — payload
    context={"session_id": ...} # dict — metadata
)
```

Skills interact with the bus through `self.bus`. Use `self.add_event()` to subscribe and `self.bus.emit()` to publish.

### Settings

Skills store persistent configuration in `~/.config/ovos/skills/<skill_id>/settings.json`. Access via `self.settings`:

```python
volume = self.settings.get("volume", 50)
self.settings["volume"] = 80
```

Settings changes are automatically persisted. `OVOSAbstractApplication` uses `apps/` instead of `skills/`.
See [settings.md](settings.md) for change callbacks and file watching.

### Resources

Resource files live in the skill's `locale/` directory, organized by language tag:

```
locale/
  en-us/
    dialog/   # .dialog files — spoken responses
    vocab/    # .voc files — keyword lists for Adapt
    intent/   # .intent files — Padatious training phrases
    regex/    # .rx files — named-entity patterns
```

Access via `self.speak_dialog("my.response")`, `self.get_response()`, etc.
See [resource-files.md](resource-files.md).

### Intents

Two intent engines are supported:

- **Adapt** — keyword-based, uses `IntentBuilder` and `.voc` files.
- **Padatious** — ML phrase-matching, uses `.intent` files.

Register intents with `@intent_handler` or `self.register_intent()`.
See [decorators.md](decorators.md) and [ovos-skill.md](ovos-skill.md).

### Decorators

Decorators are the primary way to register skill behaviour:

```python
from ovos_workshop.decorators import intent_handler, fallback_handler, skill_api_method
from ovos_workshop.decorators.killable import killable_intent
from ovos_workshop.decorators.layers import enables_layer, layer_intent
from ovos_workshop.decorators.ocp import ocp_search, ocp_featured_media
```

See [decorators.md](decorators.md) for a complete reference with source citations.

### Plugin Discovery

Skills are discovered via Python entry points in `pyproject.toml`:

```toml
[project.entry-points."opm.skills"]
my-skill-id = "my_skill.skill:MySkill"
```

`ovos-plugin-manager` scans the `opm.skills` group at runtime and loads matching classes.
