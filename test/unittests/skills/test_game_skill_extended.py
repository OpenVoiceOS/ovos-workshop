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
"""Extended tests for ovos_workshop/skills/game_skill.py — OVOSGameSkill."""
import os
import tempfile
import unittest

from ovos_utils.fakebus import FakeBus


def _make_game_skill(bus: FakeBus, skill_id: str = "test.game"):
    """Factory to create a concrete OVOSGameSkill subclass for testing."""
    from ovos_workshop.skills.game_skill import OVOSGameSkill

    class ConcreteGameSkill(OVOSGameSkill):
        """Minimal concrete subclass implementing all abstract methods."""

        def on_play_game(self):
            sid = self.get_session_id()
            self._playing_sessions.add(sid)
            self._paused_sessions.discard(sid)

        def on_pause_game(self):
            sid = self.get_session_id()
            self._paused_sessions.add(sid)
            self._playing_sessions.discard(sid)

        def on_resume_game(self):
            sid = self.get_session_id()
            self._paused_sessions.discard(sid)
            self._playing_sessions.add(sid)

        def on_stop_game(self):
            sid = self.get_session_id()
            self._playing_sessions.discard(sid)
            self._paused_sessions.discard(sid)

        def on_save_game(self):
            pass

        def on_load_game(self):
            pass

    return ConcreteGameSkill(
        skill_voc_filename="",
        skill_id=skill_id,
        bus=bus,
    )


class TestOVOSGameSkillInit(unittest.TestCase):
    """Tests for OVOSGameSkill initialization."""

    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()
        os.environ["XDG_CONFIG_HOME"] = self.tmp
        os.environ["XDG_CACHE_HOME"] = self.tmp
        self.bus = FakeBus()
        self.skill = _make_game_skill(self.bus)

    def tearDown(self) -> None:
        os.environ.pop("XDG_CONFIG_HOME", None)
        os.environ.pop("XDG_CACHE_HOME", None)

    def test_instantiates(self) -> None:
        from ovos_workshop.skills.game_skill import OVOSGameSkill
        self.assertIsInstance(self.skill, OVOSGameSkill)

    def test_is_playing_initially_false(self) -> None:
        """is_playing returns False on initialization."""
        self.assertFalse(self.skill.is_playing)

    def test_is_paused_initially_false(self) -> None:
        """is_paused returns False on initialization."""
        self.assertFalse(self.skill.is_paused)

    def test_game_image_default_empty(self) -> None:
        """game_image defaults to empty string."""
        self.assertEqual(self.skill.game_image, "")

    def test_game_image_custom(self) -> None:
        """game_image can be set via constructor."""
        from ovos_workshop.skills.game_skill import OVOSGameSkill

        class Impl(OVOSGameSkill):
            def on_play_game(self): pass
            def on_pause_game(self): pass
            def on_resume_game(self): pass
            def on_stop_game(self): pass
            def on_save_game(self): pass
            def on_load_game(self): pass

        skill = Impl(
            skill_voc_filename="",
            game_image="https://example.com/image.png",
            bus=FakeBus(),
            skill_id="test.game2",
        )
        self.assertEqual(skill.game_image, "https://example.com/image.png")

    def test_supported_media_is_game(self) -> None:
        """OVOSGameSkill sets supported_media to [MediaType.GAME]."""
        from ovos_utils.ocp import MediaType
        self.assertIn(MediaType.GAME, self.skill.supported_media)


class TestOVOSGameSkillIsPlayingPaused(unittest.TestCase):
    """Tests for is_playing and is_paused properties."""

    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()
        os.environ["XDG_CONFIG_HOME"] = self.tmp
        os.environ["XDG_CACHE_HOME"] = self.tmp
        self.bus = FakeBus()
        self.skill = _make_game_skill(self.bus, skill_id="test.game3")

    def tearDown(self) -> None:
        os.environ.pop("XDG_CONFIG_HOME", None)
        os.environ.pop("XDG_CACHE_HOME", None)

    def test_is_playing_after_on_play(self) -> None:
        """is_playing returns True after on_play_game sets the event."""
        self.skill.on_play_game()
        self.assertTrue(self.skill.is_playing)

    def test_is_paused_after_on_pause(self) -> None:
        """is_paused returns True after on_pause_game sets the event."""
        self.skill.on_play_game()
        self.skill.on_pause_game()
        self.assertTrue(self.skill.is_paused)
        self.assertFalse(self.skill.is_playing)


class TestOVOSGameSkillStop(unittest.TestCase):
    """Tests for stop_game() method."""

    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()
        os.environ["XDG_CONFIG_HOME"] = self.tmp
        os.environ["XDG_CACHE_HOME"] = self.tmp
        self.bus = FakeBus()
        self.skill = _make_game_skill(self.bus, skill_id="test.game4")

    def tearDown(self) -> None:
        os.environ.pop("XDG_CONFIG_HOME", None)
        os.environ.pop("XDG_CACHE_HOME", None)

    def test_stop_game_when_not_playing_returns_false(self) -> None:
        """stop_game returns False when not playing."""
        result = self.skill.stop_game()
        self.assertFalse(result)

    def test_stop_game_when_playing_returns_true(self) -> None:
        """stop_game returns True when game is playing."""
        self.skill._playing_sessions.add(self.skill.get_session_id())
        result = self.skill.stop_game()
        self.assertTrue(result)

    def test_stop_game_clears_playing(self) -> None:
        """stop_game clears the per-session playing state."""
        self.skill._playing_sessions.add(self.skill.get_session_id())
        self.skill.stop_game()
        self.assertFalse(self.skill.is_playing)


if __name__ == "__main__":
    unittest.main()
