# Intent Layers

Intent layers let a skill enable or disable groups of intents at runtime. This is useful for building modal interactions where different commands are valid in different states.

**Module:** `ovos_workshop.decorators.layers` / `ovos_workshop.skills.layers`

## Concept

A skill can define multiple named "layers", each containing a set of intents. Only the intents belonging to the currently active layer(s) are enabled at any time. The skill starts with no layers active — the global (non-layered) intents are always active.

## Using Decorators

### `@layer_intent`

Register a handler that only fires when a specific layer is active:

```python
from ovos_workshop.decorators.layers import layer_intent, enables_layer, disables_layer

class MySkill(OVOSSkill):

    @intent_handler("start.game.intent")
    @enables_layer("game_mode")
    def handle_start_game(self, message):
        self.speak("Game started!")

    @layer_intent("game_mode", "guess.intent")
    def handle_guess(self, message):
        guess = message.data.get("number")
        self.speak(f"You guessed {guess}")

    @layer_intent("game_mode", "quit.intent")
    @disables_layer("game_mode")
    def handle_quit(self, message):
        self.speak("Game over!")
```

### `@enables_layer` / `@disables_layer`

Activate or deactivate a layer when a handler runs (runs after the function body):

```python
@enables_layer("listening_mode")
def start_listening(self, message): ...

@disables_layer("listening_mode")
def stop_listening(self, message): ...
```

### `@replaces_layer`

Deactivate all layers and activate only the named one:

```python
from ovos_workshop.decorators.layers import replaces_layer

@replaces_layer("new_mode")
def switch_mode(self, message): ...
```

### `@removes_layer`

Remove a named layer entirely (all its intents are deregistered):

```python
from ovos_workshop.decorators.layers import removes_layer

@removes_layer("obsolete_mode")
def cleanup_mode(self, message): ...
```

### `@resets_layers`

Deactivate all layers, returning to the global state:

```python
from ovos_workshop.decorators.layers import resets_layers

@resets_layers()
def reset_all(self, message): ...
```

## Using `IntentLayers` Directly

`self.intent_layers` is an `IntentLayers` instance available on every skill:

```python
# Activate a layer
self.intent_layers.activate_layer("game_mode")

# Deactivate a layer
self.intent_layers.deactivate_layer("game_mode")

# Check if a layer is active
if self.intent_layers.is_active("game_mode"):
    ...

# Activate one layer and deactivate all others
self.intent_layers.replace_layer("new_mode")

# Reset to no active layers
self.intent_layers.reset()
```

## Registering a Layer Programmatically

```python
self.register_intent_layer("my_layer", [
    "my.first.intent",
    "my.second.intent",
    IntentBuilder("AdaptLayerIntent").require("LayerKeyword"),
])
```

This registers the intents without activating the layer. Call `activate_layer` to enable them.
