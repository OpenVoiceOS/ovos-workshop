# Copyright 2026 OpenVoiceOS
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
"""Back-compat surface for the pre-``ovos-spec-tools`` resource API.

OVOSSkill no longer drives resource loading through
``ovos_workshop.resource_files.SkillResources`` — it uses
:class:`ovos_spec_tools.LocaleResources` directly. The legacy entry points
are kept for one release so skills that still call them keep working, and
isolated here so the deprecation cycle is a single ``import`` removal away.

Surface that lives in the mixin:

- :attr:`resources` — the deprecated :class:`SkillResources` handle;
- :attr:`dialog_renderer` — the legacy
  :class:`~ovos_utils.dialog.MustacheDialogRenderer`;
- :meth:`find_resource` — pre-``LocaleResources.find`` lookup;
- :meth:`load_dialog_files` — no-op kept because some skill base classes
  call it during boot;
- :attr:`voc_match_cache` — back-compat accessor for the
  :attr:`OVOSSkill._voc_cache` dict;
- :attr:`runtime_requirements` / :attr:`network_requirements` — declared
  deprecated in ovos-core; kept so LAN/cache/offline skills still load.

The mixin assumes its host class supplies the attributes every OVOSSkill
has: ``res_dir``, ``lang``, ``skill_id``, ``log``, and ``_voc_cache``. It
owns one piece of state of its own — ``_skill_resources_compat`` — a
single :class:`SkillResources` instance lazily built on first access and
reused by every method below.

**Lifecycle.** Remove ``_LegacyResourcesMixin`` from :class:`OVOSSkill`'s
bases (and delete this file) when the deprecation period ends; nothing on
OVOSSkill depends on it.
"""
from __future__ import annotations

import warnings
from typing import Dict, List, Optional

from ovos_utils import classproperty
from ovos_utils.log import LOG, deprecated
from ovos_utils.process_utils import RuntimeRequirements
from ovos_workshop.version import VERSION_MAJOR


class _LegacyResourcesMixin:
    """Deprecated pre-spec-tools resource API on OVOSSkill.

    Inheriting this mixin gives a skill back the three legacy entry points —
    :attr:`resources`, :attr:`dialog_renderer`, :meth:`find_resource` — each
    emitting a :class:`DeprecationWarning` pointing at the spec-tools-backed
    replacement. The mixin holds one cached :class:`SkillResources` instance
    so every legacy call routes through the same object.
    """

    # one cache for resources / dialog_renderer / find_resource — single
    # construction point for the deprecated SkillResources object.
    def _legacy_skill_resources(self):
        cached = getattr(self, "_skill_resources_compat", None)
        if cached is None:
            # resource_files is itself deprecated; the SkillResources
            # constructor is silenced for workshop-internal callers via the
            # _caller_is_internal guard in resource_files.py.
            from ovos_workshop.resource_files import SkillResources
            cached = SkillResources(
                self.res_dir, self.lang, skill_id=self.skill_id)
            self._skill_resources_compat = cached
        return cached

    def load_dialog_files(self, root_directory: Optional[str] = None):
        """
        Deprecated no-op kept for backwards compatibility.

        ``.dialog`` files are now loaded lazily by
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
            Historically returned a
            :class:`ovos_workshop.resource_files.SkillResources`. The skill
            framework now routes through
            :class:`ovos_spec_tools.LocaleResources`. This property is kept
            so legacy code calling ``self.resources.load_*``,
            ``self.resources.render_dialog`` etc. keeps working through one
            release. Migrate to the high-level skill methods or construct
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
            Dialog rendering is now performed by :func:`ovos_spec_tools.render`
            via :meth:`render_dialog`. This property keeps returning a real
            renderer so legacy skill code calling
            ``self.dialog_renderer.render(name, data)`` keeps working through
            one release.
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
            override it. Some examples that historically used the override::

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
        """Pre-deprecation alias of :attr:`runtime_requirements`.

        .. deprecated::
            Renamed years ago; kept so old skills still load. Override
            :attr:`runtime_requirements` instead.
        """
        LOG.warning("network_requirements renamed to runtime_requirements, "
                    "will be removed in ovos-core 0.0.8")
        return self.runtime_requirements
