"""Tests for binding OVOSSkill.gui to the standalone ovos-gui-api-client.

The skill-side GUIInterface now lives in `ovos_gui_api_client` (extracted from
ovos-bus-client). SkillGUI must subclass it and construct without the obsolete
`ui_directories` argument (skills no longer ship QML).
"""
import unittest
from unittest.mock import MagicMock

from ovos_utils.fakebus import FakeBus


class TestGUIRebind(unittest.TestCase):
    def test_skillgui_subclasses_api_client_interface(self):
        from ovos_gui_api_client import GUIInterface
        from ovos_workshop.skills.ovos import SkillGUI, GUIInterface as wGUI
        # workshop must import the api-client interface, not the legacy one
        self.assertIs(wGUI, GUIInterface)
        self.assertTrue(issubclass(SkillGUI, GUIInterface))

    def test_app_imports_api_client_interface(self):
        from ovos_gui_api_client import GUIInterface
        import ovos_workshop.app as app
        self.assertIs(app.GUIInterface, GUIInterface)

    def _make_skillgui(self, bus):
        from ovos_workshop.skills.ovos import SkillGUI
        skill = MagicMock()
        skill.skill_id = "test.skill"
        skill.bus = bus
        skill.config_core = {"gui": {}}
        return SkillGUI(skill)

    def test_skillgui_constructs_without_ui_directories(self):
        # regression: new GUIInterface ctor has no ui_directories param
        gui = self._make_skillgui(FakeBus())
        self.assertEqual(gui.skill_id, "test.skill")

    def test_show_template_emits_page_show(self):
        bus = FakeBus()
        seen = []
        bus.on("gui.page.show", lambda m: seen.append(m))
        gui = self._make_skillgui(bus)
        gui.show_text("hello world", "a title")
        self.assertTrue(seen, "show_text should emit gui.page.show")
        page_names = seen[-1].data.get("page_names") or seen[-1].data.get("page")
        self.assertIn("SYSTEM_text", str(page_names))

    def test_show_without_bus_raises(self):
        # contract: a skill always has a bus; calling a template with no bus
        # set is a misconfiguration and surfaces a clear error (it is NOT a
        # silent no-op — the headless/no-adapter no-op guarantee lives in the
        # ovos-gui service + adapter layer, not the skill-side interface).
        from ovos_workshop.skills.ovos import SkillGUI
        skill = MagicMock()
        skill.skill_id = "test.skill"
        skill.bus = None
        skill.config_core = {"gui": {}}
        gui = SkillGUI(skill)
        with self.assertRaises(RuntimeError):
            gui.show_text("needs a bus")


if __name__ == "__main__":
    unittest.main()
