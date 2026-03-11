# Auto-Translatable Skills: UniversalSkill and UniversalFallback

`ovos-workshop` provides mixin base classes that automatically translate incoming utterances into a skill's **internal working language** and translate `speak()` output back into the user's language. This lets you write skill logic exclusively in one language while serving users in any language.

**Source:** `ovos_workshop/skills/auto_translatable.py`

---

## How Auto-Translation Works

Normal skills receive utterances in whatever language the user spoke (`self.lang`). For multi-language support the developer must handle every language explicitly.

`UniversalSkill` breaks this into two clear responsibilities:

1. **Input translation** — Before each intent handler fires, the incoming `Message` is translated so that `message.data["utterances"]` and related fields are in `self.internal_language`.
2. **Output translation** — Every call to `self.speak()` translates the text from `self.internal_language` back to `self.lang` (the user's language).

The translation is performed by the configured translator plugin (set in `ovos.conf`). `self.lang` always reflects the **original query language** from the session.

---

## UniversalSkill

`UniversalSkill` — `ovos_workshop/skills/auto_translatable.py:14`

### Constructor

```python
class UniversalSkill(OVOSSkill):
    def __init__(
        self,
        internal_language: str = None,
        translate_tags: bool = True,
        autodetect: bool = False,
        translate_keys: list = None,
        *args,
        **kwargs,
    ): ...
```

`UniversalSkill.__init__` — `ovos_workshop/skills/auto_translatable.py:30`

| Parameter | Default | Description |
|---|---|---|
| `internal_language` | `None` (falls back to `config["lang"]`) | The language in which the skill internally operates. All handlers receive utterances in this language. |
| `translate_tags` | `True` | Also translate `message.data["__tags__"]` (Adapt entity values). |
| `autodetect` | `False` | If `True`, detect the source language from the utterance text itself regardless of `Session.lang`. |
| `translate_keys` | `["utterance", "utterances"]` | Additional `message.data` keys whose values should be translated before the handler runs. |

If `internal_language` is not given, a warning is logged and the global config language is used.

---

### `internal_language`

`UniversalSkill.internal_language` — `ovos_workshop/skills/auto_translatable.py:53`

The language tag the skill expects to receive and produce. Set this in your subclass constructor:

```python
super().__init__(internal_language="en-US", *args, **kwargs)
```

---

### `detect_language(utterance)`

`UniversalSkill.detect_language` — `ovos_workshop/skills/auto_translatable.py:79`

Detects the language of `utterance` using the configured language detector plugin. Falls back to `self.lang.split("-")[0]` on error.

```python
def detect_language(self, utterance: str) -> str: ...
```

Only active when `autodetect=True`; otherwise `self.lang` (from the session) is used as the source language.

---

### `translate_utterance(text, target_lang, sauce_lang=None)`

`UniversalSkill.translate_utterance` — `ovos_workshop/skills/auto_translatable.py:104`

Translates `text` from `sauce_lang` to `target_lang`. If the source and target language share the same base code (ignoring region), the original text is returned unchanged.

```python
def translate_utterance(
    self,
    text: str,
    target_lang: str,
    sauce_lang: str = None,
) -> str: ...
```

If `autodetect=True`, `sauce_lang` is determined by calling `detect_language(text)` even if `sauce_lang` was passed.

---

### `translate_message(message)`

`UniversalSkill.translate_message` — `ovos_workshop/skills/auto_translatable.py:134`

Translates the full message in-place (or returns it unchanged if no translation is needed). The method:

1. Sets `sauce_lang = self.lang` and `out_lang = self.internal_language`.
2. Skips translation if both are equal and `autodetect` is `False`.
3. Iterates `self.translate_keys` and translates each matching value in `message.data`.
4. Optionally translates `message.data["__tags__"]` (Adapt entities).
5. Stores translation metadata in `message.context["translation_data"]`.

Returns the modified `Message`.

---

### Overridden `register_intent()` and `register_intent_file()`

`UniversalSkill.register_intent` — `ovos_workshop/skills/auto_translatable.py:228`
`UniversalSkill.register_intent_file` — `ovos_workshop/skills/auto_translatable.py:250`

Both methods wrap the provided handler with `create_universal_handler()` before passing it to the parent class. This is transparent — you register intents exactly as with a regular `OVOSSkill`:

```python
def initialize(self):
    self.register_intent_file("ask_question.intent", self.handle_question)
```

The handler will always receive `message.data["utterances"]` in `self.internal_language`.

---

### `create_universal_handler(handler)`

`UniversalSkill.create_universal_handler` — `ovos_workshop/skills/auto_translatable.py:193`

Creates a wrapper that calls `self.translate_message(message)` before calling `handler(message)`. Use this explicitly only when registering handlers with `self.add_event()` (not with `register_intent`, which wraps automatically):

```python
def initialize(self):
    self.add_event(
        "my.custom.event",
        self.create_universal_handler(self.handle_custom_event),
    )
```

---

### Overridden `speak()`

`UniversalSkill.speak` — `ovos_workshop/skills/auto_translatable.py:272`

Translates the utterance from `self.internal_language` to `self.lang` before calling `super().speak()`. Translation metadata is stored in the `meta` kwarg:

```python
meta["translation_data"] = {
    "original": <original text>,
    "internal_lang": self.internal_language,
    "target_lang": out_lang,
    "translated": <translated text>,
}
```

---

## UniversalFallback

`UniversalFallback` — `ovos_workshop/skills/auto_translatable.py:314`

```python
class UniversalFallback(UniversalSkill, FallbackSkill):
    ...
```

Combines `UniversalSkill` with `FallbackSkill`. Fallback handlers receive utterances in `self.internal_language` and `self.speak()` translates output back to `self.lang`.

### `register_fallback(handler, priority)`

`UniversalFallback.register_fallback` — `ovos_workshop/skills/auto_translatable.py:353`

Wraps the handler with `create_universal_fallback_handler()` before registering it, ensuring translation happens before the handler is called.

### `create_universal_fallback_handler(handler)`

`UniversalFallback.create_universal_fallback_handler` — `ovos_workshop/skills/auto_translatable.py:328`

Similar to `create_universal_handler()` but designed for fallback handlers (which receive `self` as an explicit argument).

---

## UniversalCommonQuerySkill

`UniversalCommonQuerySkill` — `ovos_workshop/skills/auto_translatable.py:376`

> **Deprecated.** Use `UniversalSkill` with `@common_query` instead.

Combines `UniversalSkill` with `CommonQuerySkill`. Both the input phrase and the skill's answer are translated automatically:

- `CQS_match_query_phrase` receives the phrase in `self.internal_language`.
- The returned answer is translated back to `self.lang` before being spoken.

---

## Code Example

```python
from ovos_workshop.skills.auto_translatable import UniversalSkill
from ovos_workshop.decorators import intent_handler


class WeatherSkill(UniversalSkill):
    """A weather skill that works entirely in English internally."""

    def __init__(self, *args, **kwargs):
        # All intent handlers receive utterances in en-US.
        # speak() output is auto-translated to the user's language.
        super().__init__(
            internal_language="en-US",
            translate_tags=True,
            autodetect=False,
            *args,
            **kwargs,
        )

    @intent_handler("ask_weather.intent")
    def handle_weather(self, message):
        # message.data["utterances"][0] is already in English here.
        city = message.data.get("city", "your location")
        # self.lang is still the original user language — useful for logging.
        self.log.debug(f"User language: {self.lang}")
        # speak() translates from en-US → self.lang automatically.
        self.speak(f"The weather in {city} is sunny today.")
```

For a fallback skill:

```python
from ovos_workshop.skills.auto_translatable import UniversalFallback
from ovos_workshop.decorators import fallback_handler


class MyUniversalFallback(UniversalFallback):

    def __init__(self, *args, **kwargs):
        super().__init__(internal_language="en-US", *args, **kwargs)

    @fallback_handler(priority=75)
    def handle_unknown(self, message) -> bool:
        # utterance is in English regardless of user's language
        utterance = message.data["utterances"][0]
        self.speak(f"I heard: {utterance}")
        return True
```
