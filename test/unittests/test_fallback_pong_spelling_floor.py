"""FallbackSkill may only answer the poll in its canonical spelling once the
declared ovos-spec-tools floor can build the legacy wire twin.

OVOS-FALLBACK-1 §6.1 names the poll pair `ovos.fallback.ping` and
`ovos.fallback.pong`. A skill emits the pong, and the core that counts the
answers subscribes to the legacy `ovos.skills.fallback.pong`. Once the skill
emits the canonical spelling, the only thing that reaches an older core is the
legacy twin ovos-bus-client puts on the wire, built from the migration map in
*this* process's ovos-spec-tools. A floor below the release carrying the
FALLBACK-1 renames means no twin: the poll times out, the skill is dropped from
the pool, and nothing appears in the logs.
"""
import ast
import unittest
from importlib.metadata import requires
from pathlib import Path

from packaging.requirements import Requirement
from packaging.version import Version

import ovos_workshop.skills.fallback as fallback

# The first ovos-spec-tools release whose migration map carries the four
# OVOS-FALLBACK-1 renames.
MAP_FLOOR = Version("1.12.0a1")

# The poll pair as OVOS-FALLBACK-1 section 6.1 spells it, written out here
# rather than read from ovos-spec-tools, so the expectation does not come
# from the code under test.
CANONICAL_POLL = {"ovos.fallback.ping", "ovos.fallback.pong"}

# The ovos-spec-tools SpecMessage members that carry the canonical poll pair.
# A switch written as SpecMessage.FALLBACK_PONG instead of a string literal is
# the same switch, and it needs the same floor.
CANONICAL_POLL_MEMBERS = {"FALLBACK_PING": "ovos.fallback.ping",
                          "FALLBACK_PONG": "ovos.fallback.pong"}


def poll_topics() -> set:
    """Every bus topic the fallback skill names: string literals that start
    with "ovos.", and SpecMessage.FALLBACK_PING / FALLBACK_PONG attribute uses
    counted as the canonical topic they carry."""
    tree = ast.parse(Path(fallback.__file__).read_text())
    topics = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) \
                and node.value.startswith("ovos."):
            topics.add(node.value)
        elif isinstance(node, ast.Attribute) and node.attr in CANONICAL_POLL_MEMBERS:
            topics.add(CANONICAL_POLL_MEMBERS[node.attr])
    return topics


def declared_floor() -> Version:
    """The ovos-spec-tools floor from the INSTALLED ovos-workshop metadata,
    not from pyproject.toml. CI installs fresh, so the two agree there. After
    editing the floor locally, reinstall the package before running this
    test, or it still reads the floor from the last install."""
    for raw in requires("ovos-workshop") or []:
        req = Requirement(raw)
        if req.name != "ovos-spec-tools":
            continue
        floors = [Version(s.version) for s in req.specifier if s.operator == ">="]
        if floors:
            return max(floors)
    raise AssertionError("ovos-workshop does not declare ovos-spec-tools")


class TestFallbackPongSpellingFloor(unittest.TestCase):
    def test_canonical_poll_requires_the_mapping_floor(self):
        canonical = poll_topics() & CANONICAL_POLL
        if not canonical:
            self.skipTest("the fallback poll still uses its legacy spelling")
        self.assertGreaterEqual(
            declared_floor(), MAP_FLOOR,
            f"{sorted(canonical)} is used here, so the legacy twin has to be "
            f"built here, which needs ovos-spec-tools>={MAP_FLOOR}")

    def test_the_floor_release_maps_the_poll_pair(self):
        """MAP_FLOOR is a claim about a published release; hold it to it."""
        from ovos_spec_tools import migration_counterpart
        from ovos_spec_tools.version import VERSION_MAJOR, VERSION_MINOR, \
            VERSION_BUILD, VERSION_ALPHA
        installed = Version(f"{VERSION_MAJOR}.{VERSION_MINOR}.{VERSION_BUILD}"
                            + (f"a{VERSION_ALPHA}" if VERSION_ALPHA else ""))
        if installed < MAP_FLOOR:
            self.skipTest(f"installed ovos-spec-tools {installed} predates the floor")
        expected = {"ovos.skills.fallback.ping": "ovos.fallback.ping",
                    "ovos.skills.fallback.pong": "ovos.fallback.pong"}
        for legacy, canonical in expected.items():
            self.assertEqual(migration_counterpart(legacy), canonical, legacy)
