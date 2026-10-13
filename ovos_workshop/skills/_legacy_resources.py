# Copyright 2026 OpenVoiceOS
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
"""Deprecated resource-loading entry points for :class:`OVOSSkill`.

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
  deprecated in ovos-core; kept so LAN/cache/offline skills still load.

The mixin assumes its host class supplies the attributes every OVOSSkill
has: ``res_dir``, ``lang``, ``skill_id``, ``log``, and ``_voc_cache``. It
owns one piece of state of its own — ``_skill_resources_compat`` — a
single :class:`SkillResources` instance lazily built on first access and
reused by every method below.
"""
from __future__ import annotations

import warnings
from typing import Callable, Dict, List, Optional

from ovos_spec_tools import LocaleResources
from ovos_utils import classproperty
from ovos_utils.log import LOG, deprecated, log_deprecation
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
    # find_resource. Keying on the resource language preserves
    # back-compat for UniversalSkill (whose resources live in
    # `internal_language` via `_resource_lang`) and for plain OVOSSkill
    # instances whose session language can change at runtime.
    def _legacy_skill_resources(self, root_directory: Optional[str] = None,
                                lang: Optional[str] = None):
        root_directory = root_directory or self.res_dir
        lang = lang or getattr(self, "_resource_lang", None) or self.lang
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

    # ----- homescreen concept (deprecated entirely, no replacement) -----
    # The framework calls _register_homescreen_app / _register_resting_screen
    # during _startup; these public shims keep external callers + subclass
    # call-sites working and emit both a DeprecationWarning and a log line.
    @deprecated("register_homescreen_app is deprecated; the homescreen "
                "concept is being removed. No replacement is planned.",
                _REMOVAL_VERSION)
    def register_homescreen_app(self, icon: str, name: str, event: str):
        """.. deprecated:: homescreen concept is being removed."""
        warnings.warn(
            "register_homescreen_app is deprecated; the homescreen concept "
            "is being removed. No replacement is planned.",
            DeprecationWarning, stacklevel=2)
        return self._register_homescreen_app(icon, name, event)

    @deprecated("register_resting_screen is deprecated; the resting-screen "
                "/ homescreen concept is being removed. No replacement is "
                "planned.", _REMOVAL_VERSION)
    def register_resting_screen(self):
        """.. deprecated:: resting-screen concept is being removed."""
        warnings.warn(
            "register_resting_screen is deprecated; the resting-screen / "
            "homescreen concept is being removed. No replacement is planned.",
            DeprecationWarning, stacklevel=2)
        return self._register_resting_screen()
