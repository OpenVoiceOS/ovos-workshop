"""Resource lookup memoizes package directory listings without going stale."""
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from ovos_workshop import resource_files
from ovos_workshop.resource_files import (ResourceType, match_lang_directories,
                                          locate_lang_directories)


def _touch(path: Path, text: str = "x\n"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def _bump_mtime(directory: Path):
    """Move a directory's mtime a second forward, so a change is seen even
    on a filesystem whose timestamps are too coarse to tell two writes apart."""
    st = directory.stat()
    os.utime(directory, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000_000))


class TestResourceLookupCache(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.skill = Path(self.tmp.name)
        for lang in ("en-US", "fr-FR", "de-DE", "es-ES"):
            _touch(self.skill / "locale" / lang / "intents" / "hello.intent")
        resource_files._subdir_cache.clear()
        resource_files._file_index_cache.clear()

    def tearDown(self):
        self.tmp.cleanup()

    def test_same_result_as_uncached(self):
        self.assertEqual(locate_lang_directories("fr-FR", str(self.skill)),
                         [self.skill / "locale" / "fr-FR"])
        self.assertEqual(locate_lang_directories("en-US", str(self.skill)),
                         [self.skill / "locale" / "en-US"])

    def test_listing_is_reused(self):
        locate_lang_directories("fr-FR", str(self.skill))
        with mock.patch.object(resource_files.os, "scandir",
                               side_effect=AssertionError("relisted")):
            for lang in ("fr-FR", "de-DE", "en-US"):
                locate_lang_directories(lang, str(self.skill))

    def test_new_language_directory_is_seen(self):
        self.assertEqual(locate_lang_directories("it-IT", str(self.skill)), [])
        time.sleep(0.01)
        _touch(self.skill / "locale" / "it-IT" / "intents" / "hello.intent")
        # the locale directory's mtime moved, so the listing is refreshed
        self.assertEqual(locate_lang_directories("it-IT", str(self.skill)),
                         [self.skill / "locale" / "it-IT"])

    def test_resource_file_located_once_per_directory(self):
        rt = ResourceType("intent", ".intent", "fr-FR")
        rt.locate_base_directory(str(self.skill))
        first = resource_files.IntentFile(rt, "hello").file_path
        self.assertEqual(first, self.skill / "locale" / "fr-FR" / "intents" / "hello.intent")
        with mock.patch.object(resource_files, "walk",
                               side_effect=AssertionError("walked again")):
            again = resource_files.IntentFile(rt, "hello.intent").file_path
            missing = resource_files.IntentFile(rt, "nope").file_path
        self.assertEqual(again, first)
        self.assertIsNone(missing)

    def test_missing_directory(self):
        self.assertEqual(match_lang_directories("en-US", [self.skill / "absent"]), [])

    def test_exact_match_skips_distance_for_every_other_name(self):
        """A skill whose locale tree ships far more languages than the hub
        serves (ovos-skill-date-time: 65 directories vs. a typical skill's
        handful) paid ovos_spec_tools' lang_matches/lang_distance once per
        unmatched name per lookup -- measured 7-9s of an 11-language boot's
        skill-load phase. An exact (case-insensitive) directory match is
        the nearest any name can be, so it must not cost a distance call
        for the other 64."""
        for lang in (f"xx-{n:02d}" for n in range(60)):
            _touch(self.skill / "locale" / lang / "intents" / "hello.intent")
        resource_files._subdir_cache.clear()
        with mock.patch.object(resource_files, "_lang_dir_distance",
                               side_effect=AssertionError(
                                   "distance scored for a name an exact "
                                   "match already made unnecessary")):
            result = locate_lang_directories("en-US", str(self.skill))
        self.assertEqual(result, [self.skill / "locale" / "en-US"])


if __name__ == "__main__":
    unittest.main()


class TestLocaleVocabulariesMemo(unittest.TestCase):
    def setUp(self):
        from ovos_workshop.resource_files import SkillResources
        self.tmp = tempfile.TemporaryDirectory()
        self.skill = Path(self.tmp.name)
        _touch(self.skill / "locale" / "en-US" / "vocab" / "colour.voc", "Red\nblue\n")
        _touch(self.skill / "locale" / "en-US" / "intents" / "paint.intent", "paint it <colour>\n")
        resource_files._subdir_cache.clear()
        resource_files._file_index_cache.clear()
        self.resources = SkillResources(str(self.skill), "en-US", skill_id="test.skill")

    def tearDown(self):
        self.tmp.cleanup()

    def test_read_once_and_copied(self):
        first = self.resources._locale_vocabularies()
        self.assertEqual(first["colour"], ["red", "blue"])  # workshop's own .voc ride along
        expected = {name: list(members) for name, members in first.items()}
        first["colour"].append("mutated")
        with mock.patch.object(resource_files, "walk",
                               side_effect=AssertionError("walked again")):
            second = self.resources._locale_vocabularies()
        self.assertEqual(second, expected)

    def test_user_override_directory_is_not_cached(self):
        self.resources._locale_vocabularies()
        self.resources.types.vocabulary.user_directory = self.skill / "locale" / "en-US"
        with mock.patch.object(resource_files, "walk", wraps=resource_files.walk) as spy:
            self.resources._locale_vocabularies()
        self.assertTrue(spy.called)


class TestCachesSeeChangesDeepInTheTree(unittest.TestCase):
    """A cache validated by the root's identity alone would miss these.
    (Run with no revalidation window: each lookup checks the tree.)"""

    def setUp(self):
        from ovos_workshop.resource_files import SkillResources
        window = mock.patch.object(resource_files, "_REVALIDATE_AFTER_S", 0)
        window.start()
        self.addCleanup(window.stop)
        self.tmp = tempfile.TemporaryDirectory()
        self.skill = Path(self.tmp.name)
        _touch(self.skill / "locale" / "en-US" / "vocab" / "colour.voc", "red\n")
        _touch(self.skill / "locale" / "en-US" / "intents" / "paint.intent", "paint it <colour>\n")
        resource_files._subdir_cache.clear()
        resource_files._file_index_cache.clear()
        self.resources = SkillResources(str(self.skill), "en-US", skill_id="test.skill")

    def tearDown(self):
        self.tmp.cleanup()

    def test_file_added_in_a_subdirectory_is_found(self):
        rt = ResourceType("intent", ".intent", "en-US")
        rt.locate_base_directory(str(self.skill))
        self.assertIsNone(resource_files.IntentFile(rt, "erase").file_path)
        root_before = os.stat(self.skill / "locale" / "en-US").st_mtime_ns
        time.sleep(0.01)
        _touch(self.skill / "locale" / "en-US" / "intents" / "erase.intent", "erase it\n")
        # the language directory itself did not change...
        self.assertEqual(os.stat(self.skill / "locale" / "en-US").st_mtime_ns, root_before)
        # ...but the subdirectory did, and the index notices
        self.assertEqual(resource_files.IntentFile(rt, "erase").file_path,
                         self.skill / "locale" / "en-US" / "intents" / "erase.intent")

    def test_vocabulary_added_in_a_subdirectory_is_seen(self):
        self.assertNotIn("size", self.resources._locale_vocabularies())
        _touch(self.skill / "locale" / "en-US" / "vocab" / "size.voc", "big\n")
        _bump_mtime(self.skill / "locale" / "en-US" / "vocab")
        self.assertEqual(self.resources._locale_vocabularies()["size"], ["big"])

    def test_vocabulary_edited_in_place_is_reread(self):
        self.assertEqual(self.resources._locale_vocabularies()["colour"], ["red"])
        voc = self.skill / "locale" / "en-US" / "vocab" / "colour.voc"
        dir_before = os.stat(voc.parent).st_mtime_ns
        time.sleep(0.01)
        with open(voc, "w") as f:  # same inode, same directory entry
            f.write("red\ngreen\n")
        self.assertEqual(os.stat(voc.parent).st_mtime_ns, dir_before)
        self.assertEqual(self.resources._locale_vocabularies()["colour"], ["red", "green"])


class TestRevalidationWindow(unittest.TestCase):
    """A lookup repeated within the window reuses the cached result without
    stat'ing its tree; once the window has passed, a change is seen."""

    def setUp(self):
        from ovos_workshop.resource_files import SkillResources
        self.tmp = tempfile.TemporaryDirectory()
        self.skill = Path(self.tmp.name)
        _touch(self.skill / "locale" / "en-US" / "vocab" / "colour.voc", "red\n")
        _touch(self.skill / "locale" / "en-US" / "intents" / "paint.intent", "paint it <colour>\n")
        resource_files._subdir_cache.clear()
        resource_files._file_index_cache.clear()
        self.resources = SkillResources(str(self.skill), "en-US", skill_id="test.skill")
        self.now = [1000.0]
        clock = mock.patch.object(resource_files.time, "monotonic", lambda: self.now[0])
        clock.start()
        self.addCleanup(clock.stop)

    def tearDown(self):
        self.tmp.cleanup()

    def test_no_tree_check_within_the_window(self):
        rt = ResourceType("intent", ".intent", "en-US")
        rt.locate_base_directory(str(self.skill))
        resource_files.IntentFile(rt, "paint").file_path
        self.resources._locale_vocabularies()
        self.now[0] += resource_files._REVALIDATE_AFTER_S / 2
        with mock.patch.object(resource_files, "_tree_still_matches",
                               side_effect=AssertionError("tree re-stat'ed")):
            self.assertIsNotNone(resource_files.IntentFile(rt, "paint").file_path)
            self.assertEqual(self.resources._locale_vocabularies()["colour"], ["red"])

    def test_change_seen_once_the_window_has_passed(self):
        self.assertNotIn("size", self.resources._locale_vocabularies())
        _touch(self.skill / "locale" / "en-US" / "vocab" / "size.voc", "big\n")
        _bump_mtime(self.skill / "locale" / "en-US" / "vocab")
        self.now[0] += resource_files._REVALIDATE_AFTER_S + 0.1
        self.assertEqual(self.resources._locale_vocabularies()["size"], ["big"])
        rt = ResourceType("intent", ".intent", "en-US")
        rt.locate_base_directory(str(self.skill))
        self.assertIsNone(resource_files.IntentFile(rt, "erase").file_path)
        _touch(self.skill / "locale" / "en-US" / "intents" / "erase.intent", "erase it\n")
        self.now[0] += resource_files._REVALIDATE_AFTER_S + 0.1
        self.assertIsNotNone(resource_files.IntentFile(rt, "erase").file_path)
