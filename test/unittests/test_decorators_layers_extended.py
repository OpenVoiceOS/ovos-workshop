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
"""Extended tests for ovos_workshop/decorators/layers.py — IntentLayers and decorators."""
import unittest
from unittest.mock import MagicMock, patch


class TestIntentLayers(unittest.TestCase):
    """Tests for the IntentLayers class."""

    def _make_layers(self, skill_id: str = "test.skill") -> "IntentLayers":
        from ovos_workshop.decorators.layers import IntentLayers
        mock_skill = MagicMock()
        mock_skill.skill_id = skill_id
        layers = IntentLayers()
        layers.bind(mock_skill)
        return layers

    def test_instantiation(self) -> None:
        from ovos_workshop.decorators.layers import IntentLayers
        layers = IntentLayers()
        self.assertIsNone(layers.skill)

    def test_bind_sets_skill(self) -> None:
        from ovos_workshop.decorators.layers import IntentLayers
        mock_skill = MagicMock()
        mock_skill.skill_id = "test.skill"
        layers = IntentLayers()
        result = layers.bind(mock_skill)
        self.assertIs(layers.skill, mock_skill)
        self.assertIs(result, layers)  # bind returns self

    def test_skill_id_with_skill(self) -> None:
        layers = self._make_layers("demo.skill")
        self.assertEqual(layers.skill_id, "demo.skill")

    def test_skill_id_without_skill(self) -> None:
        from ovos_workshop.decorators.layers import IntentLayers
        layers = IntentLayers()
        self.assertEqual(layers.skill_id, "IntentLayers")

    def test_active_layers_empty_initially(self) -> None:
        layers = self._make_layers()
        self.assertEqual(layers.active_layers, [])

    def test_update_layer_creates_layer(self) -> None:
        layers = self._make_layers("test.skill")
        layers.update_layer("my_layer", ["test.skill:intent1"])
        self.assertIn("test.skill:my_layer", layers._layers)

    def test_update_layer_prepends_skill_id(self) -> None:
        layers = self._make_layers("test.skill")
        layers.update_layer("my_layer")
        self.assertIn("test.skill:my_layer", layers._layers)

    def test_activate_layer_marks_active(self) -> None:
        layers = self._make_layers("test.skill")
        layers.update_layer("my_layer", ["intent1"])
        layers.activate_layer("my_layer")
        self.assertTrue(layers.is_active("my_layer"))

    def test_activate_nonexistent_layer_no_error(self) -> None:
        layers = self._make_layers()
        # Should not raise — just logs debug
        layers.activate_layer("nonexistent")

    def test_deactivate_layer_marks_inactive(self) -> None:
        layers = self._make_layers("test.skill")
        layers.update_layer("my_layer", ["intent1"])
        layers.activate_layer("my_layer")
        self.assertTrue(layers.is_active("my_layer"))
        layers.deactivate_layer("my_layer")
        self.assertFalse(layers.is_active("my_layer"))

    def test_is_active_false_for_unknown(self) -> None:
        layers = self._make_layers()
        self.assertFalse(layers.is_active("unknown_layer"))

    def test_remove_layer_deletes_it(self) -> None:
        layers = self._make_layers("test.skill")
        layers.update_layer("to_remove", ["intent1"])
        layers.remove_layer("to_remove")
        self.assertNotIn("test.skill:to_remove", layers._layers)

    def test_replace_layer_updates_intents(self) -> None:
        layers = self._make_layers("test.skill")
        layers.update_layer("my_layer", ["intent1"])
        layers.replace_layer("my_layer", ["intent2", "intent3"])
        self.assertEqual(layers._layers["test.skill:my_layer"], ["intent2", "intent3"])

    def test_replace_layer_creates_if_missing(self) -> None:
        layers = self._make_layers("test.skill")
        layers.replace_layer("new_layer", ["intent_x"])
        self.assertIn("test.skill:new_layer", layers._layers)

    def test_disable_deactivates_all_layers(self) -> None:
        layers = self._make_layers("test.skill")
        layers.update_layer("layer_a", ["intent1"])
        layers.update_layer("layer_b", ["intent2"])
        layers.activate_layer("layer_a")
        layers.activate_layer("layer_b")
        layers.disable()
        self.assertFalse(layers.is_active("layer_a"))
        self.assertFalse(layers.is_active("layer_b"))


class TestLayerIntentDecorator(unittest.TestCase):
    """Tests for the layer_intent decorator."""

    def test_layer_intent_sets_intents_attr(self) -> None:
        from ovos_workshop.decorators.layers import layer_intent

        @layer_intent("some_intent", "my_layer")
        def my_handler():
            pass

        self.assertTrue(hasattr(my_handler, "intents"))
        self.assertIn("some_intent", my_handler.intents)

    def test_layer_intent_sets_intent_layers_attr(self) -> None:
        from ovos_workshop.decorators.layers import layer_intent

        @layer_intent("some_intent", "my_layer")
        def my_handler():
            pass

        self.assertTrue(hasattr(my_handler, "intent_layers"))
        self.assertIn("my_layer", my_handler.intent_layers)
        self.assertIn("some_intent", my_handler.intent_layers["my_layer"])

    def test_layer_intent_with_builder_name(self) -> None:
        """layer_intent with an IntentBuilder extracts intent name."""
        from ovos_workshop.decorators.layers import layer_intent
        from ovos_workshop.intents import IntentBuilder

        builder = IntentBuilder("BuiltIntent").require("Action")

        @layer_intent(builder, "action_layer")
        def action_handler():
            pass

        self.assertIn("BuiltIntent", action_handler.intent_layers.get("action_layer", []))


if __name__ == "__main__":
    unittest.main()
