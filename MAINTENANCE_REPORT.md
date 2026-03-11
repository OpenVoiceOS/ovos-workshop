# Maintenance Report — `ovos-workshop`

## [2026-03-11] — Cleanup

### Changes
- Reverted accidental GUI client refactor that introduced dependency on unpublished `ovos-gui-api-client`.
- Restored `GUIInterface` imports from `ovos_bus_client` in `ovos_workshop/app.py`, `ovos_workshop/skills/ovos.py` and `test/unittests/test_abstract_app.py`.
- Restored `IdleDisplaySkill` implementation and related decorators.
- Completed migration to `pyproject.toml` (without `ovos-gui-api-client`).
- Applied Apache 2.0 license headers with "Copyright 2026 OpenVoiceOS" to all files added or modified in this PR.

### AI Transparency Report
- **AI Model**: Gemini 2.0 Flash
- **Actions Taken**: Reverted code changes in `ovos_workshop/` and tests but kept the `pyproject.toml` migration (manually removing the unpublished dependency). Batch updated license headers.
- **Oversight**: Verified that `ovos_bus_client` is used for GUI and unpublished packages are removed. Verified headers in source files.

---

## [2026-03-10] — Comprehensive documentation expansion
...
