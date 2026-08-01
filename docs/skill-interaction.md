# Skill Interaction Methods

`OVOSSkill` provides two high-level methods for collecting structured user input: `ask_yesno` for binary yes/no questions and `ask_selection` for multiple-choice prompts. Both are backed by pluggable agent engines that can be swapped per-skill or system-wide.

---

## ask_yesno

```python
OVOSSkill.ask_yesno(prompt: str, data: Optional[dict] = None) -> Optional[str]
```

Speaks *prompt*, waits for the user's response, and classifies it as `"yes"`, `"no"`, or the raw response string if neither matched.

**Source**: `OVOSSkill.ask_yesno` in `ovos_workshop/skills/ovos.py`

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `prompt` | `str` | Dialog ID (looked up in `locale/`) or a literal string to speak. |
| `data` | `dict \| None` | Template variables for Mustache rendering of the dialog string. |

### Return values

| Value | Meaning |
|-------|---------|
| `"yes"` | User confirmed (e.g. "yeah", "sure", "of course") |
| `"no"` | User declined (e.g. "nope", "nah", "definitely not") |
| `str` | User spoke something that could not be classified: raw transcript returned |
| `None` | No response received (timeout or user said nothing) |

### Basic usage

```python
class MySkill(OVOSSkill):
    def handle_delete_intent(self, message):
        if self.ask_yesno("confirm_delete") == "yes":
            self._do_delete()
            self.speak_dialog("deleted")
        else:
            self.speak_dialog("cancelled")
```

`locale/en-us/confirm_delete.dialog`:
```
Are you sure you want to delete this?
Do you really want to delete it?
```

### With template data

```python
answer = self.ask_yesno("confirm_action", data={"action": "restart the server"})
```

`locale/en-us/confirm_action.dialog`:
```
Are you sure you want to {{action}}?
```

### Handling all return values

```python
answer = self.ask_yesno("do_you_want_music")
if answer == "yes":
    self.play_music()
elif answer == "no":
    self.speak_dialog("okay_nevermind")
elif answer is None:
    self.speak_dialog("no_response")
else:
    # answer is the raw transcript: user said something unexpected
    self.speak_dialog("did_not_understand")
```

### How it works internally

1. `get_response(dialog=prompt, data=data)`: speaks the prompt, records user reply.
2. `_get_yesno_engine()`: resolves the plugin name (settings → mycroft.conf → `ovos-solver-yes-no-plugin`), loads it once, and caches it. Falls back to `HeuristicYesNoEngine` if loading fails. `OVOSSkill._get_yesno_engine`: `ovos_workshop/skills/ovos.py:1932`
3. `engine.yes_or_no(question=prompt, response=resp, lang=self.lang)` → `True`, `False`, or `None`.
4. `True` → `"yes"`, `False` → `"no"`, `None`/unmatched → raw response. `OVOSSkill.ask_yesno`: `ovos_workshop/skills/ovos.py:1970`

---

## ask_selection

```python
OVOSSkill.ask_selection(
    options: List[str],
    dialog: str = '',
    data: Optional[dict] = None,
    min_conf: float = 0.65,
    numeric: bool = False,
    num_retries: int = -1,
) -> Optional[str]
```

Speaks the options list to the user, optionally follows with a dialog prompt, then resolves the user's spoken response to one of the options.

**Source**: `OVOSSkill.ask_selection` in `ovos_workshop/skills/ovos.py`

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `options` | `List[str]` |: | The predefined options to offer. |
| `dialog` | `str` | `''` | Dialog ID or literal string spoken **after** the options list. |
| `data` | `dict \| None` | `None` | Template variables for the dialog string. |
| `min_conf` | `float` | `0.65` | Minimum fuzzy-match confidence for the default plugin. Passed to the `OptionMatcherEngine` config if no plugin-level config overrides it. |
| `numeric` | `bool` | `False` | If `True`, speaks each option prefixed with its number ("one, pizza, two, pasta, and so on"). If `False`, speaks them as a joined list ("pizza, pasta, or salad?"). |
| `num_retries` | `int` | `-1` | How many times to re-prompt on no response. `-1` means use the system default. |

### Return values

| Value | Meaning |
|-------|---------|
| `str` | One of the strings from `options`, exactly as provided. |
| `None` | No match, no response, or plugin failure. |

Special cases handled before user interaction:
- Empty `options` → `None` immediately.
- Single-element `options` → returns that element immediately (no prompt).

### Basic usage

```python
class MySkill(OVOSSkill):
    def handle_transport_intent(self, message):
        modes = ["bus", "train", "bicycle"]
        choice = self.ask_selection(modes, dialog="which_transport")
        if choice:
            self.speak_dialog("you_chose", {"mode": choice})
```

`locale/en-us/which_transport.dialog`:
```
Which would you prefer?
How would you like to travel?
```

The skill speaks: *"bus, train, or bicycle? Which would you prefer?"*

The user can say:
- `"train"`: fuzzy-matched directly
- `"the second one"` / `"number two"` / `"two"`: position matched
- `"the last one"`: last-word matched
- `"option 3"`: numeric matched (requires `ovos-number-parser`)

### Numeric menu

```python
choice = self.ask_selection(options, numeric=True)
```

Speaks each option as: *"one, bus, two, train, three, bicycle"*. Useful when options are long or ambiguous. The user can then say *"two"* or *"the second one"*.

### Handling None

```python
choice = self.ask_selection(options, dialog="which_one", num_retries=1)
if choice is None:
    self.speak_dialog("could_not_understand")
    return
```

### How it works internally

1. Validates `options` (raises `ValueError` if not a list, returns immediately for 0 or 1 items).
2. Speaks options (as list or numbered menu based on `numeric`).
3. `get_response(dialog=dialog, data=data, num_retries=num_retries)`: speaks optional follow-up dialog, records reply.
4. `_get_selection_engine()`: resolves the plugin name (settings → mycroft.conf → `ovos-option-matcher-fuzzy-plugin`), loads it once, and caches it. Falls back to `FuzzyOptionMatcherPlugin` if loading fails. Sets `engine.config["min_conf"] = min_conf` before calling. `OVOSSkill._get_selection_engine`: `ovos_workshop/skills/ovos.py:1951`
5. `engine.match_option(utterance=resp, options=options, lang=self.lang)`: resolves response to a slot. `OVOSSkill.ask_selection`: `ovos_workshop/skills/ovos.py:1990`
6. If the engine raises or returns `None`, `ask_selection` returns `None`.

---

## Plugin system

Both methods are backed by pluggable agent engines discovered and loaded via [ovos-plugin-manager](https://github.com/OpenVoiceOS/ovos-plugin-manager).

### ask_yesno: YesNoEngine

**Plugin type**: `YesNoEngine` (`opm.agents.yesno`)
**Config key**: `ask_yesno_plugin`
**Default plugin**: `ovos-solver-yes-no-plugin`
**Hard fallback**: `HeuristicYesNoEngine` from `ovos-yes-no-plugin` (used when the named plugin fails to load)

`YesNoEngine` plugins implement:

```python
def yes_or_no(self, question: str, response: str, lang: Optional[str] = None) -> Optional[bool]:
    ...  # True = yes, False = no, None = unclear
```

The `question` argument gives the plugin context about what was asked, enabling smarter inference (e.g. an LLM-backed plugin could use it to resolve ambiguous answers).

**Available plugins**:

| Plugin | Description |
|--------|-------------|
| `ovos-solver-yes-no-plugin` | Rule-based multilingual yes/no classifier (default fallback) |

### ask_selection: OptionMatcherEngine

**Plugin type**: `OptionMatcherEngine` (`opm.agents.option_matcher`)
**Config key**: `ask_selection_plugin`
**Default plugin**: `ovos-option-matcher-fuzzy-plugin` (installed as a dependency of `ovos-workshop`)

`OptionMatcherEngine` plugins implement:

```python
def match_option(self, utterance: str, options: List[str], lang: Optional[str] = None) -> Optional[str]:
    ...  # returns one of options, or None
```

**Available plugins**:

| Plugin | Description |
|--------|-------------|
| `ovos-option-matcher-fuzzy-plugin` | Fuzzy + ordinal/cardinal vocab + numeric fallback. Default. |

---

## Configuration

### Global defaults: `mycroft.conf`

```json
{
  "skills": {
    "ask_yesno_plugin": "ovos-solver-yes-no-plugin",
    "ask_selection_plugin": "ovos-option-matcher-fuzzy-plugin"
  }
}
```

`ask_yesno_plugin` defaults to `ovos-solver-yes-no-plugin`. `ask_selection_plugin` defaults to `ovos-option-matcher-fuzzy-plugin`. Both packages are installed as runtime dependencies of `ovos-workshop`.

### Per-skill override: `settings.json`

Place in the skill's `settings.json` to override for that skill only:

```json
{
  "ask_yesno_plugin": "my-llm-yesno-plugin",
  "ask_selection_plugin": "my-embedding-option-matcher"
}
```

### Plugin config

Pass configuration to the plugin via the same settings block:

```json
{
  "ask_selection_plugin": "ovos-option-matcher-fuzzy-plugin",
  "ask_selection_plugin_config": {
    "min_conf": 0.80
  }
}
```

### Priority order

```
settings.json  >  mycroft.conf skills block  >  built-in default
```

Plugins are loaded lazily on first use and cached per plugin name for the lifetime of the skill instance.

---

## Writing a custom YesNoEngine plugin

```python
# my_yesno/__init__.py
from typing import Optional
from ovos_plugin_manager.templates.agents import YesNoEngine

class MyYesNoPlugin(YesNoEngine):
    def yes_or_no(self, question: str, response: str,
                  lang: Optional[str] = None) -> Optional[bool]:
        r = response.lower()
        if "yes" in r or "sure" in r:
            return True
        if "no" in r or "never" in r:
            return False
        return None  # unclear
```

```toml
# pyproject.toml
[project.entry-points."opm.agents.yesno"]
my-yesno-plugin = "my_yesno:MyYesNoPlugin"
```

Activate for a skill:

```json
{ "ask_yesno_plugin": "my-yesno-plugin" }
```

---

## Writing a custom OptionMatcherEngine plugin

```python
# my_matcher/__init__.py
from typing import List, Optional
from ovos_plugin_manager.templates.agents import OptionMatcherEngine

class MyOptionMatcher(OptionMatcherEngine):
    def match_option(self, utterance: str, options: List[str],
                     lang: Optional[str] = None) -> Optional[str]:
        # example: embedding similarity via a local model
        scores = self._embed_and_score(utterance, options)
        best_idx = max(range(len(scores)), key=lambda i: scores[i])
        if scores[best_idx] >= self.config.get("min_conf", 0.6):
            return options[best_idx]
        return None
```

```toml
# pyproject.toml
[project.entry-points."opm.agents.option_matcher"]
my-option-matcher-plugin = "my_matcher:MyOptionMatcher"
```

Activate system-wide:

```json
{ "skills": { "ask_selection_plugin": "my-option-matcher-plugin" } }
```

---

## Failure behaviour

| Scenario | ask_yesno result | ask_selection result |
|----------|-----------------|---------------------|
| User says nothing (timeout) | `None` | `None` |
| User response unclassifiable | raw transcript string | `None` |
| Plugin fails to load | falls back to `HeuristicYesNoEngine` | falls back to `FuzzyOptionMatcherPlugin` |
| Plugin raises at runtime | falls back to `HeuristicYesNoEngine` | `None` |
| No plugin configured | `ovos-solver-yes-no-plugin` used | `ovos-option-matcher-fuzzy-plugin` used |

`ask_selection` is intentionally strict: any failure returns `None` rather than guessing. Always handle the `None` case in your skill.

---

## See also

- [`ovos-solver-yes-no-plugin`](https://github.com/OpenVoiceOS/ovos-solver-YesNo-plugin): built-in yes/no classifier
- [`ovos-option-matcher-fuzzy-plugin`](https://github.com/OpenVoiceOS/ovos-option-matcher-fuzzy-plugin): default selection plugin, with [full docs](https://github.com/OpenVoiceOS/ovos-option-matcher-fuzzy-plugin/tree/master/docs)
- `OVOSSkill.get_response`: lower-level method used internally by both
- [OPM agent templates](https://github.com/OpenVoiceOS/ovos-plugin-manager/blob/dev/ovos_plugin_manager/templates/agents.py): `YesNoEngine`, `OptionMatcherEngine` base classes

---
[← auto-translatable](auto-translatable.md) · [Home](index.md) · [skill-api →](skill-api.md)
