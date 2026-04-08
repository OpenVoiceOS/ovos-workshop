import unittest

from ovos_workshop.skills.fallback import FallbackSkill
from ovos_workshop.skills.ovos import OVOSSkill


class TestUniversalSkill(unittest.TestCase):
    from ovos_workshop.skills.auto_translatable import UniversalSkill
    test_skill = UniversalSkill()

    def test_00_init(self):
        self.assertIsInstance(self.test_skill, self.UniversalSkill)
        self.assertIsInstance(self.test_skill, OVOSSkill)

    # TODO: Test other class methods


class TestUniversalFallbackSkill(unittest.TestCase):
    from ovos_workshop.skills.auto_translatable import UniversalFallback
    test_skill = UniversalFallback()

    def test_00_init(self):
        self.assertIsInstance(self.test_skill, self.UniversalFallback)
        self.assertIsInstance(self.test_skill, OVOSSkill)
        self.assertIsInstance(self.test_skill, FallbackSkill)

    # TODO: Test other class methods
