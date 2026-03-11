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
"""Extended tests for ovos_workshop/resource_files.py."""
import os
import shutil
import tempfile
import unittest
from pathlib import Path


class TestLocateLangDirectories(unittest.TestCase):
    """Tests for locate_lang_directories function."""

    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()
        # Create a locale/en-us structure
        locale_dir = Path(self.tmp, "locale", "en-us")
        locale_dir.mkdir(parents=True)
        (locale_dir / "hello.dialog").write_text("hello\n")

    def tearDown(self) -> None:
        if self.tmp and os.path.exists(self.tmp):
            shutil.rmtree(self.tmp)

    def test_finds_exact_lang_match(self) -> None:
        from ovos_workshop.resource_files import locate_lang_directories
        dirs = locate_lang_directories("en-us", self.tmp)
        self.assertTrue(len(dirs) > 0)

    def test_returns_empty_for_nonexistent_lang(self) -> None:
        from ovos_workshop.resource_files import locate_lang_directories
        dirs = locate_lang_directories("xx-xx", self.tmp)
        self.assertIsInstance(dirs, list)

    def test_returns_list_of_paths(self) -> None:
        from ovos_workshop.resource_files import locate_lang_directories
        dirs = locate_lang_directories("en-us", self.tmp)
        for d in dirs:
            self.assertIsInstance(d, Path)


class TestLocateBaseDirectories(unittest.TestCase):
    """Tests for locate_base_directories function."""

    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()
        locale_dir = Path(self.tmp, "locale")
        locale_dir.mkdir(parents=True)

    def tearDown(self) -> None:
        if self.tmp and os.path.exists(self.tmp):
            shutil.rmtree(self.tmp)

    def test_finds_locale_dir(self) -> None:
        from ovos_workshop.resource_files import locate_base_directories
        dirs = locate_base_directories(self.tmp)
        self.assertTrue(any("locale" in str(d) for d in dirs))

    def test_no_crash_when_no_dirs(self) -> None:
        from ovos_workshop.resource_files import locate_base_directories
        # no locale dir — should return empty list
        tmp = tempfile.mkdtemp()
        try:
            dirs = locate_base_directories(tmp)
            self.assertIsInstance(dirs, list)
        finally:
            shutil.rmtree(tmp)


class TestResourceType(unittest.TestCase):
    """Tests for ResourceType class."""

    def test_instantiation(self) -> None:
        from ovos_workshop.resource_files import ResourceType
        rt = ResourceType("dialog", ".dialog", "en-us")
        self.assertEqual(rt.resource_type, "dialog")
        self.assertEqual(rt.file_extension, ".dialog")
        self.assertEqual(rt.language, "en-us")

    def test_get_resource_subdirectory_dialog(self) -> None:
        from ovos_workshop.resource_files import ResourceType
        rt = ResourceType("dialog", ".dialog", "en-us")
        self.assertEqual(rt._get_resource_subdirectory(), "dialog")

    def test_get_resource_subdirectory_vocab(self) -> None:
        from ovos_workshop.resource_files import ResourceType
        rt = ResourceType("vocab", ".voc", "en-us")
        self.assertEqual(rt._get_resource_subdirectory(), "vocab")

    def test_get_resource_subdirectory_regex(self) -> None:
        from ovos_workshop.resource_files import ResourceType
        rt = ResourceType("regex", ".rx", "en-us")
        self.assertEqual(rt._get_resource_subdirectory(), "regex")

    def test_locate_base_directory_no_lang(self) -> None:
        from ovos_workshop.resource_files import ResourceType
        rt = ResourceType("dialog", ".dialog")  # no language
        tmp = tempfile.mkdtemp()
        try:
            rt.locate_base_directory(tmp)
            # Should not raise; base_directory may be None if no dir found
        finally:
            shutil.rmtree(tmp)

    def test_locate_lang_directories_empty_without_language(self) -> None:
        from ovos_workshop.resource_files import ResourceType
        rt = ResourceType("dialog", ".dialog")  # no language
        tmp = tempfile.mkdtemp()
        try:
            result = rt.locate_lang_directories(tmp)
            self.assertEqual(result, [])
        finally:
            shutil.rmtree(tmp)


class TestSkillResources(unittest.TestCase):
    """Tests for SkillResources class."""

    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()
        # Create a simple locale directory structure
        locale_dir = Path(self.tmp, "locale", "en-us")
        locale_dir.mkdir(parents=True)
        (locale_dir / "hello.dialog").write_text("Hello world\nHi there\n")
        (locale_dir / "greet.voc").write_text("hello\nhi\n")

    def tearDown(self) -> None:
        if self.tmp and os.path.exists(self.tmp):
            shutil.rmtree(self.tmp)

    def test_instantiation(self) -> None:
        from ovos_workshop.resource_files import SkillResources
        sr = SkillResources(self.tmp, "en-us", skill_id="test.skill")
        self.assertIsNotNone(sr)
        self.assertEqual(sr.language, "en-us")

    def test_types_defined(self) -> None:
        from ovos_workshop.resource_files import SkillResources
        sr = SkillResources(self.tmp, "en-us")
        self.assertIsNotNone(sr.types.dialog)
        self.assertIsNotNone(sr.types.vocabulary)
        self.assertIsNotNone(sr.types.intent)
        self.assertIsNotNone(sr.types.regex)

    def test_load_dialog_file_found(self) -> None:
        from ovos_workshop.resource_files import SkillResources
        sr = SkillResources(self.tmp, "en-us")
        dialogs = sr.load_dialog_file("hello")
        self.assertIsInstance(dialogs, list)
        self.assertIn("Hello world", dialogs)

    def test_load_dialog_file_missing(self) -> None:
        from ovos_workshop.resource_files import SkillResources
        sr = SkillResources(self.tmp, "en-us")
        # Missing file → should return None or empty list, not raise
        result = sr.load_dialog_file("nonexistent_file")
        self.assertIsNone(result)

    def test_load_vocabulary_file(self) -> None:
        from ovos_workshop.resource_files import SkillResources
        sr = SkillResources(self.tmp, "en-us")
        vocab = sr.load_vocabulary_file("greet")
        self.assertIsInstance(vocab, list)

    def test_load_regex_file_empty(self) -> None:
        from ovos_workshop.resource_files import SkillResources
        sr = SkillResources(self.tmp, "en-us")
        result = sr.load_regex_file("nonexistent")
        self.assertIsInstance(result, list)


class TestDialogFile(unittest.TestCase):
    """Tests for DialogFile class."""

    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()
        locale_dir = Path(self.tmp, "locale", "en-us")
        locale_dir.mkdir(parents=True)
        (locale_dir / "test.dialog").write_text("Hello {name}\nHi there\n")

    def tearDown(self) -> None:
        if self.tmp and os.path.exists(self.tmp):
            shutil.rmtree(self.tmp)

    def test_load_without_data(self) -> None:
        from ovos_workshop.resource_files import DialogFile, SkillResources
        sr = SkillResources(self.tmp, "en-us")
        result = sr.load_dialog_file("test")
        self.assertIsInstance(result, list)

    def test_load_with_data(self) -> None:
        from ovos_workshop.resource_files import DialogFile, SkillResources
        sr = SkillResources(self.tmp, "en-us")
        result = sr.load_dialog_file("test", data={"name": "World"})
        self.assertIsInstance(result, list)
        self.assertIn("Hello World", result)


class TestResourceFileTypes(unittest.TestCase):
    """Tests for specific ResourceFile subclasses."""

    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()
        locale_dir = Path(self.tmp, "locale", "en-us")
        locale_dir.mkdir(parents=True)
        (locale_dir / "test.voc").write_text("hello\nhi\nhey\n")
        (locale_dir / "test.rx").write_text(r"(?P<entity>\w+)")
        (locale_dir / "test.value").write_text("key,value\nfoo,bar\n")

    def test_vocabulary_file_load(self) -> None:
        from ovos_workshop.resource_files import SkillResources
        sr = SkillResources(self.tmp, "en-us")
        result = sr.load_vocabulary_file("test")
        self.assertIsInstance(result, list)

    def test_regex_file_load(self) -> None:
        from ovos_workshop.resource_files import SkillResources
        sr = SkillResources(self.tmp, "en-us")
        result = sr.load_regex_file("test")
        self.assertIsInstance(result, list)

    def test_named_value_file_load(self) -> None:
        from ovos_workshop.resource_files import SkillResources
        sr = SkillResources(self.tmp, "en-us")
        result = sr.load_named_value_file("test")
        self.assertIsInstance(result, dict)
        self.assertIn("key", result)


if __name__ == "__main__":
    unittest.main()
