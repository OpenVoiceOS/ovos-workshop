import json
import os
import shutil
import unittest

from logging import Logger
from threading import Event, Thread
from time import time
from unittest.mock import Mock
from os.path import join, dirname, isdir
from ovos_workshop.skills.ovos import OVOSSkill

from ovos_utils.fakebus import FakeBus


class TestOVOSSkill(unittest.TestCase):
    test_config_path = join(dirname(__file__), "temp_config")
    os.environ["XDG_CONFIG_HOME"] = test_config_path
    bus = FakeBus()
    skill_id = "test_base_skill"
    skill = OVOSSkill(bus=bus, skill_id=skill_id)

    @classmethod
    def tearDownClass(cls) -> None:
        os.environ.pop("XDG_CONFIG_HOME")
        shutil.rmtree(cls.test_config_path)

    def test_00_skill_init(self):
        from ovos_workshop.skills.ovos import SkillGUI
        from ovos_bus_client.apis.events import EventSchedulerInterface
        from ovos_utils.events import EventContainer
        from ovos_workshop.intents import IntentServiceInterface
        from ovos_utils.process_utils import RuntimeRequirements
        from ovos_bus_client.apis.enclosure import EnclosureAPI
        from ovos_workshop.filesystem import FileSystemAccess
        from ovos_workshop.resource_files import SkillResources

        self.assertIsInstance(self.skill.log, Logger)
        self.assertEqual(self.skill.name, self.skill.__class__.__name__)
        self.assertEqual(self.skill.skill_id, self.skill_id)
        self.assertTrue(isdir(self.skill.root_dir))
        self.assertEqual(self.skill.res_dir, self.skill.root_dir)
        self.assertIsInstance(self.skill.gui, SkillGUI)
        self.assertIsInstance(self.skill.config_core, dict)
        self.assertIsNone(self.skill.settings_change_callback)
        self.assertTrue(self.skill.reload_skill)
        self.assertIsInstance(self.skill.events, EventContainer)
        self.assertEqual(self.skill.events.bus, self.bus)
        self.assertIsInstance(self.skill.event_scheduler,
                              EventSchedulerInterface)
        self.assertIsInstance(self.skill.intent_service, IntentServiceInterface)

        self.assertIsInstance(self.skill.runtime_requirements,
                              RuntimeRequirements)
        self.assertIsInstance(self.skill.voc_match_cache, dict)
        self.assertTrue(self.skill.is_fully_initialized)
        self.assertTrue(isdir(dirname(self.skill.settings_path)))
        self.assertIsInstance(self.skill.settings, dict)
        self.assertIsNone(self.skill.dialog_renderer)
        self.assertIsInstance(self.skill.enclosure, EnclosureAPI)
        self.assertIsInstance(self.skill.file_system, FileSystemAccess)
        self.assertTrue(isdir(self.skill.file_system.path))
        self.assertEqual(self.skill.bus, self.bus)
        self.assertIsInstance(self.skill.location, dict)
        self.assertIsInstance(self.skill.location_pretty, str)
        self.assertIsInstance(self.skill.location_timezone, str)
        self.assertIsInstance(self.skill.lang, str)
        self.assertEqual(len(self.skill.lang.split('-')), 2)
        self.assertEqual(self.skill.core_lang, self.skill.lang)
        self.assertIsInstance(self.skill.secondary_langs, list)
        self.assertIsInstance(self.skill.native_langs, list)
        self.assertIn(self.skill.core_lang, self.skill.native_langs)
        self.assertIsInstance(self.skill.alphanumeric_skill_id, str)
        self.assertIsInstance(self.skill.resources, SkillResources)
        self.assertEqual(self.skill.resources.language, self.skill.lang)
        self.assertFalse(self.skill._stop_is_implemented)

    def test_handle_first_run(self):
        # TODO
        pass

    def test_check_for_first_run(self):
        # TODO
        pass

    def test_startup(self):
        # TODO
        pass

    def test_init_settings(self):
        # Test initial settings defined and not fully initialized
        test_settings = {"init": True}
        self.skill._initial_settings = test_settings
        self.skill._settings["init"] = False
        self.skill._settings["test"] = "value"
        self.skill._init_event.clear()
        self.skill._init_settings()
        self.assertEqual(dict(self.skill.settings),
                         {**test_settings,
                          **{"__mycroft_skill_firstrun": False}})
        self.assertEqual(dict(self.skill._initial_settings),
                         dict(self.skill.settings))

        # Test settings changed during init
        stop_event = Event()
        setting_event = Event()

        def _update_skill_settings():
            while not stop_event.is_set():
                self.skill.settings["test_val"] = time()
                setting_event.set()

        # Test this a few times since this handles a race condition
        for i in range(32):
            # Reset to pre-initialized state
            self.skill._init_event.clear()
            self.skill._settings = None
            setting_event.clear()
            stop_event.clear()
            thread = Thread(target=_update_skill_settings, daemon=True)
            thread.start()
            setting_event.wait()  # settings have some value
            self.assertIsNotNone(self.skill._initial_settings["test_val"],
                                 f"run {i}")
            self.skill._init_settings()
            self.assertIsNotNone(self.skill.settings["test_val"], f"run {i}")
            self.assertIsNotNone(self.skill._initial_settings["test_val"],
                                 f"run {i}")
            setting_event.clear()
            setting_event.wait()  # settings updated since init
            stop_time = time()
            stop_event.set()
            thread.join()
            self.assertAlmostEqual(self.skill.settings["test_val"], stop_time,
                                    0, f"run {i}")
            self.assertNotEqual(self.skill.settings["test_val"],
                                self.skill._initial_settings["test_val"],
                                f"run {i}")

    def test_init_skill_gui(self):
        # TODO
        pass

    def test_init_settings_manager(self):
        # TODO
        pass

    def test_start_filewatcher(self):
        test_skill_id = "test_settingschanged.skill"
        test_skill = OVOSSkill(bus=self.bus, skill_id=test_skill_id)
        settings_changed = Event()
        on_file_change = Mock(side_effect=lambda x: settings_changed.set())
        test_skill._handle_settings_file_change = on_file_change
        test_skill._settings_watchdog = None
        test_skill._start_filewatcher()
        self.assertIsNotNone(test_skill._settings_watchdog)
        skill_settings = test_skill.settings
        skill_settings["changed_on_disk"] = True
        with open(test_skill.settings.path, 'w') as f:
            json.dump(skill_settings, f, indent=2)

        self.assertTrue(settings_changed.wait(5))
        on_file_change.assert_called_once_with(test_skill.settings.path)

    def test_upload_settings(self):
        # TODO
        pass

    def test_handle_settings_file_change(self):
        settings_file = self.skill.settings.path

        # Handle change with callback
        self.skill.settings_change_callback = Mock()
        self.skill._handle_settings_file_change(settings_file)
        self.skill.settings_change_callback.assert_called_once()

        # Handle non-settings file change
        self.skill._handle_settings_file_change(join(dirname(settings_file),
                                                     "test.file"))
        self.skill.settings_change_callback.assert_called_once()


    def test_load_lang(self):
        # TODO
        pass

    def test_bind(self):
        # TODO
        pass

    def test_register_public_api(self):
        # TODO
        pass

    def test_register_system_event_handlers(self):
        # TODO
        pass

    def test_handle_settings_change(self):
        # TODO
        pass

    def test_detach(self):
        # TODO
        pass

    def test_send_public_api(self):
        # TODO
        pass

    def test_get_intro_message(self):
        self.assertIsInstance(self.skill.get_intro_message(), str)
        self.assertFalse(self.skill.get_intro_message())

    # TODO port get_response methods per #69

    def test_ask_yesno(self):
        # TODO
        pass

    def test_ask_selection(self):
        # TODO
        pass

    def test_voc_list(self):
        # TODO
        pass

    def test_voc_match(self):
        # TODO
        pass

    def test_report_metric(self):
        # TODO
        pass

    def test_send_email(self):
        # TODO
        pass

    def test_handle_collect_resting(self):
        # TODO
        pass

    def test_register_resting_screen(self):
        # TODO
        pass

    def test_register_decorated(self):
        # TODO
        pass

    def test_find_resource(self):
        # TODO
        pass

    def test_on_event_start(self):
        # TODO
        pass

    def test_on_event_end(self):
        # TODO
        pass

    def test_on_event_error(self):
        # TODO
        pass

    def test_add_event(self):
        # TODO
        pass

    def test_remove_event(self):
        # TODO
        pass

    def test_register_adapt_intent(self):
        # TODO
        pass

    def test_register_intent(self):
        # TODO
        pass

    def test_register_intent_file(self):
        skill = OVOSSkill(bus=self.bus, skill_id=self.skill_id)
        skill._lang_resources = dict()
        skill.intent_service = Mock()
        skill.res_dir = join(dirname(__file__), "test_locale")
        en_intent_file = join(skill.res_dir, "locale", "en-us", "time.intent")
        uk_intent_file = join(skill.res_dir, "locale", "uk-ua", "time.intent")

        # No secondary languages
        skill.config_core["lang"] = "en-US"
        skill.config_core["secondary_langs"] = []
        skill.register_intent_file("time.intent", Mock(__name__="test"))
        skill.intent_service.register_padatious_intent.assert_called_once_with(
            f"{skill.skill_id}:time.intent", en_intent_file, "en-US", string_blacklist=[])

        # With secondary language
        skill.intent_service.register_padatious_intent.reset_mock()
        skill.config_core["secondary_langs"] = ["en-US", "uk-UA"]
        skill.register_intent_file("time.intent", Mock(__name__="test"))
        self.assertEqual(
            skill.intent_service.register_padatious_intent.call_count, 2)
        skill.intent_service.register_padatious_intent.assert_any_call(
            f"{skill.skill_id}:time.intent", en_intent_file, "en-US", string_blacklist=[])
        skill.intent_service.register_padatious_intent.assert_any_call(
            f"{skill.skill_id}:time.intent", uk_intent_file, "uk-UA", string_blacklist=[])

    def test_register_entity_file(self):
        skill = OVOSSkill(bus=self.bus, skill_id=self.skill_id)
        skill._lang_resources = dict()
        skill.intent_service = Mock()
        skill.res_dir = join(dirname(__file__), "test_locale")
        en_file = join(skill.res_dir, "locale", "en-us", "dow.entity")
        uk_file = join(skill.res_dir, "locale", "uk-ua", "dow.entity")

        # No secondary languages
        skill.config_core["lang"] = "en-US"
        skill.config_core["secondary_langs"] = []
        skill.register_entity_file("dow")
        skill.intent_service.register_padatious_entity.assert_called_once_with(
            f"{skill.skill_id}:dow_d446b2a6e46e7d94cdf7787e21050ff9",
            en_file, "en-US")

        # With secondary language
        skill.intent_service.register_padatious_entity.reset_mock()
        skill.config_core["secondary_langs"] = ["en-US", "uk-ua"]
        skill.register_entity_file("dow")
        self.assertEqual(
            skill.intent_service.register_padatious_entity.call_count, 2)
        skill.intent_service.register_padatious_entity.assert_any_call(
            f"{skill.skill_id}:dow_d446b2a6e46e7d94cdf7787e21050ff9",
            en_file, "en-US")
        skill.intent_service.register_padatious_entity.assert_any_call(
            f"{skill.skill_id}:dow_d446b2a6e46e7d94cdf7787e21050ff9",
            uk_file, "uk-UA")

    def test_handle_enable_intent(self):
        # TODO
        pass

    def test_handle_disable_intent(self):
        # TODO
        pass

    def test_disable_intent(self):
        # TODO
        pass

    def test_enable_intent(self):
        # TODO
        pass

    def test_set_context(self):
        # TODO
        pass

    def test_remove_context(self):
        # TODO
        pass

    def test_handle_set_cross_context(self):
        # TODO
        pass

    def test_handle_remove_cross_context(self):
        # TODO
        pass

    def test_set_cross_skill_contest(self):
        # TODO
        pass

    def test_remove_cross_skill_context(self):
        # TODO
        pass

    def test_register_vocabulary(self):
        # TODO
        pass

    def test_register_regex(self):
        # TODO
        pass

    def test_speak(self):
        # TODO
        pass

    def test_speak_dialog(self):
        # TODO
        pass

    def test_acknowledge(self):
        # TODO
        pass

    def test_load_dialog_files(self):
        # TODO
        pass

    def test_load_data_files(self):
        # TODO
        pass

    def test_load_vocab_files(self):
        # TODO
        pass

    def test_load_regex_files(self):
        # TODO
        pass

    def test_handle_stop(self):
        # TODO
        pass

    def test_stop(self):
        self.skill.stop()

    def test_shutdown(self):
        self.skill.shutdown()

    def test_default_shutdown(self):
        test_skill_id = "test_shutdown.skill"
        test_skill = OVOSSkill(bus=self.bus, skill_id=test_skill_id)
        test_skill.settings["changed"] = True
        test_skill.stop = Mock()
        test_skill.shutdown = Mock()
        test_skill.settings_change_callback = Mock()
        test_skill.settings.store = Mock()
        test_skill._settings_watchdog = Mock()
        test_skill.gui.shutdown = Mock()
        test_skill.event_scheduler = Mock()
        test_skill.events = Mock()
        message = None

        def _handle_detach_skill(msg):
            nonlocal message
            message = msg

        self.bus.on("detach_skill", _handle_detach_skill)

        test_skill.default_shutdown()

        test_skill.stop.assert_called_once()

        self.assertIsNone(test_skill.settings_change_callback)
        test_skill.settings.store.assert_called_once()
        test_skill._settings_watchdog.shutdown.assert_called_once()

        test_skill.gui.shutdown.assert_called_once()

        test_skill.event_scheduler.shutdown.assert_called_once()
        test_skill.events.clear.assert_called_once()

        test_skill.shutdown.assert_called_once()

        from ovos_bus_client import Message
        self.assertIsInstance(message, Message)
        self.assertEqual(message.msg_type, "detach_skill")
        self.assertTrue(message.data["skill_id"].startswith(test_skill_id))
        self.assertEqual(message.context["skill_id"], test_skill_id)

    def test_schedule_event(self):
        # TODO
        pass

    def test_schedule_repeating_event(self):
        # TODO
        pass

    def test_update_scheduled_event(self):
        # TODO
        pass

    def test_cancel_scheduled_event(self):
        # TODO
        pass

    def test_get_scheduled_event_status(self):
        # TODO
        pass

    def test_cancel_all_repeating_events(self):
        # TODO
        pass


class TestSkillGui(unittest.TestCase):
    class LegacySkill(Mock):
        skill_id = "old_skill"
        bus = FakeBus()
        config_core = {"gui": {"test": True,
                               "legacy": True}}
        root_dir = join(dirname(__file__), "test_gui/gui")

    class GuiSkill(Mock):
        skill_id = "new_skill"
        bus = FakeBus()
        config_core = {"gui": {"test": True,
                               "legacy": False}}
        root_dir = join(dirname(__file__), "test_gui")

