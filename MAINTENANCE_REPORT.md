
# Maintenance Report — `ovos-workshop`

## [2026-03-10] — Comprehensive documentation expansion

### Changes
- Created `docs/app.md` — full reference for `OVOSAbstractApplication` with source citations, `_dedicated_bus`, `settings_path`, `default_shutdown`, `get_language_dir`, `clear_intents`, and a minimal code example.
- Created `docs/game-skill.md` — full reference for `OVOSGameSkill` and `ConversationalGameSkill` including all abstract methods, properties (`is_playing`, `is_paused`), `stop_game()`, `calc_intent()`, auto-save behaviour, and a complete example.
- Created `docs/auto-translatable.md` — full reference for `UniversalSkill`, `UniversalFallback`, and (deprecated) `UniversalCommonQuerySkill` with all public methods and code examples.
- Created `docs/skill-api.md` — full reference for `SkillApi` inter-skill RPC, `@skill_api_method` decorator, bus message protocol, and full server/client example.
- Created `docs/filesystem.md` — full reference for `FileSystemAccess` including XDG path, migration from legacy paths, `open()`, `exists()`, and skill `file_system` property.
- Significantly improved `docs/decorators.md` — added source line citations for every decorator, added `AbortEvent`/`AbortIntent`/`AbortQuestion` class docs, expanded `@killable_intent` abort flow diagram, added all 7 OCP decorators with source line table, added decorator stacking order section.
- Significantly improved `docs/index.md` — added full ASCII class hierarchy with module paths, comprehensive navigation table, key concepts section, and quick-start example.
- Updated `docs/skill-classes.md` — added `OVOSGameSkill`, `ConversationalGameSkill`, `UniversalSkill`, `UniversalFallback`, `ActiveSkill` entries each with source citation, description, and code example. Updated inheritance tree.
- Updated `FAQ.md` — added Q&A for game skills, auto-translation, inter-skill communication, SkillApi, FileSystemAccess, and OVOSAbstractApplication.
- Updated `QUICK_FACTS.md` — added key classes table and documentation index table.

### AI Transparency Report
- **AI Model**: claude-sonnet-4-6
- **Actions Taken**: Wrote 5 new docs files and significantly improved 3 existing files, plus updated FAQ, QUICK_FACTS, and MAINTENANCE_REPORT. All content sourced by reading the actual Python source files; every behavioral claim cites `ClassName.method — file.py:LINE`.
- **Oversight**: Human review required. All line number citations were verified against source files read during this session.

---

## [2026-03-08] — Initial compliance scaffold

### Changes
- Created `QUICK_FACTS.md` with machine-readable package metadata.
- Created `FAQ.md` with common Q&A.
- Created `MAINTENANCE_REPORT.md` (this file) as the change log.
- Created `SUGGESTIONS.md` with initial improvement proposals.
- Created `docs/index.md` as the documentation entry point (if missing).

### Rationale
Establishing the required file set mandated by `AGENTS.md` for all active workspace repositories.

### Verification
- All required files exist at repo root and `docs/` folder.
- No existing content was overwritten.

### AI Transparency Report
- **AI Model**: Claude Sonnet 4.6
- **Actions Taken**: Generated boilerplate compliance scaffold (QUICK_FACTS, FAQ, MAINTENANCE_REPORT, SUGGESTIONS, docs/index).
- **Oversight**: Files are stubs — human review and enrichment required before treating as authoritative.
