# Decorators

All decorators are importable from `ovos_workshop.decorators`.

```python
from ovos_workshop.decorators import (
    intent_handler,
    fallback_handler,
    converse_handler,
    conversational_intent,
    common_query,
    skill_api_method,
    adds_context,
    removes_context,
    homescreen_app,
    killable_intent,
    killable_event,
)
from ovos_workshop.decorators.layers import (
    layer_intent,
    enables_layer,
    disables_layer,
    replaces_layer,
    removes_layer,
    resets_layers,
)
from ovos_workshop.decorators.ocp import (
    ocp_search,
    ocp_play,
    ocp_pause,
    ocp_resume,
    ocp_next,
    ocp_previous,
    ocp_featured_media,
)
```

---

## Intent Decorators

### `@intent_handler`

`intent_handler` is defined in `ovos_workshop/decorators/__init__.py:57`.
Register a method as a Padatious (`.intent` file) or Adapt (`IntentBuilder`) intent handler.

```python
from ovos_workshop.decorators import intent_handler
from ovos_workshop.intents import IntentBuilder

# Padatious intent file
@intent_handler("my.intent")
def handle_my(self, message): ...

# Adapt intent
@intent_handler(IntentBuilder("GreetIntent").require("Hello"))
def handle_greet(self, message): ...

# With voc blacklist: suppress adapt keywords in this handler
@intent_handler("my.intent", voc_blacklist=["StopKeyword"])
def handle_my_no_stop(self, message): ...
```

A method can have multiple `@intent_handler` decorators to handle multiple intents with the same function.

#### OVOS-CONTEXT-1 gating: `requires_context` / `excludes_context`

`requires_context` and `excludes_context` declare the OVOS-CONTEXT-1
§6 / §6.1 gating an intent needs: an engine that implements the spec will
not report a match unless every `requires_context` entry is a live session
context entry, and none of the `excludes_context` entries are. Each entry is
either a bare key string (scope defaults to `"private"`, owned by this
skill) or a `{"key": ..., "scope": "private"|"shared"}` mapping.

The declaration rides both `.intent` file (Padatious/template) and
`IntentBuilder` (Adapt/keyword) registrations — CONTEXT-1 §6 is explicit
that "an engine that does not implement OVOS-CONTEXT-1 ignores them and
matches as if absent," so it is not workshop's place to strip the field
for one engine family. Adapt itself has no OVOS-CONTEXT-1-aware matcher
today, so declaring `requires_context`/`excludes_context` on an
`IntentBuilder`-based `@intent_handler` currently has no effect on Adapt's
own matching, but the declaration still reaches the wire for any engine
that does honour it.

The classic use is a confirmation branch: a top-level intent asks a
yes/no question and sets a flag via `Session.set_intent_context`, and the
`yes`/`no` follow-ups only match while that flag is live.

```python
from ovos_bus_client.session import SessionManager

@intent_handler("order_milk.intent")
def handle_order_milk(self, message):
    session = SessionManager.get(message)
    session.set_intent_context("confirming_milk", None,
                               scope="private", owner_id=self.skill_id,
                               turns_remaining=1)
    # speak_dialog/speak forward() the dispatch Message, which carries
    # the mutated session (OVOS-CONTEXT-1 §5.3 point 3); a handler that
    # emits nothing does not propagate its context write.
    self.speak_dialog("confirm.milk")

@intent_handler("yes.intent", requires_context=["confirming_milk"])
def handle_confirm_milk(self, message):
    self.speak_dialog("adding.milk")

@intent_handler("no.intent", requires_context=["confirming_milk"])
def handle_decline_milk(self, message):
    self.speak_dialog("ok.no.milk")
```

`yes.intent`/`no.intent` only match in the narrow window between the
question and the answer; outside it the same words have no context to
attach to and the intents are silent.

---

### `@conversational_intent`

`conversational_intent` is defined in `ovos_workshop/decorators/__init__.py:117`.
Register a Padatious `.intent` file as a converse-only matcher. Only active when the skill is in converse mode. Requires the skill to extend `ConversationalSkill`.

> **Note:** Only Padatious intents are supported, not Adapt.

```python
from ovos_workshop.decorators import conversational_intent

@conversational_intent("help.intent")
def handle_help_in_converse(self, message): ...
```

---

### `@fallback_handler`

`fallback_handler` is defined in `ovos_workshop/decorators/__init__.py:133`.
Register a method as a fallback handler with a given priority (0–100, lower = higher priority).

```python
from ovos_workshop.decorators import fallback_handler

@fallback_handler(priority=50)
def handle_unknown(self, message):
    self.speak("I don't know.")
    return True  # consumed: stop checking other fallbacks
```

---

### `@common_query`

`common_query` is defined in `ovos_workshop/decorators/__init__.py:94`.
Register a method as a CommonQuery handler. The method must return `(answer, confidence)` or `None`.

```python
from ovos_workshop.decorators import common_query

@common_query(callback=None)
def handle_query(self, phrase, lang):
    if "meaning of life" in phrase:
        return "42", 0.99
    return None, 0
```

`callback` is optional. If provided it is called with `(phrase, answer, lang)` after the answer is spoken.

---

## Converse Decorators

### `@converse_handler`

`converse_handler` is defined in `ovos_workshop/decorators/__init__.py:108`.
Alias a method as the skill's `converse` handler instead of overriding `converse()` directly.

```python
from ovos_workshop.decorators import converse_handler

@converse_handler
def my_converse(self, message):
    return False  # not consumed
```

---

## Context Decorators

`adds_context` is defined in `ovos_workshop/decorators/__init__.py:16`.
`removes_context` is defined in `ovos_workshop/decorators/__init__.py:37`.
These run **after** the decorated method completes.

### `@adds_context`

```python
from ovos_workshop.decorators import adds_context

@adds_context("OrderContext", "ordering")
def handle_order(self, message):
    self.speak("What would you like to order?")
```

### `@removes_context`

```python
from ovos_workshop.decorators import removes_context

@removes_context("OrderContext")
def handle_cancel(self, message):
    self.speak("Order cancelled.")
```

---

## Killable / Abortable Decorators

### Exception Classes

`AbortEvent` is defined in `ovos_workshop/decorators/killable.py:12`.
`AbortIntent` is defined in `ovos_workshop/decorators/killable.py:16`.
`AbortQuestion` is defined in `ovos_workshop/decorators/killable.py:19`.
```python
class AbortEvent(StopIteration):
    """Base class: abort any bus event handler."""

class AbortIntent(AbortEvent):
    """Abort intent parsing. Raised by @killable_intent."""

class AbortQuestion(AbortEvent):
    """Gracefully abort get_response queries."""
```

These exceptions are **raised inside the handler thread** when the kill message is received. They propagate through the call stack. Wrap long-running loops to catch and clean up:

```python
from ovos_workshop.decorators.killable import killable_intent, AbortIntent

@killable_intent()
def handle_long_task(self, message):
    for step in range(1000):
        try:
            self.speak(f"Step {step}")
        except AbortIntent:
            self.speak("Task was cancelled.")
            return
```

---

### `@killable_intent`

`killable_intent` is defined in `ovos_workshop/decorators/killable.py:24`.
Mark an intent handler that can be interrupted mid-execution. Spawns the handler in a daemon thread. When the kill message arrives:

1. Optionally emits `mycroft.audio.speech.stop` (if `stop_tts=True`).
2. Optionally calls `skill.stop()` (if `call_stop=True`).
3. Raises `AbortIntent` in the handler thread.
4. Calls `callback` if one was provided.

```python
from ovos_workshop.decorators import killable_intent

@killable_intent(
    msg="mycroft.skills.abort_execution",  # bus message that triggers abort
    callback=None,                          # optional cleanup callable
    react_to_stop=True,                     # also react to stop messages
    call_stop=True,                         # call skill.stop() on abort
    stop_tts=True,                          # stop TTS playback on abort
)
def handle_long_task(self, message):
    import time
    for i in range(60):
        self.speak(f"Counting {i}")
        time.sleep(1)
```

Default parameters:

| Parameter | Default |
|---|---|
| `msg` | `"mycroft.skills.abort_execution"` |
| `callback` | `None` |
| `react_to_stop` | `True` |
| `call_stop` | `True` |
| `stop_tts` | `True` |

**Abort flow:**

```
Bus receives "mycroft.skills.abort_execution"
  └─► abort() called in main thread
      ├─► emit "mycroft.audio.speech.stop"  (if stop_tts=True)
      ├─► skill.stop()                       (if call_stop=True)
      ├─► t.raise_exc(AbortIntent)           ← raised inside handler thread
      └─► callback()                         (if provided)
```

---

### `@killable_event`

`killable_event` is defined in `ovos_workshop/decorators/killable.py:40`.
Like `@killable_intent` but for any bus event handler. Does **not** react to stop messages or call `skill.stop()` by default.

```python
from ovos_workshop.decorators.killable import killable_event, AbortEvent

@killable_event(
    msg="my.abort.signal",
    exc=AbortEvent,          # exception to raise (default AbortEvent)
    callback=None,
    react_to_stop=False,     # default False for events
    call_stop=False,         # default False for events
    stop_tts=False,
    check_skill_id=False,    # require skill_id match in message.data
)
def handle_background_task(self, message):
    # long-running work here
    pass
```

The `check_skill_id=True` option prevents accidental termination when another skill's abort message is received.

---

## Intent Layer Decorators

Intent layers let you enable or disable groups of intents at runtime, implementing modal/state-based flows.

### `@layer_intent`

`layer_intent` is defined in `ovos_workshop/decorators/layers.py:128`.
Register an intent handler that belongs to a named layer. The intent is disabled until the layer is activated.

```python
from ovos_workshop.decorators.layers import layer_intent
from ovos_workshop.intents import IntentBuilder

@layer_intent(IntentBuilder("MoveIntent").require("Move"), layer_name="game_active")
def handle_move(self, message): ...
```

---

### `@enables_layer` / `@disables_layer`

`enables_layer` is defined in `ovos_workshop/decorators/layers.py:33`.
`disables_layer` is defined in `ovos_workshop/decorators/layers.py:52`.
Activate or deactivate a named intent layer **after** the decorated method runs.

```python
from ovos_workshop.decorators.layers import enables_layer, disables_layer

@enables_layer("game_active")
def start_game(self, message):
    self.speak("Game started!")

@disables_layer("game_active")
def stop_game_intent(self, message):
    self.speak("Game stopped!")
```

---

### `@replaces_layer`

`replaces_layer` is defined in `ovos_workshop/decorators/layers.py:71`.
Replace the intent list of a named layer after the method runs.

```python
from ovos_workshop.decorators.layers import replaces_layer

@replaces_layer("my_layer", intent_list=["NewIntent1", "NewIntent2"])
def transition(self, message): ...
```

---

### `@removes_layer`

`removes_layer` is defined in `ovos_workshop/decorators/layers.py:91`.
Remove a named layer entirely (and disable its intents) after the method runs.

```python
from ovos_workshop.decorators.layers import removes_layer

@removes_layer("temporary_layer")
def finish_flow(self, message): ...
```

---

### `@resets_layers`

`resets_layers` is defined in `ovos_workshop/decorators/layers.py:110`.
Disable **all** intent layers after the method runs.

```python
from ovos_workshop.decorators.layers import resets_layers

@resets_layers()
def reset_everything(self, message):
    self.speak("All modes cleared.")
```

---

## GUI / Homescreen Decorators

### `@homescreen_app`

`homescreen_app` is defined in `ovos_workshop/decorators/__init__.py:149`.
Register a method as a homescreen app launcher. The icon file must be inside the `gui/` subfolder of the skill.

```python
from ovos_workshop.decorators import homescreen_app

@homescreen_app(icon="my_app.png", name="My App")
def launch_app(self, message):
    self.gui.show_page("main.qml")
```

---

## API Decorator

### `@skill_api_method`

`skill_api_method` is defined in `ovos_workshop/decorators/__init__.py:77`.
Expose a method over the bus so other skills or applications can call it via `SkillApi`. See [skill-api.md](skill-api.md) for the full RPC documentation.

```python
from ovos_workshop.decorators import skill_api_method

@skill_api_method
def get_data(self, key: str) -> dict:
    """Return data for key."""
    return {"key": key, "value": self.settings.get(key)}
```

The method is registered as `{skill_id}.get_data` on the bus.

---

## OCP Decorators

OCP (OpenVoiceOS Common Play) decorators are used with `OVOSCommonPlaybackSkill` and `OVOSGameSkill`.

**Source:** `ovos_workshop/decorators/ocp.py`

| Decorator | Attribute set | Description | Source line |
|---|---|---|---|
| `@ocp_search()` | `is_ocp_search_handler` | Search for playable content. Yield or return `MediaEntry` results. | `ocp.py:5` |
| `@ocp_play()` | `is_ocp_playback_handler` | Handle a play request (start playback). | `ocp.py:34` |
| `@ocp_pause()` | `is_ocp_pause_handler` | Handle a pause request. | `ocp.py:82` |
| `@ocp_resume()` | `is_ocp_resume_handler` | Handle a resume request. | `ocp.py:98` |
| `@ocp_next()` | `is_ocp_next_handler` | Handle skip-forward. | `ocp.py:66` |
| `@ocp_previous()` | `is_ocp_prev_handler` | Handle skip-backward. | `ocp.py:50` |
| `@ocp_featured_media()` | `is_ocp_featured_handler` | Provide featured/recommended media for the OCP GUI. | `ocp.py:114` |

```python
from ovos_workshop.skills.common_play import OVOSCommonPlaybackSkill
from ovos_workshop.decorators.ocp import ocp_search, ocp_featured_media
from ovos_utils.ocp import MediaType, PlaybackType, MediaEntry, Playlist


class MyMusicSkill(OVOSCommonPlaybackSkill):

    @ocp_search()
    def search_music(self, phrase: str, media_type: MediaType):
        if media_type == MediaType.MUSIC:
            yield MediaEntry(
                uri="https://example.com/song.mp3",
                title="My Song",
                playback=PlaybackType.AUDIO,
                media_type=MediaType.MUSIC,
                match_confidence=80,
            )

    @ocp_featured_media()
    def featured(self) -> Playlist:
        pl = Playlist(title="My Playlist", playback=PlaybackType.AUDIO,
                      media_type=MediaType.MUSIC, match_confidence=90)
        pl.add_entry(MediaEntry(uri="https://example.com/song.mp3",
                                title="My Song",
                                playback=PlaybackType.AUDIO,
                                media_type=MediaType.MUSIC,
                                match_confidence=90))
        return pl
```

---

## Decorator Stacking Order Matters

When stacking multiple decorators, Python applies them **bottom-up** (innermost first). The `@intent_handler` and `@killable_intent` decorators both wrap the function, so the order affects which wrapper is outermost:

```python
# CORRECT: @killable_intent wraps the already-tagged intent handler.
# The intent is registered first, then wrapped for killability.
@killable_intent(react_to_stop=True)
@intent_handler("long_task.intent")
def handle_long_task(self, message):
    ...

# WRONG: @intent_handler would wrap the killable wrapper,
# and the `intents` attribute set by @intent_handler would be lost.
@intent_handler("long_task.intent")
@killable_intent(react_to_stop=True)
def handle_long_task(self, message):
    ...  # ← intent registration silently fails
```

Similarly, context decorators (`@adds_context`, `@removes_context`) should be the **outermost** decorator when combined with `@intent_handler`, because they run after the function body:

```python
@adds_context("ConfirmContext")
@intent_handler("confirm_order.intent")
def handle_confirm(self, message):
    self.speak("Order confirmed.")
# Context is added AFTER handle_confirm() returns.
```

---
[← ovos-skill](ovos-skill.md) · [Home](index.md) · [app →](app.md)
