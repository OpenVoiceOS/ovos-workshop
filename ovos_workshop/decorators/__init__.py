import re
from functools import wraps
from typing import Optional, Callable, Dict, List, Union

# OVOS-CONTEXT-1 §6/§6.1: a gate entry is either a bare key string
# (short form, scope defaults to "private") or a {"key": ..., "scope": ...}
# mapping (long form). This module does not normalize or interpret the
# entry - it is carried verbatim to the registration payload; resolving
# scope and looking up the stored key is the consuming engine's job.
ContextGate = Union[str, Dict[str, str]]

# OVOS-INTENT-1 §3.4: a slot name is lowercase ASCII letters, digits and
# underscores, and does not begin with a digit
_SLOT_NAME_RE = re.compile(r"[a-z_][a-z0-9_]*")


def check_required_slots(required_slots: Optional[List[str]]) -> List[str]:
    """Validate an intent's required slot names (OVOS-INTENT-3 §5.3).

    @param required_slots: bare slot names, without braces or type prefix
    @return: the names as a list, empty when none are declared
    @raise ValueError: the declaration is not a list of valid slot names
    """
    if required_slots is None:
        return []
    if isinstance(required_slots, str) or not all(
            isinstance(name, str) for name in required_slots):
        raise ValueError(f"required_slots must be a list of slot names, "
                         f"got {required_slots!r}")
    invalid = [name for name in required_slots
               if not _SLOT_NAME_RE.fullmatch(name)]
    if invalid:
        raise ValueError(f"invalid required slot name(s) {invalid}: a slot "
                         f"name is lowercase ASCII letters, digits and "
                         f"underscores, does not begin with a digit, and "
                         f"has no braces or type prefix (OVOS-INTENT-1 §3.4)")
    return list(required_slots)

from ovos_utils.log import log_deprecation
import warnings
from ovos_workshop.decorators.killable import killable_intent, killable_event
from ovos_workshop.decorators.layers import enables_layer, \
    disables_layer, layer_intent, removes_layer, resets_layers, replaces_layer
from ovos_workshop.decorators.ocp import ocp_play, ocp_pause, ocp_resume, \
    ocp_search, ocp_previous, ocp_featured_media


# TODO: Deprecate unused import retained for backwards-compat.
from ovos_utils import classproperty


def adds_context(context: str, words: str = ''):
    """
    Decorator to add context to the Adapt context manager.

    Args:
        context (str): context Keyword to insert
        words (str): optional string content of Keyword
    """

    def context_add_decorator(func):
        @wraps(func)
        def func_wrapper(*args, **kwargs):
            ret = func(*args, **kwargs)
            args[0].set_context(context, words)
            return ret

        return func_wrapper

    return context_add_decorator


def removes_context(context: str):
    """
    Decorator to remove context from the Adapt context manager.

    Args:
        context (str): Context keyword to remove
    """

    def context_removes_decorator(func):
        @wraps(func)
        def func_wrapper(*args, **kwargs):
            ret = func(*args, **kwargs)
            args[0].remove_context(context)
            return ret

        return func_wrapper

    return context_removes_decorator


def intent_handler(intent_parser: object, voc_blacklist: Optional[List[str]] = None,
                    requires_context: Optional[List[ContextGate]] = None,
                    excludes_context: Optional[List[ContextGate]] = None,
                    required_slots: Optional[List[str]] = None):
    """
    Decorator for adding a method as an intent handler.
    @param intent_parser: string intent name or adapt.IntentBuilder object
    @param voc_blacklist: list of vocab entries that suppress this intent
    @param requires_context: OVOS-CONTEXT-1 §6 positive gating declaration -
        each entry is a bare key string (short form, scope defaults to
        "private") or a {"key": ..., "scope": "private"|"shared"} mapping
        (long form). Applies to any intent type and reaches every
        registration payload. Engines implementing OVOS-CONTEXT-1 enforce
        the gate, while engines that do not ignore it.
    @param excludes_context: OVOS-CONTEXT-1 §6.1 negative gating declaration,
        same entry shape as requires_context. Applies to any intent type
        and reaches every registration payload.
    @param required_slots: OVOS-INTENT-3 §5.3 bare slot names the engine
        MUST extract for a match of this template (.intent) intent. Every
        locale's templates must declare each of them, or that locale is not
        registered.
    """
    required_slots = check_required_slots(required_slots)
    if required_slots and not isinstance(intent_parser, str):
        raise ValueError("required_slots applies to a template (.intent) "
                         f"intent, not to {intent_parser!r}")

    def real_decorator(func):
        # Store the intent_parser inside the function
        # This will be used later to call register_intent
        if not hasattr(func, 'intents'):
            func.intents = []
        if not hasattr(func, 'voc_blacklist'):
            func.voc_blacklist = []
        if not hasattr(func, 'requires_context'):
            func.requires_context = []
        if not hasattr(func, 'excludes_context'):
            func.excludes_context = []
        # keyed by intent: each stacked decorator declares its own intent's
        # required slots
        if not hasattr(func, 'required_slots'):
            func.required_slots = {}
        if required_slots:
            func.required_slots[intent_parser] = required_slots
        func.intents.append(intent_parser)
        func.voc_blacklist += voc_blacklist or []
        func.requires_context += requires_context or []
        func.excludes_context += excludes_context or []
        return func

    return real_decorator


def resting_screen_handler(name: str):
    """
    Decorator for adding a method as a resting screen handler to optionally
    be shown on screen when device enters idle mode.
    @param name: Name of the restring screen to register

    .. deprecated::
        The resting-screen / homescreen concept is being deprecated entirely
        and will be removed in a future release. No replacement is planned.
    """
    import warnings
    from ovos_utils.log import LOG
    msg = ("@resting_screen_handler is deprecated; the resting-screen / "
           "homescreen concept is being removed. No replacement is planned.")
    warnings.warn(msg, DeprecationWarning, stacklevel=2)
    LOG.warning(f"DEPRECATION: {msg}")

    def real_decorator(func):
        # Store the resting information inside the function
        # This will be used later in register_resting_screen
        if not hasattr(func, 'resting_handler'):
            func.resting_handler = name
        return func

    return real_decorator


def skill_api_method(func: callable):
    """
    Decorator for adding a method to the skill's public api. Methods with this
    decorator will be registered on the messagebus and an api object can be
    created for interaction with the skill.
    @param func: API method to expose
    """
    # tag the method by adding an api_method member to it
    if not hasattr(func, 'api_method') and hasattr(func, '__name__'):
        func.api_method = True
    return func


# utterance, answer, lang
CQCallback = Callable[[Optional[str], Optional[str], Optional[str]], None]


def common_query(callback: Optional[CQCallback] = None):
    """
    Decorator for adding a method as an intent handler.
    """

    def real_decorator(func):
        # mark the method as a common_query handler
        func.common_query = True
        func.cq_callback = callback
        return func

    return real_decorator


def converse_handler(func):
    """
    Decorator for aliasing a method as the converse method
    """
    if not hasattr(func, 'converse'):
        func.converse = True
    return func


def conversational_intent(intent_file):
    """Decorator for adding a method as an converse intent handler.
    NOTE: only padatious intents supported, not adapt
    """

    def real_decorator(func):
        # Store the intent_file inside the function
        # This will be used later to train intents
        if not hasattr(func, 'converse_intents'):
            func.converse_intents = []
        func.converse_intents.append(intent_file)
        return func

    return real_decorator


def fallback_handler(priority: int = 50):
    """
    Decorator for adding a fallback intent handler.

    @param priority: Fallback priority (0-100) with lower values having higher
        priority
    """

    def real_decorator(func):
        if not hasattr(func, 'fallback_priority'):
            func.fallback_priority = priority
        return func

    return real_decorator


def homescreen_app(icon: str, name: Optional[str] = None):
    """
    Decorator for adding a method as a homescreen app

    the icon file MUST be located under 'gui' subfolder

    @param icon: icon file to use in app drawer (relative to "gui" folder)
    @param name: short name to show under the icon in app drawer

    .. deprecated::
        The homescreen concept is being deprecated entirely and will be
        removed in a future release. No replacement is planned.
    """
    import warnings
    from ovos_utils.log import LOG
    msg = ("@homescreen_app is deprecated; the homescreen concept is "
           "being removed. No replacement is planned.")
    warnings.warn(msg, DeprecationWarning, stacklevel=2)
    LOG.warning(f"DEPRECATION: {msg}")

    def real_decorator(func):
        # Store the icon inside the function
        # This will be used later to call register_homescreen_app
        func.homescreen_app_icon = icon
        func.homescreen_app_name = name
        return func

    return real_decorator
