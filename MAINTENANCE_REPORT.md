# Maintenance Report — `ovos-workshop`

## [2026-03-11] — Cleanup

### Changes
- Reverted accidental GUI client refactor that introduced dependency on unpublished `ovos-gui-api-client`.
- Restored `GUIInterface` imports from `ovos_bus_client`.
- Restored `IdleDisplaySkill` implementation and related decorators.
- Completed migration to `pyproject.toml` (without `ovos-gui-api-client`).

### AI Transparency Report
- **AI Model**: Gemini 2.0 Flash
- **Actions Taken**: Reverted code changes in `ovos_workshop/` but kept the `pyproject.toml` migration (manually removing the unpublished dependency).
- **Oversight**: Verified that `ovos_bus_client` is used for GUI and unpublished packages are removed.

---

## [2026-03-10] — Comprehensive documentation expansion

### Changes
- Created `docs/app.md` — full reference for `OVOSAbstractApplication` with source citations, `_dedicated_bus`, `settings_path`, `default_shutdown`, `get_language_dir`, `clear_intents`, and a minimal code example.
- Created `docs/game-skill.md` — full reference for `OVOSGameSkill` and `ConversationalGameSkill` including all abstract methods, properties (`is_playing`, `is_paused`), `stop_game()`, `calc_intent()`, auto-save behaviour, and a complete example.
...
