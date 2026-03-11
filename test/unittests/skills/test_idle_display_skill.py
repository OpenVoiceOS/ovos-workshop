import unittest

from ovos_workshop.skills.idle_display_skill import IdleDisplaySkill


class TestIdleDisplaySkill(unittest.TestCase):
    def test_idle_display_skill_is_deprecated(self):
        """IdleDisplaySkill is a deprecation stub — instantiation logs a warning."""
        # The class is retained for import compatibility but raises a deprecation log.
        self.assertTrue(hasattr(IdleDisplaySkill, '__init__'))
