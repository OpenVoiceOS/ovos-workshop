# Copyright 2024 Mycroft AI Inc.
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
"""Tests for OVOSSkill.ask_yesno and ask_selection agent-plugin integration."""
import unittest
from unittest.mock import MagicMock, patch


def _make_skill(settings=None, config_skills=None):
    """Build a minimal duck-typed object for testing OVOSSkill helper methods."""
    from ovos_workshop.skills.ovos import OVOSSkill
    import types

    # Bind the methods under test onto a plain object to avoid OVOSSkill.__init__
    skill = MagicMock(spec=object)
    skill.settings = settings or {}
    skill.config_core = {"skills": config_skills or {}}
    skill.lang = "en-us"

    skill._get_yesno_engine = types.MethodType(OVOSSkill._get_yesno_engine, skill)
    skill._get_selection_engine = types.MethodType(OVOSSkill._get_selection_engine, skill)
    skill.ask_yesno = types.MethodType(OVOSSkill.ask_yesno, skill)
    skill.ask_selection = types.MethodType(OVOSSkill.ask_selection, skill)
    return skill


class TestGetYesnoEngine(unittest.TestCase):
    """Tests for OVOSSkill._get_yesno_engine()."""

    def test_no_plugin_configured_returns_none(self):
        skill = _make_skill()
        self.assertIsNone(skill._get_yesno_engine())

    def test_config_core_plugin_loaded(self):
        skill = _make_skill(config_skills={"ask_yesno_plugin": "fake-yesno-plugin"})
        mock_cls = MagicMock()
        mock_instance = MagicMock()
        mock_cls.return_value = mock_instance
        with patch("ovos_plugin_manager.agents.load_yesno_plugin", return_value=mock_cls):
            engine = skill._get_yesno_engine()
        self.assertIs(engine, mock_instance)

    def test_settings_overrides_config_core(self):
        skill = _make_skill(
            settings={"ask_yesno_plugin": "settings-plugin"},
            config_skills={"ask_yesno_plugin": "config-plugin"},
        )
        mock_cls = MagicMock()
        with patch("ovos_plugin_manager.agents.load_yesno_plugin", return_value=mock_cls) as mock_load:
            skill._get_yesno_engine()
        mock_load.assert_called_once_with("settings-plugin")

    def test_plugin_load_failure_returns_none(self):
        skill = _make_skill(config_skills={"ask_yesno_plugin": "bad-plugin"})
        with patch("ovos_plugin_manager.agents.load_yesno_plugin", side_effect=Exception("oops")):
            engine = skill._get_yesno_engine()
        self.assertIsNone(engine)

    def test_engine_cached_across_calls(self):
        skill = _make_skill(config_skills={"ask_yesno_plugin": "fake-plugin"})
        mock_cls = MagicMock()
        with patch("ovos_plugin_manager.agents.load_yesno_plugin", return_value=mock_cls) as mock_load:
            skill._get_yesno_engine()
            skill._get_yesno_engine()
        mock_load.assert_called_once()


class TestGetSelectionEngine(unittest.TestCase):
    """Tests for OVOSSkill._get_selection_engine()."""

    def test_no_config_defaults_to_fuzzy_plugin(self):
        """When no plugin is configured, ovos-option-matcher-fuzzy-plugin is used."""
        skill = _make_skill()
        mock_cls = MagicMock()
        with patch("ovos_plugin_manager.agents.load_option_matcher_plugin", return_value=mock_cls) as mock_load:
            skill._get_selection_engine()
        mock_load.assert_called_once_with("ovos-option-matcher-fuzzy-plugin")

    def test_config_core_plugin_loaded(self):
        skill = _make_skill(config_skills={"ask_selection_plugin": "fake-option-matcher"})
        mock_cls = MagicMock()
        mock_instance = MagicMock()
        mock_cls.return_value = mock_instance
        with patch("ovos_plugin_manager.agents.load_option_matcher_plugin", return_value=mock_cls):
            engine = skill._get_selection_engine()
        self.assertIs(engine, mock_instance)

    def test_settings_overrides_config_core(self):
        skill = _make_skill(
            settings={"ask_selection_plugin": "settings-option-matcher"},
            config_skills={"ask_selection_plugin": "config-option-matcher"},
        )
        mock_cls = MagicMock()
        with patch("ovos_plugin_manager.agents.load_option_matcher_plugin", return_value=mock_cls) as mock_load:
            skill._get_selection_engine()
        mock_load.assert_called_once_with("settings-option-matcher")

    def test_plugin_load_failure_returns_none(self):
        skill = _make_skill(config_skills={"ask_selection_plugin": "bad-plugin"})
        with patch("ovos_plugin_manager.agents.load_option_matcher_plugin", side_effect=Exception("fail")):
            engine = skill._get_selection_engine()
        self.assertIsNone(engine)


class TestAskYesno(unittest.TestCase):
    """Tests for OVOSSkill.ask_yesno()."""

    def _make_skill_with_response(self, response, settings=None, config_skills=None):
        skill = _make_skill(settings=settings, config_skills=config_skills)
        skill.get_response = MagicMock(return_value=response)
        return skill

    def test_no_plugin_uses_yesno_solver_yes(self):
        skill = self._make_skill_with_response("yeah sure")
        with patch("ovos_workshop.skills.ovos.YesNoSolver") as mock_solver_cls:
            mock_solver = MagicMock()
            mock_solver.match_yes_or_no.return_value = True
            mock_solver_cls.return_value = mock_solver
            result = skill.ask_yesno("Do you want tea?")
        self.assertEqual(result, "yes")

    def test_no_plugin_uses_yesno_solver_no(self):
        skill = self._make_skill_with_response("nope")
        with patch("ovos_workshop.skills.ovos.YesNoSolver") as mock_solver_cls:
            mock_solver = MagicMock()
            mock_solver.match_yes_or_no.return_value = False
            mock_solver_cls.return_value = mock_solver
            result = skill.ask_yesno("Do you want tea?")
        self.assertEqual(result, "no")

    def test_no_plugin_unmatched_returns_raw_resp(self):
        skill = self._make_skill_with_response("maybe later")
        with patch("ovos_workshop.skills.ovos.YesNoSolver") as mock_solver_cls:
            mock_solver = MagicMock()
            mock_solver.match_yes_or_no.return_value = None
            mock_solver_cls.return_value = mock_solver
            result = skill.ask_yesno("Do you want tea?")
        self.assertEqual(result, "maybe later")

    def test_no_plugin_none_response_returns_none(self):
        skill = self._make_skill_with_response(None)
        result = skill.ask_yesno("Do you want tea?")
        self.assertIsNone(result)

    def test_plugin_configured_calls_engine(self):
        skill = self._make_skill_with_response("yes please",
                                               config_skills={"ask_yesno_plugin": "fake-plugin"})
        mock_engine = MagicMock()
        mock_engine.yes_or_no.return_value = True
        with patch.object(skill, "_get_yesno_engine", return_value=mock_engine):
            result = skill.ask_yesno("Do you want tea?")
        mock_engine.yes_or_no.assert_called_once_with(
            question="Do you want tea?", response="yes please", lang="en-us"
        )
        self.assertEqual(result, "yes")

    def test_plugin_configured_no_response(self):
        skill = self._make_skill_with_response(None,
                                               config_skills={"ask_yesno_plugin": "fake-plugin"})
        mock_engine = MagicMock()
        with patch.object(skill, "_get_yesno_engine", return_value=mock_engine):
            result = skill.ask_yesno("Do you want tea?")
        mock_engine.yes_or_no.assert_not_called()
        self.assertIsNone(result)

    def test_plugin_returns_false_maps_to_no(self):
        skill = self._make_skill_with_response("no way",
                                               config_skills={"ask_yesno_plugin": "fake-plugin"})
        mock_engine = MagicMock()
        mock_engine.yes_or_no.return_value = False
        with patch.object(skill, "_get_yesno_engine", return_value=mock_engine):
            result = skill.ask_yesno("Do you want tea?")
        self.assertEqual(result, "no")


class TestAskSelection(unittest.TestCase):
    """Tests for OVOSSkill.ask_selection()."""

    def _make_selection_skill(self, response, settings=None, config_skills=None):
        skill = _make_skill(settings=settings, config_skills=config_skills)
        skill.get_response = MagicMock(return_value=response)
        skill.speak = MagicMock()
        return skill

    def test_plugin_called_with_response(self):
        """Default fuzzy plugin (or any configured plugin) receives the user response."""
        skill = self._make_selection_skill("beta")
        options = ["alpha", "beta", "gamma"]
        mock_engine = MagicMock()
        mock_engine.match_option.return_value = "beta"
        with patch.object(skill, "_get_selection_engine", return_value=mock_engine):
            result = skill.ask_selection(options, numeric=True)
        mock_engine.match_option.assert_called_once_with(
            utterance="beta", options=options, lang="en-us"
        )
        self.assertEqual(result, "beta")

    def test_plugin_runtime_failure_returns_none(self):
        """If the engine raises, ask_selection returns None rather than crashing."""
        skill = self._make_selection_skill("alpha")
        options = ["alpha", "beta", "gamma"]
        mock_engine = MagicMock()
        mock_engine.match_option.side_effect = RuntimeError("model error")
        with patch.object(skill, "_get_selection_engine", return_value=mock_engine):
            result = skill.ask_selection(options, numeric=True)
        self.assertIsNone(result)

    def test_no_engine_no_response_returns_none(self):
        """If engine load fails and user gives no response, return None."""
        skill = self._make_selection_skill(None)
        options = ["alpha", "beta"]
        with patch.object(skill, "_get_selection_engine", return_value=None):
            result = skill.ask_selection(options, numeric=True)
        self.assertIsNone(result)

    def test_no_response_returns_none(self):
        skill = self._make_selection_skill(None)
        options = ["alpha", "beta"]
        result = skill.ask_selection(options, numeric=True)
        self.assertIsNone(result)

    def test_single_option_returns_immediately(self):
        skill = self._make_selection_skill(None)
        result = skill.ask_selection(["only"], numeric=True)
        self.assertEqual(result, "only")
        skill.speak.assert_not_called()

    def test_empty_options_returns_none(self):
        skill = self._make_selection_skill(None)
        result = skill.ask_selection([])
        self.assertIsNone(result)

    def test_invalid_options_raises(self):
        skill = self._make_selection_skill(None)
        with self.assertRaises(ValueError):
            skill.ask_selection("not a list")

    def test_settings_plugin_overrides_default(self):
        """settings.json ask_selection_plugin takes precedence over the fuzzy default."""
        skill = self._make_selection_skill(
            "first", settings={"ask_selection_plugin": "my-custom-option-matcher"}
        )
        options = ["alpha", "beta", "gamma"]
        mock_cls = MagicMock()
        mock_instance = MagicMock()
        mock_instance.match_option.return_value = "alpha"
        mock_cls.return_value = mock_instance
        with patch("ovos_plugin_manager.agents.load_option_matcher_plugin", return_value=mock_cls) as mock_load:
            skill.ask_selection(options, numeric=True)
        mock_load.assert_called_once_with("my-custom-option-matcher")


if __name__ == "__main__":
    unittest.main()
