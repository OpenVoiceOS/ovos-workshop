# ovos-workshop — Audit Report

_Last updated: 2026-03-10 by claude-sonnet-4-6_

---

## Fixed Issues (2026-03-10)

### CRITICAL — Bug: Wrong signature inspected in OCP handlers
**File**: `ovos_workshop/skills/common_play.py:466,481,492,501`

`__handle_ocp_pause`, `__handle_ocp_resume`, `__handle_ocp_next`, and `__handle_ocp_prev`
all called `signature(self.__playback_handler).parameters` to decide whether to pass
`message=` to the **other** (pause/resume/next/prev) handler.  This caused incorrect
kwargs when those handlers had different signatures than the playback handler — either
omitting `message` when it was expected, or passing it when the handler didn't accept it.

**Fixed**: Each method now inspects the signature of its own handler
(`self.__pause_handler`, `self.__resume_handler`, etc.).

### HIGH — Bare `except:` clauses silently swallowing exceptions
**Files**:
- `ovos_workshop/skills/ovos.py:966` — `_cq_handler` call (now `except Exception`)
- `ovos_workshop/skills/ovos.py:1216` — `intent_file.build()` (now logs warning)
- `ovos_workshop/skills/ovos.py:1450` — `intent_parser.build()` (now logs warning)
- `ovos_workshop/skills/common_query_skill.py:177` — `CQS_match_query_phrase` (now `except Exception`)
- `ovos_workshop/resource_files.py:89` — language tag distance (now `except Exception`)

All fixed to use explicit exception types and/or log the error.

### HIGH — Missing type annotations on public methods
**File**: `ovos_workshop/skills/ovos.py`

Added `-> None` / `-> Optional[str]` / parameter types to:
- `load_regex_files` — added `Optional[str]` param type and `-> None`
- `find_resource` — added `-> Optional[str]`
- `_handle_first_run`, `_check_for_first_run` — added `-> None`
- `on_ready_status`, `on_error_status`, `on_stopping_status`, `on_alive_status`, `on_started_status` — added `-> None`, `e: str`
- `_handle_settings_changed`, `__handle_get_response` — added `message: Message`
- `_handle_killed_wait_response` — added `-> None`

**File**: `ovos_workshop/skills/fallback.py`
- `register_fallback` — changed `callable` → `Callable`, added `-> None`; added `Callable` to imports

---

## Open Issues

### HIGH — Busy-wait polling loops
**File**: `ovos_workshop/skills/ovos.py:1648-1658,1765-1770`

Both `__get_response` and `_wait_response` use `time.sleep(0.1)` spin loops to
wait for results from a background thread.  Using `threading.Event` would eliminate
the polling delay (up to 100 ms per iteration) and reduce unnecessary CPU wake-ups
in time-sensitive voice interactions.

```python
# current pattern (suboptimal)
while not ans:
    time.sleep(0.1)
    ans = self.__validated_responses.get(session.session_id)
```

_Suggested fix_: Replace with `threading.Event.wait(timeout)` where the background
thread calls `event.set()` once it writes the response.

### HIGH — Race condition on `__responses` / `__validated_responses`
**File**: `ovos_workshop/skills/ovos.py:1609-1662`

`__handle_get_response` (bus callback thread) and `_real_wait_response` (daemon
thread) both read/write `self.__responses[session_id]` without a lock.  Under heavy
concurrent load or in environments with many simultaneous sessions, a lost-update
race is possible.

_Suggested fix_: Wrap dict mutations in a `threading.Lock` or replace the plain
`dict` with `collections.defaultdict` guarded by a `threading.Lock`.

### MEDIUM — God class: OVOSSkill is ~2500 lines
**File**: `ovos_workshop/skills/ovos.py:67–2509`

`OVOSSkill` conflates at least 8 distinct responsibilities:
resource loading, settings management, intent registration, message/response
handling, audio playback, dialog rendering, scheduled events, context management.

The class works correctly today, but each new feature compounds the coupling risk.
Long-term, extracting composable mixins (e.g., `SkillSettingsMixin`,
`SkillResponseMixin`) would reduce the blast radius of changes.

### MEDIUM — Unvalidated lazy initialisation of lang_detector / translator
**File**: `ovos_workshop/skills/ovos.py:282-285,294-297`

```python
if not self._lang_detector:
    self._lang_detector = OVOSLangDetectionFactory.create(self.config_core)
return self._lang_detector  # may return None if factory fails
```

If the factory returns `None`, callers receive `None` without an actionable error.
A `RuntimeError` (or at minimum a `LOG.error`) would surface misconfiguration earlier.

### MEDIUM — `callable` type hint used instead of `Callable`
**File**: `ovos_workshop/skills/ovos.py:1225`, `ovos_workshop/decorators/layers.py` multiple

Python's built-in `callable` is not a valid type annotation for `typing`-based
checkers (mypy, pyright).  Replace with `typing.Callable` (optionally parameterised).

### LOW — Inconsistent string formatting
**File**: `ovos_workshop/skills/ovos.py:1333`

`'registering regex string: ' + regex_str` mixes old-style concatenation with the
f-string style used everywhere else.  Change to `f"registering regex string: {regex_str}"`.

### LOW — Magic numbers without named constants
**File**: `ovos_workshop/skills/common_play.py:315`

Hard-coded integer threshold `20` for CSV export should be a named constant
(e.g., `_OCP_CSV_MAX_ENTITIES = 20`) to document intent and enable easy tuning.

### LOW — Variable `re` shadows built-in `re` module
**File**: `ovos_workshop/skills/ovos.py:1334`

A local variable named `re` within `load_regex_files` shadows the standard library
`re` module.  Rename to `regex_str` or `pattern` to avoid confusion.

---

## Structural / Architectural Notes

### Central point of failure
All OVOS skills depend directly on this package.  Any breaking change here has a
workspace-wide blast radius.  Pin to semantic versions in downstream packages.

### `backwards_compat.py` — structurally uncoverable in standard venv
The module provides fallback implementations inside `except ImportError` blocks.
It can only be exercised by uninstalling `ovos_utils.ocp`, making automated coverage
impractical.  Mark with `# pragma: no cover` on the `except` branch.

### `padacioso` dependency optionality
`padacioso` is pulled in unconditionally but is only needed for Padatious-style
intents.  Skills using only Adapt or regex pay the import cost regardless.

---

## Documentation Status
- [x] `docs/index.md`
- [x] `docs/skill-classes.md`
- [x] `docs/ovos-skill.md`
- [x] `docs/decorators.md`
- [x] `docs/intent-layers.md`
- [x] `docs/resource-files.md`
- [x] `docs/settings.md`
- [x] `docs/skill-launcher.md`
- [x] `docs/permissions.md`
- [x] `docs/app.md`
- [x] `docs/game-skill.md`
- [x] `docs/auto-translatable.md`
- [x] `docs/skill-api.md`
- [x] `docs/filesystem.md`
- [x] `QUICK_FACTS.md`
- [x] `FAQ.md`
- [x] `MAINTENANCE_REPORT.md`
- [x] `SUGGESTIONS.md`
