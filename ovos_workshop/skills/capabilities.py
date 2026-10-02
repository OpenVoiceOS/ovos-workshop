"""Capability derivation for the `ovos.skill.loaded` announcement.

OVOS-INTENT-4 SS8.6 fixes the capability vocabulary a skill can declare:
`fallback`, `common_query`, `converse`. These are read off the skill
instance itself, never guessed from configuration or naming.
"""
from typing import List


def get_skill_capabilities(instance) -> List[str]:
    """
    Capabilities the given skill instance declares, per OVOS-INTENT-4 SS8.6.

    - `fallback`: the instance is a `FallbackSkill`.
    - `common_query`: the instance has a handler registered via the
      `@common_query` decorator (`OVOSSkill._cq_handler`).
    - `converse`: the instance is a `ConversationalSkill`, the only base
      that wires the CONVERSE-1 SS4 surface (`ovos.converse.ping`,
      `<skill_id>.converse.ping`/`.request`). Other classes (e.g. the
      game skills) define a `converse` method of their own without that
      wiring, so a callable-attribute check would announce a capability
      the skill cannot actually be reached on.

    @param instance: the instantiated skill to inspect.
    @return: the capabilities declared by this instance.
    """
    from ovos_workshop.skills.converse import ConversationalSkill
    from ovos_workshop.skills.fallback import FallbackSkill

    capabilities = []
    if isinstance(instance, FallbackSkill):
        capabilities.append("fallback")
    if getattr(instance, "_cq_handler", None) is not None:
        capabilities.append("common_query")
    if isinstance(instance, ConversationalSkill):
        capabilities.append("converse")
    return capabilities
