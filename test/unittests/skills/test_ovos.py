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

    def test_register_adapt_intent_no_self_deprecation_warning(self):
        """OVOSSkill.register_intent (adapt path) is the framework's own
        internal registration path — it must not route through the
        deprecated IntentServiceInterface.register_adapt_intent public shim
        and must not log a deprecation warning for a plain skill-authored
        adapt intent."""
        import warnings
        from ovos_workshop.intents import IntentBuilder

        bus = FakeBus()
        skill = OVOSSkill(bus=bus, skill_id="test_no_dep_warn_skill")
        skill.register_vocabulary("hello world", "HelloWorldKeyword",
                                  lang="en-US")

        def handler(message):
            pass

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            skill.register_intent(
                IntentBuilder("HelloWorldIntent").require("HelloWorldKeyword"),
                handler)
        deprecation_warnings = [w for w in caught
                                if issubclass(w.category, DeprecationWarning)]
        self.assertEqual(deprecation_warnings, [])
        self.assertIn("HelloWorldIntent", skill.intent_service.intent_names)

    def test_register_adapt_intent_spec_emits_keyword_topic(self):
        """A plain adapt intent with cached vocab samples must spec-emit
        ovos.intent.register.keyword (OVOS-INTENT-4 §5) — regression test
        for the vocab-cache/munged-name mismatch."""
        from ovos_spec_tools import SpecMessage
        from ovos_workshop.intents import IntentBuilder

        bus = FakeBus()
        captured = []
        bus.on(str(SpecMessage.INTENT_REGISTER_KEYWORD),
              lambda m: captured.append(m))
        skill = OVOSSkill(bus=bus, skill_id="test_kw_emit_skill")
        skill.register_vocabulary("hello world", "HelloWorldKeyword",
                                  lang="en-US")

        def handler(message):
            pass

        skill.register_intent(
            IntentBuilder("HelloWorldIntent").require("HelloWorldKeyword"),
            handler)
        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0].data["required"],
                         [{"name": "HelloWorldKeyword",
                           "samples": ["hello world"]}])

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

