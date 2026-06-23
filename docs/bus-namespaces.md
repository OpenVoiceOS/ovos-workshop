# Bus Namespaces

During the transition to the OVOS message-bus specs, `OVOSSkill` emits each
event in exactly one namespace, selected by the `legacy_namespace` config key
(default `True`):

- `True` — legacy `mycroft.*` topics (e.g. `speak`, `skill.stop.pong`,
  `mycroft.skill.handler.start/.complete/.error`).
- `False` — OVOS spec topics (e.g. `ovos.utterance.speak`, `ovos.stop.pong`,
  `ovos.intent.handler.start/.complete/.error`).

Skills *subscribe* on both namespaces, so a subscriber never sees duplicates:
only one namespace is ever emitted per event.

## Spec conformance

This skill side implements:

- **OVOS-PIPELINE-1 §8** — handler-lifecycle trio. When `legacy_namespace` is
  off, `_on_event_start/_on_event_end/_on_event_error` emit
  `ovos.intent.handler.start/.complete/.error` with the §8.2 payload
  (`skill_id` + `intent_name`).
- **OVOS-PIPELINE-1 §9.6** — natural-language response exit point. `speak()`
  emits `ovos.utterance.speak` instead of the legacy `speak`.
- **OVOS-STOP-1 §4.2/§4.3/§5.3** — stop handling. Skills listen on `ovos.stop`,
  `{skill_id}:stop` and `ovos.stop.ping`, and answer stoppability pings on
  `ovos.stop.pong`.

See `ovos_workshop/skills/ovos.py` (`_legacy_namespace`, `_handle_stop_ack`,
`_on_event_start/_end/_error`, `speak`).
