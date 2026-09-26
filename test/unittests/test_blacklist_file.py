"""BlacklistFile.load expands bare template syntax: an alternation line like
``(it|this|that)`` must enumerate, not be stored verbatim (verbatim it can
never match and the blacklist is silently inert)."""
import tempfile
import unittest
from os.path import join
from unittest import mock

from ovos_workshop.resource_files import BlacklistFile


def _load(content, vocabularies=None):
    d = tempfile.mkdtemp()
    path = join(d, "word.blacklist")
    with open(path, "w") as f:
        f.write(content)
    bf = BlacklistFile.__new__(BlacklistFile)
    bf.resource_type = mock.Mock()
    bf.resource_name = "word.blacklist"
    bf.file_path = path
    bf.vocabularies = vocabularies
    return bf.load()


class TestBlacklistExpansion(unittest.TestCase):
    def test_plain_lines_unchanged(self):
        self.assertEqual(_load("he\nshe\nthey\n"), ["he", "she", "they"])

    def test_bare_alternation_expands(self):
        phrases = _load("(it|this|that)\n")
        self.assertEqual(sorted(phrases), ["it", "that", "this"])

    def test_optional_group_expands(self):
        phrases = _load("[the] weather\n")
        self.assertIn("weather", [p.strip() for p in phrases])
        self.assertIn("the weather", phrases)

    def test_residual_template_syntax_warns(self):
        with mock.patch("ovos_workshop.resource_files.LOG") as log:
            phrases = _load("he\n")
            self.assertEqual(phrases, ["he"])
            log.warning.assert_not_called()


if __name__ == "__main__":
    unittest.main()
