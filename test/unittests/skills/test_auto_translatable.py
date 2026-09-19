import os
import shutil
import tempfile
import unittest
from os.path import join

from ovos_workshop.skills.fallback import FallbackSkill
from ovos_workshop.skills.ovos import OVOSSkill


class TestUniversalSkill(unittest.TestCase):
    from ovos_workshop.skills.auto_translatable import UniversalSkill
    test_skill = UniversalSkill()

    def test_00_init(self):
        self.assertIsInstance(self.test_skill, self.UniversalSkill)
        self.assertIsInstance(self.test_skill, OVOSSkill)

    def test_load_lang_honours_root_directory(self):
        skill = self.UniversalSkill()
        lang = skill.internal_language
        skill._load_lang(lang=lang)

        other = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, other)
        voc_dir = join(other, "locale", lang)
        os.makedirs(voc_dir)
        with open(join(voc_dir, "condition.voc"), "w") as f:
            f.write("sunny\n")

        resources = skill._load_lang(root_directory=other, lang=lang)
        self.assertEqual(resources.load_vocabulary_file("condition"),
                         [["sunny"]])

    # TODO: Test other class methods


class TestUniversalFallbackSkill(unittest.TestCase):
    from ovos_workshop.skills.auto_translatable import UniversalFallback

    class _Concrete(UniversalFallback):
        """UniversalFallback inherits the abstract can_answer from
        FallbackSkill and does not implement it, so it stays abstract."""

        def can_answer(self, message):
            return False

    test_skill = _Concrete()

    def test_00_init(self):
        self.assertIsInstance(self.test_skill, self.UniversalFallback)
        self.assertIsInstance(self.test_skill, OVOSSkill)
        self.assertIsInstance(self.test_skill, FallbackSkill)

    # TODO: Test other class methods
