import unittest

from ovos_bus_client.message import Message
from ovos_utils.fakebus import FakeBus

from ovos_workshop.decorators import common_query, fallback_handler
from ovos_workshop.skill_launcher import PluginSkillLoader
from ovos_workshop.skills.capabilities import get_skill_capabilities
from ovos_workshop.skills.converse import ConversationalSkill
from ovos_workshop.skills.fallback import FallbackSkill
from ovos_workshop.skills.game_skill import ConversationalGameSkill
from ovos_workshop.skills.ovos import OVOSSkill


class _PlainSkill(OVOSSkill):
    pass


class _FallbackSkill(FallbackSkill):
    def can_answer(self, message):
        return False

    @fallback_handler
    def handle_fallback(self, message):
        pass


class _CommonQuerySkill(OVOSSkill):
    @common_query()
    def handle_query(self, phrase, lang):
        return None


class _ConverseSkill(ConversationalSkill):
    def can_converse(self, message):
        return True

    def converse(self, message):
        return False


class _GameSkill(ConversationalGameSkill):
    """Defines `converse()` (game_skill.py) but its MRO never includes
    `ConversationalSkill`, so nothing binds the CONVERSE-1 SS4 surface
    (`ovos.converse.ping`, `<skill_id>.converse.ping`/`.request`) for it."""

    def on_play_game(self):
        pass

    def on_stop_game(self):
        pass

    def on_game_command(self, utterance, lang):
        pass


def _load_and_capture(skill_class, skill_id):
    """Load `skill_class` through PluginSkillLoader and capture every
    `ovos.skill.loaded` message its own bus emits."""
    bus = FakeBus()
    seen = []
    bus.on("ovos.skill.loaded", seen.append)
    loader = PluginSkillLoader(bus, skill_id)
    loader.load(skill_class)
    return loader, seen


class TestSkillCapabilitiesHelper(unittest.TestCase):
    """`get_skill_capabilities` is asserted directly so a wrong list can't
    hide behind "a message was emitted"."""

    def test_plain_skill_has_no_capabilities(self):
        skill = _PlainSkill(bus=FakeBus(), skill_id="plain.test")
        self.assertEqual(get_skill_capabilities(skill), [])

    def test_fallback_skill_declares_fallback(self):
        skill = _FallbackSkill(bus=FakeBus(), skill_id="fallback.test")
        self.assertEqual(get_skill_capabilities(skill), ["fallback"])

    def test_common_query_skill_declares_common_query(self):
        skill = _CommonQuerySkill(bus=FakeBus(), skill_id="cq.test")
        self.assertEqual(get_skill_capabilities(skill), ["common_query"])

    def test_converse_skill_declares_converse(self):
        skill = _ConverseSkill(bus=FakeBus(), skill_id="converse.test")
        self.assertEqual(get_skill_capabilities(skill), ["converse"])

    def test_game_skill_converse_is_not_reachable_so_no_capability(self):
        """`ConversationalGameSkill.converse()` is real code, but nothing
        wires CONVERSE-1 SS4 (`ovos.converse.ping`, `<id>.converse.ping`/
        `.request`) for skills outside `ConversationalSkill`'s MRO, so
        announcing `converse` here would name a capability the skill
        cannot actually be reached on."""
        skill = _GameSkill(skill_voc_filename="game", bus=FakeBus(),
                           skill_id="game.test")
        self.assertNotIsInstance(skill, ConversationalSkill)
        self.assertTrue(callable(getattr(skill, "converse", None)))
        self.assertEqual(get_skill_capabilities(skill), [])


class TestOvosSkillLoadedAnnouncement(unittest.TestCase):
    """End-to-end through the loader: `ovos.skill.loaded` must carry the
    real capabilities of the instance that was loaded, per
    OVOS-INTENT-4 SS8.6, beside the unchanged legacy
    `mycroft.skills.loaded` announcement."""

    def test_fallback_skill_load_announces_fallback_capability(self):
        # loading a skill both readies it (its own announcement) and
        # completes the loader's load-status announcement; every one of
        # them must carry the same, correct capability list.
        loader, seen = _load_and_capture(_FallbackSkill, "fallback.test")
        self.assertTrue(loader.loaded)
        self.assertGreaterEqual(len(seen), 1)
        for message in seen:
            self.assertEqual(message.data["skill_id"], "fallback.test")
            self.assertEqual(message.data["capabilities"], ["fallback"])
            self.assertEqual(message.context["skill_id"], "fallback.test")

    def test_plain_skill_load_announces_no_capabilities(self):
        loader, seen = _load_and_capture(_PlainSkill, "plain.test")
        self.assertGreaterEqual(len(seen), 1)
        for message in seen:
            self.assertEqual(message.data["capabilities"], [])

    def test_converse_skill_load_announces_converse_capability(self):
        loader, seen = _load_and_capture(_ConverseSkill, "converse.test")
        self.assertGreaterEqual(len(seen), 1)
        for message in seen:
            self.assertEqual(message.data["capabilities"], ["converse"])

    def test_legacy_announcement_unchanged(self):
        bus = FakeBus()
        legacy = []
        bus.on("mycroft.skills.loaded", legacy.append)
        loader = PluginSkillLoader(bus, "fallback.test")
        loader.load(_FallbackSkill)
        self.assertEqual(len(legacy), 1)
        self.assertEqual(legacy[0].data,
                         {"path": loader.skill_directory,
                          "id": "fallback.test",
                          "name": loader.instance.name})

    def test_readiness_reannounces_capabilities(self):
        """Cold-start recovery: the readiness callback re-emits
        `ovos.skill.loaded` alongside the registrations it already fires."""
        bus = FakeBus()
        seen = []
        bus.on("ovos.skill.loaded", seen.append)
        skill = _FallbackSkill(bus=bus, skill_id="fallback.ready")
        seen.clear()  # only inspect the explicit re-announcement below
        skill.on_ready_status()
        self.assertEqual(len(seen), 1)
        self.assertEqual(seen[0].data["skill_id"], "fallback.ready")
        self.assertEqual(seen[0].data["capabilities"], ["fallback"])
