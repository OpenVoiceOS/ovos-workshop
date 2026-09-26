# FileSystemAccess: Sandboxed Skill File I/O

`FileSystemAccess` provides each skill with an isolated, XDG-compliant directory for persistent file storage. It prevents skills from accidentally writing to arbitrary locations and handles migration from legacy Mycroft paths.

**Source:** `ovos_workshop/filesystem.py`

---

## Storage Path

`FileSystemAccess.__init_path` is defined in `ovos_workshop/filesystem.py:34`.
Files are stored under:

```
~/.local/share/ovos/filesystem/<skill_id>/
```

The exact base is determined by `get_xdg_data_save_path()` and `get_xdg_base()` from `ovos-config`. On a default installation this resolves to `~/.local/share/ovos/filesystem/`.

The directory is created automatically if it does not exist.

---

## Migration from Old Paths

`FileSystemAccess.__init_path` is defined in `ovos_workshop/filesystem.py:43`.
If a directory exists at the legacy Mycroft location (`~/.mycroft/<skill_id>`) but the XDG path does not yet exist, the directory is automatically **moved** to the new location:

```python
old_path = expanduser(f'~/.{get_xdg_base()}/{path}')
xdg_path = expanduser(f'{get_xdg_data_save_path()}/filesystem/{path}')
if isdir(old_path) and not isdir(xdg_path):
    shutil.move(old_path, xdg_path)
```

A deprecation warning is logged during this migration.

---

## Constructor

```python
class FileSystemAccess:
    def __init__(self, path: str): ...
```

`FileSystemAccess.__init__` is defined in `ovos_workshop/filesystem.py:26`.
| Parameter | Description |
|---|---|
| `path` | Base name for the skill's directory (typically the `skill_id`). Must be a non-empty string. |

Raises `ValueError` if `path` is empty or not a string.

After construction, `self.path` holds the absolute path to the skill's storage directory.

---

## Methods

### `open(filename, mode)`

`FileSystemAccess.open` is defined in `ovos_workshop/filesystem.py:54`.
Open a file inside the skill's sandboxed directory. Equivalent to `open(skill_dir / filename, mode)`.

```python
def open(self, filename: str, mode: str) -> TextIO:
```

| Parameter | Description |
|---|---|
| `filename` | Filename relative to the skill's storage directory. |
| `mode` | File open mode (e.g. `"r"`, `"w"`, `"rb"`, `"a"`). |

Returns a file object.

### `exists(filename)`

`FileSystemAccess.exists` is defined in `ovos_workshop/filesystem.py:64`.
Check whether a file exists inside the skill's sandboxed directory.

```python
def exists(self, filename: str) -> bool:
```

Returns `True` if the file exists, `False` otherwise.

---

## `skill.file_system` Property

`OVOSSkill` (and by extension every skill and `OVOSAbstractApplication`) exposes a `file_system` property that returns a `FileSystemAccess` instance pre-configured with the skill's `skill_id`. You do not need to construct `FileSystemAccess` manually in skill code.

```python
# Inside a skill method:
with self.file_system.open("data.json", "w") as f:
    import json
    json.dump({"key": "value"}, f)
```

---

## Code Example

```python
import json
from ovos_workshop.skills.ovos import OVOSSkill
from ovos_workshop.decorators import intent_handler


class HighScoreSkill(OVOSSkill):
    """Skill that persists a high score to disk."""

    SCORES_FILE = "highscores.json"

    def initialize(self):
        self._scores = self._load_scores()

    def _load_scores(self) -> dict:
        if not self.file_system.exists(self.SCORES_FILE):
            return {}
        with self.file_system.open(self.SCORES_FILE, "r") as f:
            return json.load(f)

    def _save_scores(self):
        with self.file_system.open(self.SCORES_FILE, "w") as f:
            json.dump(self._scores, f, indent=2)

    @intent_handler("get_high_score.intent")
    def handle_get_score(self, message):
        player = message.data.get("player", "anonymous")
        score = self._scores.get(player, 0)
        self.speak(f"{player} has a high score of {score}.")

    @intent_handler("set_high_score.intent")
    def handle_set_score(self, message):
        player = message.data.get("player", "anonymous")
        score = int(message.data.get("score", 0))
        self._scores[player] = max(self._scores.get(player, 0), score)
        self._save_scores()
        self.speak(f"High score updated for {player}.")
```

Using `FileSystemAccess` directly (outside a skill):

```python
from ovos_workshop.filesystem import FileSystemAccess

fs = FileSystemAccess("my-app.author")
# Files stored at ~/.local/share/ovos/filesystem/my-app.author/

if not fs.exists("config.json"):
    with fs.open("config.json", "w") as f:
        import json
        json.dump({"initialized": True}, f)
```

---
[← skill-api](skill-api.md) · [Home](index.md) · [resource-files →](resource-files.md)
