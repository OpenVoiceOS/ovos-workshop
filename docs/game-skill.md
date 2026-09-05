# OVOSGameSkill and ConversationalGameSkill

`ovos-workshop` provides two base classes for building voice-driven games that integrate with the OCP (OpenVoiceOS Common Play) pipeline.

**Source:** `ovos_workshop/skills/game_skill.py`

---

## Class Hierarchy

```text
OVOSSkill
└── OVOSCommonPlaybackSkill
    └── OVOSGameSkill                  # abstract: OCP-integrated game loop
        └── ConversationalGameSkill    # adds converse loop + auto-save
```

`OVOSGameSkill` extends `OVOSCommonPlaybackSkill` so the game participates in OCP searches and appears in the OCP GUI media browser.

---

## OVOSGameSkill

`OVOSGameSkill` is defined in `ovos_workshop/skills/game_skill.py:14`.
### Constructor

```python
class OVOSGameSkill(OVOSCommonPlaybackSkill):
    def __init__(
        self,
        skill_voc_filename: str,
        *args,
        skill_icon: str = "",
        game_image: str = "",
        **kwargs,
    ): ...
```

`OVOSGameSkill.__init__` is defined in `ovos_workshop/skills/game_skill.py:33`.
| Parameter | Description |
|---|---|
| `skill_voc_filename` | **Required.** Name of the `.voc` file containing keywords that match the game name. Without this, OCP cannot recognize the skill as a game. |
| `skill_icon` | Path to the skill icon shown in OCP. |
| `game_image` | Path to a cover/preview image for the game. |

The constructor registers `MediaType.GAME` as the only supported media type and wires `on_play_game`, `on_pause_game`, and `on_resume_game` as the OCP playback handlers.

### Abstract Methods

Subclasses **must** implement all six abstract methods:

| Method | When called | Source line |
|---|---|---|
| `on_play_game()` | OCP pipeline selected this game and started playback. | `ovos_workshop/skills/game_skill.py:94` |
| `on_pause_game()` | OCP `pause` command while game is playing. | `ovos_workshop/skills/game_skill.py:98` |
| `on_resume_game()` | OCP `resume`/`unpause` while game is paused. | `ovos_workshop/skills/game_skill.py:102` |
| `on_stop_game()` | Game stopped for any reason. Implement auto-save here if desired. | `ovos_workshop/skills/game_skill.py:106` |
| `on_save_game()` | Explicit save request. Speak an error dialog if save is not supported. | `ovos_workshop/skills/game_skill.py:111` |
| `on_load_game()` | Explicit load request. Speak an error dialog if load is not supported. | `ovos_workshop/skills/game_skill.py:116` |

### Properties

#### `is_playing`

`OVOSGameSkill.is_playing` is defined in `ovos_workshop/skills/game_skill.py:87`.
Returns `True` when the game is actively running (OCP player state is not stopped/paused).

```python
@property
def is_playing(self) -> bool:
    return self._playing.is_set()
```

#### `is_paused`

`OVOSGameSkill.is_paused` is defined in `ovos_workshop/skills/game_skill.py:91`.
Returns `True` when the game is in the paused state.

```python
@property
def is_paused(self) -> bool:
    return self._paused.is_set()
```

### `stop_game()`

`OVOSGameSkill.stop_game` is defined in `ovos_workshop/skills/game_skill.py:121`.
Call this from within your skill code when you need to programmatically stop the game (e.g. the player lost). It:

1. Checks `is_playing`, returns `False` immediately if not playing.
2. Clears the paused flag.
3. Releases the GUI.
4. Emits `ovos.common_play.player.state` with `PlayerState.STOPPED`.
5. Clears the playing flag.
6. Calls `on_stop_game()`.

Returns `True` if the game was stopped, `False` if it was already stopped.

### `calc_intent()`

`OVOSGameSkill.calc_intent` is defined in `ovos_workshop/skills/game_skill.py:138`.
Helper that asks `ovos-core` which intent it would select for a given utterance. Useful in `converse()` to decide whether to let the intent pipeline handle the utterance or pipe it to the game.

```python
def calc_intent(
    self,
    utterance: str,
    lang: str,
    timeout: float = 1.0,
) -> Optional[Dict[str, str]]:
```

Returns the intent dict from `ovos-core`, or `None` on timeout.

---

## ConversationalGameSkill

`ConversationalGameSkill` is defined in `ovos_workshop/skills/game_skill.py:151`.
Extends `OVOSGameSkill` with a **converse loop**: every utterance that does not match a registered intent is piped to `on_game_command()` while the game is playing.

### Additional Abstract Methods

| Method | When called |
|---|---|
| `on_play_game()` | Same as `OVOSGameSkill`. Still abstract. `ovos_workshop/skills/game_skill.py:182` |
| `on_stop_game()` | Same as `OVOSGameSkill`. Still abstract. `ovos_workshop/skills/game_skill.py:186` |
| `on_game_command(utterance, lang)` | Any utterance that was not caught by an intent while the game is playing. `ovos_workshop/skills/game_skill.py:191` |

### Default Implementations

`ConversationalGameSkill` provides default (non-abstract) implementations for some methods:

| Method | Default behaviour | Source line |
|---|---|---|
| `on_save_game()` | Speaks `cant_save_game` dialog. | `ovos_workshop/skills/game_skill.py:153` |
| `on_load_game()` | Speaks `cant_load_game` dialog. | `ovos_workshop/skills/game_skill.py:158` |
| `on_pause_game()` | Sets `_paused`, calls `acknowledge()`, optionally speaks `game_pause`. | `ovos_workshop/skills/game_skill.py:163` |
| `on_resume_game()` | Clears `_paused`, calls `acknowledge()`, optionally speaks `game_unpause`. | `ovos_workshop/skills/game_skill.py:172` |

The pause/resume dialogs are controlled by `settings["pause_dialog"]` (default `False`).

### `on_abandon_game()`

`ConversationalGameSkill.on_abandon_game` is defined in `ovos_workshop/skills/game_skill.py:197`.
Called when the user stops interacting with the game long enough for the intent service to deactivate this skill. Auto-save runs before this method (if enabled). Override to play a farewell message or clean up state. `on_stop_game()` is called after this handler.

### `save_is_implemented` Property

`ConversationalGameSkill.save_is_implemented` is defined in `ovos_workshop/skills/game_skill.py:223`.
Returns `True` if the subclass has overridden `on_save_game()` (i.e. save is actually implemented). Used by `_autosave()` to skip auto-save for games that cannot save.

```python
@property
def save_is_implemented(self) -> bool:
    return self.__class__.on_save_game is not ConversationalGameSkill.on_save_game
```

### Auto-save

`ConversationalGameSkill._autosave` is defined in `ovos_workshop/skills/game_skill.py:229`.
Automatically saves the game if **both** conditions are met:

- `settings["auto_save"]` is `True` (default `False`).
- `save_is_implemented` is `True`.

Auto-save is triggered in three places:
- Before piping a command to `on_game_command()` via `converse()` (`ovos_workshop/skills/game_skill.py:256`).
- When the game is abandoned due to inactivity (`ovos_workshop/skills/game_skill.py:284`).
- When `stop()` is called (`ovos_workshop/skills/game_skill.py:292`).

### `skill_will_trigger()`

`ConversationalGameSkill.skill_will_trigger` is defined in `ovos_workshop/skills/game_skill.py:206`.
Checks whether this skill's intents would be selected by `ovos-core` for the given utterance. Useful in `converse()` to avoid double-handling:

```python
def converse(self, message):
    if self.skill_will_trigger(message.data["utterances"][0], self.lang):
        return False  # let the intent pipeline handle it normally
    # … pipe to game
```

---

## Minimal Game Skill Example

```python
from ovos_workshop.skills.game_skill import ConversationalGameSkill


class NumberGuessingSkill(ConversationalGameSkill):
    """A simple number-guessing game."""

    def __init__(self, *args, **kwargs):
        # skill_voc_filename must match a .voc file that contains the game's name
        super().__init__(
            skill_voc_filename="number_game",
            skill_icon="res/icon.png",
            *args,
            **kwargs,
        )
        self._secret: int = 0

    def on_play_game(self):
        import random
        self._secret = random.randint(1, 10)
        self.speak("I'm thinking of a number between 1 and 10. Guess!")

    def on_stop_game(self):
        self.speak("Game over!")

    def on_game_command(self, utterance: str, lang: str):
        try:
            guess = int(utterance.strip())
        except ValueError:
            self.speak("Please say a number.")
            return

        if guess == self._secret:
            self.speak("Correct! You win!")
            self.stop_game()
        elif guess < self._secret:
            self.speak("Higher!")
        else:
            self.speak("Lower!")

    def on_abandon_game(self):
        self.speak("Come back and play again!")
```

Enable auto-save in `settings.json`:

```json
{
  "auto_save": true,
  "pause_dialog": true
}
```

---
[← app](app.md) · [Home](index.md) · [auto-translatable →](auto-translatable.md)
