# Permissions

**Module:** `ovos_workshop.permissions`

Permission enums control how the converse and fallback systems select which skills may participate.

## ConverseMode

Controls which skills are allowed to participate in converse at all.

```python
from ovos_workshop.permissions import ConverseMode
```

| Value | Meaning |
|---|---|
| `ACCEPT_ALL` | Any skill may converse (default) |
| `WHITELIST` | Only explicitly whitelisted skills may converse |
| `BLACKLIST` | All skills except blacklisted ones may converse |

Configure in `mycroft.conf`:

```json
{
  "skills": {
    "converse": {
      "converse_mode": "accept_all",
      "converse_whitelist": ["skill-id-1"],
      "converse_blacklist": ["skill-id-2"]
    }
  }
}
```

## ConverseActivationMode

Controls when a skill is allowed to add itself to the active skills list (enabling converse).

```python
from ovos_workshop.permissions import ConverseActivationMode
```

| Value | Meaning |
|---|---|
| `ACCEPT_ALL` | Any skill may activate itself (default) |
| `PRIORITY` | Skill may only activate if no higher-priority skill is already active |
| `WHITELIST` | Only explicitly whitelisted skills may self-activate |
| `BLACKLIST` | All skills except blacklisted ones may self-activate |

Configure in `mycroft.conf`:

```json
{
  "skills": {
    "converse": {
      "converse_activation": "accept_all",
      "converse_activation_whitelist": [],
      "converse_activation_blacklist": []
    }
  }
}
```

## FallbackMode

Controls which skills may register as fallback handlers.

```python
from ovos_workshop.permissions import FallbackMode
```

| Value | Meaning |
|---|---|
| `ACCEPT_ALL` | Any `FallbackSkill` may handle utterances (default) |
| `WHITELIST` | Only explicitly whitelisted fallback skills may respond |
| `BLACKLIST` | All fallback skills except blacklisted ones may respond |

Configure in `mycroft.conf`:

```json
{
  "skills": {
    "fallbacks": {
      "fallback_mode": "accept_all",
      "fallback_whitelist": [],
      "fallback_blacklist": []
    }
  }
}
```

## Utility Functions

```python
from ovos_workshop.permissions import blacklist_skill, whitelist_skill

# Add a skill to the global blacklist in mycroft.conf
blacklist_skill("my-unwanted-skill-id")

# Remove from the blacklist
whitelist_skill("my-unwanted-skill-id")
```

These functions directly modify `mycroft.conf` and take effect on the next skill manager reload.

---
[← skill-launcher](skill-launcher.md) · [Home](index.md)
