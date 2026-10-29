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
"""The dialogs ovos-workshop speaks itself ship in every workshop locale."""
import re
import unittest
from pathlib import Path

import ovos_workshop

PACKAGE = Path(ovos_workshop.__file__).parent
LOCALE = PACKAGE / "locale"
# OVOS-INTENT-2 §2: a resource base name is lowercase letters, digits and underscores
BASE_NAME = re.compile(r"[a-z0-9_]+")
SPOKEN = re.compile(
    r"(?:speak_dialog|render_dialog|load_dialog_file)\((['\"])([^'\"]+)\1")


def spoken_dialogs() -> set:
    """The dialog names the workshop's own code passes as string literals."""
    return {match.group(2)
            for source in (PACKAGE / "skills").rglob("*.py")
            for match in SPOKEN.finditer(source.read_text(encoding="utf-8"))}


class TestWorkshopDialogs(unittest.TestCase):
    def test_code_speaks_dialogs(self):
        self.assertTrue({"cant_save_game", "game_pause"} <= spoken_dialogs())

    def test_spoken_dialogs_have_spec_base_names(self):
        bad = sorted(name for name in spoken_dialogs()
                     if not BASE_NAME.fullmatch(name))
        self.assertEqual(bad, [])

    def test_every_locale_ships_every_spoken_dialog(self):
        names = spoken_dialogs()
        locales = sorted(d for d in LOCALE.iterdir() if d.is_dir())
        self.assertGreater(len(locales), 40)
        missing = [f"{locale.name}/{name}.dialog"
                   for locale in locales for name in sorted(names)
                   if not (locale / f"{name}.dialog").is_file()]
        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
