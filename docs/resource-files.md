# Resource Files

Skills load localized resources from a structured directory layout. Resources are loaded automatically at startup for every language in `native_langs` (`core_lang` + `secondary_langs`).

## Directory Layout

The recommended layout uses a single `locale/` directory:

```
my-skill/
├── locale/
│   ├── en-US/
│   │   ├── my.dialog        # spoken responses
│   │   ├── my.intent        # padatious intent examples
│   │   ├── my.voc           # adapt vocabulary keywords
│   │   ├── my.entity        # adapt entity examples
│   │   ├── my.rx            # regex patterns for adapt
│   │   └── skill.json       # skill metadata (examples for homescreen)
│   └── es-ES/
│       ├── my.dialog
│       └── my.intent
└── gui/
    └── my_page.qml
```

Legacy skills may use separate `dialog/`, `vocab/`, `regex/` subdirectories: these are still supported.

## Resource Types

| Extension | Type | Description |
|---|---|---|
| `.dialog` | Dialog | Mustache-templated spoken responses (one per line, random selection) |
| `.intent` | Intent | Padatious training examples |
| `.voc` | Vocabulary | Adapt keyword definitions (one keyword per line, first is canonical) |
| `.entity` | Entity | Adapt entity examples |
| `.rx` | Regex | Adapt regex patterns |
| `.list` | List | A flat list resource |
| `.word` | Word | A single word |
| `skill.json` | Metadata | `{"examples": ["...", "..."]}` for homescreen example utterances |

## Dialog Files

Each line in a `.dialog` file is a possible response. One line is chosen randomly when `speak_dialog` is called:

```
# my.dialog
Hello there!
Hi! How are you?
Greetings, {name}!
```

Mustache template variables are filled from the `data` dict:

```python
self.speak_dialog("my", data={"name": "Alice"})
```

## Vocab Files (Adapt)

Each line is a keyword variation. The first word on each line is the canonical form:

```
# hello.voc
hello
hi
hey there
good morning
```

Loaded automatically as `HelloKeyword` (file name without extension, CamelCase from `alphanumeric_skill_id`).

## Intent Files (Padatious)

One example utterance per line. Supports entity slots `{entity}` and alternation `(a | b)`:

```
# my.intent
what is the weather in {location}
(show | tell me) the weather
```

## Entity Files (Padatious)

One example value per line. An `.entity` file fills a `{slot}` named by a `.intent` template:

```
# game.entity
chess
poker
solitaire
```

Every `.entity` file shipped under a skill's locale resources is registered
automatically the first time that language's resources are loaded - there is
no need to call `register_entity_file()` explicitly, and every file is
registered regardless of whether a `.intent` in the skill actually names a
matching slot. This can be turned off in `mycroft.conf`:

```json
{"skills": {"auto_register_entity_files": false}}
```

**Padatious version hazard:** on `ovos-padatious` >= 2.0.3a1, a registered
entity is a *hint* - the matcher still accepts values outside the registered
sample set, just with a slightly different confidence score. On older
matchers (<= 2.0.2a1), registering an entity closes the vocabulary for that
slot - values not in the sample set stop matching entirely. If a deployment
is pinned to an older `ovos-padatious`, either upgrade it alongside this
package or set `auto_register_entity_files` to `false` above to avoid
narrowing slots that previously matched anything.

## Language Fallback

When a resource is not found for the exact `lang`, the skill falls back to dialects of the same language. For example, if `en-AU` is requested but only `en-US` resources exist, `en-US` is used.

## Loading Resources Manually

```python
# Get SkillResources for current lang
resources = self.resources                         # current self.lang
resources = self.load_lang(self.res_dir, "es-ES")  # specific lang

# Find a specific file
path = self.find_resource("my.dialog", "dialog")
path = self.find_resource("hello.mp3", "snd")
```

## SkillResources API

`SkillResources` is returned by `self.resources` and `self.load_lang()`:

```python
# Render a dialog (returns a string, does not speak)
text = self.resources.render_dialog("my.dialog", data={"key": "value"})

# Check if a vocab word matches
matches = self.voc_match("hello there", "hello")  # True

# Load a vocab file into a list
words = self.resources.load_vocabulary_file("my.voc")

# Load a dialog renderer
renderer = self.dialog_renderer
```

## `skill.json` Metadata

Optional file for homescreen integration. Placed at `locale/<lang>/skill.json`:

```json
{
  "name": "My Skill",
  "description": "Does something useful",
  "examples": [
    "what is the weather",
    "tell me the weather in Paris"
  ]
}
```

These examples are emitted to the homescreen as `homescreen.register.examples` on skill startup.

---
[← filesystem](filesystem.md) · [Home](index.md) · [settings →](settings.md)
