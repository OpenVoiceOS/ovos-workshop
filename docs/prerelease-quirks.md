# Prerelease quirks

This file lists everything that changed or broke since the last stable
release, `8.0.0`. It is version-stamped and newest first. If you install an
alpha of `ovos-workshop`, read this before you file a bug: the behavior you
are seeing may be documented here already.

This file resets at the next stable release. At that point its contents
become upgrade notes for the `8.0.0 -> next-stable` jump, and a new, empty
quirks log starts.

## 9.6.0a4 — skill teardown (`shutdown` + `default_shutdown`) is re-entrant

`BaseSkill` now guards its whole teardown pair with a lock and a
`_shutdown_done` flag, set only by `default_shutdown()`. `__del__` only
checks the flag, never sets it, before calling the skill-authored
`shutdown()`. This covers both races without breaking the common case:
if `SkillManager.unload_skill()` already ran `skill.shutdown()` then
`default_shutdown()` explicitly, a later GC-triggered `__del__()` sees the
flag set and returns immediately instead of re-running the skill's own
cleanup (closing sockets, unsubscribing callbacks, stopping threads) and
`settings.store()`/`gui.shutdown()`/`event_scheduler.shutdown()` a second
time; if GC alone drops the last reference with no prior explicit unload,
the flag is still unset, so `__del__` runs the full teardown pair exactly
once and `default_shutdown()` sets the flag on its way through.

## 9.5.5a3 — intent registration carries OVOS-CONTEXT-1 gating

`@intent_handler` accepts `requires_context`/`excludes_context` kwargs —
OVOS-CONTEXT-1 §6/§6.1 gating declarations, each entry a bare key string
or a `{"key": ..., "scope": "private"|"shared"}` mapping. They ride the
`ovos.intent.register.template` / legacy `padatious:register_intent`
payloads for `.intent` file handlers, and the `ovos.intent.register.keyword`
/ legacy `register_intent` payloads for `IntentBuilder` (Adapt) handlers,
as additional fields (INTENT-4 §5.3/§5's unknown-field tolerance),
defaulting to an empty list when undeclared. Adapt has no
OVOS-CONTEXT-1-aware matcher, so the declaration currently has no effect
on Adapt's own matching, but per CONTEXT-1 §6 "an engine that does not
implement OVOS-CONTEXT-1 ignores them and matches as if absent" — the
field still reaches the wire rather than being stripped at the producer.
Enforcement is engine-side; workshop only carries the declaration.

## 9.5.0a3 — spec template registration carries slot_blacklist

The `ovos.intent.register.template` emission now includes the
`slot_blacklist` dict, matching the legacy `padatious:register_intent`
payload. It was omitted, so the §4.3 slot-value exclusion feature only
worked through the legacy emit and would have silently died with the
legacy path's planned removal. Engines already read the field.

## 9.5.0a3 — blacklist files expand bare template syntax

`BlacklistFile.load` now enumerates alternation and optional groups written
without a `<vocab>` reference — `(it|this|that)` becomes three entries
instead of one verbatim string that could never match (the blacklist was
silently inert). Any loaded entry still carrying unexpanded template syntax
logs a warning naming the source file.

## 9.5.0a1 (#541)

Every `.entity` file a skill ships is now auto-registered for its locale on
first resource load, with no filtering by whether an `.intent` file
declares a matching slot. Files in subdirectories are registered too.

- Disable via config: `{"skills": {"auto_register_entity_files": false}}`.
- Padatious closed-vocabulary hazard: on `ovos-padatious` <= 2.0.2a1, a
  registered entity can make a previously-unconstrained wildcard slot
  reject inputs it used to accept. Pin `ovos-padatious` >= 2.0.3a1
  alongside this release, or disable the config gate.
- A bare `#` placeholder line (old mycroft-core digit-wildcard convention)
  is dead: `read_resource_file` already strips it as a comment before
  `samples` is built, so it was never a wildcard. It now logs a deprecation
  warning instead of silently doing nothing.

## 9.4.0a1 (#534)

`ConversationalSkill` now answers the converse broadcast poll
(OVOS-CONVERSE-1 §4.2).

## 9.3.14a1 (#542)

Hotfix. The #538 import swap in `converse.py` moved to
`ovos_spec_tools.standardize_lang` but missed the call site inside
`_handle_converse_request`, which kept calling the no-longer-imported
`standardize_lang_tag`. Every live converse request raised `NameError`,
silently swallowed by the handler's own except-clause into a
`{result: False, error: ...}` wire response — converse never actually ran.
Fixed with a regression test that drives the real handler over the bus.

## 9.3.13a2 (#538, #537)

Closed out a completed deprecation-warnings survey: `OVOSSkill.set_context`
and `remove_context` now delegate to a private, non-warning path on
`IntentServiceInterface` instead of tripping their own deprecation warning
on every call from inside the base class. Suites that deliberately exercise
the legacy `register_adapt_*`/`register_padatious_*` facade get scoped
`filterwarnings` so their expected warnings don't pollute the rest of the
run.

## 9.3.13a1 (#535)

`set_context`/`remove_context` now delegate to the session API instead of
racing skill-reply forwards against the legacy `add_context`/
`remove_context` bus topic (finding 29). A registry write for a positive
timeout carries a real `expires_at` timestamp; an immortal entry (no
timeout) carries none.

## 9.3.11a2 - 9.3.12a1

Canonical intent-topic registration moved to `ovos-spec-tools`, with
compat left in place (#500). `register_entity_file` emits the clean entity
name, not the raw filename (#528).

## 9.3.9a1 - 9.3.11a1

`FallbackSkill` is now abstract: a skill without `can_answer` cannot load
(#523). Language matching routed through `ovos-spec-tools` (#512).
Context-only `requires` no longer leaks into the INTENT-4 keyword emit
(#525). `set_context` carries the original context key through so
CONTEXT-1 gating stays reachable (#527).

## 9.3.4a1 - 9.3.8a1

`enable_intent` rebinds the handler after `disable_intent` (#508).
`killable_intent`/`killable_event` no longer leak a thread or bus listener
on natural completion (#513). `OVOSSkill._wait_response` is now bounded so
`get_response` cannot hang forever (#514). A change to silently disable
fallback skills predating `can_answer` was reverted (#515, #517) — see
9.3.9a1 above for the final (abstract-class) approach.

## 9.3.0a1 - 9.3.2a2

Intent dispatch handlers bind to canonical INTENT-4 intent names (#497).
Padacioso floor bumped so dangling `<name>` template refs raise
`MalformedTemplate` instead of silently matching nothing (#493).

## 9.2.10a1 (#431, dual-emit landed 9.3.0a1)

OVOS-INTENT-4 registration topics are emitted dual with the legacy ones.

## 9.2.0a1 - 9.2.9a1

`ovos.utterance.handled` is now gated in converse/fallback so it fires only
when core owns the emit (PIPELINE-1 §9.5, #486). Inline `<voc>` references
are expanded before intents register to the engine, and re-registration is
deduped (#470). `.blacklist` locale resource support added for intents
(#450), with the OVOS-INTENT-2 §4.3 entity/slot blacklist emitted on
registration (#454).

## 9.0.0a1 - 9.0.4a1

Intent layers now gate via intent context instead of enable/disable
(#427). `ovos-padacioso` cap widened `<2.0.0` -> `<3.0.0` (#433).

## 8.1.0a1 - 8.3.0a1

`ovos-bus-client` cap widened `<2.0.0` -> `<3.0.0` (#416). Word-list joining
uses JSON-based euphony rules (#405). New yesno/selection agent plugins
(#390). New spec topic `ovos.utterance.speak` emitted (#425).

## 8.0.1a1 - 8.0.4a4

Locale folder names normalized to canonical BCP-47 form, with lookups and
tests updated to match (#392, #395).
