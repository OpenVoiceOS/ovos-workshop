# AGENTS.md

Conventions for AI coding agents (internal and community) working in this
repository.

## What this repo is

`ovos-workshop` provides the base classes, decorators, and helpers that
skills and standalone applications are built on within OpenVoiceOS.

That includes the `OVOSSkill` family, resource-file loading (`.intent`,
`.entity`, `.dialog`), intent-registration decorators, and lifecycle
helpers like the killable-event machinery used to abort a running intent
handler mid-execution.

It sits between `ovos-core` (which loads and drives skills through this
API) and individual skill packages (which subclass what's defined here). It
depends on `ovos-bus-client`, `ovos-config`, and `ovos-plugin-manager`.

## Ground rules

- Work on a feature branch. Never push to `dev` or `master` directly.
- Open pull requests against `dev` as **drafts** until CI is green and the
  change is ready for review.
- One commit per PR. Squash before pushing if history accumulates.

- Use conventional commit prefixes (`fix:`, `feat:`, `refactor:`, `docs:`,
  `test:`, `chore:`). Reserve `feat:` for changes a user or downstream
  consumer can actually observe.

- Never hand-edit `ovos_workshop/version.py`. CI computes and bumps the
  version from conventional commit history.

- Every PR description and issue you write or edit carries an AI-authorship
  disclosure at the top, naming the exact model used, and states the text is
  not human-reviewed.

## Dependencies

- Use `uv`, never `pip`, for installing and resolving dependencies.

- Pin floors only, and always allow prereleases: `>=X.Y.Za1`. Some floors in
  `pyproject.toml` are still plain (`ovos-config>=0.0.12`) without an alpha
  suffix. When you bump a floor for a feature, prefer pinning to the alpha
  that first ships it, not a later stable.

- All dependency and metadata declarations live in `pyproject.toml`.
- Never install a dependency from a git URL. Publish an alpha to PyPI and
  depend on that.

- `ovos-yes-no-plugin` and `ovos-option-matcher-fuzzy-plugin` are runtime
  (not test) dependencies. They back `ask_yesno`/`ask_selection` on every
  skill, not just test fixtures.

## Testing

```bash
uv venv .venv
source .venv/bin/activate
uv pip install -e ".[test]"
pytest test/
```

The `test` extra installs `ovos-core` itself plus `ovos-adapt-parser` and
`ovoscope`, because the suite exercises real skill loading and intent
matching end to end, not isolated unit mocks.

A regression test for a bug must be shown to fail against the code before the
fix and pass after it. A test that passes against unfixed code proves
nothing and does not satisfy this gate.

## Docs discipline

Any change that touches observable behavior updates `README.md` and the
relevant file under `docs/` (`ovos-skill.md`, `decorators.md`,
`resource-files.md`, `intent-layers.md`, `skill-interaction.md`,
`skill-launcher.md`, `settings.md`, `permissions.md`, `app.md`,
`game-skill.md`, `auto-translatable.md`) in the same PR.

Also add a version-stamped entry at the top of `docs/prerelease-quirks.md`
describing the change (create the file if it does not exist yet), newest
entry first.

## Repo-specific notes

- `.entity` resource files are auto-registered by `resource_files.py`
  (`ResourceType("entity", ".entity", self.language)`). A skill does not
  need to call anything to load them, dropping a file in `locale/<lang>/`
  is enough. Treat `.entity` values as training hints for the intent
  matcher, not a closed vocabulary the skill enforces at runtime.

- The killable-event decorators (`killable_intent`, `killable_event`, and
  the `AbortEvent`/`AbortIntent`/`AbortQuestion` exceptions) live in
  `ovos_workshop/decorators/killable.py`. The interrupting bus message is
  set by the decorator's `msg` argument.

- Termination on a stop command is controlled by `react_to_stop`, which
  defaults to `True` for `killable_intent` and `False` for `killable_event`.
  Do not assume every killable handler reacts to stop.

  They spawn the handler in a killable daemon thread
  (`ovos_utils.create_killable_daemon`). Changing their signatures or
  default message names is a behavior change for every skill that uses
  `@killable_intent`.

- `ovos-skill-launcher` (defined as a console script in `pyproject.toml`) is
  the entry point that runs a skill standalone outside a full `ovos-core`
  install. Keep it working when changing skill bootstrap logic.

- `test/` (singular) is the one test directory. Do not create a parallel
  `tests/` directory.
