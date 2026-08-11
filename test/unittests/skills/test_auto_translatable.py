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
