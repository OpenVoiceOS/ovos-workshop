# OVOS Workshop

Base classes, decorators, and helpers for building skills and applications for OpenVoiceOS.

## Install

```bash
pip install ovos-workshop
```

Runtime dependencies include `ovos-yes-no-plugin` and `ovos-option-matcher-fuzzy-plugin`, which back the `ask_yesno` and `ask_selection` skill methods.

## Quick Start

```python
from ovos_workshop.skills.ovos import OVOSSkill
from ovos_workshop.decorators import intent_handler


class HelloWorldSkill(OVOSSkill):

    @intent_handler("hello.intent")
    def handle_hello(self, message):
        self.speak_dialog("hello.response")


def create_skill():
    return HelloWorldSkill()
```

Register in `pyproject.toml`:

```toml
[project.entry-points."opm.skill"]
hello-world-skill = "hello_world_skill:HelloWorldSkill"
```

## Configuration

Key settings a skill can accept in its `settings.json`:

| Key | Default | Description |
|-----|---------|-------------|
| `ask_yesno_plugin` | `ovos-solver-yes-no-plugin` | YesNoEngine plugin used by `ask_yesno()` |
| `ask_selection_plugin` | `ovos-option-matcher-fuzzy-plugin` | OptionMatcherEngine plugin used by `ask_selection()` |

Both keys can also be set system-wide under the `skills` block in `mycroft.conf`.

## Documentation

The [OVOS Technical Manual](https://tigregotico.github.io/ovos-technical-manual/workshop-overview/) is the canonical skill-authoring guide. Repo-local reference with exact source citations is in [`docs/`](docs/index.md):

- [Skill classes](docs/skill-classes.md)
- [OVOSSkill base class](docs/ovos-skill.md)
- [ask_yesno / ask_selection plugin system](docs/skill-interaction.md)
- [Decorators](docs/decorators.md)
- [Settings](docs/settings.md)
- [Resource files](docs/resource-files.md)
- [Prerelease quirks](docs/prerelease-quirks.md) — what changed since the last stable release

## License

Apache 2.0
