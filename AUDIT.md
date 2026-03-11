
# ovos-workshop — Audit Report

## Documentation Status
- [ ] AGENTS.md Header Format
- [ ] QUICK_FACTS.md (Moved from docs/)
- [ ] FAQ.md (Moved from docs/)
- [ ] MAINTENANCE_REPORT.md
- [x] AUDIT.md
- [ ] SUGGESTIONS.md
- [x] docs/index.md

## Technical Debt & Issues
- **Minimal Root Documentation**: The `README.md` is extremely sparse, delegating all information to `docs/`.
- **High Coupling**: Central point of failure for all OVOS skills; any change here has a massive blast radius.
- **Dependency on padacioso**: Includes `padacioso` for intent parsing, which might be redundant if the user only uses Adapt or Padatious.

## Next Steps
- Expand the root `README.md` to include a high-level overview of skill base classes.
- Create `QUICK_FACTS.md` and `FAQ.md` specifically for skill developers.
- Add `MAINTENANCE_REPORT.md` to track the evolution of skill API versions.
