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
import binascii
import datetime
import json
import os
import random
import re
import shutil
import string
import sys
import time
import traceback
import unicodedata
import warnings
from copy import copy
from inspect import signature
from os.path import join, abspath, dirname, basename, isfile
from pathlib import Path
from queue import Queue
from threading import Event, RLock, Thread
from typing import Any, Dict, Callable, List, Optional, Set, Tuple, Union

from json_database import JsonStorage
from ovos_bus_client import MessageBusClient
from ovos_gui_api_client import EnclosureAPI
from ovos_bus_client.apis.events import EventSchedulerInterface
try:
    from ovos_bus_client.apis.scheduler import SchedulerClient
except ImportError:  # pre-SCHEDULER-1 ovos-bus-client
    SchedulerClient = None

#: put on a skill's scheduler queue to stop its sending thread
_STOP_SENDING = object()

#: how long an unloading skill waits for its queued scheduler requests to go
#: out: twice a request's own timeout, so one request already in flight and
#: one behind it can both finish, and a silent scheduler cannot hang a
#: shutdown
SCHEDULER_SHUTDOWN_TIMEOUT = 6.0
from ovos_bus_client.apis.gui import GUIInterface
from ovos_bus_client.apis.ocp import OCPInterface
from ovos_bus_client.handler import HandlerLifecycle
from ovos_bus_client.message import Message, dig_for_message
from ovos_bus_client.session import SessionManager, Session
from ovos_bus_client.util import get_message_lang
from ovos_spec_tools import (REGISTERED_TYPES, SpecMessage,
                             canonical_intent_topic, declared_slots,
                             standardize_lang)
from ovos_spec_tools.resources import read_resource_file
from ovos_config.config import Configuration
from ovos_config.locale import get_config_tz
from ovos_config.locations import get_xdg_cache_save_path
from ovos_config.locations import get_xdg_config_save_path
from ovos_config.locations import get_xdg_data_save_path
from ovos_spec_tools import (LocaleResources, MalformedResource,
                              MalformedTemplate, UnfilledSlot, find_lang_dir,
                              render,
                              iter_locale_dirs, strip_samples,
                              utterance_contains)
from ovos_number_parser import pronounce_number
from ovos_option_matcher_fuzzy import FuzzyOptionMatcherPlugin
from ovos_plugin_manager.agents import load_yesno_plugin, load_option_matcher_plugin
from ovos_plugin_manager.language import OVOSLangTranslationFactory, OVOSLangDetectionFactory
from ovos_plugin_manager.templates.agents import YesNoEngine, OptionMatcherEngine
from ovos_utils import camel_case_split
from ovos_utils.events import EventContainer, get_handler_name, create_wrapper
from ovos_utils.time import now_local
from ovos_utils.file_utils import FileWatcher
from ovos_utils.gui import get_ui_directories
from ovos_utils.json_helper import merge_dict
from ovos_utils.log import LOG, log_deprecation
from ovos_utils.process_utils import ProcessStatus, StatusCallbackMap
from ovos_utils.skills import get_non_properties
from ovos_utils.text_utils import remove_accents_and_punct
from ovos_yes_no import HeuristicYesNoEngine

from ovos_workshop.decorators import ContextGate, check_required_slots
from ovos_workshop.exceptions import DialogNotFound
from ovos_workshop.decorators.killable import AbortEvent, killable_event, AbortQuestion
from ovos_workshop.decorators.layers import IntentLayers
from ovos_workshop.filesystem import FileSystemAccess
from ovos_workshop.intents import IntentBuilder, Intent, munge_intent_parser, IntentServiceInterface
from ovos_workshop.settings import PrivateSettings
from ovos_workshop.skills._legacy_resources import (
    _LegacyLocaleResources, _LegacyResourcesMixin)
from ovos_workshop.skills.capabilities import get_skill_capabilities
from ovos_workshop.skills.util import join_word_list, simple_trace
from ovos_workshop.version import VERSION_MAJOR

# mycroft.skill.set_cross_context/remove_cross_context are pre-OVOS-CONTEXT-1
# compat broadcasts; deprecated shims are removed in the next MAJOR release.
_CROSS_CONTEXT_REMOVAL_VERSION = f"{VERSION_MAJOR + 1}.0.0"


def _typed_slots_map(message: Message) -> Dict[str, Any]:
    """The OVOS-INTENT-1 §5.6 `data.typed_slots` map, or an empty one."""
    typed_slots = message.data.get("typed_slots")
    return typed_slots if isinstance(typed_slots, dict) else {}


def _is_typed_entry(entry: Any) -> bool:
    """Whether `entry` has the OVOS-INTENT-1 §5.6 shape a consumer can read."""
    span = entry.get("span") if isinstance(entry, dict) else None
    return (isinstance(entry, dict) and "value" in entry
            and isinstance(entry.get("surface"), str)
            and isinstance(span, (list, tuple)) and len(span) == 2
            and all(isinstance(edge, int) for edge in span))


#: Set after the first naive scheduling datetime logs its warning (one per process).
_NAIVE_WHEN_WARNED = False


class OVOSSkill(_LegacyResourcesMixin):
    """
    Base class for OpenVoiceOS skills providing common behaviour and parameters
    to all Skill implementations.

    skill_launcher.py used to be skill_loader-py in mycroft-core

    for launching skills one can use skill_launcher.py to run them standalone
    (eg, docker)

    KwArgs:
        name (str): skill name - DEPRECATED
        skill_id (str): unique skill identifier
        bus (MycroftWebsocketClient): Optional bus connection
    """

    #: How many answered stop-ping rounds to remember, so the bookkeeping
    #: cannot grow without bound on a long-lived skill.
    STOP_PING_ROUNDS_REMEMBERED: int = 32

    def __init__(self, name: Optional[str] = None,
                 bus: Optional[MessageBusClient] = None,
                 resources_dir: Optional[str] = None,
                 settings: Optional[JsonStorage] = None,
                 gui: Optional[GUIInterface] = None,
                 skill_id: str = ""):
        """
        Create an OVOSSkill object.
        @param name: DEPRECATED skill_name
        @param bus: MessageBusClient to bind to skill
        @param resources_dir: optional root resource directory (else defaults to
            skill `root_dir`
        @param settings: Optional settings object, else defined in skill config
            path
        @param gui: Optional SkillGUI, else one is initialized
        @param skill_id: Unique ID for this skill
        """
        self.log = LOG  # a dedicated namespace will be assigned in _startup
        self._init_event = Event()
        self.name = name or self.__class__.__name__
        self.skill_id = skill_id  # set by SkillLoader, guaranteed unique
        self.private_settings = None

        # Get directory of skill source (__init__.py)
        self.root_dir = dirname(abspath(sys.modules[self.__module__].__file__))
        self.res_dir = resources_dir or self.root_dir

        # per-root LocaleResources cache, lazily populated by load_lang
        # so post-init res_dir mutations (legitimate for fixture-driven
        # tests and live-reload skills) take effect on the next access.
        self._lang_resources = {}
        # resource files already reported as malformed
        self._malformed_reported: Set[str] = set()

        self.gui = gui
        self._bus = bus
        self._enclosure = EnclosureAPI()

        # optional lang translation, lazy inited on first access
        self._lang_detector = None
        self._translator = None  # can be passed to solvers plugins

        # Core configuration
        self.config_core: Configuration = Configuration()

        self._settings = None
        self._initial_settings = settings or dict()
        self._settings_watchdog = None
        self._settings_lock = RLock()
        self._shutdown_lock = RLock()
        self._shutdown_done = False

        # Override to register a callback method that will be called every time
        # the skill's settings are updated. The referenced method should
        # include any logic needed to handle the updated settings.
        self.settings_change_callback = None

        # fully initialized when self.skill_id is set
        self._file_system = None

        self.reload_skill = True  # allow reloading (default True)

        self.events = EventContainer(bus)

        # Cached voc file contents
        self._voc_cache = {}

        # remembers the handler bound to each intent name so that
        # enable_intent() can rebind it after disable_intent() detaches it
        self._intent_handlers: Dict[str, callable] = {}

        # OVOS-INTENT-3 §auto-entity: tracks which (resource directory,
        # lang) pairs already had their locale .entity files auto-discovered
        # and registered, so a repeated load_lang() for the same pair
        # (reload/retrain) never double-emits the same entity registrations.
        self._auto_registered_entity_dirs = set()
        # OVOS-INTENT-3 §auto-entity: tracks (lang -> {entity_file, ...})
        # already sent to the intent service, keyed by the bare entity file
        # name (no extension). Shared by auto-discovery AND the explicit
        # register_entity_file() API so calling both for the same file (a
        # skill author who still calls register_entity_file() explicitly
        # for a file that was already auto-registered) replaces rather than
        # stacks a duplicate bus registration.
        self._registered_entity_files: Dict[str, Set[str]] = {}

        # names of the repeating schedules this skill made through
        # SCHEDULER-1, so that cancelling them all does not depend on
        # bookkeeping that belongs to the older interface
        self._repeating_schedules: Set[str] = set()
        self._scheduler_requests = Queue()
        self._scheduler_sender = None

        # Delegator classes
        self.event_scheduler = EventSchedulerInterface()
        self.intent_service = IntentServiceInterface()
        self.audio_service = None
        self.intent_layers = IntentLayers()

        # Skill Public API
        self.public_api: Dict[str, dict] = {}

        self._cq_handler = None
        self._cq_callback = None

        self.__responses = {}
        self.__validated_responses = {}
        self._threads = []  # for killable events decorator
        self._stop_ping_lock = RLock()
        self._stop_ping_rounds: List[Tuple[str, str]] = []

        # yay, following python best practices again!
        if self.skill_id and bus:
            self._startup(bus, self.skill_id)

    # skill developer abstract methods
    # devs are meant to override these
    def initialize(self):
        """
        Legacy method overridden by skills to perform extra init after __init__.
        Skills should now move any code in this method to `__init__`, after a
        call to `super().__init__`.
        """
        pass

    def get_intro_message(self) -> str:
        """
        Override to return a string to speak on first run. i.e. for post-install
        setup instructions.
        """
        return ""

    def stop(self):
        """
        Optional method implemented by subclass. Called when system or user
        requests `stop` to cancel current execution.
        """
        pass

    def shutdown(self):
        """
        Optional shutdown procedure implemented by subclass.

        This method is intended to be called during the skill process
        termination. The skill implementation must shut down all processes and
        operations in execution.
        """
        pass

    # skill class properties
    @property
    def is_fully_initialized(self) -> bool:
        """
        Determines if the skill has been fully loaded and setup.
        When True, all data has been loaded and all internal state
        and events set up.
        """
        return self._init_event.is_set()

    @property
    def _stop_is_implemented(self) -> bool:
        return self.__class__.stop is not OVOSSkill.stop or \
            self.__class__.stop_session is not OVOSSkill.stop_session

    def can_stop(self, message: Message) -> bool:
        """
        Determine whether the skill can be stopped at the current moment.

        If this method returns True, OVOS will call self.stop() when the user
        issues a command to stop the current activity.

        TIP: you can use SessionManager.get(message) if the skill is session aware

        Args:
            message (Message): The message context triggering the check.

        Returns:
            bool: True if the skill is currently performing an action that can be stopped; False otherwise.
        """
        if self._stop_is_implemented:
            raise NotImplementedError("All skills that implement self.stop or self.stop_session must also implement self.can_stop.")
        return False # if there isnt a stop method, we can be more lenient and not require can_stop to be implemented

    # safe skill_id/bus wrapper properties
    @property
    def alphanumeric_skill_id(self) -> str:
        """
        Skill id converted to only alphanumeric characters and "_".
        Non alphanumeric characters are converted to "_"
        """
        return ''.join(c if c.isalnum() else '_'
                       for c in str(self.skill_id))

    @property
    def lang_detector(self):
        """ language detector, lazy init on first access"""
        if not self._lang_detector:
            # if it's being used, there is no recovery, do not try: except:
            self._lang_detector = OVOSLangDetectionFactory.create(self.config_core)
        return self._lang_detector

    @lang_detector.setter
    def lang_detector(self, val):
        self._lang_detector = val

    @property
    def translator(self):
        """ language translator, lazy init on first access"""
        if not self._translator:
            # if it's being used, there is no recovery, do not try: except:
            self._translator = OVOSLangTranslationFactory.create(self.config_core)
        return self._translator

    @translator.setter
    def translator(self, val):
        self._translator = val

    @property
    def settings_path(self) -> str:
        """
        Absolute file path of this skill's `settings.json` (file may not exist)
        """
        return join(get_xdg_config_save_path(), 'skills', self.skill_id,
                    'settings.json')

    @property
    def settings(self) -> JsonStorage:
        """
        Get settings specific to this skill
        """
        if self._settings is not None:
            return self._settings
        else:
            self.log.warning('Skill not fully initialized. Only default values '
                             'can be set, no settings can be read or changed.'
                             f"to correct this add kwargs "
                             f"__init__(bus=None, skill_id='') "
                             f"to skill class {self.__class__.__name__} "
                             "You can only use self.settings after the call to 'super()'")
            self.log.error(simple_trace(traceback.format_stack()))
            return self._initial_settings

    @settings.setter
    def settings(self, val: dict):
        """
        Update settings specific to this skill
        """
        LOG.warning(
            "Skills are not supposed to override self.settings, expect breakage! Set individual dict keys instead")
        assert isinstance(val, dict)
        # init method
        if self._settings is None:
            self._initial_settings = val
            return
        with self._settings_lock:
            # ensure self._settings remains a JsonDatabase
            self._settings.clear()  # clear data
            self._settings.merge(val, skip_empty=False)  # merge new data

    @property
    def enclosure(self) -> EnclosureAPI:
        """
        Get an EnclosureAPI object to interact with hardware
        """
        if self._enclosure:
            return self._enclosure
        else:
            self.log.warning('Skill not fully initialized.'
                             f"to correct this add kwargs "
                             f"__init__(bus=None, skill_id='') "
                             f"to skill class {self.__class__.__name__}."
                             "You can only use self.enclosure after the call to 'super()'")
            self.log.error(simple_trace(traceback.format_stack()))
            raise Exception('Accessed OVOSSkill.enclosure in __init__')

    @property
    def file_system(self) -> FileSystemAccess:
        """
        Get an object that provides managed access to a local Filesystem.
        """
        if not self._file_system and self.skill_id:
            self._file_system = FileSystemAccess(join('skills', self.skill_id))
        if self._file_system:
            return self._file_system
        else:
            self.log.warning('Skill not fully initialized.'
                             f"to correct this add kwargs __init__(bus=None, skill_id='') "
                             f"to skill class {self.__class__.__name__} "
                             "You can only use self.file_system after the call to 'super()'")
            self.log.error(simple_trace(traceback.format_stack()))
            raise Exception('Accessed OVOSSkill.file_system in __init__')

    @file_system.setter
    def file_system(self, fs: FileSystemAccess):
        """
        Provided mainly for backwards compatibility with derivative
        MycroftSkill classes. Skills are advised against redefining the file
        system directory.
        @param fs: new FileSystemAccess object to use
        """
        LOG.warning(f"Skill manually overriding file_system path to: {fs.path}")
        self._file_system = fs

    @property
    def bus(self) -> MessageBusClient:
        """
        Get the MessageBusClient bound to this skill
        """
        if self._bus:
            return self._bus
        else:
            self.log.warning('Skill not fully initialized.'
                             f"to correct this add kwargs "
                             f"__init__(bus=None, skill_id='') "
                             f"to skill class {self.__class__.__name__} "
                             "You can only use self.bus after the call to 'super()'")
            self.log.error(simple_trace(traceback.format_stack()))
            raise Exception('Accessed OVOSSkill.bus in __init__')

    @bus.setter
    def bus(self, value: MessageBusClient):
        """
        Set the MessageBusClient bound to this skill. Note that setting this
        after init may have unintended consequences as expected events might
        not be registered. Call `bind` to connect a new MessageBusClient.
        @param value: new MessageBusClient object
        """
        from ovos_bus_client import MessageBusClient
        from ovos_utils.fakebus import FakeBus
        if isinstance(value, (MessageBusClient, FakeBus)):
            self._bus = value
        else:
            raise TypeError(f"Expected a MessageBusClient, got: {type(value)}")

    # magic properties -> depend on message.context / Session
    def render_dialog(self, name: str, data: Optional[dict] = None) -> str:
        """
        Render a random phrase from a ``.dialog`` file for the skill's current
        language, filling ``{name}`` slots from ``data``.

        A dialog the specification rejects is rendered by the legacy
        renderer, which renders the real sentence.

        Args:
            name: a dialog file name (no extension)
            data: values used to fill the dialog's named slots
        Returns:
            A rendered phrase ready for text-to-speech.
        Raises:
            DialogNotFound: no ``.dialog`` file for `name` exists in the
                current language, or no renderer can produce a sentence
                from it.
        """
        lang = self._resource_lang
        try:
            phrases = self._locale_resources.load_dialog(name, lang)
        except FileNotFoundError:
            raise DialogNotFound(name, lang, self._dialog_dirs()) from None
        except MalformedResource as err:
            self._report_malformed(err)
            raise DialogNotFound(name, lang, self._dialog_dirs(),
                                 reason=str(err)) from None
        vocabularies = self._guarded(
            self._locale_resources.vocabularies, lang, default={})
        try:
            return render(phrases, slots=data, vocabularies=vocabularies)
        except MalformedTemplate as err:
            whole = str(err)
        # the specification rejects part of the dialog: speak the phrases that
        # are valid for this data
        valid, rejected = [], []
        for phrase in phrases:
            try:
                valid.append(render([phrase], slots=data,
                                    vocabularies=vocabularies))
            except MalformedTemplate as err:
                rejected.append(f"{phrase!r}: {err}")
            except UnfilledSlot:
                rejected.append(f"{phrase!r}: slot not filled")
        found = self._guarded(self._locale_resources.find, name, ".dialog",
                              lang, default=None)
        self._report_malformed(MalformedTemplate(
            f"dialog {found or name} is rejected as a whole ({whole})"
            f"{': ' + '; '.join(rejected) if rejected else ''}"))
        if not valid:
            raise DialogNotFound(name, lang, self._dialog_dirs(),
                                 reason=f"no phrase of {found} renders ({whole}): "
                                        f"{'; '.join(rejected)}")
        return random.choice(valid)

    def _dialog_or_text(self, dialog: str, data: Optional[dict]) -> str:
        """Render a prompt that is a dialog name or the text itself.

        `get_response`, `ask_yesno` and `ask_selection` take "a dialog
        resource or string". A skill builds a prompt at runtime, for example
        from a generated sentence or a search result, so no dialog file can
        exist for it: when no locale ships a file with that name, the text is
        the prompt. A dialog that exists but cannot render in the current
        language still raises.
        """
        try:
            return self.render_dialog(dialog, data)
        except DialogNotFound as err:
            if err.reason or self._ships_dialog(dialog):
                raise
            return dialog

    def _ships_dialog(self, name: str) -> bool:
        """Whether any locale of any language ships a ``name.dialog`` file."""
        target = f"{name}.dialog".lower()
        return any(file.lower() == target
                   for directory in self._dialog_dirs()
                   for _, _, files in os.walk(directory)
                   for file in files)

    def _dialog_dirs(self) -> List[str]:
        """The locale directories a dialog is looked up in, user first."""
        dirs = [join(self.res_dir, "locale"),
                join(dirname(dirname(abspath(__file__))), "locale")]
        if self.skill_id:
            dirs.insert(0, join(get_xdg_data_save_path(), "resources",
                                self.skill_id))
        return dirs

    def _report_malformed(self, err: Exception):
        """Log a malformed resource once; the resource is then skipped."""
        reason = str(err)
        if reason not in self._malformed_reported:
            self._malformed_reported.add(reason)
            self.log.warning(f"malformed resource: {reason}")

    def _guarded(self, loader: Callable, *args, default):
        """Call a resource loader; a malformed resource is reported and
        `default` is returned in its place."""
        try:
            return loader(*args)
        except (MalformedResource, MalformedTemplate) as err:
            self._report_malformed(err)
            return default

    @property
    def system_unit(self) -> str:
        """
        Get the units preference (metric vs imperial)
        This info may come from Session, eg, injected by a voice satellite
        """
        sess = SessionManager.get()
        return sess.system_unit

    @property
    def date_format(self) -> str:
        """
        Get the date format (DMY/MDY/YMD)
        This info may come from Session, eg, injected by a voice satellite
        """
        sess = SessionManager.get()
        return sess.date_format

    @property
    def time_format(self) -> str:
        """
        Get the time format (half vs full)
        This info may come from Session, eg, injected by a voice satellite
        """
        sess = SessionManager.get()
        return sess.time_format

    @property
    def location(self) -> dict:
        """
        Get the JSON data struction holding location information.
        This info may come from Session, eg, injected by a voice satellite
        """
        sess = SessionManager.get()
        return sess.location_preferences

    @property
    def location_pretty(self) -> Optional[str]:
        """
        Get a speakable city from the location config if available
        This info may come from Session, eg, injected by a voice satellite
        """
        loc = self.location
        if type(loc) is dict and loc['city']:
            return loc['city']['name']
        return None

    @property
    def location_timezone(self) -> Optional[str]:
        """
        Get the timezone code, such as 'America/Los_Angeles'
        This info may come from Session, eg, injected by a voice satellite
        """
        sess = SessionManager.get()
        return sess.timezone

    @property
    def lang(self) -> str:
        """
        Get the current language as a BCP-47 language code.
        This info may come from Session, eg, injected by a voice satellite
        """
        lang = self.core_lang
        message = dig_for_message()
        if message:
            lang = get_message_lang(message)
        return standardize_lang(lang)

    @property
    def _locale_resources(self) -> LocaleResources:
        """Workshop-internal :class:`~ovos_spec_tools.LocaleResources` for
        ``self.res_dir`` — the language-agnostic loader that backs every
        per-language resource lookup on this skill.

        Delegates to :meth:`load_lang` (which caches per root_directory)
        so post-init changes to ``self.res_dir`` are picked up on the
        next access. Workshop-internal code (``render_dialog``,
        ``voc_match``, ``_locate_lang_file`` etc.) goes through this
        attribute; the public, deprecated :attr:`resources` shim lives
        on :class:`_LegacyResourcesMixin` and still hands back the
        legacy :class:`SkillResources`.
        """
        return self.load_lang(self.res_dir)

    @property
    def _resource_lang(self) -> str:
        """Language for resource-file lookups (``.dialog``, ``.voc``,
        ``.intent``, ``.entity``).

        Defaults to the message-context language (:attr:`lang`). Subclasses
        that decouple resource language from query language — see
        :class:`~ovos_workshop.skills.auto_translatable.UniversalSkill`,
        whose dialogs/vocab are authored in ``internal_language`` while
        ``self.lang`` reflects the incoming query language — override this
        single property and the resource lookups follow.
        """
        return self.lang

    @property
    def core_lang(self) -> str:
        """
        Get the configured default language as a BCP-47 language code.
        """
        return standardize_lang(self.config_core.get("lang", "en-US"))

    @property
    def secondary_langs(self) -> List[str]:
        """
        Get the configured secondary languages; resources will be loaded for
        these languages to provide support for multilingual input, in addition
        to `core_lang`. A skill may override this method to specify which
        languages intents are registered in.
        """
        return [standardize_lang(lang) for lang in self.config_core.get('secondary_langs', [])
                if lang != self.core_lang]

    @property
    def native_langs(self) -> List[str]:
        """
        Languages natively supported by this skill (ie, resource files available
        and explicitly supported). This is equivalent to normalized
        secondary_langs + core_lang.
        """
        valid = set([standardize_lang(lang) for lang in self.secondary_langs
                     if lang != self.core_lang] + [self.core_lang])
        return list(valid)

    # resource file loading
    def load_lang(self, root_directory: Optional[str] = None,
                  lang: Optional[str] = None) -> LocaleResources:
        """
        Get a :class:`~ovos_spec_tools.LocaleResources` object for this skill.

        The first load of a (resource directory, language) pair also registers
        every shipped ``.entity`` file for that language, so it reaches the
        matcher before any ``.intent`` template that references it.

        @param root_directory: skill root path containing ``locale/``
            (default res_dir)
        @param lang: language whose ``.entity`` files are auto-registered
            (default every native language); the returned object serves every
            language
        @return: LocaleResources object
        """
        root_directory = root_directory or self.res_dir
        lang = standardize_lang(lang) if lang else None
        key = (root_directory, lang)
        if key not in self._lang_resources:
            workshop_locale = join(dirname(dirname(abspath(__file__))),
                                   "locale")
            user_locale = join(get_xdg_data_save_path(), "resources",
                               self.skill_id) if self.skill_id else None
            self._lang_resources[key] = _LegacyLocaleResources(
                skill_locale=join(root_directory, "locale"),
                core_locale=workshop_locale,
                user_locale=user_locale,
                skill_directory=root_directory, skill_id=self.skill_id,
                default_lang=lambda: self._resource_lang, lang=lang)
        resources = self._lang_resources[key]
        for entity_lang in [standardize_lang(lang)] if lang \
                else self.native_langs:
            self._auto_register_entity_files(entity_lang, resources,
                                             root_directory)
        return resources

    def load_data_files(self, root_directory: Optional[str] = None):
        """
        Called by the skill loader to load file-based vocabulary.

        ``.dialog``/``.intent``/``.entity`` resources are loaded lazily by
        :class:`~ovos_spec_tools.LocaleResources`; only ``.voc`` resources need
        eager registration with the adapt intent service.

        Args:
            root_directory (str): root folder to use when loading files.
        """
        root_directory = root_directory or self.res_dir
        self.load_vocab_files(root_directory)
        # legacy adapt-style regex resources; silent unless a .rx exists
        self.load_regex_files(root_directory)

    def load_vocab_files(self, root_directory: Optional[str] = None):
        """Load ``.voc`` files under the skill's ``locale/`` directory and
        register each template line as a single keyword with adapt — the
        canonical entity comes first, aliases canonicalize to it
        (OVOS-INTENT-2 §4.3 / :func:`ovos_spec_tools.keyword_form`)."""
        resources = self.load_lang(root_directory or self.res_dir)
        for lang in self.native_langs:
            keywords = self._guarded(
                lambda: list(resources.vocabulary_keywords(lang)),
                default=[])
            for voc_name, entity, aliases in keywords:
                # keep exact filename case: str.title() lowercases multi-word
                # CamelCase names ("HelloWorldKeyword" -> "Helloworldkeyword"),
                # breaking IntentBuilder.require() lookups (#485/#491)
                vocab_type = self.alphanumeric_skill_id + voc_name
                self.intent_service.register_keyword(
                    vocab_type, entity, aliases, lang)

    def load_regex_files(self, root_directory: Optional[str] = None) -> None:
        """Load and register ``.rx`` regex files for adapt-style intents.

        Walks ``<root>/locale/<lang>/`` for ``.rx`` files; each non-blank,
        non-``#``-comment line is one regex pattern. ``(?P<name>...)`` named
        groups are prefixed with the skill's alphanumeric id so they don't
        collide across skills. Each pattern is then registered with the adapt
        intent service.

        Self-contained — does NOT go through the deprecated
        ``ovos_workshop.resource_files`` module. A ``DeprecationWarning`` is
        emitted **only when a ``.rx`` file is actually loaded**, so skills that
        ship none stay quiet.

        .. deprecated::
            For new intents that need pattern matching, prefer
            **padatious-style template intents** with named ``{slots}`` — they
            generalize, localize, and are part of the OVOS formal
            specifications. ``.rx`` regex support remains for legacy adapt
            skills; its deprecation is independent of (and outlives) the
            broader ``resource_files`` deprecation, and its removal is not
            yet scheduled.
        """
        root_directory = root_directory or self.res_dir
        loaded_any = False
        # iter_locale_dirs walks `<root>/locale/` and filters subdirs against
        # native_langs via closest_lang — so an `en-US/` tree is picked up for
        # a skill that declares `en` (or `en-GB`) as native.
        for lang_norm, locale_dir in iter_locale_dirs(
                root_directory, native_langs=self.native_langs):
            for directory, _, files in os.walk(locale_dir):
                for file_name in files:
                    if not file_name.endswith(".rx"):
                        continue
                    rx_path = join(directory, file_name)
                    self.log.info(
                        f"loading regex file {rx_path!r} for lang "
                        f"{lang_norm!r}")
                    with open(rx_path, "r", encoding="utf-8-sig") as f:
                        for line in f:
                            pattern = line.strip()
                            if not pattern or pattern.startswith("#"):
                                continue
                            re.compile(pattern)  # validate before handing off
                            # register_adapt_regex (IntentServiceInterface)
                            # already prefixes "(?P<" group names with the
                            # skill's alphanumeric id via munge_regex — do
                            # not pre-munge here, it would double-prefix and
                            # mismatch the keyword Adapt intents require()
                            self.intent_service.register_adapt_regex(
                                pattern, lang_norm)
                            loaded_any = True
        if loaded_any:
            msg = ("OVOSSkill.load_regex_files: .rx regex resources are "
                   "deprecated. Prefer padatious-style template intents with "
                   "named {slots} — they generalize, localize, and are part "
                   "of the OVOS formal specifications. The .rx loader is kept "
                   "for legacy adapt skills; consider migrating.")
            warnings.warn(msg, DeprecationWarning, stacklevel=2)
            LOG.warning(f"DEPRECATION: {msg}")

    def _locate_lang_file(self, name: str, ext: str,
                          lang: str) -> Optional[str]:
        """Resolve the on-disk path of a spec resource file.

        Delegates to :meth:`ovos_spec_tools.LocaleResources.find` — the same
        override-precedence + closest-language walk that backs every loader
        call on this skill.
        """
        if name.endswith(ext):
            name = name[:-len(ext)]
        try:
            path = self._locale_resources.find(name, ext, lang)
        except MalformedResource as err:
            path = self._pick_duplicate(name, ext, lang, err)
        return str(path) if path is not None else None

    @staticmethod
    def _shallowest(paths: List[Path], lang_dir: Path) -> Path:
        """The shallowest of several same-named files; a tie goes to the last
        path in sorted order."""
        depth = min(len(p.relative_to(lang_dir).parts) for p in paths)
        return sorted(p for p in paths
                      if len(p.relative_to(lang_dir).parts) == depth)[-1]

    def _pick_duplicate(self, name: str, ext: str, lang: str,
                        err: MalformedResource) -> Optional[Path]:
        """Choose one of several files that share a base name.

        OVOS-INTENT-2 §2 makes such a skill malformed and does not name a
        winner. Released skills ship duplicates, so the shallowest file wins
        and a tie goes to the last path in sorted order. The result does not
        depend on the order the file system lists directories in.
        """
        lang_dir = find_lang_dir(join(self.res_dir, "locale"), lang)
        found = sorted(p for p in lang_dir.rglob(f"{name}{ext}")
                       if p.is_file()) if lang_dir else []
        if len(found) < 2:
            self._report_malformed(err)
            return None
        winner = self._shallowest(found, lang_dir)
        others = ", ".join(str(p) for p in found if p != winner)
        self._report_malformed(MalformedResource(
            f"duplicate resource {name + ext!r}: using {winner}, "
            f"ignoring {others}"))
        return winner

    # skill object setup
    def _handle_first_run(self) -> None:
        """
        The very first time a skill is run, speak a provided intro_message.
        """
        intro = self.get_intro_message()
        if intro:
            # supports .dialog files for easy localization
            # the intro may be text built at runtime; with no .dialog file
            # the text itself is spoken, a dialog that cannot render raises
            try:
                self.speak_dialog(intro)
            except DialogNotFound as err:
                if err.reason:
                    raise
                self.speak(intro)

    def _check_for_first_run(self) -> None:
        """
        Determine if this is the very first time a skill is run by looking for
        `__mycroft_skill_firstrun` in skill settings.
        """
        first_run = self.settings.get("__mycroft_skill_firstrun", True)
        if first_run:
            self.log.info("First run of " + self.skill_id)
            self._handle_first_run()
            self.settings["__mycroft_skill_firstrun"] = False
            self.settings.store()

    def on_ready_status(self) -> None:
        LOG.info(f'{self.skill_id} is ready.')
        # OVOS-INTENT-4 SS8.6/SS10: re-announce alongside the readiness
        # registrations, so a manifest rebuilt after a core restart
        # (the skill process survives it) recovers this skill's
        # capabilities without a full reload.
        self.bus.emit(Message('ovos.skill.loaded',
                              {"skill_id": self.skill_id,
                               "capabilities": get_skill_capabilities(self)},
                              {"skill_id": self.skill_id}))

    def on_error_status(self, e: str = 'Unknown') -> None:
        LOG.exception(f'{self.skill_id} initialization failed: {e}')

    def on_stopping_status(self) -> None:
        LOG.info(f'{self.skill_id} is shutting down...')

    def on_alive_status(self) -> None:
        LOG.debug(f'{self.skill_id} is alive.')

    def on_started_status(self) -> None:
        LOG.debug(f'{self.skill_id} started.')

    def _startup(self, bus: MessageBusClient, skill_id: str = ""):
        """
        Startup the skill. Connects the skill to the messagebus, loads resources
        and finally calls the skill's "intialize" method.
        @param bus: MessageBusClient to bind to skill
        @param skill_id: Unique skill identifier, defaults to skill path for
            legacy skills and python entrypoints for modern skills
        """
        if self.is_fully_initialized:
            self.log.warning(f"Tried to initialize {self.skill_id} multiple "
                             f"times, ignoring")
            return

        callbacks = StatusCallbackMap(on_ready=self.on_ready_status,
                                      on_error=self.on_error_status,
                                      on_stopping=self.on_stopping_status,
                                      on_alive=self.on_alive_status,
                                      on_started=self.on_started_status)

        # NOTE: this method is called by SkillLoader
        # it is private to make it clear to skill devs they should not touch it
        try:
            # set the skill_id
            self.skill_id = skill_id or basename(self.root_dir)

            self.intent_service.set_id(self.skill_id)
            self.event_scheduler.set_id(self.skill_id)
            self.enclosure.set_id(self.skill_id)

            # initialize anything that depends on skill_id
            self.log = LOG.create_logger(self.skill_id)
            self._init_settings()

            # initialize anything that depends on the messagebus
            self.bind(bus)
            self.status = ProcessStatus(self.skill_id, self.bus, callback_map=callbacks)
            self.status.set_alive()
            if not self.gui:
                self._init_skill_gui()
            self.load_data_files()
            self._register_skill_json()
            self._register_decorated()
            self._register_app_launcher()
            self._register_resting_screen()

            self.status.set_started()
            # run skill developer initialization code
            self.initialize()
            self._check_for_first_run()
            self._init_event.set()
            self.status.set_ready()
        except Exception as e:
            self.status.set_error(str(e))
            # If an exception occurs, attempt to clean up the skill
            try:
                self.default_shutdown()
            except Exception as e2:
                LOG.debug(e2)
            raise e

    def _register_skill_json(self, root_directory: Optional[str] = None):
        """Load skill.json metadata found under locale folder and register with homescreen"""
        root_directory = root_directory or self.res_dir
        for lang in self.native_langs:
            lang_dir = find_lang_dir(join(root_directory, "locale"), lang)
            json_path = join(lang_dir, "skill.json") if lang_dir else None
            if not json_path or not isfile(json_path):
                self.log.debug(f'No skill.json loaded for {lang}')
            else:
                with open(json_path) as f:
                    skill_meta = json.load(f)
                utts = skill_meta.get("examples", [])
                if utts:
                    self.log.info(f"Registering example utterances with homescreen for lang: {lang} - {utts}")
                    self.bus.emit(Message("homescreen.register.examples",
                                          {"skill_id": self.skill_id, "utterances": utts, "lang": lang}))

    def _register_app_launcher(self):
        # register app launcher if registered via decorator
        for attr_name in get_non_properties(self):
            method = getattr(self, attr_name)
            if hasattr(method, 'homescreen_app_icon'):
                name = getattr(method, 'homescreen_app_name')
                event = f"{self.skill_id}.{name or method.__name__}.homescreen.app"
                icon = getattr(method, 'homescreen_app_icon')
                name = name or self.__skill_id2name
                LOG.debug(f"homescreen app registered: {name} - '{event}'")
                self._register_homescreen_app(icon=icon,
                                              name=name or self.skill_id,
                                              event=event)
                self.add_event(event, method, speak_errors=False)

    @property
    def __skill_id2name(self) -> str:
        """helper to make a nice string out of a skill_id"""
        return (self.skill_id.split(".")[0].replace("_", " ").
                replace("-", " ").replace("skill", "").title().strip())

    def _init_settings(self):
        """
        Set up skill settings. Defines settings in the specified file path,
        handles any settings passed to skill init, and starts watching the
        settings file for changes.
        """
        self.log.debug(f"initializing skill settings for {self.skill_id}")

        # NOTE: lock is disabled due to usage of deepcopy and to allow json
        # serialization
        self._settings = JsonStorage(self.settings_path, disable_lock=True)
        with self._settings_lock:
            if self._initial_settings and not self.is_fully_initialized:
                self.log.warning("Copying default settings values defined in "
                                 "__init__ \nto correct this add kwargs "
                                 "__init__(bus=None, skill_id='') "
                                 f"to skill class {self.__class__.__name__}")
                for k, v in self._initial_settings.items():
                    if k not in self._settings:
                        self._settings[k] = v
            self._initial_settings = copy(self.settings)

        # starting on ovos-core 0.0.8 a bus event is emitted
        # all settings.json files are monitored for changes in ovos-core
        self.add_event("ovos.skills.settings_changed", self._handle_settings_changed, speak_errors=False)

        if self._monitor_own_settings:
            self._start_filewatcher()

    @property
    def _monitor_own_settings(self):
        # account for isolated setups where skills might not share a filesystem with core
        return self.settings.get("monitor_own_settings", False)

    def _handle_settings_changed(self, message: Message) -> None:
        """external signal to reload skill settings"""
        skill_id = message.data.get("skill_id", "")
        if skill_id == self.skill_id:
            self._handle_settings_file_change(self._settings.path)

    def _init_skill_gui(self):
        """
        Set up the SkillGUI for this skill and connect relevant bus events.
        """
        self.gui = SkillGUI(self)
        self.gui.setup_default_handlers()

    def _register_homescreen_app(self, icon: str, name: str, event: str):
        """Internal: register a homescreen app entry. Public-name shim
        :meth:`register_homescreen_app` lives in :class:`_LegacyResourcesMixin`.
        Reached only when a ``@homescreen_app``-tagged handler exists, so the
        deprecation signal fires only for skills actually using the feature.
        """
        msg = ("homescreen apps are deprecated; the homescreen concept is "
               "being removed and @homescreen_app / register_homescreen_app "
               "will be dropped. No replacement is planned.")
        warnings.warn(msg, DeprecationWarning, stacklevel=2)
        LOG.warning(f"DEPRECATION: {msg}")
        # this path is hardcoded in ovos_gui.constants and follows XDG spec
        # we use it to ensure resource availability between containers
        # it is the only path assured to be accessible both by skills and GUI
        GUI_CACHE_PATH = get_xdg_cache_save_path('ovos_gui')

        full_icon_path = f"{self.res_dir}/gui/{icon}"
        if not os.path.isfile(full_icon_path):
            self.log.error(f"failed to register homescreen app, icon does not exist: {full_icon_path}")
            return
        os.makedirs(f"{GUI_CACHE_PATH}/{self.skill_id}", exist_ok=True)
        shared_path = f"{GUI_CACHE_PATH}/{self.skill_id}/{icon}"
        shutil.copy(full_icon_path, shared_path)

        self.bus.emit(Message("homescreen.register.app",
                              {"skill_id": self.skill_id,
                               "icon": shared_path,
                               "name": name,
                               "event": event}))

    def _register_resting_screen(self):
        """Internal: scan for ``@resting_screen_handler``-tagged methods and
        wire them up. Public-name shim :meth:`register_resting_screen` lives
        in :class:`_LegacyResourcesMixin` and warns; this implementation
        stays here because the framework calls it during ``_startup`` for
        every skill — emitting on the internal path would flood the logs
        of every skill, not just those using a resting screen.

        Only emits the per-handler log line when a tagged handler is found,
        so skills not using the feature stay silent.
        """
        for attr_name in get_non_properties(self):
            handler = getattr(self, attr_name)
            if hasattr(handler, 'resting_handler'):
                msg = ("resting screens are deprecated; the homescreen "
                       "concept is being removed and @resting_screen_handler "
                       "/ register_resting_screen will be dropped. No "
                       "replacement is planned.")
                warnings.warn(msg, DeprecationWarning, stacklevel=2)
                LOG.warning(f"DEPRECATION: {msg}")
                resting_name = handler.resting_handler
                LOG.debug(f"{get_handler_name(handler)} is a resting screen, name: {resting_name}")

                def register(message=None, name=resting_name):
                    self.log.info(f'Registering resting screen {name} for {self.skill_id}.')
                    self.bus.emit(Message("homescreen.manager.add",
                                          {"name": name, "id": self.skill_id}))

                register()  # initial registering

                self.add_event("homescreen.manager.reload.list", register, speak_errors=False)

                def wrapper(message, cb=handler):
                    if message.data["homescreen_id"] == self.skill_id:
                        LOG.debug(f"triggering resting_handler: {get_handler_name(cb)}")
                        cb(message)

                self.add_event("homescreen.manager.activate.display", wrapper, speak_errors=False)

                def shutdown_handler(message):
                    if message.data["id"] == self.skill_id:
                        msg = message.forward("homescreen.manager.remove",
                                              {"id": self.skill_id})
                        self.bus.emit(msg)

                self.add_event("mycroft.skills.shutdown", shutdown_handler, speak_errors=False)
                break  # TODO - if multiple decorators are used what do? this is not deterministic

    def _start_filewatcher(self):
        """
        Start watching settings for file changes if settings file exists and
        there isn't already a FileWatcher watching it
        """
        if self._settings_watchdog is None and isfile(self._settings.path):
            self._settings_watchdog = \
                FileWatcher([self._settings.path],
                            callback=self._handle_settings_file_change,
                            ignore_creation=True)

    def _register_decorated(self):
        """
        Register all intent handlers that are decorated with an intent.

        Looks for all functions that have been marked by a decorator
        and read the intent data from them.  The intent handlers aren't the
        only decorators used.  Skip properties as calling getattr on them
        executes the code which may have unintended side effects
        """
        for attr_name in get_non_properties(self):
            method = getattr(self, attr_name)
            if hasattr(method, 'intents'):
                for intent in getattr(method, 'intents'):
                    voc_blacklist = method.voc_blacklist if hasattr(method, 'voc_blacklist') else []
                    requires_context = method.requires_context if hasattr(method, 'requires_context') else []
                    excludes_context = method.excludes_context if hasattr(method, 'excludes_context') else []
                    required_slots = method.required_slots.get(intent) \
                        if hasattr(method, 'required_slots') and isinstance(intent, str) else None
                    self.register_intent(intent, method, voc_blacklist=voc_blacklist,
                                         requires_context=requires_context,
                                         excludes_context=excludes_context,
                                         required_slots=required_slots)

            if hasattr(method, 'intent_files'):
                requires_context = method.requires_context if hasattr(method, 'requires_context') else []
                excludes_context = method.excludes_context if hasattr(method, 'excludes_context') else []
                for intent_file in getattr(method, 'intent_files'):
                    self.register_intent_file(intent_file, method,
                                              requires_context=requires_context,
                                              excludes_context=excludes_context)

            if hasattr(method, 'intent_layers'):
                for layer_name, intent_files in \
                        getattr(method, 'intent_layers').items():
                    self.register_intent_layer(layer_name, intent_files)

            # TODO support for multiple common query handlers (?)
            if hasattr(method, 'common_query'):
                self._cq_handler = method
                self._cq_callback = method.cq_callback
                LOG.debug(f"Registering common query handler for: {self.skill_id} - callback: {self._cq_callback}")
                self.__handle_common_query_ping(Message("ovos.common_query.ping"))

    def bind(self, bus: MessageBusClient):
        """
        Register MessageBusClient with skill.
        @param bus: MessageBusClient to bind to skill and internal objects
        """
        if bus:
            self._bus = bus
            self.events.set_bus(bus)
            self.intent_service.set_bus(bus)
            self.event_scheduler.set_bus(bus)
            self._enclosure.set_bus(bus)
            self._register_system_event_handlers()
            self._register_public_api()
            self.intent_layers.bind(self)
            self.audio_service = OCPInterface(self.bus)
            self.private_settings = PrivateSettings(self.skill_id)

    def __handle_common_query_ping(self, message):
        if self._cq_handler:
            # announce skill to common query pipeline
            # ARCHITECTURE common-query.md §6.2: pong carries `utterance` and
            # `can_answer` alongside the pre-spec `skill_id`/`is_classic_cq`
            # keys; the consumer (ovos-common-query-pipeline-plugin) only
            # reads the latter today, so both are kept for one stable cycle.
            self.bus.emit(message.reply("ovos.common_query.pong",
                                        {"utterance": message.data.get("utterance", ""),
                                         "skill_id": self.skill_id,
                                         "can_answer": True,
                                         "is_classic_cq": False},
                                        {"skill_id": self.skill_id}))

    def __handle_query_action(self, message: Message):
        """
        If this skill's response was spoken to the user, this method is called.

        @param message: `question:action` message
        """
        # backwards compat, for older common query pipeline versions
        if not self._cq_callback or message.data["skill_id"] != self.skill_id:
            # Not for this skill!
            return
        # call the correct handler as if cq was updated
        message.msg_type += f".{self.skill_id}"
        self.bus.emit(message)

    def __handle_skill_query_action(self, message: Message):
        LOG.debug(f"common query callback for: {self.skill_id}")
        lang = get_message_lang(message)
        answer = message.data.get("answer") or message.data.get("callback_data", {}).get("answer")
        self.speak(answer)

        if not self._cq_callback:
            LOG.debug(f"no common query callback registered for: {self.skill_id}")
            return  # nothing to do

        # Inspect the callback signature
        callback_signature = signature(self._cq_callback)
        params = callback_signature.parameters

        # Check if the first parameter is 'self' (indicating it's an instance method)
        if len(params) > 0 and list(params.keys())[0] == 'self':
            # Instance method: pass 'self' as the first argument
            self._cq_callback(self, message.data["phrase"], answer, lang)
        else:
            # Static method or function: don't pass 'self'
            self._cq_callback(message.data["phrase"], answer, lang)

    def _emit_common_query_response(self, message: Message, data: dict):
        """
        Emit a Common Query answer.

        `question:query` (the dispatch topic this handler is bound to)
        contains a ':' and therefore has no `.response` counterpart.
        The OVOS-MSG-1 §5.3 `response()` shorthand is undefined on it, so
        the answer names `question:query.response` and derives it with
        `reply()`. That is the topic ovos-common-query-pipeline-plugin
        subscribes to.
        COMMON-QUERY-1's spec topic (`ovos.common_query.response`) uses
        an `utterance` payload key, not the `phrase` key this handler
        produces, so it is not emitted here; full adoption of the spec
        topic and payload shape lands together with the plugin.

        @param message: the `question:query` Message being answered
        @param data: the answer payload (searching/answer/no-answer leg)
        """
        self.bus.emit(message.reply("question:query.response", data))

    def __handle_question_query(self, message: Message):
        """
        Handle an incoming question query.

        @param message: Message with matched query 'phrase'
        """
        if not self._cq_handler:
            return
        lang = get_message_lang(message)
        search_phrase = message.data["phrase"]
        message.context["skill_id"] = self.skill_id
        LOG.debug(f"Common QA: {self.skill_id}")
        # First, notify the requestor that we are attempting to handle
        # (this extends a timeout while this skill looks for a match)
        self._emit_common_query_response(message, {"phrase": search_phrase,
                                                     "skill_id": self.skill_id,
                                                     "searching": True})
        answer = None
        confidence = 0
        try:
            answer, confidence = self._cq_handler(search_phrase, lang) or (None, 0)
            LOG.debug(f"Common QA {self.skill_id} result: {answer}")
        except Exception:
            LOG.exception(f"Failed to get answer from {self._cq_handler}")

        if answer and confidence >= 0.5:
            self._emit_common_query_response(message, {"phrase": search_phrase,
                                                         "skill_id": self.skill_id,
                                                         "answer": answer,
                                                         "callback_data": {"answer": answer},  # so we get it in callback
                                                         "conf": confidence})
        else:
            # Signal we are done (can't handle it)
            self._emit_common_query_response(message, {"phrase": search_phrase,
                                                         "skill_id": self.skill_id,
                                                         "searching": False})

    def _register_public_api(self):
        """
        Find and register API methods decorated with `@api_method` and create a
        messagebus handler for fetching the api info if any handlers exist.
        """

        def wrap_method(fn):
            """Boilerplate for returning the response to the sender."""

            def wrapper(message):
                result = fn(*message.data['args'], **message.data['kwargs'])
                message.context["skill_id"] = self.skill_id
                self.bus.emit(message.response(data={'result': result}))

            return wrapper

        methods = [attr_name for attr_name in get_non_properties(self)
                   if hasattr(getattr(self, attr_name), '__name__')]

        for attr_name in methods:
            method = getattr(self, attr_name)

            if hasattr(method, 'api_method'):
                doc = method.__doc__ or ''
                name = method.__name__
                self.public_api[name] = {
                    'help': doc,
                    'type': f'{self.skill_id}.{name}',
                    'func': method
                }
        for key in self.public_api:
            if ('type' in self.public_api[key] and
                    'func' in self.public_api[key]):
                self.log.debug(f"Adding api method: "
                               f"{self.public_api[key]['type']}")

                # remove the function member since it shouldn't be
                # reused and can't be sent over the messagebus
                func = self.public_api[key].pop('func')
                self.add_event(self.public_api[key]['type'],
                               wrap_method(func), speak_errors=False)

        if self.public_api:
            self.add_event(f'{self.skill_id}.public_api',
                           self._send_public_api, speak_errors=False)

    def _decline_converse(self, message: Message):
        """Per-skill converse ping (pre-broadcast cores): a plain skill never converses."""
        self.bus.emit(message.reply("skill.converse.pong",
                                    data={"skill_id": self.skill_id, "can_handle": False},
                                    context={"skill_id": self.skill_id}))

    def _decline_converse_broadcast(self, message: Message):
        """OVOS-CONVERSE-1 §4.2 broadcast ping: answer "no" when this skill is a candidate this round (§9.3)."""
        session = SessionManager.get(message)
        if any(h.get("skill_id") == self.skill_id for h in session.converse_handlers):
            self.bus.emit(message.reply("ovos.converse.pong",
                                        data={"skill_id": self.skill_id, "result": False},
                                        context={"skill_id": self.skill_id}))

    def _register_system_event_handlers(self):
        """
        Register default messagebus event handlers
        """
        self.add_event('mycroft.stop', self._handle_session_stop, speak_errors=False)
        # STOP-1 §4.3: the targeted `<skill_id>:stop` dispatch is a handler
        # dispatch like any other and MUST go through the same
        # mycroft.skill.handler.{start,complete,error} done-signal as every
        # other dispatched handler, so ovos-core's dispatcher can resolve its
        # in-flight entry instead of falling back to the PIPELINE-1 §8.3
        # timeout. `mycroft.stop` above is the broadcast fallback, not a
        # dispatch topic, and keeps no lifecycle signal.
        self.add_event(f"{self.skill_id}.stop", self._handle_session_stop,
                       handler_info='mycroft.skill.handler', is_intent=True,
                       intent_name='stop', speak_errors=False)
        # STOP-1 §4.2: the stop cascade polls on the broadcast
        # `ovos.stop.ping`, and "a handler that does not subscribe to
        # `ovos.stop.ping` is treated as `can_handle: false` for that round".
        self.add_event(SpecMessage.STOP_PING.value, self._handle_stop_ack,
                       speak_errors=False)
        # Pre-spec cores emit only the per-skill twin; they get the same answer.
        self.add_event(f"{self.skill_id}.stop.ping", self._handle_stop_ack, speak_errors=False)
        self.add_event(f"{self.skill_id}.converse.get_response", self.__handle_get_response, speak_errors=False)
        # A plain skill cannot converse, but ovos-core polls every dispatched skill and waits for ALL of them (up
        # to 0.5 s per utterance). Until ovos-workshop #339 every skill answered "no"; restore that so the round
        # closes at once. ConversationalSkill binds these topics with real answers, so bind only without it.
        if not callable(getattr(self, "can_converse", None)):
            self.add_event("ovos.converse.ping", self._decline_converse_broadcast, speak_errors=False)
            self.add_event(f"{self.skill_id}.converse.ping", self._decline_converse, speak_errors=False)

        self.add_event('mycroft.skill.enable_intent', self.handle_enable_intent, speak_errors=False)
        self.add_event('mycroft.skill.disable_intent', self.handle_disable_intent, speak_errors=False)
        self.add_event('mycroft.skill.set_cross_context', self.handle_set_cross_context, speak_errors=False)
        self.add_event('mycroft.skill.remove_cross_context', self.handle_remove_cross_context, speak_errors=False)
        self.add_event('mycroft.skills.settings.changed', self.handle_settings_change, speak_errors=False)

        self.add_event('question:query', self.__handle_question_query, speak_errors=False)
        self.add_event("ovos.common_query.ping", self.__handle_common_query_ping, speak_errors=False)
        self.add_event(f'question:action.{self.skill_id}', self.__handle_skill_query_action,
                       handler_info='mycroft.skill.handler', is_intent=True, speak_errors=False)
        self.add_event('question:action', self.__handle_query_action, speak_errors=False)

        # homescreen might load after this skill and miss the original events
        self.add_event("homescreen.metadata.get", self.handle_homescreen_loaded, speak_errors=False)

    def _send_public_api(self, message: Message):
        """
        Respond with the skill's public api.
        @param message: `{self.skill_id}.public_api` Message
        """
        message.context["skill_id"] = self.skill_id
        self.bus.emit(message.response(data=self.public_api))

    # skill internal events amd lifecycle
    def _handle_settings_file_change(self, path: str):
        """
        Handle a FileWatcher notification that a file was changed. Reload
        settings, call `self.settings_change_callback` if defined, and upload
        changes if a backend is configured.
        @param path: Modified file path
        """
        if path != self._settings.path:
            LOG.debug(f"Ignoring non-settings change")
            return
        if self._settings:
            with self._settings_lock:
                self._settings.reload()
        if self.settings_change_callback:
            try:
                self.settings_change_callback()
            except Exception as e:
                self.log.exception("settings change callback failed, "
                                   f"file changes not handled!: {e}")

    def handle_settings_change(self, message: Message):
        """
        Update settings if a remote settings changes apply to this skill.

        The skill settings downloader uses a single API call to retrieve the
        settings for all skills to limit the number API calls.
        A "mycroft.skills.settings.changed" event is emitted for each skill
        with settings changes. Only update this skill's settings if its remote
        settings were among those changed.
        """
        remote_settings = message.data.get(self.skill_id)
        if remote_settings is not None:
            self.log.info('Updating settings for skill ' + self.skill_id)
            self.settings.update(**remote_settings)
            self.settings.store()
            if self.settings_change_callback is not None:
                try:
                    self.settings_change_callback()
                except Exception as e:
                    self.log.exception("settings change callback failed, "
                                       f"remote changes not handled!: {e}")
            self._start_filewatcher()

    def _handle_stop_ack(self, message: Message):
        """
        Inform the stop cascade whether this skill has stoppable activity.
        Individual skills implement `self.can_stop` to enable or disable
        stop support.

        Answers both the STOP-1 §4.2 broadcast `ovos.stop.ping` and the
        pre-spec per-skill `{self.skill_id}.stop.ping` a core may still emit
        alongside it. A core emitting both gets exactly one pong, because
        PIPELINE-1 §4.5 keys a poll round by the `session_id` of
        `context.session` and by `context.utterance_id` (§9.1.1) — both
        propagate to either ping by reply derivation — and "where one
        candidate answers twice in a round, the first valid pong wins". A
        pre-spec core that stamps no `utterance_id` names no round, so its
        pings are answered one for one, exactly as before.
        @param message: `ovos.stop.ping` or `{self.skill_id}.stop.ping` Message
        """
        utterance_id = message.context.get("utterance_id")
        if utterance_id is not None:
            round_id = (SessionManager.get(message).session_id, utterance_id)
            with self._stop_ping_lock:
                if round_id in self._stop_ping_rounds:
                    return
                self._stop_ping_rounds.append(round_id)
                del self._stop_ping_rounds[:-self.STOP_PING_ROUNDS_REMEMBERED]
        self.bus.emit(message.reply(
            SpecMessage.STOP_PONG.value,
            data={"skill_id": self.skill_id,
                  "can_handle": self.can_stop(message)},
            context={"skill_id": self.skill_id}))

    def stop_session(self, session: Session) -> bool:
        """skill devs can subclass this if their skill is Session aware
        skill should stop any activity related to this session
        this is called before self.stop , if it returns True  the global self.stop won't be called"""
        return False

    def _handle_session_stop(self, message: Message):
        message.context['skill_id'] = self.skill_id
        sess = SessionManager.get(message)
        data = {"skill_id": self.skill_id, "result": False}
        try:
            data["result"] = self.stop_session(sess) or self.stop() or False
        except Exception as e:
            data["error"] = str(e)
            self.log.exception(f'Failed to stop skill: {self.skill_id}: {e}')
        if data["result"]:
            self.__responses[sess.session_id] = None # abort any ongoing get_response
        self.bus.emit(message.reply(f"{self.skill_id}.stop.response", data))

    def default_shutdown(self):
        """
        Parent function called internally to shut down everything.
        1) Call skill.stop() to allow skill to clean up any active processes
        2) Store skill settings and remove file watchers
        3) Shutdown skill GUI to clear any active pages
        4) Shutdown the event_scheduler and remove any pending events
        5) Emit `detach_skill` Message to notify skill is shut down

        NOTE: this method does NOT call `skill.shutdown()`. The skill-specific
        `shutdown()` hook is invoked separately by the caller (eg.
        `SkillManager.unload_skill()` or `__del__`), before/around this method.

        This method is re-entrant: `SkillManager.unload_skill()` may call it
        explicitly on the main thread while `__del__` calls it again from
        whichever thread drops the last reference to the skill instance and
        triggers garbage collection. The second call is a no-op.
        """
        with self._shutdown_lock:
            if self._shutdown_done:
                self.log.debug(f"default_shutdown already ran for "
                               f"{self.skill_id}, skipping")
                return
            self._shutdown_done = True
        if hasattr(self, 'status'):
            self.status.set_stopping()
        try:
            # Allow skill to handle `stop` actions before shutting things down
            self.stop()
        except Exception as e:
            self.log.error(f'Failed to stop skill: {self.skill_id}: {e}',
                           exc_info=True)

        try:
            self.settings_change_callback = None

            # Store settings. A skill that never finished init (no `bus`/
            # `skill_id` kwargs, so `_startup` never ran) never got a
            # `_settings` object either; the `settings` property would log
            # a full stack trace for that expected case, so check the
            # private attribute instead of going through the property.
            if self._settings is not None and self.settings != self._initial_settings:
                self.settings.store()
            if self._settings_watchdog:
                self._settings_watchdog.shutdown()
        except Exception as e:
            self.log.error(f"Failed to store settings for {self.skill_id}: {e}")

        try:
            # Clear skill from gui
            if self.gui is not None:
                self.gui.shutdown()
        except Exception as e:
            self.log.error(f"Failed to shutdown gui for {self.skill_id}: {e}")

        try:
            # removing events
            if self.event_scheduler:
                if not self.repeating_schedules_outlive_the_skill:
                    self.cancel_all_repeating_events()
                self._stop_sending_to_scheduler()
                self.event_scheduler.shutdown()
                self.events.clear()
        except Exception as e:
            self.log.error(f"Failed to remove events for {self.skill_id}: {e}")

        # Same as settings above: a skill that never finished init has no
        # bound bus, and the `bus` property raises for that expected case
        # after logging a full stack trace. Nothing attached to a bus, so
        # there is nothing to tell `detach_skill`.
        if self._bus:
            self.bus.emit(
                Message('detach_skill', {'skill_id': self.skill_id},
                        {'skill_id': self.skill_id}))

    def __del__(self):
        # GC can drop the last reference after an explicit unload already
        # tore the skill down. Read the flag, never set it: on the ordinary
        # path nothing unloaded the skill and the full teardown runs here.
        if hasattr(self, '_shutdown_lock'):
            with self._shutdown_lock:
                if self._shutdown_done:
                    return
        skill_id = getattr(self, 'skill_id', self.__class__.__name__)
        try:
            self.shutdown()
        except Exception as e:
            LOG.error(f"Skill specific shutdown for '{skill_id}' encountered an error: {e}")
        try:
            self.default_shutdown()
        except Exception as e:
            LOG.error(f"Default shutdown for skill '{skill_id}' encountered an error: {e}")

    def detach(self):
        """
        Detach all intents for this skill from the intent_service.
        """
        for (name, _) in self.intent_service:
            name = f'{self.skill_id}:{name}'
            self.intent_service.remove_intent(name)

    # intents / resource files management
    def register_intent_layer(self, layer_name: str,
                              intent_list: List[Union[IntentBuilder, Intent, str]]):
        """
        Register a named intent layer.
        @param layer_name: Name of intent layer to add
        @param intent_list: List of intents associated with the intent layer
        """
        for intent_file in intent_list:
            if isinstance(intent_file, str):
                name = canonical_intent_topic(f'{self.skill_id}:{intent_file}')
            else:
                if hasattr(intent_file, "build"):
                    try:
                        intent_file = intent_file.build()
                    except Exception as e:
                        LOG.warning(f"Failed to build intent {intent_file}: {e}")
                try:
                    name = intent_file.name
                except AttributeError:
                    name = f'{self.skill_id}:{intent_file}'

            self.intent_layers.update_layer(layer_name, [name])

    def register_intent(self, intent_parser: Union[IntentBuilder, Intent, str],
                        handler: callable, voc_blacklist: Optional[List[str]] = None,
                        requires_context: Optional[List[ContextGate]] = None,
                        excludes_context: Optional[List[ContextGate]] = None,
                        required_slots: Optional[List[str]] = None):
        """
        Register an Intent with the intent service.

        Args:
            intent_parser: Intent, IntentBuilder object or padatious intent
                           file to parse utterance for the handler.
            handler (func): function to register with intent
            requires_context: OVOS-CONTEXT-1 §6 gating declaration - each
                              entry a bare key string or a
                              {"key":..., "scope":...} mapping. Carried on
                              both file-intent and adapt-intent
                              registration payloads; adapt has no
                              OVOS-CONTEXT-1-aware matcher of its own, but
                              per §6 "an engine that does not implement
                              OVOS-CONTEXT-1 ignores them and matches as
                              if absent"
            excludes_context: OVOS-CONTEXT-1 §6.1 gating declaration, same
                              entry shape and carry-through as
                              requires_context
            required_slots: OVOS-INTENT-3 §5.3 required slot names, for a
                            padatious intent file only
        """
        if isinstance(intent_parser, str):
            if not intent_parser.endswith('.intent'):
                raise ValueError
            return self.register_intent_file(intent_parser, handler, voc_blacklist,
                                             requires_context=requires_context,
                                             excludes_context=excludes_context,
                                             required_slots=required_slots)
        if required_slots:
            raise ValueError("required_slots applies to a template (.intent) "
                             f"intent, not to {intent_parser!r}")
        return self._register_adapt_intent(intent_parser, handler,
                                           requires_context=requires_context,
                                           excludes_context=excludes_context)

    def register_intent_file(self, intent_file: str, handler: callable,
                             voc_blacklist: Optional[List[str]] = None,
                             requires_context: Optional[List[ContextGate]] = None,
                             excludes_context: Optional[List[ContextGate]] = None,
                             required_slots: Optional[List[str]] = None):
        """Register an Intent file with the intent service.

        For example:
            food.order.intent:
                Order some {food}.
                Order some {food} from {place}.
                I'm hungry.
                Grab some {food} from {place}.

        Optionally, you can also use <register_entity_file>
        to specify some examples of {food} and {place}

        In addition, instead of writing out multiple variations
        of the same sentence you can write:
            food.order.intent:
                (Order | Grab) some {food} (from {place} | ).
                I'm hungry.

        Args:
            intent_file: name of file that contains example queries
                         that should activate the intent.  Must end with
                         '.intent'
            handler:     function to register with intent
            requires_context: OVOS-CONTEXT-1 §6 gating declaration - each
                              entry a bare key string or a
                              {"key":..., "scope":...} mapping
            excludes_context: OVOS-CONTEXT-1 §6.1 gating declaration, same
                              entry shape as requires_context
            required_slots: OVOS-INTENT-3 §5.3 bare slot names the engine
                            MUST extract for a match. A locale whose
                            templates do not declare each of them is not
                            registered.
        """
        required_slots = check_required_slots(required_slots)
        # OVOS-MSG-1 §2.1.1: the dispatch topic is `<skill_id>:<intent_name>`.
        # The intent NAME is the author's label for the intent, not the name of
        # the file the samples came from, so the `.intent` authoring extension
        # never reaches the wire.
        name = canonical_intent_topic(f'{self.skill_id}:{intent_file}')
        for lang in self.native_langs:
            filename = self._locate_lang_file(intent_file, ".intent", lang)
            if filename is None:
                self.log.error(f'Unable to find "{intent_file}"')
                continue

            samples = self._guarded(read_resource_file, Path(filename),
                                    default=None)
            if samples is None:
                continue

            disallowed_strings = []
            for enty in voc_blacklist or []:
                disallowed_strings += self.voc_list(enty, lang=lang)

            # OVOS-INTENT-2 §4.3: a sibling "<intent>.blacklist" locale file
            # lists slot-free phrases that should suppress this intent from
            # matching. The file is optional — skip when absent.
            blacklist_name = intent_file.rsplit(".", 1)[0]
            try:
                disallowed_strings += self._guarded(
                    self._locale_resources.load_blacklist, blacklist_name,
                    lang, default=[])
            except FileNotFoundError:
                pass  # no sibling ".blacklist" file -> nothing to suppress

            # OVOS-INTENT-2 §4.5: a sibling "<intent>.required" locale file
            # lists keywords of which one must occur for this intent to match
            try:
                required_keywords = self._guarded(
                    self._locale_resources.load_required_keywords,
                    blacklist_name, lang, default=[])
            except FileNotFoundError:
                required_keywords = []  # no sibling ".required" file

            # OVOS-INTENT-2 §4.3: for each "{slot}" the template declares, a
            # sibling "<slot>.blacklist" locale file lists slot-value
            # exclusions — values that MUST NOT bind to that slot (the
            # canonical use is keeping anaphoric pronouns out of a referential
            # slot). Keyed by slot name so consuming engines can drop them.
            # A typed slot (OVOS-INTENT-1 §3.4 `{type:name}`) is keyed by its
            # bare name, the prefix is not part of it.
            slot_blacklist = {}
            for slot in declared_slots(samples):
                try:
                    phrases = self._guarded(
                        self._locale_resources.load_blacklist, slot, lang,
                        default=[])
                except FileNotFoundError:
                    phrases = []
                if phrases:
                    slot_blacklist[slot] = phrases

            # OVOS-INTENT-1 §3.7: supply the sibling vocabularies so an inline
            # <name> reference in the .intent is baked into the samples before
            # they are sent to the engine over the bus
            self.intent_service.register_template(
                name, samples, lang,
                blacklisted_words=disallowed_strings,
                slot_blacklist=slot_blacklist,
                required_keywords=required_keywords,
                vocabs=self._guarded(self._locale_resources.vocabularies,
                                     lang, default={}),
                requires_context=requires_context,
                excludes_context=excludes_context,
                required_slots=required_slots)
        if handler:
            # keyed canonically (bare, no "<skill_id>:" prefix, no ".intent"
            # suffix) so enable_intent()/disable_intent() can look the
            # handler up by the SAME spelling the registry itself uses
            # (registered_intents/detached_intents), regardless of whether
            # the caller re-supplies the author-facing ".intent"-suffixed
            # name or the canonical one.
            self._intent_handlers[name.split(':', 1)[1]] = handler
            # canonical topic only. A skill container running an old workshop
            # still listens on the `.intent`-suffixed twin; that compat is the
            # bus layer's job (`ovos_spec_tools.intent_topics`), not the
            # skill's. IMPORTANT: this makes `websocket.modernize` /
            # OVOS_BUS_MODERNIZE load-bearing, not a namespace convenience --
            # a suffixed dispatch from an old core/pipeline only reaches this
            # canonical-only binding if bus-client's receive-side
            # modernization (2.8.0a1+) translates it first. Disabling
            # modernize on a skill container running this workshop version
            # silently drops that dispatch (see PR #500 "Deployment note").
            self.add_event(name, handler, 'mycroft.skill.handler',
                           activation=True, is_intent=True)

    def register_entity_file(self, entity_file: str):
        """
        Register an Entity file with the intent service.

        An Entity file lists the exact values that an entity can hold.
        For example:
            ask.day.intent:
                Is it {weekend}?
            weekend.entity:
                Saturday
                Sunday

        NOTE: every ``.entity`` file shipped in a skill's locale resources is
        now registered automatically (see `_auto_register_entity_files`) the
        first time that language's resources are loaded - calling this
        method explicitly is no longer required for the entity to reach the
        matcher. It remains useful to register an entity from a non-standard
        location/name, or to force (re-)registration explicitly.

        Args:
            entity_file (string): name of file that contains examples of an
                                  entity.
        """
        if entity_file.endswith('.entity'):
            entity_file = entity_file.replace('.entity', '')
        for lang in self.native_langs:
            self._register_entity_file_for_lang(
                entity_file, lang, self._locale_resources)

    def _register_entity_file_for_lang(self, entity_file: str, lang: str,
                                       resources: LocaleResources,
                                       resolved_path: Optional[Path] = None):
        """
        Register a single Entity file with the intent service for a single
        language. Shared by the explicit `register_entity_file` API and the
        automatic per-lang discovery in `_auto_register_entity_files`.

        @param entity_file: name of file that contains examples of an
                            entity, without the ".entity" extension.
        @param lang: language code the `resources` object was loaded for.
        @param resources: LocaleResources serving `lang`, as returned by
                          `load_lang`.
        @param resolved_path: when the caller already holds the resolved
                              file path (auto-discovery via `Path.rglob`),
                              pass it directly instead of re-deriving it.
                              `LocaleResources.find` matches a BASE NAME, so
                              re-searching by a subfolder-qualified name
                              like "sub/pet" (from a discovered
                              "sub/pet.entity") never matches anything and
                              silently fails to register. Auto-discovery
                              already resolved the real path while walking
                              the language directory, so skip the lookup.
        """
        if resolved_path is not None:
            filename = str(resolved_path)
        else:
            found = self._guarded(resources.find, entity_file, ".entity",
                                  lang, default=None)
            if found is None:
                self.log.error(f'Unable to find "{entity_file}"')
                return
            filename = str(found)
        # IDEMPOTENCY: keyed by the resolved file path (not the caller's
        # spelling of `entity_file`) so auto-discovery and an explicit
        # register_entity_file() call for the same file - or two auto
        # passes that both resolve to the same file - register it once.
        # Mirrors register_template()'s own "replace, don't stack" contract.
        already = self._registered_entity_files.setdefault(lang, set())
        if filename in already:
            return
        already.add(filename)
        # The entity name IS the wire contract: consumers resolve a
        # "{slot}" in a template by the raw slot token, so the name must
        # stay "<skill_id>:<entity>". A former "_<md5(entity_file)>"
        # suffix here made every file-registered entity unresolvable
        # (padatious fell back to an unconstrained wildcard slot). The
        # hash disambiguated nothing either - "<skill_id>:" already
        # namespaces the entity and the hash was taken over the file name
        # that is already part of the key.
        name = f"{self.skill_id}:{basename(entity_file)}"
        samples = self._guarded(read_resource_file, Path(filename),
                                default=None)
        if samples is None:
            return
        # A bare '#' line is a mycroft-core-era convention some authors used
        # to mean "any digit sequence goes here" (see e.g. old date-time
        # skill forks). `read_resource_file` treats any line starting with
        # '#' as a COMMENT and drops it before `samples` is built (verified:
        # `read_resource_file(Path(".../offset.entity"))` on a file
        # containing only "#" returns `[]`) - so it is never registered as a
        # wildcard *or* a literal; it silently vanishes, and the slot it was
        # meant to fill gets whatever samples (if any) survive from other
        # lines. Detect it from the raw file (samples already dropped it) and
        # flag it - a skill relying on it is shipping a dead entity file.
        try:
            raw_lines = Path(filename).read_text(encoding="utf-8").splitlines()
        except OSError:
            raw_lines = []
        if any(line.strip() == '#' for line in raw_lines):
            log_deprecation(
                f'{self.skill_id}: entity file "{entity_file}.entity" '
                f'({lang}) contains a bare "#" placeholder line. '
                f'read_resource_file() treats it as a COMMENT and drops it - '
                f'it is NOT registered as a digit wildcard (or anything '
                f'else). Replace it with real example values.',
                "0.1.0")
        # OVOS-INTENT-2 §4.3: a sibling "<entity>.blacklist" locale file
        # lists slot-free phrases that MUST NOT fill the {slot} this entity
        # supplies (e.g. a "person.blacklist" of pronouns keeps "he" out of
        # the {person} slot)
        try:
            blacklist = self._guarded(resources.load_blacklist,
                                      basename(entity_file), lang, default=[])
        except FileNotFoundError:
            blacklist = []
        self.intent_service.register_entity(name, samples, lang,
                                            blacklisted_words=blacklist)

    def _auto_register_entity_files(self, lang: str,
                                    resources: Optional[LocaleResources] = None,
                                    root_directory: Optional[str] = None):
        """
        Auto-discover and register every ".entity" file shipped in this
        skill's locale resources for `lang`.

        Historically `register_entity_file` was opt-in: a skill author had
        to call it explicitly for each entity, and it was easy to ship a
        ".entity" file that a ".intent" template referenced by slot name but
        that was never actually registered, silently degrading matching.
        There is no good reason to leave a shipped entity file unregistered,
        so every discovered file is registered unconditionally - no
        filtering by declared slot names.

        Ordering: this is called from `load_lang` on the first load for
        `lang`, and `register_intent_file` always calls
        `load_lang` before it builds/emits its own template for that lang.
        That means every auto-registered entity for a lang reaches the bus
        strictly before (never after) the first intent template for that
        same lang - the same batch/ordering guarantee `register_intent_file`
        already relies on for manually-registered entities.

        Idempotency: `_auto_registered_entity_dirs` guards repeated calls
        (every `load_lang`, tests, or a future reload path) from
        double-emitting. The guard is per (resource directory, lang): a skill
        pointed at a new `res_dir` registers that directory's entity files.

        Can be disabled entirely via the "skills" section of mycroft.conf:
            {"skills": {"auto_register_entity_files": false}}
        """
        root_directory = root_directory or self.res_dir
        key = (root_directory, lang)
        if key in self._auto_registered_entity_dirs:
            return
        self._auto_registered_entity_dirs.add(key)

        if not self.config_core.get("skills", {}).get(
                "auto_register_entity_files", True):
            return

        lang_dir = find_lang_dir(join(root_directory, "locale"), lang)
        if lang_dir is None:
            return

        resources = resources or self.load_lang(root_directory, lang)
        by_name: Dict[str, List[Path]] = {}
        for path in sorted(lang_dir.rglob("*.entity")):
            by_name.setdefault(path.name, []).append(path)
        for paths in by_name.values():
            path = self._shallowest(paths, lang_dir)
            if len(paths) > 1:
                self._report_malformed(MalformedResource(
                    f"duplicate resource {path.name!r}: using {path}, "
                    f"ignoring "
                    f"{', '.join(str(p) for p in paths if p != path)}"))
            # name relative to the language directory, extension stripped,
            # so entities in subfolders keep a stable/readable name
            # (e.g. "sub/foo" for "<lang_dir>/sub/foo.entity")
            entity_file = str(path.relative_to(lang_dir).with_suffix(''))
            try:
                self._register_entity_file_for_lang(entity_file, lang,
                                                    resources,
                                                    resolved_path=path)
            except Exception as e:
                self.log.exception(
                    f'{self.skill_id}: failed to auto-register entity file '
                    f'"{path}" ({lang}): {e}')

    def register_vocabulary(self, entity: str, entity_type: str,
                            lang: Optional[str] = None):
        """
        Register a word to a keyword
        @param entity: word to register
        @param entity_type: Intent handler entity name to associate entity to
        @param lang: language of `entity` (default self.lang)
        """
        keyword_type = self.alphanumeric_skill_id + entity_type
        lang = standardize_lang(lang or self._resource_lang)
        self.intent_service.register_keyword(keyword_type, entity,
                                             lang=lang)

    def register_regex(self, regex_str: str, lang: Optional[str] = None):
        """
        Register a new regex.
        @param regex_str: Regex string to add
        @param lang: language of regex_str (default self.lang)
        """
        self.log.debug('registering regex string: ' + regex_str)
        re.compile(regex_str)  # validate regex
        self.intent_service.register_adapt_regex(
            regex_str, lang=standardize_lang(lang or self._resource_lang))

    # event/intent registering internal handlers
    def handle_homescreen_loaded(self, message: Message):
        """homescreen loaded, we should re-register any metadata we want to provide"""
        self._register_skill_json()
        self._register_app_launcher()

    def handle_enable_intent(self, message: Message):
        """
        Listener to enable a registered intent if it belongs to this skill.
        @param message: `mycroft.skill.enable_intent` Message
        """
        intent_name = message.data['intent_name']
        # registered_intents/detached_intents are keyed by the bare canonical
        # name; the bus payload may still carry the author-facing
        # ".intent"-suffixed spelling, so canonicalize before comparing --
        # otherwise the suffixed form never matches and this silently no-ops.
        canonical = canonical_intent_topic(
            f'{self.skill_id}:{intent_name}').split(':', 1)[1]
        for (name, _) in self.intent_service.detached_intents:
            if name == canonical:
                return self.enable_intent(intent_name)

    def handle_disable_intent(self, message: Message):
        """
        Listener to disable a registered intent if it belongs to this skill.
        @param message: `mycroft.skill.disable_intent` Message
        """
        intent_name = message.data['intent_name']
        canonical = canonical_intent_topic(
            f'{self.skill_id}:{intent_name}').split(':', 1)[1]
        for (name, _) in self.intent_service.registered_intents:
            if name == canonical:
                return self.disable_intent(intent_name)

    def handle_set_cross_context(self, message: Message):
        """
        Add global context to the intent service.

        CONTEXT-1 §5.0: "There is no context-mutation topic: no participant
        emits a Message whose purpose is to announce a context change to the
        orchestrator or to another component." So this listener MUST NOT
        write `session.intent_context`: the shared entry is already on the
        session that `set_cross_skill_context` wrote, and a second write per
        receiving skill would make one logical mutation into N+1 session
        pushes that race each other at handler completion (SESSION-2 §2.6).

        It therefore reaches the `original_key is None` path, which touches
        only the pre-CONTEXT-1 adapt `session.context` field through the
        legacy `add_context` topic, and never `Session.set_intent_context`.
        A skill's own `set_context` call keeps its private session write;
        only this broadcast-driven path gives it up.

        @param message: `mycroft.skill.set_cross_context` Message
        """
        context = message.data.get('context')
        word = message.data.get('word')
        origin = message.data.get('origin')

        if not isinstance(context, str):
            raise ValueError('Context should be a string')
        if not isinstance(word, str):
            raise ValueError('Word should be a string')
        # munged exactly as `set_context` munges it, so the adapt-engine key
        # is unchanged; `original_key` is left unset, which is what keeps
        # this off the session.
        self.intent_service._set_context(
            self.alphanumeric_skill_id + context, word, origin)

    def handle_remove_cross_context(self, message: Message):
        """
        Remove global context from the intent service.

        The mirror of :meth:`handle_set_cross_context`: adapt
        `session.context` only, never `session.intent_context`.

        @param message: `mycroft.skill.remove_cross_context` Message
        """
        context = message.data.get('context')
        if not isinstance(context, str):
            raise ValueError('context should be a string')
        self.intent_service._remove_context(
            self.alphanumeric_skill_id + context)

    def _on_event_start(self, message: Message, handler_info: str,
                        skill_data: dict, activation: Optional[bool] = None):
        """
        Indicate that the skill handler is starting.

        Emits ``mycroft.skill.handler.start`` (when ``handler_info`` is set).

        .. note::
           ``mycroft.skill.handler.{start,complete,error}`` are an **internal
           ovos-workshop → ovos-core synchronization signal** — workshop's way
           of reporting "I started / ended / errored" running a handler. They
           are **explicitly NOT part of any OVOS specification**; they are an
           implementation detail that exists only because skills (ovos-workshop)
           run in a **separate process** from the orchestrator (ovos-core). If
           core manipulated skill objects directly, in-process, this bus
           round-trip would not be needed.

           ovos-core consumes these as a private *done-signal* to emit the
           authoritative PIPELINE-1 §8 handler-lifecycle trio
           (``ovos.intent.handler.{start,complete,error}``). The legacy
           ``mycroft.skill.handler.*`` names are permanently ovos-workshop
           event-wrapper signals and do **not** bridge to the spec namespace
           (ovos-spec-tools MIGRATION_MAP deliberately excludes the trio).

        activation  (bool, optional): activate skill if True,
                                      deactivate if False,
                                      do nothing if None
        """
        if handler_info:
            # internal workshop->core done-signal (see docstring); NOT a spec
            # topic -> emits mycroft.skill.handler.start. Delegated to the
            # shared ovos-bus-client HandlerLifecycle util (DRY; same topic,
            # payload and context["skill_id"] as before).
            HandlerLifecycle(self.bus, message, skill_id=self.skill_id,
                             data=skill_data, handler_info=handler_info).start()

    def _on_event_end(self, message: Message, handler_info: str,
                      skill_data: dict, is_intent: bool = False):
        """
        Store settings (if changed) and indicate that the skill handler has
        completed.
        """
        if handler_info:
            # internal workshop->core done-signal (see _on_event_start); NOT a
            # spec topic -> emits mycroft.skill.handler.complete. Delegated to
            # the shared HandlerLifecycle util (same topic/payload/context).
            HandlerLifecycle(self.bus, message, skill_id=self.skill_id,
                             data=skill_data, handler_info=handler_info).complete()
        # PIPELINE-1 §9.5: the orchestrator owns the end marker; skills never emit it.

        try:
            if self.settings != self._initial_settings:
                self.settings.store()
                self._initial_settings = copy(self.settings)
        except Exception as e:
            LOG.error(f"Failed to update settings.json : {e}")

    def _on_event_error(self, error: str, message: Message, handler_info: str,
                        skill_data: dict, speak_errors: bool):
        """Speak and log the error."""
        # Convert "MyFancySkill" to "My Fancy Skill" for speaking
        handler_name = camel_case_split(self.name)
        msg_data = {'skill': handler_name}
        try:
            speech = self.render_dialog('skill_error', msg_data)
        except DialogNotFound as err:
            # no error dialog in this language: log it, speak nothing
            self.log.error(err)
            speech = None
        if speak_errors and speech:
            self.speak(speech)
        self.log.exception(error)
        if handler_info:
            # internal workshop->core done-signal (see _on_event_start); NOT a
            # spec topic -> emits mycroft.skill.handler.error. Delegated to the
            # shared HandlerLifecycle util, which merges {"exception": repr(...)}
            # into the payload (same topic/payload/context as before). The util
            # deliberately does NOT speak; the spoken-error UX above stays here.
            message = message or Message("")
            HandlerLifecycle(self.bus, message, skill_id=self.skill_id,
                             data=skill_data, handler_info=handler_info).error(error)

    def _register_adapt_intent(self,
                               intent_parser: Union[IntentBuilder, Intent, str],
                               handler: callable,
                               requires_context: Optional[List[ContextGate]] = None,
                               excludes_context: Optional[List[ContextGate]] = None):
        """
        Register an adapt intent.

        Args:
            intent_parser: Intent object to parse utterance for the handler.
            handler (func): function to register with intent
            requires_context: OVOS-CONTEXT-1 §6 gating declaration. Adapt
                              does not itself gate on it (it has no
                              OVOS-CONTEXT-1-aware matcher), but the
                              declaration still rides the registration
                              payload per CONTEXT-1 §6: "an engine that
                              does not implement OVOS-CONTEXT-1 ignores
                              them and matches as if absent."
            excludes_context: OVOS-CONTEXT-1 §6.1 gating declaration, same
                              carry-through as requires_context
        """
        if hasattr(intent_parser, "build"):
            try:
                intent_parser = intent_parser.build()
            except Exception as e:
                LOG.warning(f"Failed to build intent parser {intent_parser}: {e}")

        # Default to the handler's function name if none given
        is_anonymous = not intent_parser.name
        name = intent_parser.name or handler.__name__
        if is_anonymous:
            # Find a good name
            original_name = name
            nbr = 0
            while name in self.intent_service.intent_names:
                nbr += 1
                name = f'{original_name}{nbr}'
        elif name in self.intent_service.intent_names and \
                not self.intent_service.intent_is_detached(name):
            raise ValueError(f'The intent name {name} is already taken')

        # internal path: bypass the deprecated register_adapt_intent shim's warning
        self.intent_service._adapt.munge_intent_parser(intent_parser, name,
                                                        self.intent_service.skill_id)
        self.intent_service.register_intent(name, intent_parser,
                                            requires_context=requires_context,
                                            excludes_context=excludes_context)
        if handler:
            self._intent_handlers[name] = handler
            self.add_event(intent_parser.name, handler,
                           'mycroft.skill.handler',
                           activation=True, is_intent=True)

    # skill developer facing utils
    def speak(self, utterance: str, expect_response: bool = False,
              wait: Union[bool, int] = False, meta: Optional[dict] = None):
        """Speak a sentence.

        Args:
            utterance (str):        sentence mycroft should speak
            expect_response (bool): set to True if Mycroft should listen
                                    for a response immediately after
                                    speaking the utterance.
            wait (Union[bool, int]): set to True to block while the text
                                     is being spoken for 15 seconds. Alternatively, set
                                     to an integer to specify a timeout in seconds.
            meta:                   Information of what built the sentence.
        """
        # registers the skill as being active
        meta = meta or {}
        meta['skill'] = self.skill_id

        data = {'utterance': utterance,
                'expect_response': expect_response,
                'meta': meta,
                'lang': self.lang}

        # grab message that triggered speech so we can keep context
        message = dig_for_message()
        m = message.forward(SpecMessage.SPEAK, data) if message \
            else Message(SpecMessage.SPEAK, data)
        m.context["skill_id"] = self.skill_id

        # update any auto-translation metadata in message.context
        if "translation_data" in meta:
            tx_data = merge_dict(m.context.get("translation_data", {}),
                                 meta["translation_data"])
            m.context["translation_data"] = tx_data

        self.bus.emit(m)

        if wait:
            timeout = 15 if isinstance(wait, bool) else wait
            sess = SessionManager.get(m)
            sess.is_speaking = True
            SessionManager.wait_while_speaking(timeout, sess)

    def speak_dialog(self, key: str, data: Optional[dict] = None,
                     expect_response: bool = False, wait: Union[bool, int] = False,
                     render_callback: Optional[Callable[[str, str], str]] = None):
        """
        Speak a random sentence from a dialog file.

        Args:
            key (str): dialog file key (e.g. "hello" to speak from the file
                                        "locale/en-us/hello.dialog")
            data (dict): information used to populate sentence
            expect_response (bool): set to True if Mycroft should listen
                                    for a response immediately after
                                    speaking the utterance.
            wait (Union[bool, int]): set to True to block while the text
                                     is being spoken for 15 seconds. Alternatively, set
                                     to an integer to specify a timeout in seconds.
            render_callback (Optional[Callable[[str, str], str]]): A callable 
                                                           function that 
                                                           transforms the 
                                                           utterance before 
                                                           it is spoken. 
                                                           The function 
                                                           should accept 
                                                           the utterance 
                                                           string and the 
                                                           language as input 
                                                           and return the 
                                                           modified string. 
                                                           Defaults to None.
        """
        data = data or {}
        # render_dialog renders a phrase via ovos_spec_tools.render; `key` may
        # also be a literal utterance — if no .dialog file matches it, it is
        # spoken verbatim.
        # TODO - change this behaviour, speaking the dialog file name isn't that helpful!
        utterance = self.render_dialog(key, data)
        if render_callback is not None:
            utterance = render_callback(utterance, self.lang)
        self.speak(
            utterance,
            expect_response, wait, meta={'dialog': key, 'data': data}
        )

    def play_audio(self, filename: str, instant: bool = False,
                   wait: Union[bool, int] = False):
        """
        Queue and audio file for playback
        @param filename: File to play
        @param instant: if True audio will be played instantly instead of queued with TTS
        @param wait: set to True to block while the audio
                                 is being played for 30 seconds. Alternatively, set
                                 to an integer to specify a timeout in seconds.
        """
        message = dig_for_message() or Message("")
        # if running in docker we need to send binary data to the ovos-audio container
        # if sessions is not default we also need to do it since
        # it likely is a remote client such as hivemind
        send_binary = os.environ.get("IS_OVOS_CONTAINER") or \
                      SessionManager.get(message).session_id != "default"

        if instant:
            mtype = "mycroft.audio.play_sound"
        else:
            mtype = "mycroft.audio.queue"

        if not send_binary or not isfile(filename):
            data = {"uri": filename}
        else:
            with open(filename, "rb") as f:
                bindata = binascii.hexlify(f.read()).decode('utf-8')
            data = {"audio_ext": filename.split(".")[-1],
                    "binary_data": bindata}

        self.bus.emit(message.forward(mtype, data))
        if wait:
            timeout = 30 if isinstance(wait, bool) else wait
            sess = SessionManager.get(message)
            sess.is_speaking = True
            SessionManager.wait_while_speaking(timeout, sess)

    def __handle_get_response(self, message: Message) -> None:
        """
        Handle the response message to a previous get_response / speak call
        sent from the intent service
        """
        # validate session_id to ensure this isnt another
        # user querying the skill at same time
        sess2 = SessionManager.get(message)
        if sess2.session_id not in self.__responses:
            LOG.debug(f"ignoring get_response answer for session: {sess2.session_id}")
            return  # not for us!

        utterances = message.data["utterances"]
        # received get_response
        self.__responses[sess2.session_id] = utterances

    def __get_response(self, session: Session):
        """Helper to get a response from the user

        this method is unsafe and contains a race condition for
         multiple simultaneous queries in ovos-core < 0.0.8

        Returns:
            str: user's response or None on a timeout
        """
        srcm = dig_for_message() or Message("", context={"source": "skills",
                                                         "skill_id": self.skill_id})
        srcm.context["session"] = session.serialize()

        LOG.debug(f"get_response session: {session.session_id}")
        ans = []

        start = time.time()
        timeout = self.config_core.get("skills", {}).get("get_response_timeout", 20)

        def on_extension(msg):
            nonlocal start
            s = SessionManager.get(msg)
            if s.session_id == session.session_id:
                # this helps with slower voice satellites or in cases of very long responses
                LOG.debug(f"Extending get_response wait time: {msg.msg_type}")
                start = time.time()  # reset timer

        # if we have indications listener is busy, we allow extra time
        self.bus.on("recognizer_loop:record_begin", on_extension)
        self.bus.on("recognizer_loop:record_end", on_extension)

        while time.time() - start <= timeout and not ans:
            ans = self.__responses[session.session_id]
            # NOTE: a threading.Event is not used otherwise we can't raise the
            # AbortEvent exception to kill the thread
            # this is for compat with killable_intents decorators
            # a busy loop is needed to be able to raise an exception
            time.sleep(0.1)
            if ans is None:
                # aborted externally (if None)
                self.log.debug("get_response aborted")
                break

        self.bus.remove("recognizer_loop:record_begin", on_extension)
        self.bus.remove("recognizer_loop:record_end", on_extension)
        return ans

    def get_response(self, dialog: str = '', data: Optional[dict] = None,
                     validator: Optional[Callable[[str], bool]] = None,
                     on_fail: Optional[Union[str, Callable[[str], str]]] = None,
                     num_retries: int = -1, message: Message = None,
                     wait: Union[bool, int] = True) -> Optional[str]:
        """
        Get a response from the user. If a dialog is supplied it is spoken,
        followed immediately by listening for a user response. If the dialog is
        omitted, listening is started directly. The response may optionally be
        validated before returning.
        @param dialog: Optional dialog resource or string to speak
        @param data: Optional data to render dialog with
        @param validator: Optional method to validate user input with. Accepts
            the user's utterance as an arg and returns True if it is valid.
        @param on_fail: Optional string or method that accepts a failing
            utterance and returns a string to be spoken when validation fails.
        @param num_retries: Number of times to retry getting a user response;
            -1 will retry infinitely.
            * If the user asks to "cancel", this method will exit
            * If the user doesn't respond and this is `-1` this will only retry
              once.
        @param message: Optional message to use for context
        @param wait: If True, wait for the response to finish speaking before
            listening. If False, start listening immediately. Can be an int
            to set the timeout in seconds.
        @return: String user response (None if no valid response is given)
        """
        message = message or dig_for_message() or \
                  Message('mycroft.mic.listen', context={"skill_id": self.skill_id})
        data = data or {}

        session = SessionManager.get(message)
        session.enable_response_mode(self.skill_id)
        message.context["session"] = session.serialize()
        self.__responses[session.session_id] = []
        self.bus.emit(message.forward("skill.converse.get_response.enable",
                                      {"skill_id": self.skill_id}))

        def on_fail_default(utterance):
            fail_data = data.copy()
            fail_data['utterance'] = utterance
            if on_fail:
                return self._dialog_or_text(on_fail, fail_data)
            else:
                return self._dialog_or_text(dialog, data)

        def is_cancel(utterance):
            return self.voc_match(utterance, 'cancel', lang=session.lang)

        def validator_default(utterance):
            # accept anything except 'cancel'
            return not is_cancel(utterance)

        on_fail_fn = on_fail if callable(on_fail) else on_fail_default
        validator = validator or validator_default

        # Speak query and wait for user response
        if dialog:
            self.speak(self._dialog_or_text(dialog, data), True, wait,
                       meta={'dialog': dialog, 'data': data})
        else:
            self.bus.emit(message.forward('mycroft.mic.listen'))

        # NOTE: self._wait_response launches a killable thread
        #  the thread waits for a user response for 15 seconds
        #  if no response it will re-prompt the user up to num_retries
        # see killable_event decorators for more info

        #  _wait_response contains a loop that gets validated results
        #  from the killable thread and returns the answer
        ans = self._wait_response(is_cancel, validator, on_fail_fn,
                                  num_retries, message)

        session.disable_response_mode(self.skill_id)
        message.context["session"] = session.serialize()
        self.bus.emit(message.forward("skill.converse.get_response.disable",
                                      {"skill_id": self.skill_id}))
        return ans

    def _wait_response(self, is_cancel: callable, validator: callable,
                       on_fail: callable, num_retries: int,
                       message: Message) -> Optional[str]:
        """
        Loop until a valid response is received from the user or the retry
        limit is reached.
        @param is_cancel: Function that returns `True` if user asked to cancel
        @param validator: Function that returns `True` if user input is valid
        @param on_fail: Function to call if validator returns `False`
        @param num_retries: Number of times to retry getting a response
        @returns: User response if validated, else None
        """
        session = SessionManager.get(message)

        # self.__validated_responses.get(session.session_id) <- set in a killable thread
        self._real_wait_response(is_cancel, validator, on_fail, num_retries, message)

        # wait for answer from killable thread
        # NOTE: this loop has no Event to wait on (see TODO below), so it
        # needs its own hard deadline. Without one, a killable thread that
        # never finishes (eg. the bus/TTS handshake it is waiting on in
        # __get_response never completes) blocks the caller forever - see
        # OpenVoiceOS/ovos-skill-alerts#138 for a captured py-spy stack of
        # exactly this hang via ask_yesno -> get_response -> _wait_response.
        # The deadline mirrors the thread's own per-attempt budget: each
        # retry may speak a reprompt (bounded by the 15s
        # wait_while_speaking() ceiling used elsewhere in this file) and
        # then wait up to `get_response_timeout` for a transcription.
        per_attempt_budget = self.config_core.get("skills", {}).get(
            "get_response_timeout", 20) + 15
        max_attempts = (num_retries + 1) if num_retries >= 0 else 2
        deadline = time.time() + per_attempt_budget * max_attempts

        ans = []
        while not ans:
            # TODO: Refactor to Event
            time.sleep(0.1)
            ans = self.__validated_responses.get(session.session_id)
            if ans or ans is None:  # canceled response
                break
            if time.time() > deadline:
                LOG.warning(f"get_response timed out waiting for a result "
                            f"from the background thread (session: "
                            f"{session.session_id}); giving up")
                ans = None
                break

        if session.session_id in self.__validated_responses:
            self.__validated_responses.pop(session.session_id)

        if isinstance(ans, list):
            ans = ans[0]  # TODO handle multiple transcriptions

        return ans

    def _validate_response(self, response: list,
                           sess: Session,
                           is_cancel: callable,
                           validator: callable,
                           on_fail: callable):
        reprompt_speak = None
        ans = response[0]  # TODO handle multiple transcriptions

        # catch user saying 'cancel'
        if is_cancel(ans):
            # signal get_response loop to stop
            self.__responses[sess.session_id] = None
            # return None in self.get_response
            self.__validated_responses[sess.session_id] = None
            return None

        validated = validator(ans)
        if not validated:
            reprompt_speak = on_fail(response)
            self.__responses[sess.session_id] = []  # re-prompt
        else:
            # returns the validated value or the response
            # (backwards compat)
            self.__validated_responses[sess.session_id] = ans if validated is True else validated
            # signal get_response loop to stop
            self.__responses[sess.session_id] = None

        return reprompt_speak

    def _handle_killed_wait_response(self) -> None:
        """
        Handle "stop" request when getting a response.
        """
        self.__responses = {k: None for k in self.__responses}
        self.__validated_responses = {k: None for k in self.__validated_responses}
        message = dig_for_message()
        self.bus.emit(message.forward(f"{self.skill_id}.get_response.killed"))

    @killable_event("mycroft.skills.abort_question", exc=AbortQuestion,
                    callback=_handle_killed_wait_response, react_to_stop=True,
                    check_skill_id=True)
    def _real_wait_response(self, is_cancel, validator, on_fail, num_retries,
                            message: Message):
        """

        runs in a thread, result retrieved via self.__responses[sess.session_id]

        Loop until a valid response is received from the user or the retry
        limit is reached.

        Arguments:
            is_cancel (callable): function checking cancel criteria
            validator (callable): function checking for a valid response
            on_fail (callable): function handling retries

        """
        self.bus.emit(message.forward(f"{self.skill_id}.get_response.waiting"))
        sess = SessionManager.get(message)

        num_fails = 0
        self.__validated_responses[sess.session_id] = []

        while True:

            response = self.__get_response(sess)
            reprompt = None

            if response is None:
                break  # killed externally
            elif response:
                reprompt = self._validate_response(response, sess,
                                                   is_cancel, validator, on_fail)
                if reprompt:
                    # reset counter, user said something and we reformulated the question
                    num_fails = 0
            else:
                # empty response
                num_fails += 1
                LOG.debug(f"get_response N fails: {num_fails}")

                # if nothing said, prompt one more time
                if num_fails >= num_retries and num_retries >= 0:  # stop trying, exceeded num_retries
                    # signal get_response loop to stop
                    self.__responses[sess.session_id] = None
                    # return None in self.get_response
                    self.__validated_responses[sess.session_id] = None

            if self.__responses.get(sess.session_id) is None:
                return  # dont prompt

            # re-prompt user
            if reprompt:
                self.speak(reprompt, expect_response=True)
            else:
                self.bus.emit(message.reply('mycroft.mic.listen'))

    def acknowledge(self):
        """
        Acknowledge a successful request.

        This method plays a sound to acknowledge a request that does not
        require a verbal response. This is intended to provide simple feedback
        to the user that their request was handled successfully.
        """
        audio_file = self.config_core.get('sounds', {}).get('acknowledge',
                                                            'snd/acknowledge.mp3')
        self.play_audio(audio_file, instant=True)

    def _get_yesno_engine(self) -> YesNoEngine:
        """Load the configured YesNoEngine plugin, with per-skill override support.

        Checks settings.json first, then mycroft.conf skills.ask_yesno_plugin.
        Returns None if no plugin is configured, preserving built-in fallback behavior.
        """
        plugin_name = (self.settings.get("ask_yesno_plugin") or
                       self.config_core.get("skills", {}).get("ask_yesno_plugin") or
                       "ovos-solver-yes-no-plugin")
        cache_key = f"__yesno_engine_{plugin_name}"
        if not hasattr(self, cache_key):
            try:
                cls = load_yesno_plugin(plugin_name)
                setattr(self, cache_key, cls())
            except Exception as e:
                LOG.error(f"Failed to load YesNo plugin '{plugin_name}': {e}")
                setattr(self, cache_key, None)
        return getattr(self, cache_key) or HeuristicYesNoEngine()

    def _get_selection_engine(self) -> OptionMatcherEngine:
        """Load the configured OptionMatcherEngine plugin, with per-skill override support.

        Checks settings.json first, then mycroft.conf skills.ask_selection_plugin,
        defaulting to ovos-option-matcher-fuzzy-plugin when neither is set.
        """
        plugin_name = (self.settings.get("ask_selection_plugin") or
                       self.config_core.get("skills", {}).get("ask_selection_plugin") or
                       "ovos-option-matcher-fuzzy-plugin")
        cache_key = f"__selection_engine_{plugin_name}"
        if not hasattr(self, cache_key):
            try:
                cls = load_option_matcher_plugin(plugin_name)
                setattr(self, cache_key, cls())
            except Exception as e:
                LOG.error(f"Failed to load selection plugin '{plugin_name}': {e}")
                setattr(self, cache_key, None)
        return getattr(self, cache_key) or FuzzyOptionMatcherPlugin()

    def ask_yesno(self, prompt: str,
                  data: Optional[dict] = None) -> Optional[str]:
        """
        Read prompt and wait for a yes/no answer. This automatically deals with
        translation and common variants, such as 'yeah', 'sure', etc.
        @param prompt: a dialog id or string to read
        @param data: optional data to render dialog with
        @return: 'yes', 'no' or the user response if not matched to 'yes' or
            'no', including a response of None.
        """
        resp = self.get_response(dialog=prompt, data=data)
        engine = self._get_yesno_engine()
        answer = engine.yes_or_no(question=prompt, response=resp, lang=self.lang) if resp else None
        if answer is True:
            return "yes"
        elif answer is False:
            return "no"
        else:
            return resp

    def ask_selection(self, options: List[str], dialog: str = '',
                      data: Optional[dict] = None, min_conf: float = 0.65,
                      numeric: bool = False, num_retries: int = -1):
        """
        Read options, ask dialog question and wait for an answer.

        This automatically deals with fuzzy matching and selection by number
        e.g.

        * "first option"
        * "last option"
        * "second option"
        * "option number four"

        Args:
              options (list): list of options to present user
              dialog (str): a dialog id or string to read AFTER all options
              data (dict): Data used to render the dialog
              min_conf (float): minimum confidence for fuzzy match, if not
                                reached return None
              numeric (bool): speak options as a numeric menu
        Returns:
              string: list element selected by user, or None
        """
        if not isinstance(options, list):
            raise ValueError("invalid value for 'options', must be a list of strings")

        if not len(options):
            return None
        elif len(options) == 1:
            return options[0]

        if numeric:
            for idx, opt in enumerate(options):
                number = pronounce_number(idx + 1, self.lang)
                self.speak(f"{number}, {opt}", wait=True)
        else:
            opt_str = join_word_list(options, "or", sep=",", lang=self.lang) + "?"
            self.speak(opt_str, wait=True)

        resp = self.get_response(dialog=dialog, data=data, num_retries=num_retries)

        if resp:
            engine = self._get_selection_engine()
            engine.config["min_conf"] = min_conf
            try:
                resp = engine.match_option(utterance=resp, options=options, lang=self.lang)
            except Exception as e:
                LOG.error(f"OptionMatcher plugin failed: {e}")
                resp = None
        return resp

    def typed_slot(self, message: Message, name: str) -> Any:
        """
        Get the normalized value an engine computed for a slot, if any.

        OVOS-INTENT-1 §5.6: `data.typed_slots` maps a registered type to the
        entries of that type found in the utterance, while `message.data[name]`
        stays the surface string the slot bound. The entry for a slot is the
        one whose `surface` equals that value; a repeated value is ambiguous
        and the first entry is taken.

        Only the type the intent declared for this slot is searched, so a
        surface string that several engines found under different types still
        resolves to the declared one. A slot with no declared type - an
        untyped template placeholder, or a name the handler invented - falls
        back to searching every registered type, in REGISTERED_TYPES order.

        @param message: intent dispatch message
        @param name: slot name, as declared by the intent template
        @return: normalized value of the type the slot declared, or None if no
                 entry covers the slot
        """
        surface = message.data.get(name)
        if not isinstance(surface, str):
            return None
        declared = self._declared_slot_type(message, name)
        for slot_type in [declared] if declared else REGISTERED_TYPES:
            for entry in self.typed_slots(message, slot_type):
                if entry["surface"] == surface:
                    return entry["value"]
        return None

    def _declared_slot_type(self, message: Message,
                            name: str) -> Optional[str]:
        """The type this skill declared for `name`, per the OVOS-INTENT-4 §6.1
        registration of the intent `message` dispatches."""
        # OVOS-MSG-1 §2.1.1: the dispatch topic is `<skill_id>:<intent_name>`,
        # and registrations are keyed by the bare intent name.
        intent_name = message.msg_type.split(":")[-1]
        for registered, data in self.intent_service.registered_intents:
            if registered == intent_name and isinstance(data, dict):
                declared = data.get("slot_types") or {}
                if name in declared:
                    return declared[name]
        return None

    def typed_slots(self, message: Message,
                    slot_type: str) -> List[Dict[str, Any]]:
        """
        Get every entry of one registered type found in the utterance.

        OVOS-INTENT-1 §5.6: an engine that computes a type reports what it
        found whether or not a slot bound it, so a handler that parses the
        whole utterance reads the entries directly. Each entry carries `span`,
        `surface` and `value`; the `typed_slots` map carries only types with
        at least one entry, so an empty list means no value of that type is
        available, whatever the cause.

        @param message: intent dispatch message
        @param slot_type: registered type name, e.g. "number" or "date"
        @return: entries of that type in span order
        """
        entries = _typed_slots_map(message).get(slot_type)
        if not isinstance(entries, list):
            return []
        valid = [entry for entry in entries if _is_typed_entry(entry)]
        if len(valid) != len(entries):
            LOG.debug(f"dropping malformed OVOS-INTENT-1 §5.6 typed_slots "
                      f"entries for type {slot_type!r}")
        return sorted(valid, key=lambda entry: tuple(entry["span"]))

    def voc_list(self, voc_filename: str,
                 lang: Optional[str] = None) -> List[str]:
        """Cached per-skill view of a ``.voc`` phrase set.

        Delegates the lookup to :meth:`LocaleResources.voc_list` (which
        returns ``[]`` for a missing resource) and caches the result on
        this skill instance so subsequent ``voc_match`` / ``remove_voc``
        calls do not re-walk the locale tree.
        """
        lang = standardize_lang(lang or self._resource_lang)
        cache_key = (self.res_dir, lang, voc_filename)
        if cache_key not in self._voc_cache:
            vocab = self._guarded(self._locale_resources.voc_list,
                                  voc_filename, lang, default=[])
            if vocab:
                self._voc_cache[cache_key] = [v.lower() for v in vocab]
        return self._voc_cache.get(cache_key) or []

    def voc_match(self, utt: str, voc_filename: str, lang: Optional[str] = None,
                  exact: bool = False, ensure_ascii=True):
        """Determine if ``utt`` matches any phrase from a ``.voc``.

        By default (``exact=False``) a sample matches when it appears in the
        utterance as a whole-word substring — so ``"yes, please"`` matches a
        ``yes.voc`` of just ``yes``. With ``exact=True`` the utterance must
        equal a sample after normalization.

        ``ensure_ascii`` bundles the normalization knobs — it drops
        diacritics and ASCII punctuation together; for finer control call
        :func:`ovos_spec_tools.utterance_contains` directly with
        ``strip_diacritics`` / ``strip_punct``.
        """
        return utterance_contains(
            utt, self.voc_list(voc_filename, lang), exact=exact,
            strip_diacritics=ensure_ascii, strip_punct=ensure_ascii)

    @staticmethod
    def _normalize_with_offsets(utt: str) -> Tuple[str, List[int]]:
        """
        Apply the same accent/punctuation stripping as
        `remove_accents_and_punct`, but keep a per-character map back to the
        original string so match spans found in the normalized text can be
        translated back to offsets into `utt`.

        Returns:
            Tuple[str, List[int]]: the normalized string, and a list where
                                   `idx_map[j]` is the index in the original
                                   `utt` that produced normalized char `j`.
        """
        rm_chars = set(c for c in string.punctuation if c not in ("{", "}"))
        out_chars = []
        idx_map = []
        for i, ch in enumerate(utt):
            for c in unicodedata.normalize('NFD', ch):
                if unicodedata.category(c) == 'Mn' or c in rm_chars:
                    continue
                out_chars.append(c)
                idx_map.append(i)
        return ''.join(out_chars), idx_map

    def voc_match_span(self, utt: str, voc_filename: str,
                        lang: Optional[str] = None,
                        exact: bool = False,
                        ensure_ascii: bool = True) -> List[Tuple[str, int, int]]:
        """
        Determine which vocabulary entries the given utterance matches, and
        where in the utterance each match occurs.

        This is the span-reporting counterpart to `voc_match`, returning
        every matched vocab entry together with its `(start, end)` offset
        into `utt`, enabling in-handler recovery of the exact text that
        matched (e.g. for `<voc>`-inline intents where the matched keyword
        needs to be sliced back out of the original utterance).

        Results are returned in UTTERANCE ORDER, i.e. sorted by `start`
        offset (not longest-first: a later, shorter match is intentionally
        listed after an earlier, longer one). Each occurrence of a matched
        entry gets its own span, so a repeated keyword produces multiple
        entries. `matched_entry` is always the canonical spelling as written
        in the `.voc` file, never a normalized form.

        Overlap rule: spans never overlap. When two candidate matches
        overlap (e.g. vocab entries "new york" and "york" both matching the
        utterance "new york"), the LONGEST candidate wins that stretch of
        text and the shorter, overlapping candidate is dropped entirely.

        Offset reference: `ensure_ascii=True` matches leniently by stripping
        accents/punctuation before comparing, but the returned `start`/`end`
        always index into the ORIGINAL `utt` as passed in, so
        `utt[start:end]` reproduces the actually-matched substring
        regardless of `ensure_ascii`.

        Args:
            utt (str): Utterance to be tested
            voc_filename (str): Name of vocabulary file (e.g. 'cancel' for
                                'locale/en-us/cancel.voc')
            lang (str): Language code, defaults to self.lang
            exact (bool): Whether the vocab must exactly match the utterance.
                         When True, a match yields a single span covering
                         the whole utterance: `(0, len(utt))`.
            ensure_ascii (bool): Whether to ignore accents and punctuation

        Returns:
            List[Tuple[str, int, int]]: `(matched_entry, start, end)` for
                       every match, in utterance order. Empty list if there
                       is no match. Callers that only want the entries can
                       use `[m[0] for m in voc_match_span(...)]`; callers
                       that only want the first/best-positioned match can
                       use `voc_match_span(...)[0]`.
        """
        lang = lang or self.lang
        try:
            _vocs = self.voc_list(voc_filename, lang)
        except FileNotFoundError:
            LOG.warning(
                f"{self.skill_id} failed to find voc file '{voc_filename}' for lang '{lang}' in `{self.res_dir}'")
            return []

        matches: List[Tuple[str, int, int]] = []
        if not utt or not _vocs:
            return matches

        orig_vocs = _vocs
        if ensure_ascii:
            search_utt, idx_map = self._normalize_with_offsets(utt)
            _vocs = [remove_accents_and_punct(v) for v in _vocs]
        else:
            search_utt, idx_map = utt, list(range(len(utt)))

        if exact:
            for orig, i in zip(orig_vocs, _vocs):
                if i.strip().lower() == search_utt.lower():
                    matches.append((orig, 0, len(utt)))
                    break
        else:
            # collect every candidate span first, so overlaps across
            # different vocab entries can be resolved (longest wins)
            candidates = []  # (start_n, end_n, orig)
            for orig, i in zip(orig_vocs, _vocs):
                pattern = r'\b' + re.escape(i) + r'\b'
                for m in re.finditer(pattern, search_utt, re.IGNORECASE):
                    start_n, end_n = m.span()
                    if start_n == end_n:
                        continue
                    candidates.append((start_n, end_n, orig))

            # longest first (ties: leftmost first), greedily accept
            # non-overlapping candidates so the longest entry always wins
            # a contested stretch of text
            occupied: List[Tuple[int, int]] = []
            for start_n, end_n, orig in sorted(
                    candidates, key=lambda c: (-(c[1] - c[0]), c[0])):
                if any(start_n < e and s < end_n for s, e in occupied):
                    continue
                occupied.append((start_n, end_n))
                start = idx_map[start_n] if idx_map else start_n
                end = idx_map[end_n - 1] + 1 if idx_map else end_n
                matches.append((orig, start, end))

        matches.sort(key=lambda t: t[1])
        return matches

    def remove_voc(self, utt: str, voc_filename: str,
                   lang: Optional[str] = None) -> str:
        """Return ``utt`` with every whole-word occurrence of any phrase from
        a ``.voc`` removed (longest first so composite phrases consume their
        parts)."""
        if not utt:
            return utt
        return strip_samples(utt, self.voc_list(voc_filename, lang))

    # event related skill developer facing utils
    def add_event(self, name: str, handler: callable,
                  handler_info: Optional[str] = None, once: bool = False,
                  speak_errors: bool = True, activation: Optional[bool] = None,
                  is_intent: bool = False, intent_name: Optional[str] = None):
        """
        Create event handler for executing intent or other event.

        Args:
            name (string): event name
            handler (func): Method to call
            handler_info (string): Base message when reporting skill event
                                   handler status on messagebus.
            once (bool, optional): Event handler will be removed after it has
                                   been run once.
            speak_errors (bool, optional): Determines if an error dialog should be
                                           spoken to inform the user whenever
                                           an exception happens inside the handler
            activation  (bool, optional): activate skill if True, deactivate if False, do nothing if None
            intent_name (string, optional): rides in the framework done-signal
                                   payload's ``intent_name`` field. ovos-core's
                                   dispatcher (``_resolve_entry``) reads it to
                                   disambiguate which in-flight dispatch for
                                   this ``skill_id`` a done-signal concludes,
                                   needed whenever more than one dispatch to
                                   the same skill can be in flight at once
                                   (eg. a targeted `<skill_id>:stop` racing an
                                   already-running intent handler).
        """
        skill_data = {'name': get_handler_name(handler)}
        if intent_name:
            skill_data['intent_name'] = intent_name

        def on_error(error, message):
            if isinstance(error, AbortEvent):
                self.log.info("Skill execution aborted")
                self._on_event_end(message, handler_info, skill_data,
                                   is_intent=is_intent)
                return
            LOG.error(f"Error handling event '{name}' : {error}")
            self._on_event_error(str(error), message, handler_info, skill_data,
                                 speak_errors)

        def on_start(message):
            self._on_event_start(message, handler_info,
                                 skill_data, activation)

        def on_end(message):
            self._on_event_end(message, handler_info, skill_data,
                               is_intent=is_intent)

        wrapper = create_wrapper(handler, self.skill_id, on_start, on_end,
                                 on_error)
        return self.events.add(name, wrapper, once)

    def remove_event(self, name: str) -> bool:
        """
        Removes an event from bus emitter and events list.

        Args:
            name (string): Name of Intent or Scheduler Event
        Returns:
            bool: True if found and removed, False if not found
        """
        return self.events.remove(name)

    # scheduled events
    # These methods are the skill-facing scheduling API. They speak SCHEDULER-1
    # through the scheduler client when one is installed and a scheduler is
    # answering on the bus, and the pre-specification mycroft.scheduler.*
    # protocol when either is missing. Whichever they speak, they behave the
    # way a skill has always been able to rely on: they do not block the
    # caller and a scheduler that refuses or never answers reaches the log,
    # not the skill.

    #: A repeating schedule made through SCHEDULER-1 belongs to the skill id
    #: rather than to the process, so it is left running when the skill stops
    #: and is still there when the skill comes back. Set this false to cancel
    #: repeats on shutdown, as the pre-specification protocol did.
    repeating_schedules_outlive_the_skill = True

    @property
    def _use_spec_scheduler(self) -> bool:
        """
        Whether to schedule through SCHEDULER-1 rather than the old topics.

        Having the client is not the same as having something to talk to: the
        scheduler runs in another process on its own release cycle, so its
        presence is asked for once and remembered. Every call that goes out
        on the sending thread asks it there; get_scheduled_event_status waits
        for its answer anyway and asks on the caller's thread.
        """
        if SchedulerClient is None or \
                not isinstance(self.event_scheduler, SchedulerClient):
            return False
        return self.event_scheduler.is_available()

    def _send_to_scheduler(self, description: str, request: Callable):
        """
        Send one scheduler request without holding the caller up.

        Scheduling has never blocked a skill or raised at it when the
        scheduler was unhappy, and that is the contract whichever protocol
        carries it. Requests go out on one thread in the order they were
        made, and only failures reach the log.
        """
        self._scheduler_requests.put((description, request))
        if self._scheduler_sender is None:
            self._scheduler_sender = Thread(
                target=self._send_scheduler_requests, daemon=True,
                name=f"{self.skill_id}-scheduler")
            self._scheduler_sender.start()

    def _send_scheduler_requests(self):
        while True:
            description, request = self._scheduler_requests.get()
            try:
                if request is _STOP_SENDING:
                    return
                request()
            except Exception as failure:
                LOG.error(f"{description} failed: {failure}")
            finally:
                self._scheduler_requests.task_done()

    def _scheduler_requests_sent(self):
        """
        Wait for the requests already made to reach the scheduler.
        """
        self._scheduler_requests.join()

    def _stop_sending_to_scheduler(self,
                                   timeout: float = SCHEDULER_SHUTDOWN_TIMEOUT):
        """
        Let the queued requests go out, then stop the sending thread.

        An unloaded skill's process may exit immediately afterwards, so a
        cancellation still sitting on the queue would simply never happen and
        the shutdown policy would come down to luck. The wait is bounded: a
        scheduler that has stopped answering must not be able to hang a
        shutdown, and the thread is a daemon that dies with the process
        either way.
        """
        if self._scheduler_sender is None:
            return
        self._scheduler_requests.put(("stopping", _STOP_SENDING))
        self._scheduler_sender.join(timeout)
        if self._scheduler_sender.is_alive():
            LOG.warning(f"scheduler requests from {self.skill_id} were still "
                        f"going out after {timeout}s and were abandoned")
        self._scheduler_sender = None

    def _spec_schedule_name(self, name: Optional[str],
                            handler: Callable) -> str:
        """
        The name a SCHEDULER-1 schedule is known by, and cancelled by.

        Without one the handler's name is used. The older interface derives
        its own default differently and keeps it: a schedule an older release
        persisted is stored under that name, and reaching it later is the
        only way to cancel it. Renaming the handler orphans the schedule on
        either path.
        """
        return name or handler.__name__

    def _schedule_context(self, context: Optional[dict]) -> dict:
        """
        The message context a scheduled handler is called with: the one the
        caller gave, else the context of the message being handled.

        The scheduler stores it and fires the occurrence with it, so it is
        settled here, once, while the message that would supply it is still
        in flight.
        """
        message = dig_for_message()
        context = dict(context or (message.context if message else {}))
        context["skill_id"] = self.skill_id
        return context

    def _schedule_instant(self, when: datetime.datetime) -> datetime.datetime:
        """
        A scheduling time as a point on the time line. A naive datetime is
        read in the configured timezone, never the platform's.

        The first naive datetime in a process logs one warning that names
        this contract, because ``datetime.now()`` is platform time and lands
        off by the zone difference where the two zones differ.
        """
        if when.tzinfo is None:
            global _NAIVE_WHEN_WARNED
            if not _NAIVE_WHEN_WARNED:
                _NAIVE_WHEN_WARNED = True
                LOG.warning(
                    f"{self.skill_id} scheduled a naive datetime ({when}). A "
                    f"naive `when` is read in the configured timezone "
                    f"({get_config_tz()}), not the system timezone. Pass an "
                    f"aware datetime (ovos_utils.time.now_local()) or a "
                    f"number of seconds. This warning is shown once per "
                    f"process.")
            return when.replace(tzinfo=get_config_tz())
        return when

    def _one_shot_timing(self, when: Union[int, float, datetime.datetime]) -> dict:
        """
        A single-shot `when` as the one timing a schedule record carries.
        """
        if isinstance(when, (int, float)):
            if when < 0:
                raise ValueError(f"Expected datetime or positive int/float. "
                                 f"got: {when}")
            if when == 0:
                # SCHEDULER-1 §3.4.3: in.seconds is a number > 0. "Now" is an
                # `at` instant (§3.1), which the scheduler fires on time
                # within grace_s (§4.3).
                return {"at": now_local()}
            return {"in_seconds": when}
        if not isinstance(when, datetime.datetime):
            raise TypeError(f"Expected datetime, int, or float but got: {when}")
        return {"at": self._schedule_instant(when)}

    def _first_occurrence(self, when: Optional[Union[int, float, datetime.datetime]],
                          frequency: Union[int, float]) -> datetime.datetime:
        """
        When a repeating schedule fires for the first time: the time asked
        for, or one period from now.
        """
        if when is None:
            return now_local() + datetime.timedelta(seconds=frequency)
        timing = self._one_shot_timing(when)
        if "in_seconds" in timing:
            return now_local() + datetime.timedelta(seconds=timing["in_seconds"])
        return timing["at"]

    def schedule_event(self, handler: callable,
                       when: Union[int, float, datetime.datetime],
                       data: Optional[dict] = None, name: Optional[str] = None,
                       context: Optional[dict] = None):
        """
        Schedule a single-shot event.

        Args:
            handler:               method to be called
            when (datetime/int/float):   datetime or number of seconds in
                                   the future when the handler should be
                                   called. A naive datetime is read in the
                                   configured timezone, not the system
                                   timezone; pass an aware datetime
                                   (ovos_utils.time.now_local()) or seconds.
            data (dict, optional): data to send when the handler is called
            name (str, optional):  reference name. Against a SCHEDULER-1
                                   scheduler the same name is one schedule
                                   and using it again replaces the pending
                                   event; against the older scheduler it adds
                                   a second one. Without a name each derives
                                   one from the handler in its own way, so
                                   name a schedule you mean to cancel.
            context (dict, optional): context (dict, optional): message
                                      context to send when the handler
                                      is called
        """
        context = self._schedule_context(context)
        timing = self._one_shot_timing(when)

        def send():
            if not self._use_spec_scheduler:
                self.event_scheduler.schedule_event(handler, when, data, name,
                                                    context=context)
                return
            self.event_scheduler.schedule(
                self._spec_schedule_name(name, handler), handler,
                data=data, context=context, **timing)

        self._send_to_scheduler(f"scheduling {name or handler.__name__}", send)

    def schedule_repeating_event(self, handler: Callable,
                                 when: Optional[Union[int, float, datetime.datetime]],
                                 frequency: Union[int, float],
                                 data: Optional[dict] = None,
                                 name: Optional[str] = None,
                                 context: Optional[dict] = None):
        """
        Schedule a repeating event.

        Args:
            handler (callable):         method to be called
            when (datetime, optional):  time for first calling the handler,
                                        or None to initially trigger
                                        <frequency> seconds from now. A naive
                                        datetime is read in the configured
                                        timezone, not the system timezone.
            frequency (float/int):      time in seconds between calls
            data (dict, optional):      data to send when the handler is called
            name (str, optional):       reference name. Scheduling a name
                                        that is already repeating is ignored;
                                        cancel it first to replace it. Name a
                                        schedule you mean to cancel: without
                                        one, each protocol derives a name
                                        from the handler in its own way.
            context (dict, optional):   context (dict, optional): message
                                        context to send when the handler
                                        is called
        """
        context = self._schedule_context(context)
        first = self._first_occurrence(when, frequency)

        def send():
            if not self._use_spec_scheduler:
                self.event_scheduler.schedule_repeating_event(
                    handler, when, frequency, data, name, context=context)
                return
            repeating = self._spec_schedule_name(name, handler)
            if repeating in self._repeating_schedules:
                LOG.debug('The event is already scheduled, cancel previous '
                          'event if this scheduling should replace the last.')
                return
            self._repeating_schedules.add(repeating)
            self.event_scheduler.schedule(
                repeating, handler, data=data, context=context,
                every={"seconds": frequency, "start": first.isoformat()})

        self._send_to_scheduler(f"scheduling {name or handler.__name__}", send)

    def update_scheduled_event(self, name: str, data: Optional[dict] = None):
        """
        Change data of event.

        The time the event fires is not touched, whether it was scheduled for
        an instant, after a delay, or on a recurrence.

        Args:
            name (str): reference name of event (from original scheduling)
            data (dict): event data
        """
        def send():
            if not self._use_spec_scheduler:
                self.event_scheduler.update_scheduled_event(name, data)
                return
            self.event_scheduler.reschedule(name, data=data or {})

        self._send_to_scheduler(f"updating {name}", send)

    def cancel_scheduled_event(self, name: str):
        """
        Cancel a pending event. The event will no longer be scheduled
        to be executed

        Args:
            name (str): reference name of event (from original scheduling)
        """
        def send():
            if not self._use_spec_scheduler:
                self.event_scheduler.cancel_scheduled_event(name)
                return
            self._repeating_schedules.discard(name)
            self.event_scheduler.cancel(name)

        self._send_to_scheduler(f"cancelling {name}", send)

    def get_scheduled_event_status(self, name: str) -> Optional[int]:
        """Get scheduled event data and return the amount of time left

        This is the one scheduling call that waits, because it has an answer
        to bring back. "Nothing by that name is scheduled" is one of the
        answers: it comes back as None, so that
        `if self.get_scheduled_event_status(name):` reads as "is this still
        coming". Only a scheduler that says nothing at all raises.

        Args:
            name (str): reference name of event (from original scheduling)

        Returns:
            int: seconds until the event fires, or None when nothing by that
                 name is scheduled any more. An event due this second
                 answers 0, which is falsy for the same reason it is small.

        Raises:
            Exception: Raised if the scheduler does not answer
        """
        self._scheduler_requests_sent()
        if not self._use_spec_scheduler:
            # the older scheduler answers "not scheduled" with an empty
            # payload, which its own client reads off the end of
            try:
                return self.event_scheduler.get_scheduled_event_status(name)
            except (KeyError, IndexError):
                return None
        schedule = self.event_scheduler.get(name)
        upcoming = schedule["state"]["next"] if schedule else None
        if upcoming is None:
            return None
        due = datetime.datetime.fromisoformat(upcoming)
        return int(due.timestamp()) - int(time.time())

    def cancel_all_repeating_events(self):
        """
        Cancel any repeating events started by the skill.
        """
        def send():
            if not self._use_spec_scheduler:
                self.event_scheduler.cancel_all_repeating_events()
                return
            for name in sorted(self._repeating_schedules):
                self._repeating_schedules.discard(name)
                self.event_scheduler.cancel(name)

        self._send_to_scheduler("cancelling every repeating event", send)

    # intent/context skill dev facing utils
    def disable_intent(self, intent_name: str) -> bool:
        """
        Disable a registered intent if it belongs to this skill.

        Args:
            intent_name (string): name of the intent to be disabled

        Returns:
                bool: True if disabled, False if it wasn't registered
        """
        # a skill author names the intent as authored ("time.intent"); the
        # registry and the bus both key it by its canonical name ("time")
        name = canonical_intent_topic(f'{self.skill_id}:{intent_name}')
        if name.split(':', 1)[1] in self.intent_service:
            self.log.info('Disabling intent ' + intent_name)
            self.intent_service.remove_intent(name)
            self.remove_event(name)

            langs = [self.core_lang] + self.secondary_langs
            for lang in langs:
                lang_intent_name = f'{name}_{lang}'
                self.intent_service.remove_intent(lang_intent_name)
            return True
        else:
            self.log.error(f'Could not disable {intent_name}, it hasn\'t been registered.')
            return False

    def enable_intent(self, intent_name: str) -> bool:
        """
        (Re)Enable a registered intent if it belongs to this skill.

        Args:
            intent_name: name of the intent to be enabled

        Returns:
            bool: True if enabled, False if it wasn't registered
        """
        # the registry keys intents by their canonical name; the author may
        # still refer to the intent by its authoring file name
        canonical = canonical_intent_topic(
            f'{self.skill_id}:{intent_name}').split(':', 1)[1]
        intent = self.intent_service.get_intent(canonical)
        if intent:
            # _intent_handlers is keyed canonically (see register_intent_file/
            # _register_adapt_intent), so look it up by the same canonical
            # spelling regardless of which spelling the caller used.
            handler = self._intent_handlers.get(canonical)
            if not handler:
                self.log.error(f'Could not enable {intent_name}, no handler '
                               f'is on record for it (was it ever registered '
                               f'with a handler by this skill instance?).')
                return False
            # padatious intents are stored as the register_template() data
            # dict; adapt intents as the IntentBuilder/Intent object. Branch
            # on what's actually in the registry, not on the caller's
            # spelling -- a caller may legitimately ask for the canonical
            # name of a padatious (".intent"-authored) intent.
            if isinstance(intent, dict):
                # OVOS-INTENT-3 §5.3: the declaration travels on every
                # registration of the intent
                self.register_intent_file(f'{canonical}.intent', handler,
                                          required_slots=intent.get('required_slots'))
            else:
                intent.name = intent_name
                self.register_intent(intent, handler)
            self.log.debug(f'Enabling intent {intent_name}')
            return True
        else:
            self.log.error(f'Could not enable {intent_name}, it hasn\'t been registered.')
            return False

    def skill_will_match(self, utterance: str, lang: Optional[str] = None,
                         timeout: float = 0.8,
                         exclude_pipeline: Optional[List[str]] = None,
                         session: Optional[Session] = None) -> bool:
        """Ask the intent service whether one of THIS skill's intents would match
        the utterance under a given session's context.

        Uses the read-only `intent.service.intent.get` probe (it never executes a
        handler, so it has no side effects). The probe runs under `session`'s
        intent context, so context-gated intents (e.g. layer-gated game intents)
        are accounted for per-session — essential when several sessions are active
        at once.

        @param utterance: utterance to probe
        @param lang: language tag (defaults to skill lang)
        @param timeout: seconds to wait for the intent-service reply
        @param exclude_pipeline: pipeline stages to skip for this probe (substring
            match). A skill that is currently conversing should pass
            `["converse"]` to avoid re-entering its own converse stage.
        @param session: the Session whose intent context to probe under; defaults
            to the current/default session.
        @return: True if the matched intent belongs to this skill
        """
        lang = standardize_lang(lang or self.lang)
        session = session or SessionManager.get()
        data = {"utterance": utterance, "lang": lang}
        if exclude_pipeline:
            data["exclude_pipeline"] = list(exclude_pipeline)
        response = self.bus.wait_for_response(
            Message("intent.service.intent.get", data,
                    {"session": session.serialize(), "lang": lang}),
            "intent.service.intent.reply", timeout=timeout)
        if not response:
            return False
        intent = response.data.get("intent")
        if not intent:
            return False
        return intent.get("skill_id") == self.skill_id

    def set_context(self, context: str, word: str = '', origin: str = '',
                     turns_remaining: Optional[int] = None,
                     expires_at: Optional[float] = None):
        """
        Add context to intent service.

        CONTEXT-1 §5.0: writes directly into the session bound to the
        current dispatch message (`Session.intent_context`, private scope
        owned by this skill) via `IntentServiceInterface`/`_AdaptIntentApi`,
        so the mutation rides forward on whatever Message this handler
        emits next (§5.3). The legacy `add_context` bus message is also
        emitted, for pre-spec orchestrators only: it carries the write to
        the adapt-engine `session.context` field. A core that predates
        §5.0 reads it there; a modern core folds the same key back into
        `session.intent_context`, so the topic is a write-through of the
        session write above and not an independent mutation.

        `turns_remaining`/`expires_at` are the CONTEXT-1 §2 decay fields.
        Passing `turns_remaining=1` is the one-turn confirmation-branch
        gate; the literal `{"value": ..., "turns_remaining": 1}` is §3.2's
        flag-context worked example, and §1.2 describes the same branch in
        prose. Left unset, decay stays time-based only, as before this
        parameter existed.

        Args:
            context:    Keyword
            word:       word connected to keyword
            origin:     origin of context
            turns_remaining: number of intent matches this entry survives,
                              per CONTEXT-1 §2/§4. `None` (default) means no
                              turn-based decay.
            expires_at: absolute unix timestamp this entry decays at. `None`
                        (default) falls back to `context.timeout` config.
        """
        if not isinstance(context, str):
            raise ValueError('Context should be a string')
        if not isinstance(word, str):
            raise ValueError('Word should be a string')

        original_context = context
        context = self.alphanumeric_skill_id + context
        self.intent_service._set_context(context, word, origin,
                                          original_key=original_context,
                                          turns_remaining=turns_remaining,
                                          expires_at=expires_at)

    def remove_context(self, context: str):
        """
        Remove a keyword from the context manager.

        CONTEXT-1 §5.0: same session-delegation + legacy compat emit
        as `set_context` above.
        """
        if not isinstance(context, str):
            raise ValueError('context should be a string')
        original_context = context
        context = self.alphanumeric_skill_id + context
        self.intent_service._remove_context(context,
                                             original_key=original_context)

    def set_cross_skill_context(self, context: str, word: str = '',
                                 turns_remaining: Optional[int] = None,
                                 expires_at: Optional[float] = None):
        """
        Add a context entry visible to every skill's intents.

        CONTEXT-1 §3/§5.0: a shared entry is a bare (owner-less) key in
        `session.intent_context`, so writing it directly into the session
        bound to the current dispatch message (§5.3) already makes it
        visible to every other skill's intents reading that same session -
        no bus round trip is needed for the mutation itself. The session
        write above is the only `session.intent_context` mutation this call
        causes, and it is the authoritative one.

        The legacy `mycroft.skill.set_cross_context` broadcast below is kept
        for orchestrators that still consume it. Its listener in every
        receiving skill (`handle_set_cross_context`) writes only that
        skill's adapt `session.context` field and never
        `session.intent_context`, so the broadcast adds no second writer of
        the shared entry — §5.0 removes the class of context-mutation topic
        rather than replacing it, and this emit is a compat surface with a
        removal version, not a mechanism.

        Args:
            context: Keyword
            word: word connected to keyword
            turns_remaining: number of intent matches this entry survives,
                              per CONTEXT-1 §2/§4. `None` (default) means no
                              turn-based decay.
            expires_at: absolute unix timestamp this entry decays at. `None`
                        (default) falls back to the `context.timeout`
                        configuration **of the process making this call**,
                        which on a satellite is not the orchestrator's
                        configuration. §5.3 gives a deployer-configurable
                        default decay to the orchestrator, for entries
                        written without an explicit `turns_remaining` or
                        `expires_at`; because this path always stamps one,
                        that orchestrator-side default never reaches a
                        shared entry. Pass `expires_at` explicitly when the
                        window matters.
        """
        if not isinstance(context, str):
            raise ValueError('Context should be a string')
        if not isinstance(word, str):
            raise ValueError('Word should be a string')
        msg = dig_for_message() or Message("")
        if "skill_id" not in msg.context:
            msg.context["skill_id"] = self.skill_id
        session = SessionManager.get(msg)
        if expires_at is None:
            # OVOS-CONTEXT-1: same decay policy as the private set_context
            # path (`context.timeout`, minutes, default 2).
            context_cfg = Configuration().get('context', {})
            timeout_s = context_cfg.get('timeout', 2) * 60
            expires_at = time.time() + timeout_s if timeout_s > 0 else None
        session.set_intent_context(context, word, scope="shared",
                                    expires_at=expires_at,
                                    turns_remaining=turns_remaining)
        log_deprecation(
            "mycroft.skill.set_cross_context is a pre-OVOS-CONTEXT-1 "
            "compat broadcast kept for orchestrators that still consume "
            "it; the shared session write above is now the authoritative "
            "mutation", _CROSS_CONTEXT_REMOVAL_VERSION)
        self.bus.emit(msg.forward('mycroft.skill.set_cross_context',
                                  {'context': context, 'word': word,
                                   'origin': self.skill_id}))

    def remove_cross_skill_context(self, context: str):
        """
        Remove a shared context entry from every skill's intents.

        CONTEXT-1 §3/§5.0: same session-delegation + legacy compat emit
        as `set_cross_skill_context` above.
        """
        if not isinstance(context, str):
            raise ValueError('context should be a string')
        msg = dig_for_message() or Message("")
        if "skill_id" not in msg.context:
            msg.context["skill_id"] = self.skill_id
        session = SessionManager.get(msg)
        session.remove_intent_context(context, scope="shared")
        log_deprecation(
            "mycroft.skill.remove_cross_context is a pre-OVOS-CONTEXT-1 "
            "compat broadcast kept for orchestrators that still consume "
            "it; the shared session removal above is now the authoritative "
            "mutation", _CROSS_CONTEXT_REMOVAL_VERSION)
        self.bus.emit(msg.forward('mycroft.skill.remove_cross_context',
                                  {'context': context}))

    # killable_events support
    def send_stop_signal(self, stop_event: Optional[str] = None):
        """
        Notify services to stop current execution
        @param stop_event: optional `stop` event name to forward
        """
        waiter = Event()
        msg = dig_for_message() or Message("mycroft.stop")
        # stop event execution
        if stop_event:
            self.bus.emit(msg.forward(stop_event))

        # stop TTS
        self.bus.emit(msg.forward("mycroft.audio.speech.stop"))

        # Tell ovos-core to stop recording (not in mycroft-core)
        self.bus.emit(msg.forward('recognizer_loop:record_stop'))

        # TODO: register TTS events to track state instead of guessing
        waiter.wait(0.5)  # if TTS had not yet started
        self.bus.emit(msg.forward("mycroft.audio.speech.stop"))


class SkillGUI(GUIInterface):
    def __init__(self, skill: OVOSSkill):
        """
        Initialize a SkillGUI that connects a skill to the GUI framework.
        
        Parameters:
        	skill (OVOSSkill): The skill instance whose GUI should be managed. The constructor initializes the underlying GUIInterface using the skill's id, message bus, GUI configuration, and UI directories.
        """
        self._skill = skill
        skill_id = skill.skill_id
        bus = skill.bus
        config = skill.config_core.get('gui')
        ui_directories = get_ui_directories(skill.root_dir)
        GUIInterface.__init__(self, skill_id=skill_id, bus=bus, config=config,
                              ui_directories=ui_directories)




