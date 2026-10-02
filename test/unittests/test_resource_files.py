import unittest
import shutil

from os import environ
from os.path import isdir, join, dirname
from pathlib import Path


class TestResourceFiles(unittest.TestCase):
    def test_locate_base_directories(self):
        from ovos_workshop.resource_files import locate_base_directories
        # TODO

    def test_locate_lang_directories(self):
        from ovos_workshop.resource_files import locate_lang_directories
        # TODO

    def test_find_resource(self):
        from ovos_workshop.resource_files import find_resource
        test_dir = join(dirname(__file__), "test_res")

        # Test valid nested request
        valid_dialog = find_resource("test.dialog", test_dir, "dialog", "en-US")
        self.assertEqual(valid_dialog, Path(test_dir, "en-us", "dialog",
                                            "test.dialog"))

        # Test valid top-level lang resource
        valid_vocab = find_resource("test.voc", test_dir, "vocab", "en-US")
        self.assertEqual(valid_vocab, Path(test_dir, "en-us", "test.voc"))

        # Test lang-agnostic resource
        valid_ui = find_resource("test.qml", test_dir, "ui")
        self.assertEqual(valid_ui, Path(test_dir, "ui", "test.qml"))

        # Test valid in other locale
        valid_dialog = find_resource("test.dialog", test_dir, "dialog", "en-gb")
        self.assertEqual(valid_dialog, Path(test_dir, "en-us", "dialog",
                                            "test.dialog"))

        # Test invalid resource
        invalid_resource = find_resource("test.dialog", test_dir, "vocab",
                                         "de-de")
        self.assertIsNone(invalid_resource)


class TestFindResourceLanguageScope(unittest.TestCase):
    """A nested resource resolves inside the requested language only.

    OVOS-INTENT-2 §2: "A loader resolves a resource by searching the language
    directory and all its subdirectories, recursively." The recursion is scoped
    to one language directory, so a request for a language must not be answered
    with another language's file. find_resource used to check only a
    subdirectory whose name equalled res_dirname, then fall back to walking the
    whole locale tree, which returned whichever language scandir listed first.
    """

    def setUp(self):
        import tempfile
        self.root = tempfile.mkdtemp(prefix="ovos-t4396-")
        self.addCleanup(shutil.rmtree, self.root, True)

    def _write(self, rel):
        path = Path(self.root, "locale", rel)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("a template\n", encoding="utf-8")
        return path

    def test_a_nested_resource_resolves_in_the_requested_language(self):
        from ovos_workshop.resource_files import find_resource
        en = self._write("en-US/dialog/no_word.dialog")
        ca = self._write("ca-ES/dialog/no_word.dialog")
        self.assertEqual(find_resource("no_word.dialog", self.root, "locale",
                                       "en-US"), en)
        self.assertEqual(find_resource("no_word.dialog", self.root, "locale",
                                       "ca-ES"), ca)

    def test_another_language_does_not_answer_for_the_requested_one(self):
        """The reported defect: en-US ships no such file, ca-ES does."""
        from ovos_workshop.resource_files import find_resource
        self._write("en-US/spell.intent")
        self._write("ca-ES/dialog/no_word.dialog")
        self.assertIsNone(find_resource("no_word.dialog", self.root, "locale",
                                        "en-US"))

    def test_a_skill_can_detect_a_missing_translation(self):
        """The purpose of the fix: absence is reported as absence."""
        from ovos_workshop.resource_files import find_resource
        self._write("ca-ES/dialog/no_word.dialog")
        self.assertIsNone(find_resource("no_word.dialog", self.root, "locale",
                                        "de-DE"))

    def test_a_deeply_nested_resource_is_found(self):
        """§2 says recursively, not one level."""
        from ovos_workshop.resource_files import find_resource
        deep = self._write("en-US/a/b/c/deep.dialog")
        self.assertEqual(find_resource("deep.dialog", self.root, "locale",
                                       "en-US"), deep)

    def test_a_flat_resource_still_resolves(self):
        from ovos_workshop.resource_files import find_resource
        flat = self._write("en-US/spell.intent")
        self.assertEqual(find_resource("spell.intent", self.root, "locale",
                                       "en-US"), flat)

    def test_a_close_region_still_falls_back(self):
        """§2.2 permits the nearest language; en-GB may answer for en-US."""
        from ovos_workshop.resource_files import find_resource
        gb = self._write("en-GB/dialog/kettle.dialog")
        self.assertEqual(find_resource("kettle.dialog", self.root, "locale",
                                       "en-US"), gb)

    def test_the_result_does_not_depend_on_directory_order(self):
        """Both languages ship it; each request gets its own copy."""
        from ovos_workshop.resource_files import find_resource
        first = self._write("en-US/dialog/both.dialog")
        second = self._write("ca-ES/dialog/both.dialog")
        for lang, expected in (("en-US", first), ("ca-ES", second)):
            with self.subTest(lang=lang):
                self.assertEqual(find_resource("both.dialog", self.root,
                                               "locale", lang), expected)


class TestResourceType(unittest.TestCase):
    from ovos_workshop.resource_files import ResourceType
    # TODO


class TestResourceFile(unittest.TestCase):
    def test_resource_file(self):
        from ovos_workshop.resource_files import ResourceFile
        # TODO

    def test_qml_file(self):
        from ovos_workshop.resource_files import QmlFile, ResourceFile
        self.assertTrue(issubclass(QmlFile, ResourceFile))
        # TODO: test locate/load

    def test_dialog_file(self):
        from ovos_workshop.resource_files import DialogFile, ResourceFile
        self.assertTrue(issubclass(DialogFile, ResourceFile))
        # TODO: test load/render

    def test_vocab_file(self):
        from ovos_workshop.resource_files import VocabularyFile, ResourceFile
        self.assertTrue(issubclass(VocabularyFile, ResourceFile))
        # TODO test load

    def test_named_value_file(self):
        from ovos_workshop.resource_files import NamedValueFile, ResourceFile
        self.assertTrue(issubclass(NamedValueFile, ResourceFile))
        # TODO test load/_load_line

    def test_list_file(self):
        from ovos_workshop.resource_files import ListFile, ResourceFile
        self.assertTrue(issubclass(ListFile, ResourceFile))

    def test_template_file(self):
        from ovos_workshop.resource_files import TemplateFile, ResourceFile
        self.assertTrue(issubclass(TemplateFile, ResourceFile))

    def test_regex_file(self):
        from ovos_workshop.resource_files import RegexFile, ResourceFile
        self.assertTrue(issubclass(RegexFile, ResourceFile))
        # TODO: Test load

    def test_word_file(self):
        from ovos_workshop.resource_files import WordFile, ResourceFile
        self.assertTrue(issubclass(WordFile, ResourceFile))
        # TODO: Test load


class TestSkillResources(unittest.TestCase):
    from ovos_workshop.resource_files import SkillResources
    test_data_path = join(dirname(__file__), "xdg_data")

    @classmethod
    def setUpClass(cls) -> None:
        environ['XDG_DATA_HOME'] = cls.test_data_path

    @classmethod
    def tearDownClass(cls) -> None:
        data_path = environ.pop('XDG_DATA_HOME')
        if isdir(data_path):
            shutil.rmtree(data_path)

    def test_load_dialog_renderer(self):
        """The skill's own dialog is rendered when there is no override."""
        skill_id = "test.dialog.plain"
        skill_dir = self._skill_with_dialog(skill_id, "hello.dialog",
                                            "hello from the skill")
        resources = self.SkillResources(str(skill_dir), "en-us", skill_id=skill_id)
        self.assertEqual(resources.dialog_renderer.render("hello"),
                         "hello from the skill")

    def test_a_user_dialog_override_is_rendered_instead_of_the_skill_one(self):
        """What a skill says must be overridable, like everything else it owns.

        Every other resource type prefers the user override directory, so a
        translation written there changes what the skill hears. Dialog is what
        the skill *says*, and it was read only from the skill's own directory,
        so an override there was written, kept, and never used.
        """
        skill_id = "test.dialog.overridden"
        skill_dir = self._skill_with_dialog(skill_id, "hello.dialog",
                                            "hello from the skill")
        self._user_override(skill_id, "en-us", "hello.dialog", "hello from the user")

        resources = self.SkillResources(str(skill_dir), "en-us", skill_id=skill_id)
        self.assertEqual(resources.dialog_renderer.render("hello"),
                         "hello from the user")

    def test_an_override_for_another_language_is_not_used(self):
        skill_id = "test.dialog.other.lang"
        skill_dir = self._skill_with_dialog(skill_id, "hello.dialog",
                                            "hello from the skill")
        self._user_override(skill_id, "de-de", "hello.dialog", "hallo vom Benutzer")

        resources = self.SkillResources(str(skill_dir), "en-us", skill_id=skill_id)
        self.assertEqual(resources.dialog_renderer.render("hello"),
                         "hello from the skill")

    def _skill_with_dialog(self, skill_id, file_name, text):
        skill_dir = Path(self.test_data_path) / "skills" / skill_id
        dialog_dir = skill_dir / "locale" / "en-us"
        dialog_dir.mkdir(parents=True, exist_ok=True)
        (dialog_dir / file_name).write_text(text, encoding="utf-8")
        return skill_dir

    def _user_override(self, skill_id, lang, file_name, text):
        from ovos_config.locations import get_xdg_data_save_path

        override = Path(get_xdg_data_save_path()) / "resources" / skill_id / lang
        override.mkdir(parents=True, exist_ok=True)
        (override / file_name).write_text(text, encoding="utf-8")
        return override

    def test_define_resource_types(self):
        # TODO
        pass

    def test_load_dialog_file(self):
        # TODO
        pass

    def test_locate_qml_file(self):
        # TODO
        pass

    def test_load_list_file(self):
        # TODO
        pass

    def test_load_named_value_file(self):
        # TODO
        pass

    def test_load_regex_file(self):
        # TODO
        pass

    def test_load_template_file(self):
        # TODO
        pass

    def test_load_vocabulary_file(self):
        # TODO
        pass

    def test_load_word_file(self):
        # TODO
        pass

    def test_render_dialog(self):
        # TODO
        pass

    def test_load_skill_vocabulary(self):
        # TODO
        pass

    def test_load_skill_regex(self):
        # TODO
        pass

    def test_make_unique_regex_group(self):
        # TODO
        pass


class TestCoreResources(unittest.TestCase):
    test_data_path = join(dirname(__file__), "xdg_data")

    @classmethod
    def setUpClass(cls) -> None:
        environ['XDG_DATA_HOME'] = cls.test_data_path
    @classmethod
    def tearDownClass(cls) -> None:
        data_path = environ.pop('XDG_DATA_HOME')
        if isdir(data_path):
            shutil.rmtree(data_path)

    def test_core_resources(self):
        from ovos_workshop.resource_files import CoreResources, SkillResources
        core_res = CoreResources("en-US")
        self.assertIsInstance(core_res, SkillResources)
        self.assertEqual(core_res.language, "en-US")
        self.assertTrue(isdir(core_res.skill_directory))


class TestUserResources(unittest.TestCase):
    test_data_path = join(dirname(__file__), "xdg_data")

    @classmethod
    def setUpClass(cls) -> None:
        environ['XDG_DATA_HOME'] = cls.test_data_path

    @classmethod
    def tearDownClass(cls) -> None:
        data_path = environ.pop('XDG_DATA_HOME')
        if isdir(data_path):
            shutil.rmtree(data_path)

    def test_user_resources(self):
        from ovos_workshop.resource_files import UserResources, SkillResources
        user_res = UserResources("en-US", "test.skill")
        self.assertIsInstance(user_res, SkillResources)
        self.assertEqual(user_res.language, "en-US")
        self.assertEqual(user_res.skill_directory,
                         join(self.test_data_path, "mycroft", "resources",
                              "test.skill"))


class TestRegexExtractor(unittest.TestCase):
    from ovos_workshop.resource_files import RegexExtractor
    # TODO
