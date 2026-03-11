# Maintenance Report — `ovos-workshop`

## 2026-03-11 — CodeRabbit PR #386 review fixes + CI workflow integration

**AI Model**: claude-sonnet-4-6
**Oversight**: Human review pending

### Actions Taken

#### Bug Fixes
- `ovos_workshop/resource_files.py:89` — Narrowed `except Exception` to `except ValueError` in `locate_lang_directories`; `tag_distance` only raises `ValueError` for invalid language codes.
- `ovos_workshop/skills/ovos.py:682` — Added error context to initialization failure log (`LOG.exception` with `{e}`).
- `test/unittests/test_abstract_app.py:26` — Fixed constructor typo `__int__` → `__init__` (class constructor was never called).

#### Test Improvements
- `test/unittests/skills/test_idle_display_skill.py` — Replaced misleading `hasattr(__init__)` check with a proper assertion that `handle_idle` is abstract.
- `test/unittests/skills/test_converse_extended.py` — Tightened `assertIsInstance(dict)` to `assertEqual({})` for `converse_matchers`.
- `test/unittests/skills/test_common_play_extended.py` — Save/restore XDG env vars in `tearDown`; tightened `ocp_cache_dir` assertion with `os.path.basename`; added `initial_count + 1` assertion to `test_register_media_type`.
- `test/unittests/test_decorators_layers_extended.py:73-76` — Added `assertFalse(layers.is_active("nonexistent"))` after `activate_layer` on non-existent layer.
- `test/unittests/skills/test_intent_provider.py:23` — Added actual `DeprecationWarning` assertion using `warnings.catch_warnings`.
- `test/unittests/test_decorators.py` — Removed unnecessary `f`-prefixes from string literals with no interpolation.

#### Documentation Fixes
- `docs/game-skill.md:11` — Added `text` language specifier to fenced code block.
- `FAQ.md:18,32` — Fixed path examples to use `.` instead of `ovos-workshop/` prefix.

#### CI Workflow Fixes
- `.github/workflows/license_tests.yml` — Removed invalid empty `with:` block; added `secrets: inherit`.
- `.github/workflows/build_tests.yml` — Added `dev` to push trigger branches.

#### New CI Workflows Added
- `.github/workflows/test.yml` — Unit tests via shared `build-tests.yml@dev`.
- `.github/workflows/lint.yml` — Ruff linting via shared `lint.yml@dev`.
- `.github/workflows/pip_audit.yml` — Dependency CVE scan via shared `pip-audit.yml@dev`.
- `.github/workflows/repo_health.yml` — Repo hygiene check via shared `repo-health.yml@dev`.
