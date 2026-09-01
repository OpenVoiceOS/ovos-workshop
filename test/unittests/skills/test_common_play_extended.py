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
"""Extended tests for ovos_workshop/skills/common_play.py — OVOSCommonPlaybackSkill."""
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

from ovos_utils.fakebus import FakeBus


class _SimplePlaybackSkill:
    """Concrete OVOSCommonPlaybackSkill subclass for testing."""

    _instance = None

    @classmethod
    def get(cls, bus: FakeBus) -> "OVOSCommonPlaybackSkill":
        from ovos_workshop.skills.common_play import OVOSCommonPlaybackSkill
        from ovos_utils.ocp import MediaType

        class _Impl(OVOSCommonPlaybackSkill):
            pass

        return _Impl(
            skill_id="test.common_play",
            bus=bus,
            supported_media=[MediaType.MUSIC],
        )


class TestOVOSCommonPlaybackSkillInit(unittest.TestCase):
    """Tests for OVOSCommonPlaybackSkill initialization."""

    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()
        self._orig_config_home = os.environ.get("XDG_CONFIG_HOME")
        self._orig_cache_home = os.environ.get("XDG_CACHE_HOME")
        os.environ["XDG_CONFIG_HOME"] = self.tmp
        os.environ["XDG_CACHE_HOME"] = self.tmp
        self.bus = FakeBus()
        self.skill = _SimplePlaybackSkill.get(self.bus)

    def tearDown(self) -> None:
        if self._orig_config_home is not None:
            os.environ["XDG_CONFIG_HOME"] = self._orig_config_home
        else:
            os.environ.pop("XDG_CONFIG_HOME", None)
        if self._orig_cache_home is not None:
            os.environ["XDG_CACHE_HOME"] = self._orig_cache_home
        else:
            os.environ.pop("XDG_CACHE_HOME", None)

    def test_skill_instantiates(self) -> None:
        from ovos_workshop.skills.common_play import OVOSCommonPlaybackSkill
        self.assertIsInstance(self.skill, OVOSCommonPlaybackSkill)

    def test_supported_media_set(self) -> None:
        from ovos_utils.ocp import MediaType
        self.assertIn(MediaType.MUSIC, self.skill.supported_media)

    def test_skill_aliases_is_list(self) -> None:
        self.assertIsInstance(self.skill.skill_aliases, list)

    def test_ocp_cache_dir_property(self) -> None:
        """ocp_cache_dir returns a path string whose final component is OCP."""
        cache_dir = self.skill.ocp_cache_dir
        self.assertIsInstance(cache_dir, str)
        self.assertEqual(os.path.basename(cache_dir), "OCP")

    def test_ocp_cache_dir_created(self) -> None:
        """ocp_cache_dir creates the directory on access."""
        cache_dir = self.skill.ocp_cache_dir
        self.assertTrue(os.path.isdir(cache_dir))

    def test_skill_icon_default_empty(self) -> None:
        self.assertIsInstance(self.skill.skill_icon, str)

    def test_search_handlers_initially_empty(self) -> None:
        self.assertIsInstance(self.skill._search_handlers, list)

    def test_no_playing_sessions_on_init(self) -> None:
        """No session is marked as playing on init (not actively playing)."""
        self.assertEqual(self.skill._playing_sessions, set())
        self.assertEqual(self.skill.playing_sessions, [])
        self.assertFalse(self.skill.is_playing)

    def test_no_paused_sessions_on_init(self) -> None:
        """No session is marked as paused on init."""
        self.assertEqual(self.skill._paused_sessions, set())
        self.assertFalse(self.skill.is_paused)

    def test_register_media_type(self) -> None:
        """register_media_type adds a new type to supported_media."""
        from ovos_utils.ocp import MediaType
        initial_count = len(self.skill.supported_media)
        self.skill.register_media_type(MediaType.VIDEO)
        self.assertIn(MediaType.VIDEO, self.skill.supported_media)
        self.assertEqual(len(self.skill.supported_media), initial_count + 1)

    def test_ocp_voc_match_no_matchers(self) -> None:
        """ocp_voc_match returns empty dict when no matchers registered."""
        result = self.skill.ocp_voc_match("play some music")
        self.assertIsInstance(result, dict)
        self.assertEqual(result, {})


class TestOCPKeywordSoftFail(unittest.TestCase):
    """register_ocp_keyword must still emit ovos.common_play.register_keyword
    over the bus even when the optional ahocorasick_ner dependency is missing.
    """

    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()
        self._orig_config_home = os.environ.get("XDG_CONFIG_HOME")
        self._orig_cache_home = os.environ.get("XDG_CACHE_HOME")
        os.environ["XDG_CONFIG_HOME"] = self.tmp
        os.environ["XDG_CACHE_HOME"] = self.tmp
        self.bus = FakeBus()
        self.skill = _SimplePlaybackSkill.get(self.bus)

    def tearDown(self) -> None:
        if self._orig_config_home is not None:
            os.environ["XDG_CONFIG_HOME"] = self._orig_config_home
        else:
            os.environ.pop("XDG_CONFIG_HOME", None)
        if self._orig_cache_home is not None:
            os.environ["XDG_CACHE_HOME"] = self._orig_cache_home
        else:
            os.environ.pop("XDG_CACHE_HOME", None)

    def _collect(self, event):
        messages = []
        self.bus.on(event, lambda m: messages.append(m))
        return messages

    def test_register_ocp_keyword_emits_with_ner_available(self) -> None:
        """Sanity check: with AhocorasickNER present, the message still emits
        with the same payload shape (samples list)."""
        from ovos_utils.ocp import MediaType

        messages = self._collect("ovos.common_play.register_keyword")
        self.skill.register_ocp_keyword(MediaType.MUSIC, "artist_name",
                                         ["queen", "abba"], langs=["en-us"])
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].data["skill_id"], "test.common_play")
        self.assertEqual(messages[0].data["label"], "artist_name")
        self.assertEqual(sorted(messages[0].data["samples"]), ["abba", "queen"])

    def test_register_ocp_keyword_soft_fails_without_ahocorasick_ner(self) -> None:
        """With ahocorasick_ner unavailable (AhocorasickNER is None), the
        bus emit must still happen with the same payload shape, and no
        exception should propagate."""
        from ovos_utils.ocp import MediaType
        import ovos_workshop.skills.common_play as common_play_mod

        messages = self._collect("ovos.common_play.register_keyword")

        with patch.object(common_play_mod, "AhocorasickNER", None):
            # must not raise, unlike the unfixed code which raised ImportError
            self.skill.register_ocp_keyword(MediaType.MUSIC, "artist_name",
                                             ["queen", "abba"], langs=["en-us"])

        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].data["skill_id"], "test.common_play")
        self.assertEqual(messages[0].data["label"], "artist_name")
        self.assertEqual(messages[0].data["media_type"], MediaType.MUSIC)
        self.assertEqual(sorted(messages[0].data["samples"]), ["abba", "queen"])
        # no local matcher was built for the missing optional dependency
        self.assertNotIn("en-us", self.skill.ocp_matchers)

    def test_register_ocp_keyword_soft_fails_with_empty_samples(self) -> None:
        """Even with an empty sample list and no ahocorasick_ner, the bus
        emit is still the contract and must still fire."""
        from ovos_utils.ocp import MediaType
        import ovos_workshop.skills.common_play as common_play_mod

        messages = self._collect("ovos.common_play.register_keyword")

        with patch.object(common_play_mod, "AhocorasickNER", None):
            self.skill.register_ocp_keyword(MediaType.MUSIC, "artist_name",
                                             [], langs=["en-us"])

        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].data["samples"], [])

    def test_register_ocp_keyword_soft_fails_large_sample_set(self) -> None:
        """The >=20 samples branch exports a CSV via export_ocp_keywords_csv,
        which depends on ocp_matchers being populated. Without
        ahocorasick_ner that export is not possible, so the emit must fall
        back to sending the raw samples instead of silently dropping them."""
        from ovos_utils.ocp import MediaType
        import ovos_workshop.skills.common_play as common_play_mod

        messages = self._collect("ovos.common_play.register_keyword")
        samples = [f"track{i}" for i in range(25)]

        with patch.object(common_play_mod, "AhocorasickNER", None):
            self.skill.register_ocp_keyword(MediaType.MUSIC, "album_name",
                                             samples, langs=["en-us"])

        self.assertEqual(len(messages), 1)
        self.assertIn("samples", messages[0].data)
        self.assertEqual(sorted(messages[0].data["samples"]), sorted(samples))
        self.assertNotIn("csv", messages[0].data)

    def test_register_ocp_keyword_warns_once(self) -> None:
        """The missing-dependency warning should be logged, not silently
        swallowed, so operators can discover why local matching is off."""
        from ovos_utils.ocp import MediaType
        import ovos_workshop.skills.common_play as common_play_mod

        common_play_mod._ner_missing_warned = False
        with patch.object(common_play_mod, "AhocorasickNER", None), \
                patch.object(common_play_mod, "LOG") as mock_log:
            self.skill.register_ocp_keyword(MediaType.MUSIC, "artist_name",
                                             ["queen"], langs=["en-us"])
            self.skill.register_ocp_keyword(MediaType.MUSIC, "artist_name",
                                             ["abba"], langs=["en-us"])
        self.assertEqual(mock_log.warning.call_count, 1)


if __name__ == "__main__":
    unittest.main()
