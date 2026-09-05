# Copyright 2026 OpenVoiceOS
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import json
import os
import shutil
import unittest

from logging import Logger
from threading import Event, Thread
from time import time
from unittest.mock import ANY, Mock
from os.path import join, dirname, isdir
from ovos_workshop.skills.ovos import OVOSSkill

from ovos_utils.fakebus import FakeBus
from ovos_bus_client.message import Message


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
        from ovos_gui_api_client import EnclosureAPI
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
        from unittest.mock import patch

        # "yes" response -> "yes"
        with patch.object(self.skill, 'get_response', return_value='yes'):
            self.assertEqual(self.skill.ask_yesno('do you want tea'), 'yes')

        # "nope" response -> "no"
        with patch.object(self.skill, 'get_response', return_value='nope'):
            self.assertEqual(self.skill.ask_yesno('do you want tea'), 'no')

        # "maybe" -> not matched, raw response returned
        with patch.object(self.skill, 'get_response', return_value='maybe'):
            self.assertEqual(self.skill.ask_yesno('do you want tea'), 'maybe')

        # None response (timeout) -> None
        with patch.object(self.skill, 'get_response', return_value=None):
            self.assertIsNone(self.skill.ask_yesno('do you want tea'))

    def test_ask_selection(self):
        from unittest.mock import patch

        options = ['alpha', 'beta', 'gamma']

        # empty list -> None
        self.assertIsNone(self.skill.ask_selection([]))

        # single option -> returned immediately without prompting
        with patch.object(self.skill, 'speak', wraps=self.skill.speak) as mock_speak:
            result = self.skill.ask_selection(['only'])
        self.assertEqual(result, 'only')

        # invalid type -> ValueError
        with self.assertRaises(ValueError):
            self.skill.ask_selection('not a list')

        # fuzzy match "beta" -> "beta"
        with patch.object(self.skill, 'get_response', return_value='beta'):
            result = self.skill.ask_selection(options, numeric=True)
        self.assertEqual(result, 'beta')

        # no response (timeout) -> None
        with patch.object(self.skill, 'get_response', return_value=None):
            result = self.skill.ask_selection(options, numeric=True)
        self.assertIsNone(result)

    def test_voc_list(self):
        # TODO
        pass

    def test_voc_match(self):
        skill = OVOSSkill(bus=self.bus, skill_id=self.skill_id)
        skill._lang_resources = dict()
        skill.res_dir = join(dirname(__file__), "test_locale")
        lang = "en-US"

        self.assertTrue(skill.voc_match("it is hot outside", "condition",
                                         lang=lang))
        self.assertFalse(skill.voc_match("it is nice outside", "condition",
                                          lang=lang))

    def test_voc_match_span(self):
        skill = OVOSSkill(bus=self.bus, skill_id=self.skill_id)
        skill._lang_resources = dict()
        skill.res_dir = join(dirname(__file__), "test_locale")
        lang = "en-US"

        # no match -> empty list
        self.assertEqual(
            skill.voc_match_span("it is nice outside", "condition",
                                  lang=lang),
            [])

        # single match, span slices back to the matched text
        utt = "it is hot outside"
        matches = skill.voc_match_span(utt, "condition", lang=lang)
        self.assertEqual(len(matches), 1)
        entry, start, end = matches[0]
        self.assertEqual(entry, "hot")
        self.assertEqual(utt[start:end], "hot")

        # multiple matches, returned in UTTERANCE order (position, not length)
        utt = "it is hot and freezing outside"
        matches = skill.voc_match_span(utt, "condition", lang=lang)
        self.assertEqual([m[0] for m in matches], ["hot", "freezing"])
        for entry, start, end in matches:
            self.assertEqual(utt[start:end], entry)

        # exact mode -> single span covering the whole utterance
        utt = "hot"
        self.assertEqual(
            skill.voc_match_span(utt, "condition", lang=lang, exact=True),
            [("hot", 0, len(utt))])
        self.assertEqual(
            skill.voc_match_span("it is hot outside", "condition", lang=lang,
                                  exact=True),
            [])

        # ensure_ascii normalizes accents/punctuation before matching, but
        # the returned span still indexes the ORIGINAL utterance, even
        # though the normalized string is shorter (accent + "!" stripped)
        utt = "está muito frío!"
        matches = skill.voc_match_span(utt, "condition_accents", lang=lang,
                                        ensure_ascii=True)
        self.assertEqual(len(matches), 1)
        entry, start, end = matches[0]
        self.assertEqual(entry, "frio")
        self.assertEqual(utt[start:end], "frío")
        self.assertEqual(
            skill.voc_match_span(utt, "condition_accents", lang=lang,
                                  ensure_ascii=False),
            [])

        # duplicate vocab lines produce one span per occurrence in the utt
        utt = "it is hot and hot outside"
        matches = skill.voc_match_span(utt, "condition_dupe", lang=lang)
        self.assertEqual([m[0] for m in matches], ["hot", "hot"])
        starts = [m[1] for m in matches]
        self.assertEqual(len(set(starts)), 2)
        for entry, start, end in matches:
            self.assertEqual(utt[start:end], entry)

        # overlap rule: "new york" and "york" both match "new york", the
        # longest entry wins and the shorter, overlapping one is dropped
        utt = "i live in new york"
        matches = skill.voc_match_span(utt, "place", lang=lang)
        self.assertEqual(len(matches), 1)
        entry, start, end = matches[0]
        self.assertEqual(entry, "new york")
        self.assertEqual(utt[start:end], "new york")

    def test_report_metric(self):
        # TODO
        pass

    def test_send_email(self):
        # TODO
        pass

    def test_register_decorated_intent_files_forwards_context_gates(self):
        """OVOS-CONTEXT-1 §6: an intent_files-decorated handler's gate
        declarations must reach register_intent_file the same way the
        `intents` branch already forwards them to register_intent, or the
        gate is silently dropped on the intent_files registration path."""
        def handler(self, message):
            pass

        handler.intent_files = ["time.intent"]
        handler.requires_context = ["confirming_time"]
        handler.excludes_context = [{"key": "active_room", "scope": "shared"}]

        skill_cls = type("_IntentFileContextGateSkill", (OVOSSkill,),
                         {"handle_time_intent": handler})
        skill = skill_cls(bus=self.bus, skill_id=self.skill_id)
        skill._lang_resources = dict()
        skill.intent_service = Mock()
        skill.res_dir = join(dirname(__file__), "test_locale")
        skill.config_core["lang"] = "en-US"
        skill.config_core["secondary_langs"] = []

        skill.intent_service.register_template.reset_mock()
        skill._register_decorated()

        skill.intent_service.register_template.assert_called_once_with(
            f"{skill.skill_id}:time", ["what time is it"], "en-US",
            blacklisted_words=[], slot_blacklist={}, vocabs=ANY,
            requires_context=["confirming_time"],
            excludes_context=[{"key": "active_room", "scope": "shared"}])

    def test_find_resource(self):
        # TODO
        pass

    def _capture(self, fn, *args, **kwargs):
        """Run an _on_event_* callback against a private FakeBus and return the
        list of (type, data, context) tuples it emitted on the topics of
        interest (the handler trio + ovos.utterance.handled)."""
        from ovos_spec_tools import SpecMessage
        skill = OVOSSkill(bus=FakeBus(), skill_id=self.skill_id)
        captured = []
        topics = ["mycroft.skill.handler.start",
                  "mycroft.skill.handler.complete",
                  "mycroft.skill.handler.error",
                  SpecMessage.UTTERANCE_HANDLED.value]
        for t in topics:
            skill.bus.on(t, lambda m: captured.append(
                (m.msg_type, m.data, dict(m.context))))
        fn(skill, *args, **kwargs)
        return captured

    def test_on_event_start(self):
        from ovos_bus_client.message import Message
        msg = Message("trigger", {}, {"session": {"session_id": "sess1"}})
        skill_data = {"name": "TestSkill.handle_test"}
        captured = self._capture(OVOSSkill._on_event_start, msg,
                                 "mycroft.skill.handler", dict(skill_data))
        # exactly one emission: the .start done-signal
        starts = [c for c in captured
                  if c[0] == "mycroft.skill.handler.start"]
        self.assertEqual(len(starts), 1)
        mtype, data, context = starts[0]
        # byte-identical topic + payload
        self.assertEqual(mtype, "mycroft.skill.handler.start")
        self.assertEqual(data, {"name": "TestSkill.handle_test"})
        # context carries skill_id + preserves originating session
        self.assertEqual(context["skill_id"], self.skill_id)
        self.assertEqual(context["session"]["session_id"], "sess1")
        # original message context not mutated by the util
        self.assertNotIn("skill_id", msg.context)
        # empty/false handler_info disables emission entirely
        none_captured = self._capture(OVOSSkill._on_event_start, msg, "",
                                      dict(skill_data))
        self.assertEqual(
            [c for c in none_captured
             if c[0].startswith("mycroft.skill.handler")], [])

    def test_on_event_end(self):
        from ovos_bus_client.message import Message
        msg = Message("trigger", {}, {"session": {"session_id": "sess1"}})
        skill_data = {"name": "TestSkill.handle_test"}
        captured = self._capture(OVOSSkill._on_event_end, msg,
                                 "mycroft.skill.handler", dict(skill_data))
        completes = [c for c in captured
                     if c[0] == "mycroft.skill.handler.complete"]
        self.assertEqual(len(completes), 1)
        mtype, data, context = completes[0]
        self.assertEqual(mtype, "mycroft.skill.handler.complete")
        self.assertEqual(data, {"name": "TestSkill.handle_test"})
        self.assertEqual(context["skill_id"], self.skill_id)
        self.assertEqual(context["session"]["session_id"], "sess1")

    def test_on_event_end_intent_never_emits_utterance_handled(self):
        # PIPELINE-1 §9.5: the orchestrator owns the end marker; the skill
        # never emits it, on the matched-intent path or any other.
        from ovos_spec_tools import SpecMessage
        msg = Message("trigger", {}, {})
        skill_data = {"name": "TestSkill.handle_test"}
        captured = self._capture(OVOSSkill._on_event_end, msg,
                                  "mycroft.skill.handler",
                                  dict(skill_data), True)
        types = [c[0] for c in captured]
        self.assertIn("mycroft.skill.handler.complete", types)
        self.assertNotIn(SpecMessage.UTTERANCE_HANDLED.value, types)

    def test_on_event_error(self):
        from ovos_bus_client.message import Message
        msg = Message("trigger", {}, {"session": {"session_id": "sess1"}})
        skill_data = {"name": "TestSkill.handle_test"}
        err = "boom"  # workshop passes str(error)
        captured = self._capture(OVOSSkill._on_event_error, err, msg,
                                 "mycroft.skill.handler", dict(skill_data),
                                 False)
        errors = [c for c in captured
                  if c[0] == "mycroft.skill.handler.error"]
        self.assertEqual(len(errors), 1)
        mtype, data, context = errors[0]
        self.assertEqual(mtype, "mycroft.skill.handler.error")
        # payload = original {name} + repr(error) under "exception" (identical
        # to the pre-refactor skill_data['exception'] = repr(error))
        self.assertEqual(data, {"name": "TestSkill.handle_test",
                                "exception": repr(err)})
        self.assertEqual(context["skill_id"], self.skill_id)
        self.assertEqual(context["session"]["session_id"], "sess1")

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

    def test_register_intent_adapt_context_gating_reaches_intent_service(self):
        """OVOS-CONTEXT-1 §6: an engine that does not implement
        OVOS-CONTEXT-1 "ignores them and matches as if absent" - the
        declaration still has to reach the wire on adapt registrations too,
        it is not workshop's place to strip it at the producer."""
        from ovos_spec_tools import IntentBuilder

        skill = OVOSSkill(bus=self.bus, skill_id=self.skill_id)
        skill._lang_resources = dict()
        skill.intent_service = Mock()
        skill.intent_service.intent_names = []
        skill.intent_service.intent_is_detached.return_value = False
        parser = IntentBuilder("test_adapt").require("Foo").build()
        skill.register_intent(parser, Mock(__name__="test"),
                              requires_context=["confirming"],
                              excludes_context=[{"key": "active_room", "scope": "shared"}])
        skill.intent_service.register_intent.assert_called_once()
        args, kwargs = skill.intent_service.register_intent.call_args
        self.assertEqual(kwargs["requires_context"], ["confirming"])
        self.assertEqual(kwargs["excludes_context"],
                         [{"key": "active_room", "scope": "shared"}])

    def test_register_intent_file(self):
        skill = OVOSSkill(bus=self.bus, skill_id=self.skill_id)
        skill._lang_resources = dict()
        skill.intent_service = Mock()
        skill.res_dir = join(dirname(__file__), "test_locale")
        en_intent_file = join(skill.res_dir, "locale", "en-US", "time.intent")
        uk_intent_file = join(skill.res_dir, "locale", "uk-UA", "time.intent")
        en_samples = ["what time is it"]
        uk_samples = ["котра година"]

        # No secondary languages
        skill.config_core["lang"] = "en-US"
        skill.config_core["secondary_langs"] = []
        skill.register_intent_file("time.intent", Mock(__name__="test"))
        skill.intent_service.register_template.assert_called_once_with(
            f"{skill.skill_id}:time", en_samples, "en-US",
            blacklisted_words=[], slot_blacklist={}, vocabs=ANY,
            requires_context=None, excludes_context=None)

        # With secondary language
        skill.intent_service.register_template.reset_mock()
        skill.config_core["secondary_langs"] = ["en-US", "uk-UA"]
        skill.register_intent_file("time.intent", Mock(__name__="test"))
        self.assertEqual(
            skill.intent_service.register_template.call_count, 2)
        skill.intent_service.register_template.assert_any_call(
            f"{skill.skill_id}:time", en_samples, "en-US",
            blacklisted_words=[], slot_blacklist={}, vocabs=ANY,
            requires_context=None, excludes_context=None)
        skill.intent_service.register_template.assert_any_call(
            f"{skill.skill_id}:time", uk_samples, "uk-UA",
            blacklisted_words=[], slot_blacklist={}, vocabs=ANY,
            requires_context=None, excludes_context=None)

    def test_register_intent_file_with_context_gating(self):
        skill = OVOSSkill(bus=self.bus, skill_id=self.skill_id)
        skill._lang_resources = dict()
        skill.intent_service = Mock()
        skill.res_dir = join(dirname(__file__), "test_locale")
        en_samples = ["what time is it"]
        skill.config_core["lang"] = "en-US"
        skill.config_core["secondary_langs"] = []

        skill.register_intent_file(
            "time.intent", Mock(__name__="test"),
            requires_context=["confirming_time"],
            excludes_context=[{"key": "active_room", "scope": "shared"}])
        skill.intent_service.register_template.assert_called_once_with(
            f"{skill.skill_id}:time", en_samples, "en-US",
            blacklisted_words=[], slot_blacklist={}, vocabs=ANY,
            requires_context=["confirming_time"],
            excludes_context=[{"key": "active_room", "scope": "shared"}])

    def test_register_intent_file_binds_the_canonical_event_only(self):
        # OVOS-MSG-1 §2.1.1: the dispatch topic is `<skill_id>:<intent_name>`.
        # The `.intent` authoring extension is not part of the intent name, so
        # workshop must neither register nor listen on the suffixed twin —
        # that compat belongs to ovos-spec-tools at the bus layer.
        skill = OVOSSkill(bus=FakeBus(), skill_id=self.skill_id)
        skill._lang_resources = dict()
        skill.intent_service = Mock()
        skill.res_dir = join(dirname(__file__), "test_locale")
        skill.config_core["lang"] = "en-US"
        skill.config_core["secondary_langs"] = []

        legacy_name = f"{skill.skill_id}:time.intent"
        canonical_name = f"{skill.skill_id}:time"

        handler = Mock(__name__="test")
        skill.register_intent_file("time.intent", handler)

        self.assertTrue(any(n == canonical_name for n, _ in skill.events))
        self.assertFalse(any(n == legacy_name for n, _ in skill.events))

    def test_register_intent_file_registers_the_canonical_name(self):
        # the name that goes to the intent service (and so onto the wire in
        # the INTENT-4 registration payload) carries no authoring extension
        skill = OVOSSkill(bus=FakeBus(), skill_id=self.skill_id)
        skill._lang_resources = dict()
        skill.intent_service = Mock()
        skill.res_dir = join(dirname(__file__), "test_locale")
        skill.config_core["lang"] = "en-US"
        skill.config_core["secondary_langs"] = []

        skill.register_intent_file("time.intent", Mock(__name__="test"))

        registered = skill.intent_service.register_template.call_args[0][0]
        self.assertEqual(registered, f"{skill.skill_id}:time")

    def test_no_suffixed_topic_originates_from_workshop(self):
        # nothing workshop emits or binds while registering a file intent may
        # carry the `.intent` suffix in a `<skill_id>:` topic
        import json
        bus = FakeBus()
        emitted = []
        bus.on("message", lambda m: emitted.append(
            json.loads(m)["type"] if isinstance(m, str) else m.msg_type))
        skill = OVOSSkill(bus=bus, skill_id=self.skill_id)
        skill._lang_resources = dict()
        skill.res_dir = join(dirname(__file__), "test_locale")
        skill.config_core["lang"] = "en-US"
        skill.config_core["secondary_langs"] = []

        skill.register_intent_file("time.intent", Mock(__name__="test"))

        suffixed = [t for t in emitted
                    if ":" in t and t.rsplit(":", 1)[-1].endswith(".intent")]
        self.assertEqual(suffixed, [])
        self.assertFalse(any(":" in n and n.rsplit(":", 1)[-1].endswith(".intent")
                             for n, _ in skill.events))

    def test_register_intent_file_canonical_topic_fires_handler(self):
        # emitting the canonical (suffix-less) topic on the bus must invoke
        # the registered handler, matching how a pipeline dispatches
        bus = FakeBus()
        skill = OVOSSkill(bus=bus, skill_id=self.skill_id)
        skill._lang_resources = dict()
        skill.intent_service = Mock()
        skill.res_dir = join(dirname(__file__), "test_locale")
        skill.config_core["lang"] = "en-US"
        skill.config_core["secondary_langs"] = []

        called = Event()

        def handler(message):
            called.set()

        handler.__name__ = "test_handler"
        skill.register_intent_file("time.intent", handler)

        canonical_name = f"{skill.skill_id}:time"
        from ovos_bus_client.message import Message
        bus.emit(Message(canonical_name, {}, {}))
        self.assertTrue(called.wait(2))

    def test_legacy_registration_fires_on_canonical_dispatch(self):
        # OVOS-INTENT-4 §5/§8 alias-collapse: a still-un-migrated consumer
        # that registers under the suffixed `X:Y.intent` name (what old
        # workshop releases dispatched on) must still fire when the intent
        # service dispatches the canonical `X:Y` topic. The collapse is
        # `canonical_intent_topic`, normalizing the suffixed registration to
        # canonical before binding to the bus.
        from ovos_bus_client.message import Message
        from ovos_spec_tools.intent_topics import canonical_intent_topic

        canonical_name = f"{self.skill_id}:legacy_normalization"
        legacy_name = f"{canonical_name}.intent"

        bus = FakeBus()
        hits = []
        name = canonical_intent_topic(legacy_name)
        self.assertEqual(name, canonical_name,
                         "legacy registration was not normalized to canonical")

        bus.on(name, hits.append)
        bus.emit(Message(canonical_name, {"x": 1}))
        self.assertEqual(len(hits), 1)

    def test_dual_registration_does_not_double_fire(self):
        # registering both the canonical and the legacy-suffixed spelling of
        # the same intent (e.g. a consumer that binds both while migrating)
        # must collapse to a single dispatch, not fire the handler twice.
        from ovos_bus_client.message import Message
        from ovos_spec_tools.intent_topics import canonical_intent_topic

        canonical_name = f"{self.skill_id}:dual_registration"
        legacy_name = f"{canonical_name}.intent"

        bus = FakeBus()
        hits = []
        bus.on(canonical_intent_topic(canonical_name), hits.append)
        bus.on(canonical_intent_topic(legacy_name), hits.append)
        bus.emit(Message(canonical_name, {"x": 1}))
        self.assertEqual(len(hits), 1,
                         "registering both the canonical and legacy forms "
                         "caused a double dispatch")

    def test_disable_intent_removes_the_canonical_event(self):
        # the author still names the intent by its authoring file
        skill = OVOSSkill(bus=FakeBus(), skill_id=self.skill_id)
        skill._lang_resources = dict()
        skill.intent_service = Mock()
        skill.intent_service.__contains__ = Mock(return_value=True)
        skill.res_dir = join(dirname(__file__), "test_locale")
        skill.config_core["lang"] = "en-US"
        skill.config_core["secondary_langs"] = []

        canonical_name = f"{skill.skill_id}:time"

        skill.register_intent_file("time.intent", Mock(__name__="test"))
        self.assertTrue(any(n == canonical_name for n, _ in skill.events))

        skill.disable_intent("time.intent")
        self.assertFalse(any(n == canonical_name for n, _ in skill.events))
        # the registry is asked about the canonical name, not the file name
        skill.intent_service.__contains__.assert_called_with("time")

    def test_register_entity_file(self):
        skill = OVOSSkill(bus=self.bus, skill_id=self.skill_id)
        skill._lang_resources = dict()
        skill.intent_service = Mock()
        skill.res_dir = join(dirname(__file__), "test_locale")
        en_file = join(skill.res_dir, "locale", "en-US", "dow.entity")
        uk_file = join(skill.res_dir, "locale", "uk-UA", "dow.entity")
        with open(en_file) as f:
            en_samples = f.read().split("\n")
        with open(uk_file) as f:
            uk_samples = f.read().split("\n")
        en_samples = [_ for _ in en_samples if _ and not _.startswith("#")]
        uk_samples = [_ for _ in uk_samples if _ and not _.startswith("#")]

        # No secondary languages
        skill.config_core["lang"] = "en-US"
        skill.config_core["secondary_langs"] = []
        skill.register_entity_file("dow")
        skill.intent_service.register_entity.assert_called_once_with(
            f"{skill.skill_id}:dow",
            en_samples, "en-US", blacklisted_words=[])

        # With secondary language - en-US's "dow" was already registered
        # above (and auto-discovered on first resource load before that),
        # so re-registering it here is a deduped no-op (OVOS-INTENT-3
        # §auto-entity idempotency: register once, don't stack). Only the
        # newly-added uk-UA language actually fires a new registration.
        skill.intent_service.register_entity.reset_mock()
        skill.config_core["secondary_langs"] = ["en-US", "uk-UA"]
        skill.register_entity_file("dow")
        self.assertEqual(
            skill.intent_service.register_entity.call_count, 1)
        skill.intent_service.register_entity.assert_any_call(
            f"{skill.skill_id}:dow",
            uk_samples, "uk-UA", blacklisted_words=[])

    def test_disable_intent(self):
        """Regression test: disable_intent() followed by enable_intent()
        must rebind the ORIGINAL handler for a padatious (.intent file)
        intent, addressed by its author-facing (".intent"-suffixed) name,
        under the INTENT-4 canonical suffix-less dispatch topic. Per the
        canonical-registration refactor (OVOS-MSG-1 §2.1.1), the skill layer
        binds the canonical topic only -- there is no suffixed twin to
        assert on (see test_disable_intent_removes_the_canonical_event)."""
        from ovos_bus_client.message import Message

        bus = FakeBus()
        skill = OVOSSkill(bus=bus, skill_id=self.skill_id)
        skill._lang_resources = dict()
        skill.res_dir = join(dirname(__file__), "test_locale")
        skill.config_core["lang"] = "en-US"
        skill.config_core["secondary_langs"] = []

        called = Event()

        def handler(message):
            called.set()

        handler.__name__ = "test_handler"
        skill.register_intent_file("time.intent", handler)

        canonical_name = f"{skill.skill_id}:time"

        # sanity: bound before disabling
        self.assertTrue(any(n == canonical_name for n, _ in skill.events))

        self.assertTrue(skill.disable_intent("time.intent"))
        self.assertFalse(any(n == canonical_name for n, _ in skill.events))
        self.assertTrue(skill.intent_service.intent_is_detached("time.intent"))

        self.assertTrue(skill.enable_intent("time.intent"))
        self.assertTrue(any(n == canonical_name for n, _ in skill.events))
        self.assertFalse(skill.intent_service.intent_is_detached("time.intent"))

        called.clear()
        bus.emit(Message(canonical_name, {}, {}))
        self.assertTrue(called.wait(2),
                        "handler was not rebound by enable_intent()")

    def test_disable_enable_intent_canonical_spelling_round_trip(self):
        """Regression test: disable_intent()/enable_intent() must work when
        called with the CANONICAL (suffix-less) spelling of a padatious
        intent, not just the author-facing ".intent"-suffixed one.
        _intent_handlers used to be keyed by the raw spelling passed to
        register_intent_file() ("time.intent"), while enable_intent() looked
        the handler up by whatever spelling ITS caller used -- so
        disable_intent("time") succeeded (the registry itself is
        canonical-keyed) but enable_intent("time") silently failed with "no
        handler is on record", a one-way door: once disabled by its
        canonical name, the intent could never be re-enabled that way.
        Also guards against re-registration leaving a duplicate bus
        listener bound to the canonical topic."""
        from ovos_bus_client.message import Message

        bus = FakeBus()
        skill = OVOSSkill(bus=bus, skill_id=self.skill_id)
        skill._lang_resources = dict()
        skill.res_dir = join(dirname(__file__), "test_locale")
        skill.config_core["lang"] = "en-US"
        skill.config_core["secondary_langs"] = []

        called = Event()

        def handler(message):
            called.set()

        handler.__name__ = "test_handler"
        skill.register_intent_file("time.intent", handler)

        canonical_name = f"{skill.skill_id}:time"

        self.assertTrue(skill.disable_intent(canonical_name.split(':', 1)[1]))
        self.assertTrue(skill.intent_service.intent_is_detached(
            canonical_name.split(':', 1)[1]))

        self.assertTrue(skill.enable_intent(canonical_name.split(':', 1)[1]),
                        "enable_intent() must succeed for the canonical "
                        "spelling, not just the '.intent'-suffixed one")
        self.assertFalse(skill.intent_service.intent_is_detached(
            canonical_name.split(':', 1)[1]))
        self.assertTrue(any(n == canonical_name for n, _ in skill.events))

        # guard: exactly one listener bound to the canonical topic, not a
        # duplicate left over from re-registration
        listener_count = len(bus.ee.listeners(canonical_name))
        self.assertEqual(listener_count, 1,
                         f"expected exactly one listener on {canonical_name}, "
                         f"found {listener_count}")

        called.clear()
        bus.emit(Message(canonical_name, {}, {}))
        self.assertTrue(called.wait(2),
                        "handler was not rebound by enable_intent()")

    def test_enable_intent(self):
        """Regression test: disable_intent() followed by enable_intent()
        must rebind the ORIGINAL handler for an adapt intent."""
        from ovos_bus_client.message import Message
        from ovos_workshop.intents import IntentBuilder

        bus = FakeBus()
        skill = OVOSSkill(bus=bus, skill_id=self.skill_id)
        skill.register_vocabulary("hello world", "HelloWorldKeyword",
                                  lang="en-US")

        called = Event()

        def handler(message):
            called.set()

        skill.register_intent(
            IntentBuilder("HelloWorldIntent").require("HelloWorldKeyword"),
            handler)

        event_name = f"{skill.skill_id}:HelloWorldIntent"
        self.assertTrue(any(n == event_name for n, _ in skill.events))

        self.assertTrue(skill.disable_intent("HelloWorldIntent"))
        self.assertFalse(any(n == event_name for n, _ in skill.events))
        self.assertTrue(
            skill.intent_service.intent_is_detached("HelloWorldIntent"))

        self.assertTrue(skill.enable_intent("HelloWorldIntent"))
        self.assertTrue(any(n == event_name for n, _ in skill.events))
        self.assertFalse(
            skill.intent_service.intent_is_detached("HelloWorldIntent"))

        called.clear()
        bus.emit(Message(event_name, {}, {}))
        self.assertTrue(called.wait(2),
                        "handler was not rebound by enable_intent()")

    def test_handle_disable_intent(self):
        """The `mycroft.skill.disable_intent` bus handler disables an
        intent that belongs to this skill and is currently registered."""
        from ovos_bus_client.message import Message

        bus = FakeBus()
        skill = OVOSSkill(bus=bus, skill_id=self.skill_id)
        skill._lang_resources = dict()
        skill.res_dir = join(dirname(__file__), "test_locale")
        skill.config_core["lang"] = "en-US"
        skill.config_core["secondary_langs"] = []
        skill.register_intent_file("time.intent", Mock(__name__="test"))

        skill.handle_disable_intent(
            Message("mycroft.skill.disable_intent",
                   {"intent_name": "time.intent"}))

        self.assertTrue(skill.intent_service.intent_is_detached("time.intent"))
        legacy_name = f"{skill.skill_id}:time.intent"
        self.assertFalse(any(n == legacy_name for n, _ in skill.events))

    def test_handle_enable_intent(self):
        """The `mycroft.skill.enable_intent` bus handler re-enables an
        intent that belongs to this skill and is currently detached,
        rebinding its handler."""
        from ovos_bus_client.message import Message

        bus = FakeBus()
        skill = OVOSSkill(bus=bus, skill_id=self.skill_id)
        skill._lang_resources = dict()
        skill.res_dir = join(dirname(__file__), "test_locale")
        skill.config_core["lang"] = "en-US"
        skill.config_core["secondary_langs"] = []

        called = Event()

        def handler(message):
            called.set()

        handler.__name__ = "test_handler"
        skill.register_intent_file("time.intent", handler)
        skill.disable_intent("time.intent")
        self.assertTrue(skill.intent_service.intent_is_detached("time.intent"))

        skill.handle_enable_intent(
            Message("mycroft.skill.enable_intent",
                   {"intent_name": "time.intent"}))

        self.assertFalse(skill.intent_service.intent_is_detached("time.intent"))
        canonical_name = f"{skill.skill_id}:time"
        self.assertTrue(any(n == canonical_name for n, _ in skill.events))

        bus.emit(Message(canonical_name, {}, {}))
        self.assertTrue(called.wait(2))

    def test_set_context(self):
        """set_context must emit both the legacy munged `context` key
        (adapt-engine spelling) and the original unmunged `key`, so the
        declarative OVOS-CONTEXT-1 gate (resolve_key) can also see it."""
        bus = FakeBus()
        skill = OVOSSkill(bus=bus, skill_id=self.skill_id)

        received = Event()
        payloads = []

        def handler(message):
            payloads.append(message.data)
            received.set()

        bus.on("add_context", handler)
        skill.set_context("kitchen", "kitchen")
        self.assertTrue(received.wait(2))

        self.assertEqual(len(payloads), 1)
        data = payloads[0]
        self.assertEqual(data["context"], skill.alphanumeric_skill_id + "kitchen")
        self.assertEqual(data["key"], "kitchen")

    def test_remove_context(self):
        """remove_context must emit both the legacy munged `context` key
        and the original unmunged `key`, symmetrically with set_context."""
        bus = FakeBus()
        skill = OVOSSkill(bus=bus, skill_id=self.skill_id)

        received = Event()
        payloads = []

        def handler(message):
            payloads.append(message.data)
            received.set()

        bus.on("remove_context", handler)
        skill.remove_context("kitchen")
        self.assertTrue(received.wait(2))

        self.assertEqual(len(payloads), 1)
        data = payloads[0]
        self.assertEqual(data["context"], skill.alphanumeric_skill_id + "kitchen")
        self.assertEqual(data["key"], "kitchen")

    def test_set_context_owner_is_true_caller_not_ambient_message(self):
        """Round 2 (C1) regression: skill B calling set_context WHILE
        handling skill A's message must resolve the private key under B's
        own skill_id, never A's. `_AdaptIntentApi.set_context` only stamps
        `skill_id` onto the dug ambient message IF ABSENT - so without the
        fix, a message already carrying A's skill_id leaks straight
        through `forward()`, and B's context is written under A's owner
        (opening A's private gate for B's action)."""
        bus = FakeBus()
        skill_a = OVOSSkill(bus=bus, skill_id="skill.a")
        skill_b = OVOSSkill(bus=bus, skill_id="skill.b")

        received = Event()
        payloads = []

        def handler(message):
            payloads.append(message)
            received.set()

        bus.on("add_context", handler)

        a_message = Message("skill.a.some.handler", {},
                            {"skill_id": "skill.a"})

        def handle_as_if_dispatched(message):
            # `message` is a local Message arg -> dig_for_message() finds
            # THIS frame, carrying A's skill_id, even though B is the one
            # actually calling set_context.
            skill_b.set_context("kitchen", "kitchen")

        handle_as_if_dispatched(a_message)
        self.assertTrue(received.wait(2))

        self.assertEqual(len(payloads), 1)
        emitted = payloads[0]
        self.assertEqual(emitted.data["key"], "kitchen")
        self.assertEqual(
            emitted.context.get("skill_id"), "skill.b",
            "resolved-key mirror was forged under the ambient message's "
            "skill_id (skill.a) instead of the true caller (skill.b)")

    def test_handle_set_cross_context(self):
        """Round 2 (C1b) regression: each RECEIVING skill's
        handle_set_cross_context must resolve the mirrored key under ITS
        OWN skill_id, not the originating broadcaster's - the broadcast
        message's context.skill_id is stamped by the ORIGINATOR."""
        bus = FakeBus()
        skill_b = OVOSSkill(bus=bus, skill_id="skill.b")

        received = Event()
        payloads = []

        def handler(message):
            payloads.append(message)
            received.set()

        bus.on("add_context", handler)

        # broadcast as emitted by the originating skill (skill.a)
        broadcast = Message("mycroft.skill.set_cross_context",
                            {"context": "kitchen", "word": "kitchen",
                             "origin": "skill.a"},
                            {"skill_id": "skill.a"})
        skill_b.handle_set_cross_context(broadcast)
        self.assertTrue(received.wait(2))

        self.assertEqual(len(payloads), 1)
        emitted = payloads[0]
        self.assertEqual(emitted.data["key"], "kitchen")
        self.assertEqual(
            emitted.context.get("skill_id"), "skill.b",
            "cross-context receiver mirrored the resolved key under the "
            "ORIGINATING skill's id instead of its own")

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
        """STOP-1 §4.3: the targeted `<skill_id>:stop` dispatch completes
        like any other dispatched handler — the orchestrator's dispatcher
        resolves the in-flight entry from the workshop->core done-signal
        (`mycroft.skill.handler.start`/`.complete`), so the skill's stop
        handler MUST fire that trio exactly like an intent handler, in
        addition to the existing `.stop.response` reply (STOP-1 §4.2/§8).
        """
        emitted = []
        self.bus.on("mycroft.skill.handler.start", lambda m: emitted.append(m))
        self.bus.on("mycroft.skill.handler.complete", lambda m: emitted.append(m))
        self.bus.on(f"{self.skill_id}.stop.response", lambda m: emitted.append(m))

        self.skill.stop = Mock(return_value=False)
        self.bus.emit(Message(f"{self.skill_id}.stop",
                              context={"session": {"session_id": "test-stop-session"}}))

        types = [m.msg_type for m in emitted]
        self.assertEqual(types.count("mycroft.skill.handler.start"), 1)
        self.assertEqual(types.count("mycroft.skill.handler.complete"), 1)
        self.assertEqual(types.count(f"{self.skill_id}.stop.response"), 1)

        # ovos-core's dispatcher (`_resolve_entry`) keys the done-signal on
        # exactly these three fields: context["skill_id"], a well-formed
        # context["session"], and data["intent_name"] — the last one
        # disambiguates this dispatch from any other in-flight dispatch for
        # the same skill_id (eg. an already-running intent handler), which
        # skill_id alone cannot do.
        complete_msg = [m for m in emitted
                        if m.msg_type == "mycroft.skill.handler.complete"][0]
        self.assertEqual(complete_msg.context["skill_id"], self.skill_id)
        self.assertEqual(complete_msg.context["session"]["session_id"],
                         "test-stop-session")
        self.assertEqual(complete_msg.data["intent_name"], "stop")

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

        from ovos_bus_client import Message
        self.assertIsInstance(message, Message)
        self.assertEqual(message.msg_type, "detach_skill")
        self.assertTrue(message.data["skill_id"].startswith(test_skill_id))
        self.assertEqual(message.context["skill_id"], test_skill_id)

    def test_default_shutdown_is_reentrant(self):
        """
        SkillManager.unload_skill() and __del__ (triggered by GC on another
        thread) can both call default_shutdown() for the same instance. The
        second concurrent call must be a no-op: settings must only be stored
        once and no exception (eg. the ValueError from an unguarded
        EventSchedulerInterface.scheduled_repeats mutation) may escape.
        """
        import time as _time

        test_skill_id = "test_reentrant_shutdown.skill"
        test_skill = OVOSSkill(bus=self.bus, skill_id=test_skill_id)
        test_skill.settings["changed"] = True
        test_skill.stop = Mock()
        test_skill.shutdown = Mock()
        test_skill.settings_change_callback = Mock()

        store_calls = []

        def _slow_store():
            # widen the race window so two threads reliably interleave
            _time.sleep(0.05)
            store_calls.append(1)

        test_skill.settings.store = Mock(side_effect=_slow_store)
        test_skill._settings_watchdog = Mock()
        test_skill.gui.shutdown = Mock()
        test_skill.event_scheduler = Mock()
        test_skill.events = Mock()

        errors = []

        def _run():
            try:
                test_skill.default_shutdown()
            except Exception as e:
                errors.append(e)

        threads = [Thread(target=_run) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        self.assertEqual(errors, [])
        self.assertEqual(len(store_calls), 1)
        test_skill.settings.store.assert_called_once()

    def test_del_does_not_rerun_shutdown_after_explicit_unload(self):
        """
        SkillManager.unload_skill() calls skill.shutdown() +
        default_shutdown() explicitly, then GC eventually drops the last
        reference and __del__ runs the same pair again on (possibly) another
        thread. __del__ must notice the explicit unload already happened and
        skip calling the skill-authored shutdown() a second time -- that is
        the dangerous half of the teardown (arbitrary skill cleanup: sockets,
        threads, unsubscribes), unlike default_shutdown() which is already
        internally idempotent.
        """
        test_skill_id = "test_del_shutdown_once.skill"
        test_skill = OVOSSkill(bus=self.bus, skill_id=test_skill_id)
        test_skill.stop = Mock()
        test_skill.shutdown = Mock()
        test_skill.settings_change_callback = Mock()
        test_skill.settings.store = Mock()
        test_skill._settings_watchdog = Mock()
        test_skill.gui.shutdown = Mock()
        test_skill.event_scheduler = Mock()
        test_skill.events = Mock()

        # simulate SkillManager.unload_skill()
        test_skill.shutdown()
        test_skill.default_shutdown()

        # simulate GC dropping the last reference
        test_skill.__del__()

        test_skill.shutdown.assert_called_once()

    def test_del_alone_still_fully_tears_down_skill(self):
        """
        The common case: no explicit SkillManager.unload_skill() call, GC
        simply drops the last reference to the skill and __del__ runs alone.
        __del__ must not treat itself as a duplicate teardown -- it only
        checks the shared flag (never sets it), so on this path the flag is
        still unset and the full shutdown() + default_shutdown() pair runs
        exactly once.
        """
        test_skill_id = "test_del_alone.skill"
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

        # simulate GC dropping the last reference with no prior explicit
        # unload
        test_skill.__del__()

        test_skill.shutdown.assert_called_once()
        test_skill.settings.store.assert_called_once()
        test_skill.gui.shutdown.assert_called_once()
        test_skill.event_scheduler.shutdown.assert_called_once()

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

