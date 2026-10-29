import os
import unittest
import shutil
from os import environ
from os.path import join, dirname, isdir
from ovos_workshop.filesystem import FileSystemAccess


class TestFilesystem(unittest.TestCase):
    test_data_path = join(dirname(__file__), "xdg_data")

    @classmethod
    def setUpClass(cls) -> None:
        environ['XDG_DATA_HOME'] = cls.test_data_path

    @classmethod
    def tearDownClass(cls) -> None:
        data_path = environ.pop('XDG_DATA_HOME')
        if isdir(data_path):
            shutil.rmtree(data_path)

    def test_filesystem(self):
        fs = FileSystemAccess("test")

        # FS path init
        self.assertEqual(fs.path, join(self.test_data_path, "mycroft",
                                       "filesystem", "test"))
        self.assertTrue(isdir(fs.path))

        # Invalid open
        with self.assertRaises(FileNotFoundError):
            fs.open("test.txt", "r")
        self.assertFalse(fs.exists("test.txt"))

        # Valid file creation
        file = fs.open("test.txt", "w+")
        self.assertIsNotNone(file)
        file.close()
        self.assertTrue(fs.exists("test.txt"))


class TestFilesystemDirectoryRace(unittest.TestCase):
    def test_existing_directory_when_isdir_reports_missing(self):
        import tempfile
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as base, \
                patch.dict(environ, {"XDG_DATA_HOME": base}):
            marker = join(base, "mycroft", "filesystem", "race", "kept.txt")
            os.makedirs(dirname(marker))
            with open(marker, "w") as f:
                f.write("kept")
            with patch("ovos_workshop.filesystem.isdir", return_value=False):
                fs = FileSystemAccess("race")
            self.assertEqual(fs.path, dirname(marker))
            with fs.open("kept.txt", "r") as f:
                self.assertEqual(f.read(), "kept")
