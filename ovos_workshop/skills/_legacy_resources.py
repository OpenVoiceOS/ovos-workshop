# Copyright 2026 OpenVoiceOS
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
"""Deprecated entry points of :class:`OVOSSkill`.

OVOSSkill drives resource loading through
:class:`ovos_spec_tools.LocaleResources`. These legacy entry points delegate
to :class:`ovos_workshop.resource_files.SkillResources` and are isolated here
so skills that still call them keep working.

Surface that lives in the mixin:

- :attr:`resources` — a :class:`SkillResources` handle;
- :attr:`dialog_renderer` — a
  :class:`~ovos_utils.dialog.MustacheDialogRenderer`;
- :meth:`find_resource` — a :class:`SkillResources`-backed lookup;
- :meth:`load_dialog_files` — no-op kept because some skill base classes
  call it during boot;
- :attr:`voc_match_cache` — accessor for the
  :attr:`OVOSSkill._voc_cache` dict;
- :class:`_LegacyLocaleResources` — the object :meth:`OVOSSkill.load_lang`
  returns, which still answers the :class:`SkillResources` methods;
- :attr:`runtime_requirements` / :attr:`network_requirements` — declared
  deprecated in ovos-core; kept so LAN/cache/offline skills still load;
- :meth:`load_regex_files` — the adapt ``.rx`` loader;
- :meth:`register_homescreen_app`, :meth:`register_resting_screen` and the
  ``@homescreen_app`` scan — the homescreen concept, which has no
  replacement.

The mixin assumes its host class supplies the attributes every OVOSSkill
has: ``res_dir``, ``lang``, ``skill_id``, ``log``, and ``_voc_cache``. It
owns one piece of state of its own — ``_skill_resources_compat`` — a
single :class:`SkillResources` instance lazily built on first access and
reused by every method below.
"""
from __future__ import annotations

import os
import re
import shutil
import warnings
from os.path import join
from typing import Callable, Dict, List, Optional

from ovos_bus_client.message import Message
from ovos_config.locations import get_xdg_cache_save_path
from ovos_spec_tools import LocaleResources, iter_locale_dirs
from ovos_utils import classproperty
from ovos_utils.events import get_handler_name
from ovos_utils.log import LOG, deprecated, log_deprecation
from ovos_utils.skills import get_non_properties
from ovos_utils.process_utils import RuntimeRequirements
from ovos_workshop.version import VERSION_MAJOR

_REMOVAL_VERSION = f"{VERSION_MAJOR + 1}.0.0"


class _LegacyLocaleResources(LocaleResources):
    """A :class:`LocaleResources` that still answers the methods of the
    :class:`SkillResources` that :meth:`OVOSSkill.load_lang` used to return
    (``load_dialog_file``, ``render_dialog``, ``load_vocabulary_file``,
    ``dialog_renderer``, ...).

    Any attribute that :class:`LocaleResources` lacks is looked up on the
    :class:`SkillResources` of the same skill directory and language, and a
    deprecation warning names the replacement.
    """

    def __init__(self, *args, skill_directory: str, skill_id: Optional[str],
                 default_lang: Callable[[], str], lang: Optional[str] = None,
                 **kwargs):
        super().__init__(*args, **kwargs)
        self._skill_directory = skill_directory
        self._skill_id = skill_id
        self._default_lang = default_lang
        self._lang = lang
        self._skill_resources = None

    def _legacy_resources(self):
        """The :class:`SkillResources` for this skill directory and language,
        built on first use. Only the deprecated methods reach it."""
        if self._skill_resources is None:
            from ovos_workshop.resource_files import SkillResources
            self._skill_resources = SkillResources(
                self._skill_directory, self._lang or self._default_lang(),
                skill_id=self._skill_id)
        return self._skill_resources

    def vocabularies(self, lang: Optional[str] = None):
        """``LocaleResources.vocabularies(lang)``; without a language, the
        deprecated ``SkillResources.vocabularies()``."""
        if lang is not None:
            return super().vocabularies(lang)
        return self.__getattr__("vocabularies")()

    def __getattr__(self, name: str):
        if name.startswith("_"):
            raise AttributeError(name)
        legacy = self._legacy_resources()
        try:
            member = getattr(legacy, name)
        except AttributeError:
            raise AttributeError(
                f"{type(self).__name__!r} object has no attribute {name!r}"
            ) from None
        msg = (f"load_lang() now returns an ovos_spec_tools.LocaleResources; "
               f"{name!r} is a SkillResources method. Use the high-level "
               f"skill methods or the LocaleResources API instead.")
        warnings.warn(msg, DeprecationWarning, stacklevel=2)
        log_deprecation(msg, _REMOVAL_VERSION)
        return member


class _LegacyResourcesMixin:
    """Deprecated resource API entry points on OVOSSkill.

    Inheriting this mixin gives a skill the legacy entry points —
    :attr:`resources`, :attr:`dialog_renderer`, :meth:`find_resource` — each
    emitting a :class:`DeprecationWarning` pointing at the spec-tools-backed
    replacement. The mixin holds one cached :class:`SkillResources` instance
    so every legacy call routes through the same object.
    """

    # one cache per (res_dir, lang) for resources / dialog_renderer /
    # find_resource, because the session language can change at runtime
    def _legacy_skill_resources(self, root_directory: Optional[str] = None,
                                lang: Optional[str] = None):
        root_directory = root_directory or self.res_dir
        lang = lang or self.lang
        key = (root_directory, lang)
        cache = getattr(self, "_skill_resources_compat", None)
        if not isinstance(cache, dict):
            cache = {}
            self._skill_resources_compat = cache
        if key not in cache:
            from ovos_workshop.resource_files import SkillResources
            cache[key] = SkillResources(
                root_directory, lang, skill_id=self.skill_id)
        return cache[key]

    def load_dialog_files(self, root_directory: Optional[str] = None):
        """
        Deprecated no-op kept for backwards compatibility.

        ``.dialog`` files are loaded lazily by
        :class:`~ovos_spec_tools.LocaleResources` when a dialog is rendered.
        """

    @property
    @deprecated("self.resources is deprecated; use the high-level skill "
                "methods (speak_dialog, register_intent_file, voc_match, "
                "...) or construct ovos_spec_tools.LocaleResources directly",
                f"{VERSION_MAJOR + 1}.0.0")
    def resources(self):
        """Back-compat handle returning a :class:`SkillResources`.

        .. deprecated::
            Returns a
            :class:`ovos_workshop.resource_files.SkillResources`. The skill
            framework routes through
            :class:`ovos_spec_tools.LocaleResources`. This property keeps
            code calling ``self.resources.load_*``,
            ``self.resources.render_dialog`` etc. working. Migrate to the
            high-level skill methods or construct
            :class:`ovos_spec_tools.LocaleResources` directly.
        """
        # stacklevel=3: warn() -> body -> @deprecated wrapper -> caller
        warnings.warn(
            "self.resources is deprecated; use the high-level skill methods "
            "or construct ovos_spec_tools.LocaleResources directly",
            DeprecationWarning, stacklevel=3)
        return self._legacy_skill_resources()

    @property
    @deprecated("dialog_renderer is deprecated; dialogs are rendered by "
                "ovos_spec_tools.render via OVOSSkill.render_dialog. "
                "This compat shim will be removed.",
                f"{VERSION_MAJOR + 1}.0.0")
    def dialog_renderer(self):
        """Back-compat handle returning the legacy
        :class:`~ovos_utils.dialog.MustacheDialogRenderer`.

        .. deprecated::
            Dialog rendering is performed by :func:`ovos_spec_tools.render`
            via :meth:`render_dialog`. This property returns a real renderer
            so skill code calling ``self.dialog_renderer.render(name, data)``
            keeps working.
        """
        warnings.warn(
            "dialog_renderer is deprecated; use OVOSSkill.render_dialog",
            DeprecationWarning, stacklevel=3)
        return self._legacy_skill_resources().dialog_renderer

    @deprecated("find_resource is deprecated; use ovos_spec_tools.LocaleResources "
                "for resource discovery", f"{VERSION_MAJOR + 1}.0.0")
    def find_resource(self, res_name: str,
                      res_dirname: Optional[str] = None,
                      lang: Optional[str] = None) -> Optional[str]:
        """Find a resource file (legacy).

        .. deprecated::
            Use :class:`ovos_spec_tools.LocaleResources` (or the high-level
            skill methods) for resource discovery. This delegates to
            :func:`ovos_workshop.resource_files.find_resource` for backward
            compatibility with skills that still call it directly.
        """
        # stacklevel=3: warn() -> body -> @deprecated wrapper -> caller
        warnings.warn(
            "OVOSSkill.find_resource is deprecated; use "
            "ovos_spec_tools.LocaleResources for resource discovery",
            DeprecationWarning, stacklevel=3)
        # import locally — the spec-tools-backed path doesn't touch this.
        from ovos_spec_tools import standardize_lang
        from ovos_workshop.resource_files import find_resource as _find
        lang = standardize_lang(lang or self.lang)
        x = _find(res_name, self.res_dir, res_dirname, lang)
        if x:
            return str(x)
        self.log.error(f"Skill {self.skill_id} resource {res_name!r} for lang "
                       f"{lang!r} not found in skill")
        return None

    @property
    def voc_match_cache(self) -> Dict[str, List[str]]:
        """Back-compat accessor for the per-skill vocab cache.

        .. deprecated::
            The cache is an internal detail; the public
            :meth:`OVOSSkill.voc_list` / :meth:`OVOSSkill.voc_match` already
            cache and reuse results. External callers should read or
            invalidate via those methods, not this dict.
        """
        return self._voc_cache

    @voc_match_cache.setter
    @deprecated("OVOSSkill.voc_match_cache external mutation is deprecated; "
                "use voc_list / voc_match instead", _REMOVAL_VERSION)
    def voc_match_cache(self, val):
        warnings.warn(
            "OVOSSkill.voc_match_cache external mutation is deprecated; "
            "use voc_list / voc_match instead",
            DeprecationWarning, stacklevel=2)
        if isinstance(val, dict):
            self._voc_cache = val

    @classproperty
    def runtime_requirements(self) -> RuntimeRequirements:
        """Declare what a skill expects to be available at init and at runtime.

        .. deprecated::
            Deprecated in ovos-core. Skills should let the framework infer
            requirements from the intent surface; this hook stays around for
            one release for the LAN/cache/offline-only skills that still
            override it. Some examples that override it::

                # IOT skill that scans the LAN on init
                scans_on_init = True
                RuntimeRequirements(internet_before_load=False,
                                    network_before_load=scans_on_init,
                                    requires_internet=False,
                                    requires_network=True,
                                    no_internet_fallback=True,
                                    no_network_fallback=False)

                # online search skill with a local cache
                has_cache = False
                RuntimeRequirements(internet_before_load=not has_cache,
                                    network_before_load=not has_cache,
                                    requires_internet=True,
                                    requires_network=True,
                                    no_internet_fallback=True,
                                    no_network_fallback=True)

                # a fully offline skill
                RuntimeRequirements(internet_before_load=False,
                                    network_before_load=False,
                                    requires_internet=False,
                                    requires_network=False,
                                    no_internet_fallback=True,
                                    no_network_fallback=True)
        """
        return RuntimeRequirements()

    @classproperty
    def network_requirements(self) -> RuntimeRequirements:
        """Deprecated alias of :attr:`runtime_requirements`.

        .. deprecated::
            Kept so old skills still load. Override
            :attr:`runtime_requirements` instead.
        """
        warnings.warn(
            "network_requirements is deprecated; rename your override to "
            "runtime_requirements.",
            DeprecationWarning, stacklevel=2)
        LOG.warning("network_requirements renamed to runtime_requirements, "
                    "will be removed in ovos-core 0.0.8")
        return self.runtime_requirements

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
                self.register_homescreen_app(icon=icon,
                                              name=name or self.skill_id,
                                              event=event)
                self.add_event(event, method, speak_errors=False)

    @property
    def __skill_id2name(self) -> str:
        """helper to make a nice string out of a skill_id"""
        return (self.skill_id.split(".")[0].replace("_", " ").
                replace("-", " ").replace("skill", "").title().strip())

    def register_homescreen_app(self, icon: str, name: str, event: str):
        """Register a homescreen app entry.

        .. deprecated:: the homescreen concept is being removed.
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

    def register_resting_screen(self):
        """Register the ``@resting_screen_handler`` methods of the skill.

        ``_startup`` calls this for every skill, so the deprecation warning
        fires only for a skill that has such a handler.

        .. deprecated:: the resting-screen concept is being removed.
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

