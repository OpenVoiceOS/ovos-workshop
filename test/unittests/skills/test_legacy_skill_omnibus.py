# Copyright 2026 OpenVoiceOS
# Licensed under the Apache License, Version 2.0
"""Omnibus tripwire: a single skill that exercises **every** deprecated
``OVOSSkill`` resource entry point and **every** legacy resource file
type in one ``initialize``.

The motivation is regression coverage in the migration period — the
unit tests in :mod:`test_legacy_resources` already pin each shim and
each file type individually, but a real skill in the wild typically
combines several of them (e.g. ``runtime_requirements`` declaration +
``.list`` lookup + ``self.dialog_renderer.render`` + ``find_resource``
for a QML page). If any one shim regresses, the omnibus skill below
fails to instantiate or initialize and the failure is easy to bisect.

What this covers:

- **Class-level shims**: ``runtime_requirements`` (override) and the
  ``network_requirements`` alias.
- **Property shims**: ``resources`` (legacy ``SkillResources``),
  ``dialog_renderer`` (legacy ``MustacheDialogRenderer``),
  ``voc_match_cache`` (live ``_voc_cache``).
- **Method shims**: ``load_dialog_files`` (no-op), ``find_resource``.
- **Resource roles loaded via the legacy ``self.resources`` handle**:
  ``.list``, ``.value``, ``.template``, ``.word``, ``.json``.
- **UI resource located via ``find_resource``**: ``.qml``.
- **Adapt registration via the kept legacy entry point**:
  ``load_regex_files`` (``.rx``).

The ``.dialog`` and ``.voc`` modern roles are exercised too — through
``self.dialog_renderer.render`` and ``self.voc_match_cache`` — to lock
the legacy path behaviour, not just the deprecation warning.
"""
from __future__ import annotations

import json
import os
import tempfile
import unittest
import warnings
from os.path import dirname, isfile, join

from ovos_utils import classproperty
from ovos_utils.fakebus import FakeBus
from ovos_utils.process_utils import RuntimeRequirements

from ovos_workshop.skills.ovos import OVOSSkill


def _write(path, text):
    os.makedirs(dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


class _LegacyOmnibusFixture:
    """Skill root with one of every legacy resource type laid out."""

    def __init__(self):
        self.root = tempfile.mkdtemp(prefix="wk_legacy_omni_")
        locale_en = join(self.root, "locale", "en-US")
        os.makedirs(locale_en)

        # legacy resource roles loaded via SkillResources.load_*_file
        _write(join(locale_en, "colors.list"), "red\ngreen\nblue\n")
        _write(join(locale_en, "aliases.value"), "yes,sure\nno,nope\n")
        _write(join(locale_en, "greet.template"),
               "Hello {name}!\n")
        _write(join(locale_en, "magic.word"), "abracadabra\n")
        _write(join(locale_en, "config.json"),
               json.dumps({"theme": "dark"}))
        # modern roles — still loaded through the legacy handle here
        # to lock behaviour
        _write(join(locale_en, "greet.dialog"), "Hello there\n")
        _write(join(locale_en, "yes.voc"), "yes\nyes please\n")
        # adapt regex
        _write(join(locale_en, "play.rx"),
               "play (?P<thing>.+)\n")
        # UI resource located via find_resource — outside the locale tree
        _write(join(self.root, "ui", "main.qml"),
               "import QtQuick 2.0\nItem {}\n")

    def cleanup(self):
        import shutil
        shutil.rmtree(self.root, ignore_errors=True)


class _LegacyOmnibusSkill(OVOSSkill):
    """One skill, every legacy API.

    Each call writes its result to ``self.results`` so the test can
    assert end-state without coupling to the order in which warnings
    fired.
    """

    @classproperty
    def runtime_requirements(self):
        # Offline-skill pattern — historic LAN/cache skills declared
        # exactly this shape; the mixin must still honour subclass
        # overrides.
        return RuntimeRequirements(
            internet_before_load=False,
            network_before_load=False,
            requires_internet=False,
            requires_network=False,
            no_internet_fallback=True,
            no_network_fallback=True)

    def initialize(self):
        self.results = {}

        # method shim — must be callable + return None
        self.results["load_dialog_files"] = self.load_dialog_files()

        # resources -> SkillResources -> load_*_file (one per legacy role)
        res = self.resources
        self.results["list"] = sorted(res.load_list_file("colors"))
        self.results["value"] = res.load_named_value_file("aliases")
        self.results["template"] = res.load_template_file("greet")
        self.results["word"] = res.load_word_file("magic")
        self.results["json"] = res.load_json_file("config.json")

        # modern .voc through the legacy handle — exercises the shared
        # SkillResources cache path. ``load_vocabulary_file`` returns
        # the parsed groups (a list of lists, one per line) — flatten
        # to assert on the surface phrases.
        groups = res.load_vocabulary_file("yes")
        self.results["voc"] = sorted(p for grp in groups for p in grp)

        # dialog_renderer property — must be a real renderer that
        # produces the dialog text on .render(name)
        self.results["dialog"] = self.dialog_renderer.render("greet")

        # voc_match_cache getter — must be the live _voc_cache dict.
        # Mutate it through the legacy accessor and verify the
        # underlying dict moves.
        cache = self.voc_match_cache
        cache["legacy_marker"] = ["marker"]
        self.results["voc_cache_is_live"] = (
            self._voc_cache.get("legacy_marker") == ["marker"])

        # voc_match_cache setter — separate path, triggers the
        # external-mutation DeprecationWarning the test below pins.
        self.voc_match_cache = {"legacy_marker": ["marker"]}

        # find_resource — locate the QML file outside the locale tree
        self.results["qml"] = self.find_resource("main.qml", "ui")


class TestLegacyOmnibusSkill(unittest.TestCase):
    """One skill, every legacy API, every legacy file type."""

    @classmethod
    def setUpClass(cls):
        cls.fixture = _LegacyOmnibusFixture()
        with warnings.catch_warnings():
            # The skill emits a deprecation warning on every legacy
            # call in initialize(); we count them in the dedicated test
            # below. Silence here to keep setUp tidy.
            warnings.simplefilter("ignore", DeprecationWarning)
            # Passing bus + skill_id triggers ``_startup`` which calls
            # ``initialize``; ``resources_dir`` MUST be a constructor
            # kwarg, not a post-init attribute set, otherwise
            # initialize() runs against the wrong res_dir.
            cls.skill = _LegacyOmnibusSkill(
                bus=FakeBus(),
                skill_id="omni.openvoiceos",
                resources_dir=cls.fixture.root)
        cls.results = cls.skill.results

    @classmethod
    def tearDownClass(cls):
        cls.fixture.cleanup()

    # --- class-level shims --------------------------------------------------

    def test_runtime_requirements_override_is_honoured(self):
        self.assertFalse(self.skill.runtime_requirements.requires_internet)
        self.assertFalse(self.skill.runtime_requirements.requires_network)

    def test_network_requirements_alias_returns_same_object(self):
        self.assertEqual(self.skill.network_requirements,
                         self.skill.runtime_requirements)

    # --- method shims -------------------------------------------------------

    def test_load_dialog_files_is_callable_noop(self):
        self.assertIsNone(self.results["load_dialog_files"])

    def test_find_resource_locates_qml_outside_locale_tree(self):
        self.assertIsNotNone(self.results["qml"])
        self.assertTrue(isfile(self.results["qml"]))
        self.assertTrue(self.results["qml"].endswith("main.qml"))

    # --- legacy resource roles ---------------------------------------------

    def test_list_file_loads(self):
        self.assertEqual(self.results["list"], ["blue", "green", "red"])

    def test_named_value_file_loads(self):
        self.assertEqual(self.results["value"].get("yes"), "sure")
        self.assertEqual(self.results["value"].get("no"), "nope")

    def test_template_file_loads(self):
        self.assertTrue(any("Hello" in line for line in self.results["template"]),
                        f"expected 'Hello' in {self.results['template']!r}")

    def test_word_file_loads(self):
        self.assertEqual(self.results["word"], "abracadabra")

    def test_json_file_loads(self):
        self.assertEqual(self.results["json"].get("theme"), "dark")

    def test_vocabulary_file_loads_through_legacy_handle(self):
        self.assertEqual(self.results["voc"], ["yes", "yes please"])

    # --- dialog_renderer + voc_match_cache shims ---------------------------

    def test_dialog_renderer_renders_dialog(self):
        self.assertEqual(self.results["dialog"].strip(), "Hello there")

    def test_voc_match_cache_is_the_live_voc_cache(self):
        self.assertTrue(self.results["voc_cache_is_live"],
                        "voc_match_cache getter did not return the live "
                        "_voc_cache dict — mutation did not propagate")

    # --- deprecation warnings ----------------------------------------------

    def test_initialize_emits_deprecation_warnings_for_every_legacy_call(self):
        """Driving the skill once must surface a DeprecationWarning for
        every legacy entry point (resources, dialog_renderer,
        find_resource, voc_match_cache setter). The omnibus skill's
        ``initialize`` calls each at least once."""
        # Re-run initialize() in a recorded-warnings context so we can
        # inspect each warning category + message; the class-scoped
        # ``setUpClass`` silences them for the result-fetching pass.
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            _LegacyOmnibusSkill(
                bus=FakeBus(),
                skill_id="omni-warn.openvoiceos",
                resources_dir=self.fixture.root)

        deprecations = [w for w in caught
                        if issubclass(w.category, DeprecationWarning)]
        messages = " | ".join(str(w.message) for w in deprecations)
        for needle in ("self.resources is deprecated",
                       "dialog_renderer is deprecated",
                       "find_resource is deprecated",
                       "voc_match_cache external mutation is deprecated"):
            self.assertIn(needle, messages,
                          f"no DeprecationWarning matched {needle!r}; "
                          f"saw: {messages}")


if __name__ == "__main__":
    unittest.main()
