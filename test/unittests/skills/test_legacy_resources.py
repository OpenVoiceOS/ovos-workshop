# Copyright 2026 OpenVoiceOS
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
"""Unit tests for the resource surface of :class:`OVOSSkill` and
:class:`_LegacyResourcesMixin`.

This module pins three independent layers that together define the
backward-compat contract of this PR:

1. **The OVOSSkill resource plumbing** — :attr:`_locale_resources` delegates
   to :meth:`load_lang` so post-init ``res_dir`` mutation is picked up;
   :meth:`render_dialog` resolves via :class:`LocaleResources` and falls
   back to its argument as a literal phrase when no ``.dialog`` matches;
   :attr:`_resource_lang` is the single extension point subclasses
   override to decouple resource lang from query lang.

2. **The :class:`_LegacyResourcesMixin` deprecation shims** — every
   pre-spec-tools surface (``self.resources``, ``self.dialog_renderer``,
   ``self.find_resource``, ``self.voc_match_cache`` mutation,
   ``self.load_dialog_files``, ``self.runtime_requirements``,
   ``self.network_requirements``) keeps working and emits a
   :class:`DeprecationWarning` pointing at the spec-tools replacement.

3. **Legacy file formats in the wild** — ``.qml``, ``.json``, ``.list``,
   ``.value``, ``.word``, ``.template`` resources are not part of
   OVOS-INTENT-2 but skills out there still ship them. The deprecated
   ``self.resources`` accessor hands back a real
   :class:`~ovos_workshop.resource_files.SkillResources`, so these
   formats remain loadable through one release.
"""
import os
import tempfile
import unittest
import warnings
from os.path import dirname, join
from unittest.mock import patch

from ovos_utils.dialog import MustacheDialogRenderer
from ovos_utils.fakebus import FakeBus
from ovos_spec_tools import LocaleResources

from ovos_workshop.skills.ovos import OVOSSkill


def _write(path, text):
    os.makedirs(dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


class _ResourceFixture:
    """Create a temporary skill root with a ``locale/en-US/`` tree."""

    def __init__(self):
        self.root = tempfile.mkdtemp(prefix="wk_resfix_")
        self.locale_en = join(self.root, "locale", "en-US")
        os.makedirs(self.locale_en)

    def write(self, name, text):
        path = join(self.locale_en, name)
        _write(path, text)
        return path

    def cleanup(self):
        import shutil
        shutil.rmtree(self.root, ignore_errors=True)


# --- OVOSSkill resource plumbing --------------------------------------------

class TestLocaleResourcesAttribute(unittest.TestCase):
    """Pin that :attr:`_locale_resources` is a fresh delegation to
    :meth:`load_lang` (so ``res_dir`` mutation takes effect) and that it
    threads the §2.1 override-precedence chain (user → skill → workshop
    core)."""

    def test_locale_resources_is_a_locale_resources(self):
        skill = OVOSSkill(bus=FakeBus(), skill_id="resfix.openvoiceos")
        self.assertIsInstance(skill._locale_resources, LocaleResources)

    def test_locale_resources_picks_up_res_dir_changes(self):
        """The OLD bound-at-init impl missed this; the new property
        delegates to load_lang(self.res_dir) so res_dir mutation works."""
        skill = OVOSSkill(bus=FakeBus(), skill_id="resfix.openvoiceos")
        before = skill._locale_resources
        fixture = _ResourceFixture()
        self.addCleanup(fixture.cleanup)
        skill.res_dir = fixture.root
        after = skill._locale_resources
        self.assertIsNot(before, after)

    def test_locale_resources_caches_by_root_directory(self):
        """Repeated access for the same res_dir returns the same instance."""
        skill = OVOSSkill(bus=FakeBus(), skill_id="resfix.openvoiceos")
        self.assertIs(skill._locale_resources, skill._locale_resources)

    def test_locale_resources_walks_workshop_core_locale(self):
        """A bare skill must still find workshop's bundled vocab (cancel,
        skill.error.dialog, …). This is the §2.1 precedence chain the
        OLD ``LocaleResources(self.res_dir)`` construction silently
        truncated."""
        skill = OVOSSkill(bus=FakeBus(), skill_id="resfix.openvoiceos")
        # workshop ships locale/en-US/cancel.voc; without the core source
        # in the chain, voc_list would return [].
        self.assertTrue(skill.voc_list("cancel", "en-US"),
                        "workshop core cancel.voc not reachable — the "
                        "core_locale source is missing from the chain")


class TestRenderDialog(unittest.TestCase):
    """:meth:`render_dialog` resolves the dialog file via LocaleResources
    and falls back to the argument as a literal utterance when no
    ``.dialog`` exists (the polymorphic ``speak_dialog`` / ``get_response``
    contract)."""

    def setUp(self):
        self.fixture = _ResourceFixture()
        self.skill = OVOSSkill(bus=FakeBus(), skill_id="rd.openvoiceos")
        self.skill.res_dir = self.fixture.root

    def tearDown(self):
        self.fixture.cleanup()

    def test_renders_phrase_from_dialog_file(self):
        self.fixture.write("welcome.dialog", "Hello {name}!\n")
        out = self.skill.render_dialog("welcome", {"name": "world"})
        self.assertEqual(out, "Hello world!")

    def test_missing_dialog_returns_argument_verbatim(self):
        """speak_dialog / get_response accept literal utterances too."""
        out = self.skill.render_dialog("not_a_dialog_key", None)
        self.assertEqual(out, "not_a_dialog_key")


class TestResourceLangExtensionPoint(unittest.TestCase):
    """:attr:`_resource_lang` defaults to :attr:`lang` and overrides
    propagate to every resource lookup site."""

    def test_default_resource_lang_is_self_lang(self):
        skill = OVOSSkill(bus=FakeBus(), skill_id="rl.openvoiceos")
        self.assertEqual(skill._resource_lang, skill.lang)

    def test_subclass_override_changes_voc_list_lookup_lang(self):
        """A subclass that pins resource_lang to a fixed value drives
        every resource-lookup method through that value — the
        single-point extension contract."""
        fixture = _ResourceFixture()
        self.addCleanup(fixture.cleanup)
        fixture.write("greet.voc", "hello\nhi\n")

        class _PinnedSkill(OVOSSkill):
            @property
            def _resource_lang(self):
                return "en-US"

        skill = _PinnedSkill(bus=FakeBus(), skill_id="rl.openvoiceos")
        skill.res_dir = fixture.root
        # voc_list with no lang arg routes through _resource_lang
        self.assertIn("hello", skill.voc_list("greet"))


# --- _LegacyResourcesMixin shims --------------------------------------------

class TestLegacyResourceShimsFireWarnings(unittest.TestCase):
    """Every deprecated entry point emits a :class:`DeprecationWarning`."""

    def setUp(self):
        self.skill = OVOSSkill(bus=FakeBus(), skill_id="leg.openvoiceos")

    def _assert_warns(self, msg_substr, action):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            action()
        deps = [w for w in caught
                if issubclass(w.category, DeprecationWarning)
                and msg_substr in str(w.message)]
        self.assertTrue(deps, f"no DeprecationWarning matched {msg_substr!r}")

    def test_resources_property_warns(self):
        self._assert_warns("self.resources is deprecated",
                           lambda: self.skill.resources)

    def test_dialog_renderer_property_warns(self):
        self._assert_warns("dialog_renderer is deprecated",
                           lambda: self.skill.dialog_renderer)

    def test_find_resource_warns(self):
        self._assert_warns("find_resource is deprecated",
                           lambda: self.skill.find_resource("nope", "voc"))

    def test_voc_match_cache_setter_warns(self):
        def _set():
            self.skill.voc_match_cache = {}
        self._assert_warns("voc_match_cache external mutation is deprecated",
                           _set)


class TestLegacyResourceShimsStillWork(unittest.TestCase):
    """Past the deprecation message, the legacy entry points return
    working objects — skills that still call them keep functioning."""

    def setUp(self):
        self.skill = OVOSSkill(bus=FakeBus(), skill_id="legw.openvoiceos")

    def test_resources_returns_a_skill_resources(self):
        from ovos_workshop.resource_files import SkillResources
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            self.assertIsInstance(self.skill.resources, SkillResources)

    def test_dialog_renderer_returns_a_mustache_dialog_renderer(self):
        """The legacy ``MustacheDialogRenderer`` only materializes when at
        least one ``.dialog`` file exists in the skill's locale tree —
        otherwise the loader returns ``None``. Provide one, then check."""
        fixture = _ResourceFixture()
        self.addCleanup(fixture.cleanup)
        fixture.write("hello.dialog", "Hi {name}\n")
        self.skill.res_dir = fixture.root
        # invalidate any cached SkillResources from the previous tests
        if hasattr(self.skill, "_skill_resources_compat"):
            del self.skill._skill_resources_compat
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            self.assertIsInstance(
                self.skill.dialog_renderer, MustacheDialogRenderer)

    def test_skill_resources_compat_cache_is_shared(self):
        """resources, dialog_renderer and find_resource share one cached
        SkillResources so they do not drift."""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            r1 = self.skill.resources
            r2 = self.skill.resources
            self.assertIs(r1, r2)


class TestLoadDialogFilesNoOp(unittest.TestCase):
    """:meth:`load_dialog_files` is a deprecated no-op kept for skills
    whose base classes call it in their boot path."""

    def test_load_dialog_files_returns_none(self):
        skill = OVOSSkill(bus=FakeBus(), skill_id="ldf.openvoiceos")
        self.assertIsNone(skill.load_dialog_files())


# --- legacy file formats "in the wild" --------------------------------------

class TestLegacyFileFormats(unittest.TestCase):
    """Skills in the wild ship ``.qml`` / ``.json`` / ``.list`` / ``.value``
    / ``.word`` / ``.template`` files — formats outside OVOS-INTENT-2 with
    no spec-tools replacement. They are still loadable through the
    deprecated :attr:`resources` accessor so the skill keeps booting
    while the maintainer migrates."""

    def setUp(self):
        self.fixture = _ResourceFixture()
        self.skill = OVOSSkill(bus=FakeBus(), skill_id="legfmt.openvoiceos")
        self.skill.res_dir = self.fixture.root

    def tearDown(self):
        self.fixture.cleanup()

    def _resources(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            return self.skill.resources

    def test_list_file_loads(self):
        """``.list`` — line-by-line list, no expansion."""
        self.fixture.write("colors.list", "red\ngreen\nblue\n")
        items = self._resources().load_list_file("colors")
        self.assertEqual(sorted(items), ["blue", "green", "red"])

    def test_named_value_file_loads(self):
        """``.value`` — key,value pairs delimited by comma (no whitespace
        stripping of the value: ``"a, b"`` keeps the leading space)."""
        self.fixture.write("aliases.value", "yes,sure\nno,nope\n")
        data = self._resources().load_named_value_file("aliases")
        self.assertEqual(data.get("yes"), "sure")
        self.assertEqual(data.get("no"), "nope")

    def test_template_file_loads(self):
        """``.template`` — returns a list of expanded phrases (the loader
        treats the file as a multi-line template, not a Mustache body)."""
        self.fixture.write("greet.template", "Hello {name}!\n")
        lines = self._resources().load_template_file("greet")
        self.assertTrue(any("Hello" in line for line in lines),
                        f"expected 'Hello' in {lines!r}")

    def test_word_file_loads(self):
        """``.word`` — single token per file."""
        self.fixture.write("magic.word", "abracadabra\n")
        token = self._resources().load_word_file("magic")
        self.assertEqual(token, "abracadabra")

    def test_json_file_loads(self):
        """``.json`` — generic JSON data."""
        import json
        self.fixture.write("config.json", json.dumps({"theme": "dark"}))
        data = self._resources().load_json_file("config.json")
        self.assertEqual(data.get("theme"), "dark")

    def test_find_resource_resolves_qml_file(self):
        """``.qml`` — UI definitions, located via the deprecated
        :meth:`find_resource` (which routes through resource_files)."""
        path = join(self.fixture.root, "ui", "main.qml")
        _write(path, "import QtQuick 2.0\nItem {}\n")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            located = self.skill.find_resource("main.qml", "ui")
        self.assertIsNotNone(located)


# --- user-override precedence (§2.1) ----------------------------------------

class TestUserOverridePrecedence(unittest.TestCase):
    """The bound :class:`LocaleResources` chains user-data > skill > core,
    so a per-user override of a workshop-core resource wins."""

    def setUp(self):
        # Per-test tmp dir holding the user-override locale tree. The
        # override is plumbed via patching ``get_xdg_data_save_path`` —
        # touching os.environ here would contaminate other test classes
        # that read it via cached config.
        self._data_tmp = tempfile.mkdtemp(prefix="wk_uovr_data_")

    def tearDown(self):
        import shutil
        shutil.rmtree(self._data_tmp, ignore_errors=True)

    def test_user_override_wins_over_workshop_core(self):
        """``cancel.voc`` ships in workshop core; a user file at
        ``<xdg-data>/resources/<skill_id>/<lang>/cancel.voc`` overrides it.

        ``ovos_config`` reads the XDG path lazily through
        ``ovos_utils.xdg_utils`` — patch the underlying call so the
        skill picks up our fixture even if the XDG env vars were already
        cached at module import time.
        """
        from ovos_workshop.skills import ovos as _ovos_mod

        skill_id = "uovr.openvoiceos"
        user_root = join(self._data_tmp, "resources", skill_id)
        _write(join(user_root, "en-US", "cancel.voc"),
               "abort\nstop everything\n")

        with patch.object(_ovos_mod, "get_xdg_data_save_path",
                          return_value=self._data_tmp):
            skill = OVOSSkill(bus=FakeBus(), skill_id=skill_id)
            samples = skill.voc_list("cancel", "en-US")
        # the user file contributes ``abort`` and ``stop everything``;
        # the workshop core file does NOT contain those phrases
        self.assertIn("abort", samples)


if __name__ == "__main__":
    unittest.main()
