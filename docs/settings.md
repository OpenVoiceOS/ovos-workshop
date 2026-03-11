# Skill Settings

Settings provide per-skill persistent key-value storage backed by a JSON file.

## Storage Location

```
~/.config/ovos/skills/<skill_id>/settings.json
```

For `OVOSAbstractApplication`:
```
~/.config/ovos/apps/<skill_id>/settings.json
```

## Accessing Settings

`self.settings` is a `JsonStorage` dict-like object. Read and write as a normal dict:

```python
# Read with default
name = self.settings.get("username", "stranger")

# Write
self.settings["username"] = "Alice"

# Persist immediately (normally auto-saved on shutdown)
self.settings.store()
```

Do not replace the whole `self.settings` dict — update individual keys:

```python
# WRONG
self.settings = {"key": "value"}

# CORRECT
self.settings["key"] = "value"
```

## Default Values

Pass defaults as a dict to `super().__init__` or set them as initial values in `__init__`. These are only applied if the key does not already exist in the stored settings:

```python
class MySkill(OVOSSkill):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Prefer setting defaults in settings.json (settingsmeta.json) instead
```

The `__mycroft_skill_firstrun` key is managed automatically to track first-run state.

## Change Callback

Set `self.settings_change_callback` to a callable that will be invoked whenever settings change (either via file change or remote update):

```python
def initialize(self):
    self.settings_change_callback = self.on_settings_changed

def on_settings_changed(self):
    self.log.info("Settings updated!")
    self._apply_new_volume(self.settings.get("volume", 50))
```

## File Watching

Settings changes can arrive two ways:

1. **Bus event** (`ovos.skills.settings_changed`) — emitted by `ovos-core`'s file watcher. This is the primary mechanism in a standard setup.
2. **Local file watcher** — the skill can also watch its own `settings.json` directly. Enabled by setting `monitor_own_settings: true` in the skill's own settings. Useful in isolated setups (e.g. containers) where the skill and core don't share a filesystem.

## Remote Settings

Skills can receive remote settings updates via `mycroft.skills.settings.changed`. Only settings for this skill (keyed by `skill_id`) are applied. After applying remote settings the file watcher is started if not already running.

## Private Settings

Skills also have access to `self.private_settings` (`PrivateSettings`), a separate storage for data that should not be shared or synced. Backed by a JSON file outside the standard settings path.
