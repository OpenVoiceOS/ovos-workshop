# Changelog

## [9.2.3a1](https://github.com/OpenVoiceOS/ovos-workshop/tree/9.2.3a1) (2026-07-17)

[Full Changelog](https://github.com/OpenVoiceOS/ovos-workshop/compare/9.2.2a1...9.2.3a1)

**Merged pull requests:**

- fix: bound inline-vocab expansion and dedupe intent re-registration [\#470](https://github.com/OpenVoiceOS/ovos-workshop/pull/470) ([JarbasAl](https://github.com/JarbasAl))

## [9.2.2a1](https://github.com/OpenVoiceOS/ovos-workshop/tree/9.2.2a1) (2026-07-17)

[Full Changelog](https://github.com/OpenVoiceOS/ovos-workshop/compare/9.2.1a1...9.2.2a1)

**Merged pull requests:**

- fix: expand inline \<voc\> refs before registering intents to the engine [\#458](https://github.com/OpenVoiceOS/ovos-workshop/pull/458) ([JarbasAl](https://github.com/JarbasAl))

## [9.2.1a1](https://github.com/OpenVoiceOS/ovos-workshop/tree/9.2.1a1) (2026-07-17)

[Full Changelog](https://github.com/OpenVoiceOS/ovos-workshop/compare/9.2.0a1...9.2.1a1)

**Merged pull requests:**

- fix: skip malformed template lines instead of failing the whole resource [\#466](https://github.com/OpenVoiceOS/ovos-workshop/pull/466) ([JarbasAl](https://github.com/JarbasAl))

## [9.2.0a1](https://github.com/OpenVoiceOS/ovos-workshop/tree/9.2.0a1) (2026-07-03)

[Full Changelog](https://github.com/OpenVoiceOS/ovos-workshop/compare/9.1.1a1...9.2.0a1)

**Merged pull requests:**

- feat: emit OVOS-INTENT-2 §4.3 entity/slot blacklist on registration [\#454](https://github.com/OpenVoiceOS/ovos-workshop/pull/454) ([JarbasAl](https://github.com/JarbasAl))

## [9.1.1a1](https://github.com/OpenVoiceOS/ovos-workshop/tree/9.1.1a1) (2026-07-03)

[Full Changelog](https://github.com/OpenVoiceOS/ovos-workshop/compare/9.1.0a1...9.1.1a1)

**Merged pull requests:**

- fix: resolve inline \<voc\> references when loading .intent/.blacklist [\#455](https://github.com/OpenVoiceOS/ovos-workshop/pull/455) ([JarbasAl](https://github.com/JarbasAl))

## [9.1.0a1](https://github.com/OpenVoiceOS/ovos-workshop/tree/9.1.0a1) (2026-07-02)

[Full Changelog](https://github.com/OpenVoiceOS/ovos-workshop/compare/9.0.4a1...9.1.0a1)

**Merged pull requests:**

- feat: support .blacklist locale resource for intents \(OVOS-INTENT-2\) [\#450](https://github.com/OpenVoiceOS/ovos-workshop/pull/450) ([JarbasAl](https://github.com/JarbasAl))

## [9.0.4a1](https://github.com/OpenVoiceOS/ovos-workshop/tree/9.0.4a1) (2026-07-02)

[Full Changelog](https://github.com/OpenVoiceOS/ovos-workshop/compare/9.0.3a1...9.0.4a1)

## [9.0.3a1](https://github.com/OpenVoiceOS/ovos-workshop/tree/9.0.3a1) (2026-07-02)

[Full Changelog](https://github.com/OpenVoiceOS/ovos-workshop/compare/9.0.2a1...9.0.3a1)

**Merged pull requests:**

- fix: intent-layers e2e + utterance.handled test, bump pins [\#446](https://github.com/OpenVoiceOS/ovos-workshop/pull/446) ([JarbasAl](https://github.com/JarbasAl))

## [9.0.2a1](https://github.com/OpenVoiceOS/ovos-workshop/tree/9.0.2a1) (2026-06-28)

[Full Changelog](https://github.com/OpenVoiceOS/ovos-workshop/compare/9.0.1a5...9.0.2a1)

**Merged pull requests:**

- fix: stop emitting ovos.utterance.handled when ovos-core owns it \(PIPELINE-1 §9.5\) [\#442](https://github.com/OpenVoiceOS/ovos-workshop/pull/442) ([JarbasAl](https://github.com/JarbasAl))

## [9.0.1a5](https://github.com/OpenVoiceOS/ovos-workshop/tree/9.0.1a5) (2026-06-28)

[Full Changelog](https://github.com/OpenVoiceOS/ovos-workshop/compare/9.0.1a4...9.0.1a5)

**Merged pull requests:**

- refactor: delegate handler-lifecycle done-signal to shared HandlerLifecycle util [\#440](https://github.com/OpenVoiceOS/ovos-workshop/pull/440) ([JarbasAl](https://github.com/JarbasAl))

## [9.0.1a4](https://github.com/OpenVoiceOS/ovos-workshop/tree/9.0.1a4) (2026-06-28)

[Full Changelog](https://github.com/OpenVoiceOS/ovos-workshop/compare/9.0.1a3...9.0.1a4)

**Merged pull requests:**

- refactor: use SpecMessage enum for spec topic strings [\#438](https://github.com/OpenVoiceOS/ovos-workshop/pull/438) ([JarbasAl](https://github.com/JarbasAl))

## [9.0.1a3](https://github.com/OpenVoiceOS/ovos-workshop/tree/9.0.1a3) (2026-06-28)

[Full Changelog](https://github.com/OpenVoiceOS/ovos-workshop/compare/9.0.1a2...9.0.1a3)

**Merged pull requests:**

- docs: mark mycroft.skill.handler.\* as internal workshop-\>core sync \(not spec\) [\#436](https://github.com/OpenVoiceOS/ovos-workshop/pull/436) ([JarbasAl](https://github.com/JarbasAl))

## [9.0.1a2](https://github.com/OpenVoiceOS/ovos-workshop/tree/9.0.1a2) (2026-06-27)

[Full Changelog](https://github.com/OpenVoiceOS/ovos-workshop/compare/9.0.1a1...9.0.1a2)

**Merged pull requests:**

- refactor: re-export intent-definition primitives from ovos-spec-tools [\#432](https://github.com/OpenVoiceOS/ovos-workshop/pull/432) ([JarbasAl](https://github.com/JarbasAl))

## [9.0.1a1](https://github.com/OpenVoiceOS/ovos-workshop/tree/9.0.1a1) (2026-06-27)

[Full Changelog](https://github.com/OpenVoiceOS/ovos-workshop/compare/9.0.0a1...9.0.1a1)

**Merged pull requests:**

- fix: allow latest padacioso \(widen cap to \<3.0.0\) [\#433](https://github.com/OpenVoiceOS/ovos-workshop/pull/433) ([JarbasAl](https://github.com/JarbasAl))

## [9.0.0a1](https://github.com/OpenVoiceOS/ovos-workshop/tree/9.0.0a1) (2026-06-26)

[Full Changelog](https://github.com/OpenVoiceOS/ovos-workshop/compare/8.3.0a1...9.0.0a1)

**Breaking changes:**

- refactor: intent layers gate via intent context, not enable/disable [\#427](https://github.com/OpenVoiceOS/ovos-workshop/pull/427) ([JarbasAl](https://github.com/JarbasAl))

## [8.3.0a1](https://github.com/OpenVoiceOS/ovos-workshop/tree/8.3.0a1) (2026-06-25)

[Full Changelog](https://github.com/OpenVoiceOS/ovos-workshop/compare/8.2.1a1...8.3.0a1)

**Merged pull requests:**

- feat: emit OVOS spec topic ovos.utterance.speak [\#425](https://github.com/OpenVoiceOS/ovos-workshop/pull/425) ([JarbasAl](https://github.com/JarbasAl))

## [8.2.1a1](https://github.com/OpenVoiceOS/ovos-workshop/tree/8.2.1a1) (2026-06-06)

[Full Changelog](https://github.com/OpenVoiceOS/ovos-workshop/compare/8.2.0a1...8.2.1a1)

**Closed issues:**

- Problem when running in Italian [\#410](https://github.com/OpenVoiceOS/ovos-workshop/issues/410)

**Merged pull requests:**

- fix\(deps\): allow ovos-bus-client 2.x \(widen cap to \<3.0.0\) [\#416](https://github.com/OpenVoiceOS/ovos-workshop/pull/416) ([JarbasAl](https://github.com/JarbasAl))

## [8.2.0a1](https://github.com/OpenVoiceOS/ovos-workshop/tree/8.2.0a1) (2026-04-09)

[Full Changelog](https://github.com/OpenVoiceOS/ovos-workshop/compare/8.1.0a1...8.2.0a1)

**Merged pull requests:**

- feat: yesno/selection agent plugins [\#390](https://github.com/OpenVoiceOS/ovos-workshop/pull/390) ([JarbasAl](https://github.com/JarbasAl))

## [8.1.0a1](https://github.com/OpenVoiceOS/ovos-workshop/tree/8.1.0a1) (2026-04-08)

[Full Changelog](https://github.com/OpenVoiceOS/ovos-workshop/compare/8.0.4a4...8.1.0a1)

**Merged pull requests:**

- feat: use JSON-based euphony rules for word list joining [\#405](https://github.com/OpenVoiceOS/ovos-workshop/pull/405) ([JarbasAl](https://github.com/JarbasAl))

## [8.0.4a4](https://github.com/OpenVoiceOS/ovos-workshop/tree/8.0.4a4) (2026-04-08)

[Full Changelog](https://github.com/OpenVoiceOS/ovos-workshop/compare/8.0.4a3...8.0.4a4)

## [8.0.4a3](https://github.com/OpenVoiceOS/ovos-workshop/tree/8.0.4a3) (2026-04-08)

[Full Changelog](https://github.com/OpenVoiceOS/ovos-workshop/compare/8.0.4a2...8.0.4a3)

**Merged pull requests:**

- Update actions/setup-python action to v6 [\#402](https://github.com/OpenVoiceOS/ovos-workshop/pull/402) ([renovate[bot]](https://github.com/apps/renovate))
- Update actions/checkout action to v6 [\#401](https://github.com/OpenVoiceOS/ovos-workshop/pull/401) ([renovate[bot]](https://github.com/apps/renovate))
- chore: remove deprecated class flagged for removal in 4.0.0 [\#400](https://github.com/OpenVoiceOS/ovos-workshop/pull/400) ([JarbasAl](https://github.com/JarbasAl))

## [8.0.4a2](https://github.com/OpenVoiceOS/ovos-workshop/tree/8.0.4a2) (2026-04-08)

[Full Changelog](https://github.com/OpenVoiceOS/ovos-workshop/compare/8.0.4a1...8.0.4a2)

## [8.0.4a1](https://github.com/OpenVoiceOS/ovos-workshop/tree/8.0.4a1) (2026-04-08)

[Full Changelog](https://github.com/OpenVoiceOS/ovos-workshop/compare/8.0.3a1...8.0.4a1)

**Merged pull requests:**

- fix: update locale lookups and tests after BCP-47 folder rename [\#395](https://github.com/OpenVoiceOS/ovos-workshop/pull/395) ([JarbasAl](https://github.com/JarbasAl))

## [8.0.3a1](https://github.com/OpenVoiceOS/ovos-workshop/tree/8.0.3a1) (2026-04-08)

[Full Changelog](https://github.com/OpenVoiceOS/ovos-workshop/compare/8.0.2a1...8.0.3a1)

**Merged pull requests:**

- fix: use list.remove\(\) instead of list.pop\(\) in whitelist\_skill [\#394](https://github.com/OpenVoiceOS/ovos-workshop/pull/394) ([JarbasAl](https://github.com/JarbasAl))

## [8.0.2a1](https://github.com/OpenVoiceOS/ovos-workshop/tree/8.0.2a1) (2026-04-03)

[Full Changelog](https://github.com/OpenVoiceOS/ovos-workshop/compare/8.0.1a5...8.0.2a1)

**Merged pull requests:**

- fix\(i18n\): normalize locale folders to canonical BCP-47 [\#392](https://github.com/OpenVoiceOS/ovos-workshop/pull/392) ([JarbasAl](https://github.com/JarbasAl))

## [8.0.1a5](https://github.com/OpenVoiceOS/ovos-workshop/tree/8.0.1a5) (2026-03-11)

[Full Changelog](https://github.com/OpenVoiceOS/ovos-workshop/compare/8.0.1a4...8.0.1a5)

**Merged pull requests:**

- Tests docs automations [\#386](https://github.com/OpenVoiceOS/ovos-workshop/pull/386) ([JarbasAl](https://github.com/JarbasAl))
- Add French workshop locale resources [\#385](https://github.com/OpenVoiceOS/ovos-workshop/pull/385) ([goldyfruit](https://github.com/goldyfruit))

## [8.0.1a4](https://github.com/OpenVoiceOS/ovos-workshop/tree/8.0.1a4) (2025-12-27)

[Full Changelog](https://github.com/OpenVoiceOS/ovos-workshop/compare/8.0.1a3...8.0.1a4)

**Merged pull requests:**

- chore\(deps\): update actions/setup-python action to v6 [\#382](https://github.com/OpenVoiceOS/ovos-workshop/pull/382) ([renovate[bot]](https://github.com/apps/renovate))
- chore\(deps\): update actions/checkout action to v6 [\#379](https://github.com/OpenVoiceOS/ovos-workshop/pull/379) ([renovate[bot]](https://github.com/apps/renovate))

## [8.0.1a3](https://github.com/OpenVoiceOS/ovos-workshop/tree/8.0.1a3) (2025-12-19)

[Full Changelog](https://github.com/OpenVoiceOS/ovos-workshop/compare/8.0.1a2...8.0.1a3)

**Merged pull requests:**

- chore\(deps\): update dependency python to 3.14 [\#378](https://github.com/OpenVoiceOS/ovos-workshop/pull/378) ([renovate[bot]](https://github.com/apps/renovate))

## [8.0.1a2](https://github.com/OpenVoiceOS/ovos-workshop/tree/8.0.1a2) (2025-12-18)

[Full Changelog](https://github.com/OpenVoiceOS/ovos-workshop/compare/8.0.1a1...8.0.1a2)

**Merged pull requests:**

- chore: Configure Renovate [\#377](https://github.com/OpenVoiceOS/ovos-workshop/pull/377) ([renovate[bot]](https://github.com/apps/renovate))

## [8.0.1a1](https://github.com/OpenVoiceOS/ovos-workshop/tree/8.0.1a1) (2025-12-16)

[Full Changelog](https://github.com/OpenVoiceOS/ovos-workshop/compare/8.0.0...8.0.1a1)

**Merged pull requests:**

- fix: standalone skills wait\_for\_core [\#375](https://github.com/OpenVoiceOS/ovos-workshop/pull/375) ([JarbasAl](https://github.com/JarbasAl))



\* *This Changelog was automatically generated by [github_changelog_generator](https://github.com/github-changelog-generator/github-changelog-generator)*
