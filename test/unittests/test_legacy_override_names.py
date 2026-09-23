"""The legacy spelling of a user override file is still read, once, with a
warning.

OVOS-INTENT-2 §2 at `OpenVoiceOS/architecture` dev 7b019d3: "A resource base
name MUST consist only of lowercase ASCII letters, digits, and underscores,
and MUST NOT contain whitespace; file extensions are likewise lowercase."

The rename wave brought the skill fleet to that rule. A user's override
folder is not ours to rename, so a file that user wrote as `TurnOn.intent`
or `word.connectors.dialog` is still on their disk under the old name.
§2.1 puts user overrides first in the resolution order, so a file that stops
being found stops overriding, silently.
"""
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import ovos_workshop.resource_files as rf
from ovos_workshop.resource_files import SkillResources

SKILL_ID = "legacy.override.test"
LANG = "en-US"


class LegacyOverrideNameTest(unittest.TestCase):

    def setUp(self):
        self._tmp = TemporaryDirectory()
        root = Path(self._tmp.name)
        self.skill_dir = root / "skill"
        self.xdg = root / "xdg"
        (self.skill_dir / "locale" / LANG).mkdir(parents=True)
        self.override = self.xdg / "resources" / SKILL_ID / "locale" / LANG
        self.override.mkdir(parents=True)
        getattr(rf, "_WARNED_LEGACY_OVERRIDES", set()).clear()

    def tearDown(self):
        self._tmp.cleanup()

    def _resources(self):
        return SkillResources(str(self.skill_dir), LANG, skill_id=SKILL_ID)

    def _render(self, name="hello_world"):
        with patch("ovos_workshop.resource_files.get_xdg_data_save_path",
                   return_value=str(self.xdg)):
            return self._resources().load_dialog_file(name)

    def test_legacy_named_override_is_found_and_warns(self):
        (self.skill_dir / "locale" / LANG / "hello_world.dialog").write_text("from the skill\n")
        (self.override / "HelloWorld.dialog").write_text("from the user\n")
        with patch.object(rf, "log_deprecation", create=True) as warn:
            lines = self._render()
        self.assertEqual(lines, ["from the user"])
        warn.assert_called_once()
        message, version = warn.call_args[0]
        self.assertIn("HelloWorld.dialog", message)
        self.assertIn("hello_world.dialog", message)
        self.assertRegex(version, r"^\d+\.0\.0$")

    def test_dotted_legacy_name_is_found(self):
        (self.override / "hello.world.dialog").write_text("dotted user file\n")
        with patch.object(rf, "log_deprecation", create=True):
            self.assertEqual(self._render(), ["dotted user file"])

    def test_compliant_override_wins_when_both_exist(self):
        (self.override / "hello_world.dialog").write_text("compliant\n")
        (self.override / "HelloWorld.dialog").write_text("legacy\n")
        with patch.object(rf, "log_deprecation", create=True) as warn:
            self.assertEqual(self._render(), ["compliant"])
        warn.assert_not_called()

    def test_no_fallback_inside_the_skills_own_tree(self):
        # the legacy spelling sits in the skill's own locale tree, not in the
        # override folder. The rename wave owns that tree, so nothing is read.
        (self.skill_dir / "locale" / LANG / "HelloWorld.dialog").write_text("skill legacy\n")
        with patch.object(rf, "log_deprecation", create=True) as warn:
            self.assertIsNone(self._render())
        warn.assert_not_called()
        # control: the same file in the override folder IS read, so the
        # measurement above is of the location and not of the file.
        (self.override / "HelloWorld.dialog").write_text("user legacy\n")
        with patch.object(rf, "log_deprecation", create=True):
            self.assertEqual(self._render(), ["user legacy"])

    def test_the_warning_fires_once_per_file(self):
        (self.override / "HelloWorld.dialog").write_text("from the user\n")
        with patch.object(rf, "log_deprecation", create=True) as warn:
            for _ in range(3):
                self.assertEqual(self._render(), ["from the user"])
        self.assertEqual(warn.call_count, 1)

    def test_a_name_with_no_underscore_has_no_legacy_form(self):
        from ovos_workshop.resource_files import legacy_resource_name
        self.assertIsNone(legacy_resource_name("hello.dialog"))
        self.assertEqual(legacy_resource_name("hello_world.dialog"),
                         ["hello.world.dialog", "HelloWorld.dialog"])


if __name__ == "__main__":
    unittest.main()
