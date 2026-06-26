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
import tempfile
import unittest

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


if __name__ == "__main__":
    unittest.main()
