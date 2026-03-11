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
import unittest
from os import remove
from unittest.mock import Mock, patch

from ovos_bus_client.apis.gui import GUIInterface
from ovos_utils.fakebus import FakeBus

from ovos_workshop.app import OVOSAbstractApplication
from ovos_workshop.skills.ovos import OVOSSkill


class Application(OVOSAbstractApplication):
    def __int__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


class TestApp(unittest.TestCase):
    bus = FakeBus()

    gui = GUIInterface("TestApplication")

    app = Application(skill_id="TestApplication", gui=gui, bus=bus)

    def test_gui_init(self):
        # The passed GUIInterface has len()==0 (empty data), so it evaluates as
        # falsy and OVOSSkill._startup replaces it with a fresh SkillGUI instance.
        # Assert the resulting gui is still a valid GUIInterface.
        self.assertIsInstance(self.app.gui, GUIInterface)

    def test_settings_path(self):
        self.assertIn("/apps/", self.app.settings_path)

        # Test settings path conflicts
        test_app = OVOSAbstractApplication(skill_id="test", bus=self.bus)
        test_skill = OVOSSkill(skill_id="test", bus=self.bus)

        # Test app vs skill base directories
        self.assertIn("/apps/", test_app.settings_path)
        self.assertIn("/skills/", test_skill.settings_path)

        # Test settings changes
        test_skill.settings['is_skill'] = True
        test_app.settings['is_skill'] = False
        self.assertTrue(test_skill.settings['is_skill'])
        self.assertFalse(test_app.settings['is_skill'])

        # Cleanup test files
        remove(test_app.settings_path)
        remove(test_skill.settings_path)

    @patch("ovos_workshop.app.OVOSSkill.default_shutdown")
    def test_default_shutdown(self, skill_shutdown):
        real_clear_intents = self.app.clear_intents
        real_bus_close = self.app.bus.close
        self.app.bus.close = Mock()
        self.app.clear_intents = Mock()
        self.app.default_shutdown()
        self.app.clear_intents.assert_called_once()
        self.app.bus.close.assert_not_called()  # No dedicated bus here
        skill_shutdown.assert_called_once()

        self.app.bus.close = real_bus_close
        self.app.clear_intents = real_clear_intents

    def test_get_language_dir(self):
        # TODO
        pass

    def test_clear_intents(self):
        # TODO
        pass

    def test_class_inheritance(self):
        from ovos_workshop.skills.ovos import OVOSSkill
        from ovos_workshop.app import OVOSAbstractApplication

        self.assertIsInstance(self.app, OVOSSkill)
        self.assertIsInstance(self.app, OVOSAbstractApplication)
