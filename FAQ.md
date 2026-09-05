# FAQ — `ovos-workshop`

## What is `ovos-workshop`?

`ovos-workshop` provides all base classes, decorators, and helpers needed to write skills and applications for OpenVoiceOS. It includes `OVOSSkill`, `FallbackSkill`, `CommonQuerySkill`, `OVOSCommonPlaybackSkill`, `OVOSGameSkill`, `UniversalSkill`, `OVOSAbstractApplication`, `FileSystemAccess`, `SkillApi`, and all intent decorators.

---

## How do I install it?

```bash
pip install ovos-workshop
```

For development (editable install):

```bash
uv pip install -e .
```

---

## Where do I report bugs?

Open an issue on the GitHub repository. Ensure you are targeting the `dev` branch for fixes.

---

## How do I run tests?

```bash
uv run pytest test/ --cov=ovos_workshop
```

---

## How do I contribute?

1. Fork the repository and create a feature branch from `dev`.
2. Write tests for your changes.
3. Open a PR targeting the `dev` branch.
4. Ensure CI passes before requesting review.

---

## What Python versions are supported?

See `QUICK_FACTS.md` — currently `>=3.9`.

---

## How do I make a game skill?

Extend `ConversationalGameSkill` (for games with a converse loop) or `OVOSGameSkill` (for simpler games). You must implement the abstract methods `on_play_game`, `on_stop_game`, and `on_game_command` (ConversationalGameSkill only). Your skill must supply a `.voc` file named by `skill_voc_filename` containing the game's name keywords.

```python
from ovos_workshop.skills.game_skill import ConversationalGameSkill

class MyGameSkill(ConversationalGameSkill):
    def __init__(self, *args, **kwargs):
        super().__init__(skill_voc_filename="my_game", *args, **kwargs)

    def on_play_game(self):
        self.speak("Game started!")

    def on_stop_game(self):
        self.speak("Game over.")

    def on_game_command(self, utterance: str, lang: str):
        self.speak(f"You said: {utterance}")
```

See [docs/game-skill.md](docs/game-skill.md) for the full reference.

---

## How do I use auto-translation?

Extend `UniversalSkill` and set `internal_language` in your constructor. All intent handlers will receive utterances in your internal language, and `self.speak()` will auto-translate back to the user's language. Requires a translator plugin to be configured in `ovos.conf`.

```python
from ovos_workshop.skills.auto_translatable import UniversalSkill
from ovos_workshop.decorators import intent_handler

class MySkill(UniversalSkill):
    def __init__(self, *args, **kwargs):
        super().__init__(internal_language="en-US", *args, **kwargs)

    @intent_handler("ask_something.intent")
    def handle_ask(self, message):
        # utterance is always in en-US here
        self.speak("I understood you!")  # auto-translated to user's lang
```

See [docs/auto-translatable.md](docs/auto-translatable.md) for the full reference.

---

## How does inter-skill communication work?

OVOS skills communicate via the MessageBus. For direct method calls between skills, use `SkillApi`. Decorate the method you want to expose with `@skill_api_method`, then call it from another skill using `SkillApi.get(skill_id).method_name(...)`.

See the next two questions for examples.

---

## How do I expose a method via SkillApi?

Decorate the method with `@skill_api_method`:

```python
from ovos_workshop.skills.ovos import OVOSSkill
from ovos_workshop.decorators import skill_api_method

class WeatherSkill(OVOSSkill):
    @skill_api_method
    def get_temperature(self, city: str) -> float:
        """Return the current temperature in Celsius."""
        return 18.5
```

Call it from another skill:

```python
from ovos_workshop.skills.api import SkillApi

class MySkill(OVOSSkill):
    def initialize(self):
        SkillApi.connect_bus(self.bus)

    def handle_weather(self, message):
        api = SkillApi.get("my-weather-skill.author")
        temp = api.get_temperature("London") if api else None
        self.speak(f"{temp} degrees" if temp else "Weather unavailable.")
```

See [docs/skill-api.md](docs/skill-api.md) for the full protocol reference.

---

## What is FileSystemAccess and how do I use it?

`FileSystemAccess` provides a sandboxed directory for persistent file storage. Files are written to `~/.local/share/ovos/filesystem/<skill_id>/`. Access it through `self.file_system` inside any skill:

```python
import json

class MySkill(OVOSSkill):
    def save_data(self, data: dict):
        with self.file_system.open("data.json", "w") as f:
            json.dump(data, f)

    def load_data(self) -> dict:
        if not self.file_system.exists("data.json"):
            return {}
        with self.file_system.open("data.json", "r") as f:
            return json.load(f)
```

See [docs/filesystem.md](docs/filesystem.md) for the full reference including migration from legacy Mycroft paths.

---

## What does OVOSAbstractApplication do differently from OVOSSkill?

`OVOSAbstractApplication` is designed to run **without** being loaded by `ovos-core`. Key differences:

| | `OVOSSkill` | `OVOSAbstractApplication` |
|---|---|---|
| Loaded by `ovos-core` | Yes | No |
| Creates own bus connection | No | Yes (if no bus passed) |
| Settings path | `skills/<id>/settings.json` | `apps/<id>/settings.json` |
| Clears intents on shutdown | No | Yes (`clear_intents()`) |

Use `OVOSAbstractApplication` for standalone GUI apps, daemon processes, or any service that needs OVOS infrastructure without a full skill lifecycle.

```python
from ovos_workshop.app import OVOSAbstractApplication

app = OVOSAbstractApplication(skill_id="my-app.author")
```

See [docs/app.md](docs/app.md) for the full reference.
