# Copyright 2024, OpenVoiceOS
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
"""Tests for ovos_workshop/backwards_compat.py — import and basic enum coverage."""
import unittest
import warnings


class TestBackwardsCompatImports(unittest.TestCase):
    """Verify that backwards_compat exports the expected OCP enums/dataclasses."""

    def test_import_module_with_deprecation_warning(self) -> None:
        """Importing backwards_compat raises DeprecationWarning."""
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            import ovos_workshop.backwards_compat  # noqa: F401
            self.assertTrue(
                any(issubclass(w.category, DeprecationWarning) for w in caught),
                "Expected a DeprecationWarning when importing backwards_compat",
            )

    def test_match_confidence_from_ocp(self) -> None:
        """MatchConfidence (or equivalent) is importable from ovos_utils.ocp."""
        from ovos_utils.ocp import MatchConfidence
        self.assertIsNotNone(MatchConfidence)
        self.assertTrue(hasattr(MatchConfidence, "EXACT"))
        self.assertTrue(hasattr(MatchConfidence, "HIGH"))
        self.assertTrue(hasattr(MatchConfidence, "LOW"))

    def test_media_type_values(self) -> None:
        """MediaType enum has expected members."""
        from ovos_utils.ocp import MediaType
        self.assertTrue(hasattr(MediaType, "GENERIC"))
        self.assertTrue(hasattr(MediaType, "MUSIC"))
        self.assertTrue(hasattr(MediaType, "VIDEO"))

    def test_playback_type_values(self) -> None:
        """PlaybackType enum has expected members."""
        from ovos_utils.ocp import PlaybackType
        self.assertTrue(hasattr(PlaybackType, "SKILL"))
        self.assertTrue(hasattr(PlaybackType, "AUDIO"))
        self.assertTrue(hasattr(PlaybackType, "VIDEO"))
        self.assertTrue(hasattr(PlaybackType, "UNDEFINED"))

    def test_player_state_values(self) -> None:
        """PlayerState enum has STOPPED, PLAYING, PAUSED."""
        from ovos_utils.ocp import PlayerState
        self.assertTrue(hasattr(PlayerState, "STOPPED"))
        self.assertTrue(hasattr(PlayerState, "PLAYING"))
        self.assertTrue(hasattr(PlayerState, "PAUSED"))

    def test_media_entry_instantiation(self) -> None:
        """MediaEntry can be instantiated with just a uri."""
        from ovos_utils.ocp import MediaEntry
        entry = MediaEntry(uri="https://example.com/audio.mp3", title="Test")
        self.assertEqual(entry.uri, "https://example.com/audio.mp3")
        self.assertEqual(entry.title, "Test")

    def test_media_entry_infocard(self) -> None:
        """MediaEntry.infocard returns expected keys."""
        from ovos_utils.ocp import MediaEntry
        entry = MediaEntry(uri="https://example.com/audio.mp3", title="Test")
        card = entry.infocard
        self.assertIn("uri", card)
        self.assertIn("track", card)

    def test_playlist_instantiation(self) -> None:
        """Playlist can be instantiated empty."""
        from ovos_utils.ocp import Playlist
        pl = Playlist(title="My Playlist")
        self.assertEqual(pl.title, "My Playlist")
        self.assertEqual(len(pl), 0)

    def test_playlist_add_entry(self) -> None:
        """Playlist.add_entry works with MediaEntry objects."""
        from ovos_utils.ocp import Playlist, MediaEntry
        pl = Playlist(title="Test")
        entry = MediaEntry(uri="https://example.com/song.mp3", title="Song")
        pl.add_entry(entry)
        self.assertEqual(len(pl), 1)

    def test_track_state_values(self) -> None:
        """TrackState enum has expected members."""
        from ovos_utils.ocp import TrackState
        self.assertTrue(hasattr(TrackState, "DISAMBIGUATION"))
        self.assertTrue(hasattr(TrackState, "PLAYING_SKILL"))

    def test_loop_state_values(self) -> None:
        """LoopState enum has expected members."""
        from ovos_utils.ocp import LoopState
        self.assertTrue(hasattr(LoopState, "NONE"))
        self.assertTrue(hasattr(LoopState, "REPEAT"))


if __name__ == "__main__":
    unittest.main()
