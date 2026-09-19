
# Quick Facts — `ovos-workshop`

frameworks, templates and patches for the OpenVoiceOS universe

| Feature | Details |
|---------|---------|
| Package Name | `ovos-workshop` |
| Version | `8.0.0` |
| License | apache-2.0 |
| Repository | [https://github.com/OpenVoiceOS/OVOS-workshop](https://github.com/OpenVoiceOS/OVOS-workshop) |
| Python Support | >=3.9 |

## Entry Points

### Scripts
- `ovos-skill-launcher`: `ovos_workshop.skill_launcher:_launch_script`

## Key Classes

| Class | Module | Description |
|---|---|---|
| `OVOSSkill` | `ovos_workshop.skills.ovos` | Universal base class for all skills |
| `ConversationalSkill` | `ovos_workshop.skills.converse` | Adds converse loop support |
| `ActiveSkill` | `ovos_workshop.skills.active` | Always-active converse skill |
| `FallbackSkill` | `ovos_workshop.skills.fallback` | Handles unmatched utterances |
| `CommonQuerySkill` | `ovos_workshop.skills.common_query_skill` | Question/answer pipeline |
| `OVOSCommonPlaybackSkill` | `ovos_workshop.skills.common_play` | OCP media playback |
| `OVOSGameSkill` | `ovos_workshop.skills.game_skill` | OCP-integrated game loop |
| `ConversationalGameSkill` | `ovos_workshop.skills.game_skill` | Game skill with converse loop and auto-save |
| `UniversalSkill` | `ovos_workshop.skills.auto_translatable` | Auto-translates I/O to/from internal language |
| `UniversalFallback` | `ovos_workshop.skills.auto_translatable` | Auto-translating fallback skill |
| `OVOSAbstractApplication` | `ovos_workshop.app` | Skill-like app without intent service |
| `FileSystemAccess` | `ovos_workshop.filesystem` | Sandboxed XDG-compliant file storage |
| `SkillApi` | `ovos_workshop.skills.api` | Inter-skill RPC over MessageBus |
| `IntentLayers` | `ovos_workshop.decorators.layers` | Runtime enable/disable of intent groups |

## Documentation

| File | Description |
|---|---|
| `docs/index.md` | Overview, class hierarchy, navigation table, quick-start |
| `docs/skill-classes.md` | Full class reference with source citations |
| `docs/ovos-skill.md` | `OVOSSkill` base class detail |
| `docs/decorators.md` | All decorators with source citations |
| `docs/app.md` | `OVOSAbstractApplication` reference |
| `docs/game-skill.md` | `OVOSGameSkill` and `ConversationalGameSkill` reference |
| `docs/auto-translatable.md` | `UniversalSkill` and `UniversalFallback` reference |
| `docs/skill-api.md` | `SkillApi` inter-skill RPC reference |
| `docs/filesystem.md` | `FileSystemAccess` reference |
| `docs/resource-files.md` | Locale and dialog resource files |
| `docs/settings.md` | Skill settings persistence and change callbacks |
| `docs/intent-layers.md` | Intent layer runtime switching |
| `docs/skill-launcher.md` | `SkillLoader` and standalone mode |
| `docs/permissions.md` | Converse and fallback permission modes |
