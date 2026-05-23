# Copyright 2026 OpenVoiceOS
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
"""Dedicated tests for OVOSSkill.load_regex_files.

`.rx` regex resources are kept as a deprecated-but-functional legacy path for
adapt-style intents (their deprecation is separate from, and outlives, the
broader ``resource_files`` deprecation — see PR #413). These tests pin the
behaviour of the self-contained regex loader living on `OVOSSkill` itself:

- a tree with no ``.rx`` files loads silently (no register call, no warning);
- ``.rx`` patterns are read, their ``(?P<name>...)`` groups are prefixed with
  the skill's alphanumeric id (so groups don't collide across skills), and
  each pattern is passed to ``intent_service.register_adapt_regex``;
- a ``DeprecationWarning`` is emitted **only when** at least one ``.rx`` file
  is actually loaded — silent for skills that ship none;
- the specific file path is logged at info level.
"""
import logging
import os
import shutil
import tempfile
import unittest
import warnings
from os.path import join
from unittest.mock import patch

from ovos_utils.fakebus import FakeBus

from ovos_workshop.skills.ovos import OVOSSkill


class TestRegexLoading(unittest.TestCase):
    """Pin the self-contained regex loader on OVOSSkill."""

    @classmethod
    def setUpClass(cls):
        cls._old_xdg_config_home = os.environ.get("XDG_CONFIG_HOME")
        cls._tmp_config = tempfile.mkdtemp(prefix="ws_rx_cfg_")
        os.environ["XDG_CONFIG_HOME"] = cls._tmp_config

    @classmethod
    def tearDownClass(cls):
        if cls._old_xdg_config_home is None:
            os.environ.pop("XDG_CONFIG_HOME", None)
        else:
            os.environ["XDG_CONFIG_HOME"] = cls._old_xdg_config_home
        shutil.rmtree(cls._tmp_config, ignore_errors=True)

    def setUp(self):
        # one tmp skill dir per test, with a locale/ tree we can populate
        self.skill_root = tempfile.mkdtemp(prefix="ws_rx_skill_")
        self.locale_dir = join(self.skill_root, "locale", "en-US")
        os.makedirs(self.locale_dir)
        self.skill = OVOSSkill(bus=FakeBus(), skill_id="rxtest.openvoiceos")
        # capture register_adapt_regex calls
        self.registered = []
        self.skill.intent_service.register_adapt_regex = (
            lambda regex, lang: self.registered.append((regex, lang)))

    def tearDown(self):
        shutil.rmtree(self.skill_root, ignore_errors=True)

    def _write_rx(self, name: str, text: str) -> str:
        path = join(self.locale_dir, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return path

    # --- behaviour --------------------------------------------------------

    def test_no_rx_files_is_silent(self):
        """A skill that ships no .rx must not register anything and must
        emit no deprecation warning."""
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            self.skill.load_regex_files(self.skill_root)
        self.assertEqual(self.registered, [])
        # only assert *our* regex-deprecation warning didn't fire; other
        # unrelated DeprecationWarnings (e.g. the ovos-utils standardize_lang_tag
        # one bubbling up from native_langs) are out of scope here.
        self.assertFalse([w for w in caught
                          if issubclass(w.category, DeprecationWarning)
                          and "padatious" in str(w.message).lower()])

    def test_loading_an_rx_registers_and_warns(self):
        """A real .rx file gets read; its pattern is registered (with the
        skill-id prefix on the named group) and a DeprecationWarning fires."""
        self._write_rx("play.rx", "play (?P<thing>.*) please\n")
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            self.skill.load_regex_files(self.skill_root)
        self.assertEqual(len(self.registered), 1)
        pattern, lang = self.registered[0]
        # the group name is prefixed with the alphanumeric skill id so
        # patterns from different skills do not collide
        self.assertIn("(?P<" + self.skill.alphanumeric_skill_id + "thing>",
                      pattern)
        self.assertEqual(lang, "en-US")
        self.assertTrue(
            any(issubclass(w.category, DeprecationWarning)
                and "padatious" in str(w.message)
                for w in caught),
            "expected a DeprecationWarning recommending padatious-style intents")

    def test_comments_and_blank_lines_are_skipped(self):
        self._write_rx("commented.rx",
                       "# a leading comment\n\n"
                       "stop (?P<what>.*)\n"
                       "\n"
                       "# trailing comment\n")
        self.skill.load_regex_files(self.skill_root)
        self.assertEqual(len(self.registered), 1)

    def test_multiple_rx_files_load(self):
        self._write_rx("a.rx", "alpha (?P<a>.*)\n")
        self._write_rx("b.rx", "beta (?P<b>.*)\n")
        self.skill.load_regex_files(self.skill_root)
        self.assertEqual(len(self.registered), 2)

    def test_filename_is_logged(self):
        """The specific .rx file path is reported at info level when loaded."""
        path = self._write_rx("named.rx", "hello (?P<name>.*)\n")
        with patch.object(self.skill, "log") as mock_log:
            self.skill.load_regex_files(self.skill_root)
        info_calls = [str(c) for c in mock_log.info.call_args_list]
        self.assertTrue(
            any(path in c for c in info_calls),
            f"expected log.info() to mention {path!r}; got: {info_calls}")

    def test_invalid_regex_raises(self):
        """A malformed regex pattern fails compilation — no silent swallow."""
        self._write_rx("bad.rx", "this is (an unclosed group\n")
        import re as _re
        with self.assertRaises(_re.error):
            self.skill.load_regex_files(self.skill_root)


if __name__ == "__main__":
    unittest.main()
