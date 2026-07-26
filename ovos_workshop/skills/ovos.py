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
import re
import shutil
import sys
import time
import traceback
import warnings
from copy import copy
from hashlib import md5
from inspect import signature
from os.path import join, abspath, dirname, basename, isfile
from pathlib import Path
from threading import Event, RLock
from typing import Dict, Callable, List, Optional, Union

from json_database import JsonStorage
from ovos_bus_client import MessageBusClient
from ovos_gui_api_client import EnclosureAPI
from ovos_bus_client.apis.events import EventSchedulerInterface
from ovos_bus_client.apis.gui import GUIInterface
from ovos_bus_client.apis.ocp import OCPInterface
from ovos_bus_client.handler import HandlerLifecycle
from ovos_bus_client.message import Message, dig_for_message
from ovos_bus_client.session import SessionManager, Session
from ovos_bus_client.util import get_message_lang
from ovos_spec_tools import SpecMessage, standardize_lang
from ovos_spec_tools.resources import read_resource_file
from ovos_config.config import Configuration
from ovos_config.locations import get_xdg_cache_save_path
from ovos_config.locations import get_xdg_config_save_path
from ovos_config.locations import get_xdg_data_save_path
from ovos_spec_tools import (LocaleResources, render, iter_locale_dirs,
                              standardize_lang, strip_samples,
                              utterance_contains)
from ovos_number_parser import pronounce_number
from ovos_option_matcher_fuzzy import FuzzyOptionMatcherPlugin
from ovos_plugin_manager.agents import load_yesno_plugin, load_option_matcher_plugin
from ovos_plugin_manager.language import OVOSLangTranslationFactory, OVOSLangDetectionFactory
from ovos_plugin_manager.templates.agents import YesNoEngine, OptionMatcherEngine
from ovos_utils import camel_case_split
from ovos_utils.events import EventContainer, get_handler_name, create_wrapper
from ovos_utils.file_utils import FileWatcher
from ovos_utils.gui import get_ui_directories
from ovos_utils.json_helper import merge_dict
from ovos_utils.log import LOG
from ovos_utils.process_utils import ProcessStatus, StatusCallbackMap
from ovos_utils.skills import get_non_properties
from ovos_yes_no import HeuristicYesNoEngine

from ovos_workshop.decorators.killable import AbortEvent, killable_event, AbortQuestion
from ovos_workshop.decorators.layers import IntentLayers
from ovos_workshop.filesystem import FileSystemAccess
from ovos_workshop.intents import IntentBuilder, Intent, munge_regex, munge_intent_parser, IntentServiceInterface
from ovos_workshop.settings import PrivateSettings
from ovos_workshop.skills._legacy_resources import _LegacyResourcesMixin
from ovos_workshop.skills.util import join_word_list, simple_trace


def _core_owns_utterance_handled() -> bool:
    """PIPELINE-1 §9.5: core >= 2.3.0 emits ``ovos.utterance.handled`` on every
    terminal path, the matched path included — the framework must not double-emit.
    Older or absent core -> the framework still owns the emit (back-compat)."""
    try:
        from ovos_core.version import OVOS_VERSION_TUPLE
    except ImportError:
        return False
    return OVOS_VERSION_TUPLE >= (2, 3, 0)


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

        ``name`` may also be a **literal utterance** rather than a dialog key:
        ``speak_dialog`` / ``get_response`` accept either form, so if no
        ``.dialog`` resource matches, ``name`` is returned verbatim.

        Args:
            name: a dialog file name (no extension), or a literal utterance
            data: values used to fill the dialog's named slots
        Returns:
            A rendered phrase ready for text-to-speech.
        """
        lang = self._resource_lang
        try:
            phrases = self._locale_resources.load_dialog(name, lang)
        except FileNotFoundError:
            # `name` is not a dialog key — treat it as a literal utterance
            return name
        vocabularies = self._locale_resources.vocabularies(lang)
        return render(phrases, slots=data, vocabularies=vocabularies)

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

        @param root_directory: skill root path containing ``locale/``
            (default res_dir)
        @param lang: unused, kept for backwards compatibility — language is
            passed per ``load_*`` call.
        @return: LocaleResources object
        """
        root_directory = root_directory or self.res_dir
        if root_directory not in self._lang_resources:
            workshop_locale = join(dirname(dirname(abspath(__file__))),
                                   "locale")
            user_locale = join(get_xdg_data_save_path(), "resources",
                               self.skill_id) if self.skill_id else None
            self._lang_resources[root_directory] = LocaleResources(
                skill_locale=join(root_directory, "locale"),
                core_locale=workshop_locale,
                user_locale=user_locale)
        return self._lang_resources[root_directory]

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
            for voc_name, entity, aliases in resources.vocabulary_keywords(lang):
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
        path = self._locale_resources.find(name, ext, lang)
        return str(path) if path is not None else None

    # skill object setup
    def _handle_first_run(self) -> None:
        """
        The very first time a skill is run, speak a provided intro_message.
        """
        intro = self.get_intro_message()
        if intro:
            # supports .dialog files for easy localization
            # when .dialog does not exist, the text is spoken
            # it is backwards compatible
            self.speak_dialog(intro)

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
            json_path = join(root_directory, "locale", lang, "skill.json")
            if not isfile(json_path):
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
                    self.register_intent(intent, method, voc_blacklist=voc_blacklist)

            if hasattr(method, 'intent_files'):
                for intent_file in getattr(method, 'intent_files'):
                    self.register_intent_file(intent_file, method)

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
            self.bus.emit(message.reply("ovos.common_query.pong",
                                        {"skill_id": self.skill_id, "is_classic_cq": False},
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
        self.bus.emit(message.response({"phrase": search_phrase,
                                        "skill_id": self.skill_id,
                                        "searching": True}))
        answer = None
        confidence = 0
        try:
            answer, confidence = self._cq_handler(search_phrase, lang) or (None, 0)
            LOG.debug(f"Common QA {self.skill_id} result: {answer}")
        except Exception:
            LOG.exception(f"Failed to get answer from {self._cq_handler}")

        if answer and confidence >= 0.5:
            self.bus.emit(message.response({"phrase": search_phrase,
                                            "skill_id": self.skill_id,
                                            "answer": answer,
                                            "callback_data": {"answer": answer},  # so we get it in callback
                                            "conf": confidence}))
        else:
            # Signal we are done (can't handle it)
            self.bus.emit(message.response({"phrase": search_phrase,
                                            "skill_id": self.skill_id,
                                            "searching": False}))

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

    def _register_system_event_handlers(self):
        """
        Register default messagebus event handlers
        """
        self.add_event('mycroft.stop', self._handle_session_stop, speak_errors=False)
        self.add_event(f"{self.skill_id}.stop", self._handle_session_stop, speak_errors=False)
        self.add_event(f"{self.skill_id}.stop.ping", self._handle_stop_ack, speak_errors=False)
        self.add_event(f"{self.skill_id}.converse.get_response", self.__handle_get_response, speak_errors=False)

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
        Inform skills service if we want to handle stop. Individual skills
        must implement the method self.can_stop to enable or
        disable stop support.
        @param message: `{self.skill_id}.stop.ping` Message
        """
        self.bus.emit(message.reply(
            "skill.stop.pong",
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
        """
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

            # Store settings
            if self.settings != self._initial_settings:
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
                self.event_scheduler.shutdown()
                self.events.clear()
        except Exception as e:
            self.log.error(f"Failed to remove events for {self.skill_id}: {e}")

        self.bus.emit(
            Message('detach_skill', {'skill_id': self.skill_id},
                    {'skill_id': self.skill_id}))

    def __del__(self):
        try:
            self.shutdown()
        except Exception as e:
            LOG.error(f"Skill specific shutdown for '{self.skill_id}' encountered an error: {e}")
        try:
            self.default_shutdown()
        except Exception as e:
            LOG.error(f"Default shutdown for skill '{self.skill_id}' encountered an error: {e}")

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
                name = f'{self.skill_id}:{intent_file}'
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
                        handler: callable, voc_blacklist: Optional[List[str]] = None):
        """
        Register an Intent with the intent service.

        Args:
            intent_parser: Intent, IntentBuilder object or padatious intent
                           file to parse utterance for the handler.
            handler (func): function to register with intent
        """
        if isinstance(intent_parser, str):
            if not intent_parser.endswith('.intent'):
                raise ValueError
            return self.register_intent_file(intent_parser, handler, voc_blacklist)
        return self._register_adapt_intent(intent_parser, handler)

    def register_intent_file(self, intent_file: str, handler: callable,
                             voc_blacklist: Optional[List[str]] = None):
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
        """
        name = f'{self.skill_id}:{intent_file}'
        for lang in self.native_langs:
            filename = self._locate_lang_file(intent_file, ".intent", lang)
            if filename is None:
                self.log.error(f'Unable to find "{intent_file}"')
                continue

            samples = read_resource_file(Path(filename))

            disallowed_strings = []
            for enty in voc_blacklist or []:
                disallowed_strings += self.voc_list(enty, lang=lang)

            # OVOS-INTENT-2 §4.3: a sibling "<intent>.blacklist" locale file
            # lists slot-free phrases that should suppress this intent from
            # matching. The file is optional — skip when absent.
            blacklist_name = intent_file.rsplit(".", 1)[0]
            try:
                disallowed_strings += self._locale_resources.load_blacklist(
                    blacklist_name, lang)
            except FileNotFoundError:
                pass  # no sibling ".blacklist" file -> nothing to suppress

            # OVOS-INTENT-2 §4.3: for each "{slot}" the template declares, a
            # sibling "<slot>.blacklist" locale file lists slot-value
            # exclusions — values that MUST NOT bind to that slot (the
            # canonical use is keeping anaphoric pronouns out of a referential
            # slot). Keyed by slot name so consuming engines can drop them.
            slot_blacklist = {}
            with open(filename) as f:
                slots = set(re.findall(r"{(.+?)}", f.read()))
            for slot in slots:
                try:
                    phrases = self._locale_resources.load_blacklist(slot, lang)
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
                vocabs=self._locale_resources.vocabularies(lang))
        if handler:
            self.add_event(name, handler, 'mycroft.skill.handler',
                           activation=True, is_intent=True)
            # INTENT-4: pipelines are migrating to dispatch on the canonical,
            # suffix-less intent name (`<skill_id>:<file>`, no `.intent`) instead
            # of this legacy `<skill_id>:<file>.intent` topic. Both identities
            # are emitted on the wire by register_template above, so bind the
            # handler to both -- whichever name the matching pipeline used to
            # dispatch, a handler is bound. Drop the legacy binding once all
            # supported pipelines have migrated (padatious-pipeline #89,
            # padacioso #73).
            canonical = name[:-len('.intent')] if name.endswith('.intent') else name
            if canonical != name:
                self.add_event(canonical, handler, 'mycroft.skill.handler',
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

        Args:
            entity_file (string): name of file that contains examples of an
                                  entity.
        """
        if entity_file.endswith('.entity'):
            entity_file = entity_file.replace('.entity', '')
        for lang in self.native_langs:
            filename = self._locate_lang_file(entity_file, ".entity", lang)
            if filename is None:
                self.log.error(f'Unable to find "{entity_file}"')
                continue
            name = f"{self.skill_id}:{basename(entity_file)}_" \
                   f"{md5(entity_file.encode('utf-8')).hexdigest()}"
            samples = read_resource_file(Path(filename))
            # OVOS-INTENT-2 §4.3: a sibling "<entity>.blacklist" locale file
            # lists slot-free phrases that MUST NOT fill the {slot} this entity
            # supplies (e.g. a "person.blacklist" of pronouns keeps "he" out of
            # the {person} slot)
            try:
                blacklist = self._locale_resources.load_blacklist(entity_file,
                                                                  lang)
            except FileNotFoundError:
                blacklist = []
            self.intent_service.register_padatious_entity(name, filename, lang,
                                                          blacklist=blacklist)

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
        regex = munge_regex(regex_str, self.skill_id)
        re.compile(regex)  # validate regex
        self.intent_service.register_adapt_regex(
            regex, lang=standardize_lang(lang or self._resource_lang))

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
        for (name, _) in self.intent_service.detached_intents:
            if name == intent_name:
                return self.enable_intent(intent_name)

    def handle_disable_intent(self, message: Message):
        """
        Listener to disable a registered intent if it belongs to this skill.
        @param message: `mycroft.skill.disable_intent` Message
        """
        intent_name = message.data['intent_name']
        for (name, _) in self.intent_service.registered_intents:
            if name == intent_name:
                return self.disable_intent(intent_name)

    def handle_set_cross_context(self, message: Message):
        """
        Add global context to the intent service.
        @param message: `mycroft.skill.set_cross_context` Message
        """
        context = message.data.get('context')
        word = message.data.get('word')
        origin = message.data.get('origin')

        self.set_context(context, word, origin)

    def handle_remove_cross_context(self, message: Message):
        """
        Remove global context from the intent service.
        @param message: `mycroft.skill.remove_cross_context` Message
        """
        context = message.data.get('context')
        self.remove_context(context)

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
        if is_intent and not _core_owns_utterance_handled():
            # PIPELINE-1 §9.5: skip if core (>=2.3.0a1) already owns this emit.
            self.bus.emit(message.forward(SpecMessage.UTTERANCE_HANDLED, skill_data))

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
        # render_dialog renders a phrase via ovos_spec_tools.render; if the
        # `skill.error` dialog is missing, the key is returned verbatim.
        speech = self.render_dialog('skill.error', msg_data)
        if speak_errors:
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
                               handler: callable):
        """
        Register an adapt intent.

        Args:
            intent_parser: Intent object to parse utterance for the handler.
            handler (func): function to register with intent
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
        self.intent_service.register_intent(name, intent_parser)
        if handler:
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
            # render_dialog renders a phrase via ovos_spec_tools.render; a
            # missing .dialog file falls back to the name with dots replaced
            # by spaces.
            if on_fail:
                return self.render_dialog(on_fail, fail_data)
            else:
                return self.render_dialog(dialog, data)

        def is_cancel(utterance):
            return self.voc_match(utterance, 'cancel', lang=session.lang)

        def validator_default(utterance):
            # accept anything except 'cancel'
            return not is_cancel(utterance)

        on_fail_fn = on_fail if callable(on_fail) else on_fail_default
        validator = validator or validator_default

        # Speak query and wait for user response
        if dialog:
            self.speak_dialog(dialog, data, expect_response=True, wait=wait)
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
        ans = []
        while not ans:
            # TODO: Refactor to Event
            time.sleep(0.1)
            ans = self.__validated_responses.get(session.session_id)
            if ans or ans is None:  # canceled response
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

    def voc_list(self, voc_filename: str,
                 lang: Optional[str] = None) -> List[str]:
        """Cached per-skill view of a ``.voc`` phrase set.

        Delegates the lookup to :meth:`LocaleResources.voc_list` (which
        returns ``[]`` for a missing resource) and caches the result on
        this skill instance so subsequent ``voc_match`` / ``remove_voc``
        calls do not re-walk the locale tree.
        """
        lang = standardize_lang(lang or self._resource_lang)
        cache_key = lang + voc_filename
        if cache_key not in self._voc_cache:
            vocab = self._locale_resources.voc_list(voc_filename, lang)
            if vocab:
                self._voc_cache[cache_key] = list(vocab)
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
                  is_intent: bool = False):
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
        """
        skill_data = {'name': get_handler_name(handler)}

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

    def schedule_event(self, handler: callable,
                       when: Union[int, float, datetime.datetime],
                       data: Optional[dict] = None, name: Optional[str] = None,
                       context: Optional[dict] = None):
        """
        Schedule a single-shot event.

        Args:
            handler:               method to be called
            when (datetime/int/float):   datetime (in system timezone) or
                                   number of seconds in the future when the
                                   handler should be called
            data (dict, optional): data to send when the handler is called
            name (str, optional):  reference name
                                   NOTE: This will not warn or replace a
                                   previously scheduled event of the same
                                   name.
            context (dict, optional): context (dict, optional): message
                                      context to send when the handler
                                      is called
        """
        message = dig_for_message()
        context = context or message.context if message else {}
        context["skill_id"] = self.skill_id
        return self.event_scheduler.schedule_event(handler, when, data, name,
                                                   context=context)

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
            when (datetime, optional):  time (in system timezone) for first
                                        calling the handler, or None to
                                        initially trigger <frequency> seconds
                                        from now
            frequency (float/int):      time in seconds between calls
            data (dict, optional):      data to send when the handler is called
            name (str, optional):       reference name, must be unique
            context (dict, optional):   context (dict, optional): message
                                        context to send when the handler
                                        is called
        """
        message = dig_for_message()
        context = context or message.context if message else {}
        context["skill_id"] = self.skill_id
        self.event_scheduler.schedule_repeating_event(handler, when, frequency,
                                                      data, name,
                                                      context=context)

    def update_scheduled_event(self, name: str, data: Optional[dict] = None):
        """
        Change data of event.

        Args:
            name (str): reference name of event (from original scheduling)
            data (dict): event data
        """
        self.event_scheduler.update_scheduled_event(name, data)

    def cancel_scheduled_event(self, name: str):
        """
        Cancel a pending event. The event will no longer be scheduled
        to be executed

        Args:
            name (str): reference name of event (from original scheduling)
        """
        self.event_scheduler.cancel_scheduled_event(name)

    def get_scheduled_event_status(self, name: str) -> int:
        """Get scheduled event data and return the amount of time left

        Args:
            name (str): reference name of event (from original scheduling)

        Returns:
            int: the time left in seconds

        Raises:
            Exception: Raised if event is not found
        """
        return self.event_scheduler.get_scheduled_event_status(name)

    def cancel_all_repeating_events(self):
        """
        Cancel any repeating events started by the skill.
        """
        self.event_scheduler.cancel_all_repeating_events()

    # intent/context skill dev facing utils
    def disable_intent(self, intent_name: str) -> bool:
        """
        Disable a registered intent if it belongs to this skill.

        Args:
            intent_name (string): name of the intent to be disabled

        Returns:
                bool: True if disabled, False if it wasn't registered
        """
        if intent_name in self.intent_service:
            self.log.info('Disabling intent ' + intent_name)
            name = f'{self.skill_id}:{intent_name}'
            self.intent_service.remove_intent(name)
            # unbind the dispatch handler from both the legacy suffixed name
            # and the INTENT-4 canonical suffix-less name (see
            # register_intent_file, which binds both)
            self.remove_event(name)
            canonical = name[:-len('.intent')] if name.endswith('.intent') else name
            if canonical != name:
                self.remove_event(canonical)

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
        intent = self.intent_service.get_intent(intent_name)
        if intent:
            if ".intent" in intent_name:
                self.register_intent_file(intent_name, None)
            else:
                intent.name = intent_name
                self.register_intent(intent, None)
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

    def set_context(self, context: str, word: str = '', origin: str = ''):
        """
        Add context to intent service

        Args:
            context:    Keyword
            word:       word connected to keyword
            origin:     origin of context
        """
        if not isinstance(context, str):
            raise ValueError('Context should be a string')
        if not isinstance(word, str):
            raise ValueError('Word should be a string')

        context = self.alphanumeric_skill_id + context
        self.intent_service.set_context(context, word, origin)

    def remove_context(self, context: str):
        """
        Remove a keyword from the context manager.
        """
        if not isinstance(context, str):
            raise ValueError('context should be a string')
        context = self.alphanumeric_skill_id + context
        self.intent_service.remove_context(context)

    def set_cross_skill_context(self, context: str, word: str = ''):
        """
        Tell all skills to add a context to the intent service

        Args:
            context:    Keyword
            word:       word connected to keyword
        """
        msg = dig_for_message() or Message("")
        if "skill_id" not in msg.context:
            msg.context["skill_id"] = self.skill_id
        self.bus.emit(msg.forward('mycroft.skill.set_cross_context',
                                  {'context': context, 'word': word,
                                   'origin': self.skill_id}))

    def remove_cross_skill_context(self, context: str):
        """
        Tell all skills to remove a keyword from the context manager.
        """
        if not isinstance(context, str):
            raise ValueError('context should be a string')
        msg = dig_for_message() or Message("")
        if "skill_id" not in msg.context:
            msg.context["skill_id"] = self.skill_id
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




