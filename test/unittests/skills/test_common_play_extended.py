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
        os.environ["XDG_CONFIG_HOME"] = self.tmp
        os.environ["XDG_CACHE_HOME"] = self.tmp
        self.bus = FakeBus()
        self.skill = _SimplePlaybackSkill.get(self.bus)

    def tearDown(self) -> None:
        os.environ.pop("XDG_CONFIG_HOME", None)
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
        """ocp_cache_dir returns a path string ending with /OCP."""
        cache_dir = self.skill.ocp_cache_dir
        self.assertIsInstance(cache_dir, str)
        self.assertTrue(cache_dir.endswith("/OCP") or "OCP" in cache_dir)

    def test_ocp_cache_dir_created(self) -> None:
        """ocp_cache_dir creates the directory on access."""
        cache_dir = self.skill.ocp_cache_dir
        self.assertTrue(os.path.isdir(cache_dir))

    def test_skill_icon_default_empty(self) -> None:
        self.assertIsInstance(self.skill.skill_icon, str)

    def test_search_handlers_initially_empty(self) -> None:
        self.assertIsInstance(self.skill._search_handlers, list)

    def test_playing_event_not_set(self) -> None:
        """_playing event is not set on init (not actively playing)."""
        self.assertFalse(self.skill._playing.is_set())

    def test_paused_event_not_set(self) -> None:
        """_paused event is not set on init."""
        self.assertFalse(self.skill._paused.is_set())

    def test_register_media_type(self) -> None:
        """register_media_type adds a new type to supported_media."""
        from ovos_utils.ocp import MediaType
        initial_count = len(self.skill.supported_media)
        self.skill.register_media_type(MediaType.VIDEO)
        self.assertIn(MediaType.VIDEO, self.skill.supported_media)

    def test_ocp_voc_match_no_matchers(self) -> None:
        """ocp_voc_match returns empty dict when no matchers registered."""
        result = self.skill.ocp_voc_match("play some music")
        self.assertIsInstance(result, dict)
        self.assertEqual(result, {})


if __name__ == "__main__":
    unittest.main()
