# ovos-workshop Documentation

`ovos-workshop` provides all base classes, decorators, and helpers needed to write skills and applications for OpenVoiceOS.

**Package:** `ovos-workshop`
**Source:** `ovos_workshop/`
**Entry point group:** `opm.skill`

For the full skill-authoring guide (class hierarchy, quick-start, bus basics, settings, resources, decorators, plugin discovery), see the
[OVOS Technical Manual: Workshop Overview](https://openvoiceos.github.io/beta-technical-manual/workshop-overview/).
This page and the files below cover repo-local detail (exact source line citations, files without a manual counterpart) that the manual omits by design.

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
[project.entry-points."opm.skill"]
hello-world-skill = "hello_world_skill:HelloWorldSkill"
```

---

## Navigation

| Document | Key Classes | Description |
|---|---|---|
| [skill-classes.md](skill-classes.md) | `OVOSSkill`, `FallbackSkill`, `OVOSCommonPlaybackSkill`, `ActiveSkill`, `OVOSGameSkill`, `ConversationalGameSkill`, `UniversalSkill`, `UniversalFallback`, `IdleDisplaySkill` | Class reference and when to use each |
| [ovos-skill.md](ovos-skill.md) | `OVOSSkill` | Base class: intent registration, settings, resources, GUI, lifecycle |
| [decorators.md](decorators.md) | `intent_handler`, `killable_intent`, `ocp_search`, `layer_intent`, `skill_api_method` | All intent and utility decorators with source citations |
| [app.md](app.md) | `OVOSAbstractApplication` | Skill-like app that runs without the intent service |
| [game-skill.md](game-skill.md) | `OVOSGameSkill`, `ConversationalGameSkill` | OCP-integrated game loop with converse and auto-save |
| [auto-translatable.md](auto-translatable.md) | `UniversalSkill`, `UniversalFallback` | Auto-translate input/output for any language |
| [skill-interaction.md](skill-interaction.md) | `OVOSSkill.ask_yesno`, `OVOSSkill.ask_selection` | Pluggable yes/no and option-selection engines |
| [skill-api.md](skill-api.md) | `SkillApi`, `skill_api_method` | Inter-skill RPC over the MessageBus |
| [filesystem.md](filesystem.md) | `FileSystemAccess` | Sandboxed, XDG-compliant file storage for skills |
| [resource-files.md](resource-files.md) | `SkillResources` | Locale, dialog, vocab, regex, and other resource files |
| [settings.md](settings.md) | `SkillSettingsManager` | Skill settings: persistence, change callbacks, file watching |
| [scheduled-events.md](scheduled-events.md) | `OVOSSkill.schedule_event`, `OVOSSkill.schedule_repeating_event` | Calling a handler later, once or repeatedly |
| [intent-layers.md](intent-layers.md) | `IntentLayers` | Enable/disable intent sets at runtime |
| [skill-launcher.md](skill-launcher.md) | `SkillLoader`, `PluginSkillLoader` | Loading skills as plugins or in standalone mode |
| [permissions.md](permissions.md) | `ConverseMode`, `FallbackMode` | Converse and fallback permission modes |

---

## Plugin Discovery

Skills are discovered via Python entry points in `pyproject.toml`:

```toml
[project.entry-points."opm.skill"]
my-skill-id = "my_skill.skill:MySkill"
```

`ovos-plugin-manager` scans the `opm.skill` group at runtime and loads matching classes. It still accepts the older `ovos.plugin.skill` group name as a deprecated alias.

See the manual's [Workshop Overview](https://openvoiceos.github.io/beta-technical-manual/workshop-overview/) for the MessageBus, settings, resources, intents, and decorators concepts shared by every skill.
