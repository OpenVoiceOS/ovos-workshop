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
"""Tests for ovos_workshop/settings.py — PrivateSettings and settings2meta."""
import os
import tempfile
import unittest


class TestSettings2Meta(unittest.TestCase):
    """Unit tests for the settings2meta helper function."""

    def setUp(self) -> None:
        self.tmp_dir = tempfile.mkdtemp()
        os.environ["XDG_CONFIG_HOME"] = self.tmp_dir

    def tearDown(self) -> None:
        os.environ.pop("XDG_CONFIG_HOME", None)

    def test_bool_field_type(self) -> None:
        """Bool values generate 'checkbox' fields."""
        from ovos_workshop.settings import settings2meta
        meta = settings2meta({"enabled": True})
        fields = meta["skillMetadata"]["sections"][0]["fields"]
        bool_field = next(f for f in fields if f["name"] == "enabled")
        self.assertEqual(bool_field["type"], "checkbox")
        self.assertEqual(bool_field["value"], "true")

    def test_str_field_type(self) -> None:
        """String values generate 'text' fields."""
        from ovos_workshop.settings import settings2meta
        meta = settings2meta({"api_key": "abc123"})
        fields = meta["skillMetadata"]["sections"][0]["fields"]
        str_field = next(f for f in fields if f["name"] == "api_key")
        self.assertEqual(str_field["type"], "text")
        self.assertEqual(str_field["value"], "abc123")

    def test_int_field_type(self) -> None:
        """Integer values generate 'number' fields."""
        from ovos_workshop.settings import settings2meta
        meta = settings2meta({"max_results": 5})
        fields = meta["skillMetadata"]["sections"][0]["fields"]
        int_field = next(f for f in fields if f["name"] == "max_results")
        self.assertEqual(int_field["type"], "number")
        self.assertEqual(int_field["value"], "5")

    def test_private_keys_excluded(self) -> None:
        """Keys starting with '_' are excluded from metadata."""
        from ovos_workshop.settings import settings2meta
        meta = settings2meta({"_internal": "hidden", "visible": "yes"})
        fields = meta["skillMetadata"]["sections"][0]["fields"]
        names = [f["name"] for f in fields]
        self.assertNotIn("_internal", names)
        self.assertIn("visible", names)

    def test_section_name(self) -> None:
        """Custom section name is respected."""
        from ovos_workshop.settings import settings2meta
        meta = settings2meta({"x": 1}, section_name="Custom Section")
        section = meta["skillMetadata"]["sections"][0]
        self.assertEqual(section["name"], "Custom Section")

    def test_label_formatting(self) -> None:
        """Underscores and hyphens in keys are converted to title-case labels."""
        from ovos_workshop.settings import settings2meta
        meta = settings2meta({"my_setting": "val"})
        fields = meta["skillMetadata"]["sections"][0]["fields"]
        field = next(f for f in fields if f["name"] == "my_setting")
        self.assertEqual(field["label"], "My Setting")

    def test_empty_settings(self) -> None:
        """Empty dict produces no fields."""
        from ovos_workshop.settings import settings2meta
        meta = settings2meta({})
        fields = meta["skillMetadata"]["sections"][0]["fields"]
        self.assertEqual(fields, [])


class TestPrivateSettings(unittest.TestCase):
    """Unit tests for PrivateSettings class."""

    def setUp(self) -> None:
        self.tmp_dir = tempfile.mkdtemp()
        os.environ["XDG_CONFIG_HOME"] = self.tmp_dir

    def tearDown(self) -> None:
        os.environ.pop("XDG_CONFIG_HOME", None)

    def test_instantiation(self) -> None:
        """PrivateSettings can be instantiated with a skill_id."""
        from ovos_workshop.settings import PrivateSettings
        ps = PrivateSettings("test.skill")
        self.assertIsNotNone(ps)

    def test_dict_operations(self) -> None:
        """PrivateSettings supports basic dict set/get."""
        from ovos_workshop.settings import PrivateSettings
        ps = PrivateSettings("test.skill2")
        ps["key"] = "value"
        self.assertEqual(ps["key"], "value")

    def test_settingsmeta_property(self) -> None:
        """settingsmeta property returns properly structured dict."""
        from ovos_workshop.settings import PrivateSettings
        ps = PrivateSettings("test.skill3")
        ps["volume"] = 80
        ps["enabled"] = True
        meta = ps.settingsmeta
        self.assertIn("skillMetadata", meta)
        sections = meta["skillMetadata"]["sections"]
        self.assertIsInstance(sections, list)
        self.assertGreater(len(sections), 0)


if __name__ == "__main__":
    unittest.main()
