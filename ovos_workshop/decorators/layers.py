"""Intent layers gated by intent context.

An "intent layer" is a named group of intents that should only be matchable
while the layer is active. Instead of mutating the global enabled/disabled
intent set (detaching/re-attaching intents from the intent service), each layer
is mapped to a synthetic **intent context** token. Every intent belonging to a
layer additionally *requires* that context token, so adapt only validates it
while the context is set on the session.

- activating a layer  -> `skill.set_context(<layer token>)`
- deactivating a layer -> `skill.remove_context(<layer token>)`

The intents themselves stay registered for the lifetime of the skill; what
changes is whether their required context is present. This keeps the intent
service stable (no detach/attach churn) and makes layer gating per-session,
matching how the rest of OVOS contextual intents behave.
"""
import inspect
from functools import wraps
from typing import Optional, List

from ovos_bus_client import MessageBusClient
from ovos_utils.log import LOG


def layer_context_token(layer_name: str) -> str:
    """Return the intent-context keyword token used to gate a layer.

    The token is a plain keyword (no skill_id prefix); `set_context` and the
    adapt intent muging both prefix it with the alphanumeric skill_id, so the
    injected context and the intent requirement line up automatically.
    @param layer_name: bare layer name (without skill_id prefix)
    """
    return f"layer_{layer_name}"


def dig_for_skill(max_records: int = 10) -> Optional[object]:
    """
    Dig through the call stack to locate a Skill object
    @param max_records: maximum number of records in the stack to check
    @return: Skill or AbstractApplication instance if found
    """

    from ovos_workshop.skills.ovos import OVOSSkill

    stack = inspect.stack()[1:]  # First frame will be this function call
    stack = stack if len(stack) <= max_records else stack[:max_records]
    for record in stack:
        args = inspect.getargvalues(record.frame)
        if args.locals.get("self"):
            obj = args.locals["self"]
            if isinstance(obj, OVOSSkill):
                return obj
        elif args.locals.get("args"):
            for obj in args.locals["args"]:
                if isinstance(obj, OVOSSkill):
                    return obj
    return None


def _bound_layers(skill: object) -> "IntentLayers":
    skill.intent_layers = skill.intent_layers or IntentLayers().bind(skill)
    return skill.intent_layers


def enables_layer(layer_name: str):
    """
    Decorator to activate an intent layer (set its context) after the
    decorated method runs.
    @param layer_name: name of intent layer to activate
    """
    def layer_handler(func):
        @wraps(func)
        def call_function(*args, **kwargs):
            skill = dig_for_skill()
            layers = _bound_layers(skill)
            func(*args, **kwargs)
            layers.activate_layer(layer_name)

        return call_function

    return layer_handler


def disables_layer(layer_name: str):
    """
    Decorator to deactivate an intent layer (remove its context) after the
    decorated method runs.
    @param layer_name: name of intent layer to deactivate
    """
    def layer_handler(func):
        @wraps(func)
        def call_function(*args, **kwargs):
            skill = dig_for_skill()
            layers = _bound_layers(skill)
            func(*args, **kwargs)
            layers.deactivate_layer(layer_name)

        return call_function

    return layer_handler


def replaces_layer(layer_name: str, intent_list: Optional[List[str]]):
    """
    Replaces intents at the specified layer
    @param layer_name: name of intent layer to replace
    @param intent_list: list of new intents for the specified layer
    """
    def layer_handler(func):
        @wraps(func)
        def call_function(*args, **kwargs):
            skill = dig_for_skill()
            layers = _bound_layers(skill)
            func(*args, **kwargs)
            layers.replace_layer(layer_name, intent_list)

        return call_function

    return layer_handler


def removes_layer(layer_name: str):
    """
    Decorator to remove an intent layer (forget it and drop its context) after
    the decorated method runs.
    @param layer_name: name of intent layer to remove
    """
    def layer_handler(func):
        @wraps(func)
        def call_function(*args, **kwargs):
            skill = dig_for_skill()
            layers = _bound_layers(skill)
            func(*args, **kwargs)
            layers.remove_layer(layer_name)

        return call_function

    return layer_handler


def resets_layers():
    """
    Decorator to reset intent layers (deactivate all layer contexts)
    """
    def layer_handler(func):
        @wraps(func)
        def call_function(*args, **kwargs):
            skill = dig_for_skill()
            layers = _bound_layers(skill)
            func(*args, **kwargs)
            layers.reset()

        return call_function

    return layer_handler


def layer_intent(intent_parser: callable, layer_name: str):
    """
    Decorator for adding a method as an intent handler belonging to an
    intent layer.

    The intent is augmented to *require* the layer's context token via an
    OVOS-CONTEXT-1 §6 ``requires_context`` declaration, so it only matches
    while the layer is active — engine-agnostically, for adapt and padatious
    alike. The legacy adapt ``require(<token>)`` vocab gate is kept as a
    deprecated bridge for stacks whose engine does not yet enforce
    OVOS-CONTEXT-1.

    @param intent_parser: intent parser method
    @param layer_name: name of intent layer intent is associated with
    """

    def real_decorator(func):
        nonlocal intent_parser
        # Store the intent_parser inside the function
        # This will be used later to call register_intent
        if not hasattr(func, 'intents'):
            func.intents = []
        if not hasattr(func, 'intent_layers'):
            func.intent_layers = {}
        if not hasattr(func, 'requires_context'):
            func.requires_context = []

        token = layer_context_token(layer_name)

        # OVOS-CONTEXT-1 §6 — the engine-agnostic layer gate (private scope,
        # resolves to <skill_id>:layer_<name>, set by IntentLayers.activate_layer)
        if token not in func.requires_context:
            func.requires_context.append(token)

        # legacy adapt vocab gate — deprecated bridge, see docstring
        if hasattr(intent_parser, "require"):
            # IntentBuilder - require the layer context token
            intent_parser = intent_parser.require(token)

        func.intents.append(intent_parser)
        if layer_name not in func.intent_layers:
            func.intent_layers[layer_name] = []

        # get intent_name
        if hasattr(intent_parser, "build"):
            intent = intent_parser.build()
            intent_name = intent.name or func.__name__
        elif hasattr(intent_parser, "name"):
            intent_name = intent_parser.name
        else:
            intent_name = intent_parser

        func.intent_layers[layer_name].append(intent_name)
        return func

    return real_decorator


class IntentLayers:
    """Manage intent layers via intent context.

    Each layer maps to a single context token. Activating a layer sets that
    context on the intent service; deactivating removes it. The layer's intents
    require the token (see `layer_intent`), so they only match while active.
    """

    def __init__(self):
        self._skill = None
        # layer_name (skill-id-prefixed) -> list of intent names (informational)
        self._layers = {}
        self._active_layers = []

    def bind(self, skill: object):
        if skill:
            self._skill = skill
        return self

    @property
    def skill(self):
        return self._skill

    @property
    def bus(self) -> Optional[MessageBusClient]:
        return self._skill.bus if self._skill else None

    @property
    def skill_id(self) -> str:
        return self._skill.skill_id if self._skill else "IntentLayers"

    @property
    def active_layers(self) -> List[str]:
        return self._active_layers

    def _full_name(self, layer_name: str) -> str:
        if not layer_name.startswith(f"{self.skill_id}:"):
            layer_name = f"{self.skill_id}:{layer_name}"
        return layer_name

    @staticmethod
    def _bare_name(full_name: str) -> str:
        return full_name.split(":")[-1]

    def update_layer(self, layer_name: str,
                     intent_list: Optional[List[str]] = None):
        """Register intents under a (possibly new) layer."""
        layer_name = self._full_name(layer_name)
        intent_list = intent_list or []
        if layer_name not in self._layers:
            self._layers[layer_name] = []
        self._layers[layer_name] += intent_list
        LOG.info(f"Adding {intent_list} to {layer_name}")

    def activate_layer(self, layer_name: str):
        """Activate a layer by setting its intent context.

        Intents in the layer require this context token, so they become
        matchable only after this call.
        """
        layer_name = self._full_name(layer_name)
        if layer_name in self._layers:
            LOG.info("activating layer named: " + layer_name)
            if layer_name not in self._active_layers:
                self._active_layers.append(layer_name)
            self._set_context(layer_name)
        else:
            LOG.debug("no layer named: " + layer_name)

    def deactivate_layer(self, layer_name: str):
        """Deactivate a layer by removing its intent context."""
        layer_name = self._full_name(layer_name)
        if layer_name in self._layers:
            LOG.info("deactivating layer named: " + layer_name)
            if layer_name in self._active_layers:
                self._active_layers.remove(layer_name)
            self._remove_context(layer_name)
        else:
            LOG.debug("no layer named: " + layer_name)

    def remove_layer(self, layer_name: str):
        """Forget a layer entirely (deactivating it first)."""
        layer_name = self._full_name(layer_name)
        if layer_name in self._layers:
            self.deactivate_layer(layer_name)
            LOG.info("removing layer named: " + layer_name)
            self._layers.pop(layer_name)
        else:
            LOG.debug("no layer named: " + layer_name)

    def replace_layer(self, layer_name: str,
                      intent_list: Optional[List[str]] = None):
        """Replace the intent names tracked for a layer."""
        layer_name = self._full_name(layer_name)
        if layer_name in self._layers:
            LOG.info("replacing layer named: " + layer_name)
            self._layers[layer_name] = intent_list or []
        else:
            self.update_layer(layer_name, intent_list)

    def reset(self):
        """Deactivate every layer (remove all layer contexts)."""
        LOG.info("Resetting layers")
        for layer_name in list(self._active_layers):
            self.deactivate_layer(layer_name)

    # back-compat-free alias kept because the public verb "disable" reads well
    # for "turn all layers off"; it is reset(), not the old enable/disable model
    disable = reset

    def is_active(self, layer_name: str, session=None) -> bool:
        """True if the layer is active.

        Layer gating is per-session (the layer's context token lives in the
        session). When a `session` (or the current message's session) is
        available, this checks that session's context - the source of truth for
        concurrent multi-session play. Otherwise it falls back to the
        skill-level bookkeeping in `active_layers`.

        @param session: a Session to check; if None, the current message's
            session is used when one can be resolved.
        """
        layer_name = self._full_name(layer_name)
        sess = session or self._current_session()
        if sess is not None:
            token = layer_context_token(self._bare_name(layer_name))
            full_token = self._alnum_id() + token
            return any(c.get("key") == token or
                       full_token in [d[1] for d in c.get("data", [])]
                       for c in sess.context.get_context())
        return layer_name in self.active_layers

    # context plumbing -------------------------------------------------------
    def _alnum_id(self) -> str:
        if self.skill and hasattr(self.skill, "alphanumeric_skill_id"):
            return self.skill.alphanumeric_skill_id
        return ""

    def _current_session(self):
        """Resolve the current message's session, if any."""
        try:
            from ovos_bus_client.message import dig_for_message
            from ovos_bus_client.session import SessionManager
            msg = dig_for_message()
            if msg is not None:
                return SessionManager.get(msg)
        except Exception:
            pass
        return None

    def _set_context(self, full_layer_name: str):
        if not self.skill:
            return
        token = layer_context_token(self._bare_name(full_layer_name))
        # OVOS-CONTEXT-1 §5.3 — the engine-agnostic layer gate; stored at the
        # private key <skill_id>:layer_<name>, matching layer_intent's
        # requires_context declaration
        self.skill.set_intent_context(token)
        # legacy adapt vocab context — deprecated bridge (word is the token
        # itself so adapt has a value to inject)
        self.skill.set_context(token, token)

    def _remove_context(self, full_layer_name: str):
        if not self.skill:
            return
        token = layer_context_token(self._bare_name(full_layer_name))
        self.skill.remove_intent_context(token)
        # legacy adapt vocab context — deprecated bridge
        self.skill.remove_context(token)
