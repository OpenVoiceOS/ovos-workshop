# Bus Namespaces

`OVOSSkill` emits every migrated event on exactly ONE topic — the OVOS spec
`ovos.*` topic, sourced from `ovos_spec_tools.SpecMessage`. It does **not**
hand-roll a dual-emit or gate on any config flag.

The legacy `mycroft.*` compatibility is provided **transparently by the bus**:
`MessageBusClient` / `FakeBus` read the legacy↔`ovos.*` rename table
(`ovos_spec_tools.MIGRATION_MAP`) and bridge each spec emit to its legacy
counterpart (and vice versa). So a subscriber on either namespace receives the
event, and producers stay spec-only. The single source of truth for the message
types and their renames is `ovos-spec-tools`.

## Spec conformance

This skill side implements:

- **OVOS-PIPELINE-1 §8** — handler-lifecycle trio. `_on_event_start/_on_event_end/
  _on_event_error` emit `SpecMessage.INTENT_HANDLER_START/.COMPLETE/.ERROR`
  (`ovos.intent.handler.*`) with the §8.2 payload (`skill_id` + `intent_name`).
  The bus bridges them to the legacy `mycroft.skill.handler.*`.
- **OVOS-PIPELINE-1 §9.6** — natural-language response exit point. `speak()`
  emits `SpecMessage.SPEAK` (`ovos.utterance.speak`); the bus bridges to `speak`.
- **OVOS-STOP-1 §4.2/§4.3/§5.3** — stop handling. Skills listen on `ovos.stop`,
  `{skill_id}:stop` and `ovos.stop.ping`, and answer stoppability pings on
  `SpecMessage.STOP_PONG` (`ovos.stop.pong`). The 1:1 legacy renames
  (`mycroft.stop` → `ovos.stop`, `skill.stop.pong` → `ovos.stop.pong`) are bridged
  by the bus; only the per-skill placeholder `{skill_id}.stop.ping` (which the
  broadcast `ovos.stop.ping` replaces and which cannot be a static rename) is
  still subscribed directly for back-compat.

See `ovos_workshop/skills/ovos.py` (`_handle_stop_ack`,
`_on_event_start/_end/_error`, `speak`).
