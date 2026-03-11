# Skill Classes

All skill base classes are available from their individual modules. The table below shows the full class hierarchy.

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
│   └── UniversalCommonQuerySkill     ovos_workshop/skills/auto_translatable.py (deprecated)
└── OVOSAbstractApplication           ovos_workshop/app.py
```

---

## OVOSSkill

**Module:** `ovos_workshop.skills.ovos`

The universal base class. Every skill and application ultimately inherits from `OVOSSkill`. Handles intent registration, resource files, settings, GUI interface, MessageBus events, and the full skill lifecycle (`initialize`, `default_shutdown`).

```python
from ovos_workshop.skills.ovos import OVOSSkill
```

See [ovos-skill.md](ovos-skill.md) for full detail.

---

## ConversationalSkill

**Module:** `ovos_workshop.skills.converse`

Extends `OVOSSkill` with explicit converse support — `activate()`, `deactivate()`, and `@conversational_intent` decorated handlers. The skill registers itself in the active-skills list after handling an intent.

```python
from ovos_workshop.skills.converse import ConversationalSkill

class MySkill(ConversationalSkill):
    def converse(self, message):
        utterance = message.data["utterances"][0]
        if "help" in utterance:
            self.speak("Here to help!")
            return True   # consumed
        return False      # pass to next handler
```

Additional bus events registered:
- `{skill_id}.converse.ping` — capability advertisement
- `{skill_id}.converse.request` — converse request from pipeline
- `{skill_id}.activate` / `{skill_id}.deactivate`
- `intent.service.skills.deactivated` / `intent.service.skills.activated`

---

## ActiveSkill

**Module:** `ovos_workshop.skills.active`

Extends `ConversationalSkill`. Always present in the converse active-skills list — the skill never deactivates unless explicitly told to. Useful for always-on assistants or global command handlers.

```python
from ovos_workshop.skills.active import ActiveSkill

class AlwaysListeningSkill(ActiveSkill):
    def converse(self, message):
        utterance = message.data["utterances"][0]
        # handle every utterance
        return False  # let other skills also process
```

---

## FallbackSkill

**Module:** `ovos_workshop.skills.fallback`

Handles utterances that matched no intent. Must implement `can_answer()` and provide at least one `@fallback_handler`.

```python
from ovos_workshop.skills.fallback import FallbackSkill
from ovos_workshop.decorators import fallback_handler

class MyFallback(FallbackSkill):
    def can_answer(self, utterances, lang) -> bool:
        return True   # always willing to try

    @fallback_handler(priority=50)
    def handle_fallback(self, message):
        self.speak("I don't know, but I tried.")
        return True   # consumed
```

Priority determines stage:

| Range | Stage |
|---|---|
| 0–4 | `fallback_high` |
| 5–89 | `fallback_medium` |
| 90–100 | `fallback_low` |

Priority can be overridden in config:
```json
{"skills": {"fallbacks": {"fallback_priorities": {"my-skill-id": 10}}}}
```

---

## CommonQuerySkill

**Module:** `ovos_workshop.skills.common_query_skill`

Participates in the `question:query` / `common_qa` pipeline. The skill attempts to answer a natural language question and returns a confidence score. The pipeline collects responses from all skills and speaks the highest-confidence answer via `question:action`.

```python
from ovos_workshop.skills.common_query_skill import CommonQuerySkill
from ovos_workshop.decorators import common_query

class MyQuerySkill(CommonQuerySkill):
    @common_query()
    def handle_query(self, phrase, lang):
        if "capital of france" in phrase.lower():
            return "Paris", 0.9   # (answer, confidence)
        return None, 0
```

---

## OVOSCommonPlaybackSkill

**Module:** `ovos_workshop.skills.common_play`

Integrates with OCP (OpenVoiceOS Common Play) for media playback. Uses `@ocp_search`, `@ocp_play`, and related decorators to respond to play requests and appear in the OCP media browser.

```python
from ovos_workshop.skills.common_play import OVOSCommonPlaybackSkill
from ovos_workshop.decorators.ocp import ocp_search
from ovos_utils.ocp import MediaType, PlaybackType, MediaEntry

class MyMusicSkill(OVOSCommonPlaybackSkill):
    @ocp_search()
    def search_music(self, phrase, media_type):
        if media_type == MediaType.MUSIC:
            yield MediaEntry(
                title="My Song",
                uri="https://example.com/song.mp3",
                playback=PlaybackType.AUDIO,
                media_type=MediaType.MUSIC,
                match_confidence=80,
            )
```

---

## OVOSGameSkill

**Module:** `ovos_workshop.skills.game_skill`
**Source:** `ovos_workshop/skills/game_skill.py:14`

Extends `OVOSCommonPlaybackSkill`. Structured base for OCP-integrated voice games. The game is discoverable through OCP and appears in the media browser. Subclasses must implement all six abstract methods: `on_play_game`, `on_pause_game`, `on_resume_game`, `on_stop_game`, `on_save_game`, `on_load_game`.

```python
from ovos_workshop.skills.game_skill import OVOSGameSkill

class TriviaGameSkill(OVOSGameSkill):
    def __init__(self, *args, **kwargs):
        super().__init__(skill_voc_filename="trivia_game", *args, **kwargs)

    def on_play_game(self):
        self.speak("Starting trivia!")

    def on_pause_game(self):
        self._paused.set()

    def on_resume_game(self):
        self._paused.clear()

    def on_stop_game(self):
        self.speak("Game over.")

    def on_save_game(self):
        self.speak("Save is not supported.")

    def on_load_game(self):
        self.speak("Load is not supported.")
```

See [game-skill.md](game-skill.md) for full documentation.

---

## ConversationalGameSkill

**Module:** `ovos_workshop.skills.game_skill`
**Source:** `ovos_workshop/skills/game_skill.py:151`

Extends `OVOSGameSkill`. Adds a **converse loop**: every utterance that does not match a registered intent is piped to `on_game_command()` while the game is playing. Also adds auto-save support, default pause/resume dialogs, and `on_abandon_game()`.

Remaining abstract methods: `on_play_game`, `on_stop_game`, `on_game_command`.

```python
from ovos_workshop.skills.game_skill import ConversationalGameSkill

class AdventureSkill(ConversationalGameSkill):
    def __init__(self, *args, **kwargs):
        super().__init__(skill_voc_filename="adventure_game", *args, **kwargs)

    def on_play_game(self):
        self.speak("You enter a dark room. What do you do?")

    def on_stop_game(self):
        self.speak("Adventure ends.")

    def on_game_command(self, utterance: str, lang: str):
        if "north" in utterance:
            self.speak("You walk north.")
        else:
            self.speak("I don't understand that command.")
```

See [game-skill.md](game-skill.md) for full documentation including auto-save and converse loop behaviour.

---

## UniversalSkill

**Module:** `ovos_workshop.skills.auto_translatable`
**Source:** `ovos_workshop/skills/auto_translatable.py:14`

Extends `OVOSSkill`. Automatically translates incoming utterances to `self.internal_language` before the intent handler runs, and translates `self.speak()` output back to the user's language. Requires a translator plugin to be configured.

```python
from ovos_workshop.skills.auto_translatable import UniversalSkill
from ovos_workshop.decorators import intent_handler

class MySkill(UniversalSkill):
    def __init__(self, *args, **kwargs):
        # All handlers receive utterances in English regardless of user's language.
        super().__init__(internal_language="en-US", *args, **kwargs)

    @intent_handler("ask_weather.intent")
    def handle_weather(self, message):
        # Utterance is already in en-US here.
        self.speak("The weather is sunny.")  # auto-translated back to user's lang
```

See [auto-translatable.md](auto-translatable.md) for full documentation.

---

## UniversalFallback

**Module:** `ovos_workshop.skills.auto_translatable`
**Source:** `ovos_workshop/skills/auto_translatable.py:314`

Combines `UniversalSkill` and `FallbackSkill`. Fallback handlers receive utterances in `self.internal_language`. `self.speak()` translates output back to the user's language.

```python
from ovos_workshop.skills.auto_translatable import UniversalFallback
from ovos_workshop.decorators import fallback_handler

class MyUniversalFallback(UniversalFallback):
    def __init__(self, *args, **kwargs):
        super().__init__(internal_language="en-US", *args, **kwargs)

    @fallback_handler(priority=75)
    def handle_unknown(self, message) -> bool:
        utterance = message.data["utterances"][0]
        self.speak(f"I heard: {utterance}")
        return True
```

See [auto-translatable.md](auto-translatable.md) for full documentation.

---

## OVOSAbstractApplication

**Module:** `ovos_workshop.app`
**Source:** `ovos_workshop/app.py:12`

Like `OVOSSkill` but designed to run **without** an intent service. Suitable for standalone GUI apps, HiveMind-attached services, or any program that needs TTS/MessageBus/settings but does not register intents with `ovos-core`. Creates its own bus connection if none is provided. Settings stored under `apps/<id>/` instead of `skills/<id>/`.

```python
from ovos_workshop.app import OVOSAbstractApplication

class MyApp(OVOSAbstractApplication):
    def __init__(self, **kwargs):
        super().__init__(skill_id="my-app.author", **kwargs)

    def initialize(self):
        self.speak("App is ready.")

app = MyApp()  # Creates its own bus connection automatically.
```

See [app.md](app.md) for full documentation.
