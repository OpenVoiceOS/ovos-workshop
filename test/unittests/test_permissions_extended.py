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
"""Extended tests for ovos_workshop/permissions.py — enums and blacklist/whitelist."""
import unittest
from unittest.mock import patch, MagicMock


class TestConverseMode(unittest.TestCase):
    """Tests for the ConverseMode enum."""

    def test_accept_all_value(self) -> None:
        from ovos_workshop.permissions import ConverseMode
        self.assertEqual(ConverseMode.ACCEPT_ALL, "accept_all")

    def test_whitelist_value(self) -> None:
        from ovos_workshop.permissions import ConverseMode
        self.assertEqual(ConverseMode.WHITELIST, "whitelist")

    def test_blacklist_value(self) -> None:
        from ovos_workshop.permissions import ConverseMode
        self.assertEqual(ConverseMode.BLACKLIST, "blacklist")

    def test_is_str_subclass(self) -> None:
        from ovos_workshop.permissions import ConverseMode
        self.assertIsInstance(ConverseMode.ACCEPT_ALL, str)


class TestFallbackMode(unittest.TestCase):
    """Tests for the FallbackMode enum."""

    def test_accept_all_value(self) -> None:
        from ovos_workshop.permissions import FallbackMode
        self.assertEqual(FallbackMode.ACCEPT_ALL, "accept_all")

    def test_whitelist_value(self) -> None:
        from ovos_workshop.permissions import FallbackMode
        self.assertEqual(FallbackMode.WHITELIST, "whitelist")

    def test_blacklist_value(self) -> None:
        from ovos_workshop.permissions import FallbackMode
        self.assertEqual(FallbackMode.BLACKLIST, "blacklist")

    def test_all_members_are_strings(self) -> None:
        from ovos_workshop.permissions import FallbackMode
        for member in FallbackMode:
            self.assertIsInstance(member, str)


class TestConverseActivationMode(unittest.TestCase):
    """Tests for the ConverseActivationMode enum."""

    def test_accept_all_value(self) -> None:
        from ovos_workshop.permissions import ConverseActivationMode
        self.assertEqual(ConverseActivationMode.ACCEPT_ALL, "accept_all")

    def test_priority_value(self) -> None:
        from ovos_workshop.permissions import ConverseActivationMode
        self.assertEqual(ConverseActivationMode.PRIORITY, "priority")

    def test_whitelist_value(self) -> None:
        from ovos_workshop.permissions import ConverseActivationMode
        self.assertEqual(ConverseActivationMode.WHITELIST, "whitelist")

    def test_blacklist_value(self) -> None:
        from ovos_workshop.permissions import ConverseActivationMode
        self.assertEqual(ConverseActivationMode.BLACKLIST, "blacklist")

    def test_four_members(self) -> None:
        from ovos_workshop.permissions import ConverseActivationMode
        self.assertEqual(len(list(ConverseActivationMode)), 4)


class TestBlacklistSkill(unittest.TestCase):
    """Tests for blacklist_skill function."""

    def test_adds_skill_to_blacklist(self) -> None:
        """blacklist_skill adds a skill not already blacklisted and returns True."""
        from ovos_workshop.permissions import blacklist_skill
        mock_config = {"skills": {"blacklisted_skills": []}}
        with patch("ovos_workshop.permissions.update_mycroft_config") as mock_update:
            result = blacklist_skill("test.skill", config=mock_config)
            self.assertTrue(result)
            mock_update.assert_called_once()

    def test_already_blacklisted_returns_false(self) -> None:
        """blacklist_skill returns False if skill is already blacklisted."""
        from ovos_workshop.permissions import blacklist_skill
        mock_config = {"skills": {"blacklisted_skills": ["test.skill"]}}
        with patch("ovos_workshop.permissions.update_mycroft_config") as mock_update:
            result = blacklist_skill("test.skill", config=mock_config)
            self.assertFalse(result)
            mock_update.assert_not_called()

    def test_no_existing_blacklist_key(self) -> None:
        """blacklist_skill works even when blacklisted_skills key is absent."""
        from ovos_workshop.permissions import blacklist_skill
        mock_config = {"skills": {}}
        with patch("ovos_workshop.permissions.update_mycroft_config") as mock_update:
            result = blacklist_skill("new.skill", config=mock_config)
            self.assertTrue(result)
            mock_update.assert_called_once()

    def test_no_skills_key(self) -> None:
        """blacklist_skill works even when skills key is absent."""
        from ovos_workshop.permissions import blacklist_skill
        mock_config = {}
        with patch("ovos_workshop.permissions.update_mycroft_config") as mock_update:
            result = blacklist_skill("new.skill", config=mock_config)
            self.assertTrue(result)
            mock_update.assert_called_once()


if __name__ == "__main__":
    unittest.main()
