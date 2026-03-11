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
"""Tests for ovos_workshop/version.py."""
import unittest


class TestVersion(unittest.TestCase):
    """Verify version constants are importable and have correct types."""

    def test_version_major_is_int(self) -> None:
        from ovos_workshop.version import VERSION_MAJOR
        self.assertIsInstance(VERSION_MAJOR, int)

    def test_version_minor_is_int(self) -> None:
        from ovos_workshop.version import VERSION_MINOR
        self.assertIsInstance(VERSION_MINOR, int)

    def test_version_build_is_int(self) -> None:
        from ovos_workshop.version import VERSION_BUILD
        self.assertIsInstance(VERSION_BUILD, int)

    def test_version_alpha_is_int(self) -> None:
        from ovos_workshop.version import VERSION_ALPHA
        self.assertIsInstance(VERSION_ALPHA, int)

    def test_dunder_version_is_str(self) -> None:
        from ovos_workshop.version import __version__
        self.assertIsInstance(__version__, str)

    def test_dunder_version_format(self) -> None:
        """__version__ starts with MAJOR.MINOR.BUILD."""
        from ovos_workshop.version import __version__, VERSION_MAJOR, VERSION_MINOR, VERSION_BUILD
        expected_prefix = f"{VERSION_MAJOR}.{VERSION_MINOR}.{VERSION_BUILD}"
        self.assertTrue(
            __version__.startswith(expected_prefix),
            f"__version__={__version__!r} does not start with {expected_prefix!r}",
        )

    def test_version_values_non_negative(self) -> None:
        from ovos_workshop.version import VERSION_MAJOR, VERSION_MINOR, VERSION_BUILD, VERSION_ALPHA
        self.assertGreaterEqual(VERSION_MAJOR, 0)
        self.assertGreaterEqual(VERSION_MINOR, 0)
        self.assertGreaterEqual(VERSION_BUILD, 0)
        self.assertGreaterEqual(VERSION_ALPHA, 0)


if __name__ == "__main__":
    unittest.main()
