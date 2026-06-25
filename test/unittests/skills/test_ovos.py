import unittest

from ovos_utils.process_utils import RuntimeRequirements
from ovos_utils.fakebus import FakeBus
from ovos_utils import classproperty
from ovos_workshop.decorators.layers import IntentLayers
from ovos_workshop.resource_files import SkillResources

from ovos_workshop.skills.ovos import OVOSSkill


class OfflineSkill(OVOSSkill):
    @classproperty
    def runtime_requirements(self):
        return RuntimeRequirements(internet_before_load=False,
                                   network_before_load=False,
                                   requires_internet=False,
                                   requires_network=False,
                                   no_internet_fallback=True,
                                   no_network_fallback=True)


class LANSkill(OVOSSkill):
    @classproperty
    def runtime_requirements(self):
        scans_on_init = True
        return RuntimeRequirements(internet_before_load=False,
                                   network_before_load=scans_on_init,
                                   requires_internet=False,
                                   requires_network=True,
                                   no_internet_fallback=True,
                                   no_network_fallback=False)


class MockSkill(OVOSSkill):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


class TestOVOSSkill(unittest.TestCase):
    bus = FakeBus()
    skill = OVOSSkill(bus=bus, skill_id="test_ovos_skill")

    def test_00_skill_init(self):
        from ovos_bus_client.apis.ocp import OCPInterface
        self.assertIsInstance(self.skill.private_settings, dict)
        self.assertIsInstance(self.skill._threads, list)
        self.assertIsInstance(self.skill.intent_layers, IntentLayers)
        self.assertIsInstance(self.skill.audio_service, OCPInterface)
        self.assertTrue(self.skill.is_fully_initialized)
        self.assertFalse(self.skill._stop_is_implemented)
        self.assertIsInstance(self.skill.core_lang, str)
        self.assertIsInstance(self.skill.secondary_langs, list)
        self.assertIsInstance(self.skill.native_langs, list)
        self.assertIsInstance(self.skill.alphanumeric_skill_id, str)
        self.assertIsInstance(self.skill.resources, SkillResources)

    def test_activate(self):
        # TODO
        pass

    def test_deactivate(self):
        # TODO
        pass

    def test_play_audio(self):
        # TODO
        pass

    def test_load_lang(self):
        # TODO
        pass

    def test_voc_match(self):
        # TODO
        pass

    def test_voc_list(self):
        # TODO
        pass

    def test_remove_voc(self):
        # TODO
        pass

    def test_register_decorated(self):
        # TODO
        pass

    def test_register_intent_layer(self):
        # TODO
        pass

    def test_send_stop_signal(self):
        # TODO
        pass

    def test_bus_setter(self):
        bus = FakeBus()
        skill = MockSkill()
        skill._startup(bus)
        self.assertEqual(skill.bus, bus)
        new_bus = FakeBus()
        skill.bus = new_bus
        self.assertEqual(skill.bus, new_bus)
        with self.assertRaises(TypeError):
            skill.bus = None

    def test_runtime_requirements(self):
        self.assertEqual(OfflineSkill.runtime_requirements,
                         RuntimeRequirements(internet_before_load=False,
                                             network_before_load=False,
                                             requires_internet=False,
                                             requires_network=False,
                                             no_internet_fallback=True,
                                             no_network_fallback=True)
                         )
        self.assertEqual(LANSkill.runtime_requirements,
                         RuntimeRequirements(internet_before_load=False,
                                             network_before_load=True,
                                             requires_internet=False,
                                             requires_network=True,
                                             no_internet_fallback=True,
                                             no_network_fallback=False)
                         )
        self.assertEqual(OVOSSkill.runtime_requirements,
                         RuntimeRequirements())

    def test_class_inheritance(self):
        from ovos_workshop.skills.ovos import OVOSSkill
        from ovos_workshop.app import OVOSAbstractApplication

        skill = MockSkill()
        self.assertIsInstance(skill, OVOSSkill)
        self.assertNotIsInstance(skill, OVOSAbstractApplication)


class TestSpeakNamespaceMigration(unittest.TestCase):
    """speak -> ovos.utterance.speak bus-namespace migration (dual-emit)."""

    def setUp(self):
        self.bus = FakeBus()
        self.skill = OVOSSkill(bus=self.bus, skill_id="test_speak_ns")
        self.emitted = []
        # FakeBus dispatches by exact msg_type, so subscribe to both topics
        self.bus.on("speak", lambda m: self.emitted.append(m))
        self.bus.on("ovos.utterance.speak",
                    lambda m: self.emitted.append(m))

    def _types(self):
        return [m.msg_type for m in self.emitted]

    def test_dual_emit_when_legacy_namespace(self):
        from unittest.mock import patch
        cfg = {"legacy_namespace": True}
        with patch("ovos_workshop.skills.ovos.Configuration",
                   return_value=cfg):
            self.skill.speak("hello world")
        # both the legacy and the new topic are emitted
        self.assertIn("speak", self._types())
        self.assertIn("ovos.utterance.speak", self._types())
        self.assertEqual(len(self.emitted), 2)
        # identical payload on both, all fields preserved
        for m in self.emitted:
            self.assertEqual(m.data["utterance"], "hello world")
            self.assertIn("expect_response", m.data)
            self.assertIn("meta", m.data)
            self.assertIn("lang", m.data)
            self.assertEqual(m.data["meta"]["skill"], "test_speak_ns")
            # context preserved on both emissions
            self.assertEqual(m.context.get("skill_id"), "test_speak_ns")

    def test_only_new_topic_when_legacy_disabled(self):
        from unittest.mock import patch
        cfg = {"legacy_namespace": False}
        with patch("ovos_workshop.skills.ovos.Configuration",
                   return_value=cfg):
            self.skill.speak("goodbye", expect_response=True)
        self.assertEqual(self._types(), ["ovos.utterance.speak"])
        m = self.emitted[0]
        self.assertEqual(m.data["utterance"], "goodbye")
        # expect_response carried on the new topic too
        self.assertTrue(m.data["expect_response"])

    def test_default_is_dual_emit(self):
        # no legacy_namespace key -> defaults to True (dual-emit during migration)
        from unittest.mock import patch
        with patch("ovos_workshop.skills.ovos.Configuration",
                   return_value={}):
            self.skill.speak("default behaviour")
        self.assertIn("speak", self._types())
        self.assertIn("ovos.utterance.speak", self._types())

