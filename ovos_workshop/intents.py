from os.path import exists
from pathlib import Path
from threading import RLock
from typing import List, Optional
import re
import warnings
from ovos_bus_client.message import Message, dig_for_message
from ovos_bus_client.util import get_mycroft_bus
from ovos_utils.log import LOG, log_deprecation

# OVOS-INTENT-4 keyword-intent *definition* primitives. The canonical, adapt-free
# implementations live in ovos-spec-tools; they are re-exported here so skills keep
# their long-standing `from ovos_workshop.intents import IntentBuilder` import while
# the single source of truth is the spec.
from ovos_spec_tools import Intent, IntentBuilder, open_intent_envelope, SpecMessage
from ovos_spec_tools.resources import read_resource_file

from ovos_workshop.version import VERSION_MAJOR

# Breaking changes follow semver: the deprecated adapt/padatious shims below are
# removed in the next MAJOR release. Compute the target dynamically from version.py
# so this never drifts from the actual shipped version.
_DEPRECATION_VERSION = f"{VERSION_MAJOR + 1}.0.0"


def _legacy_warn(msg, version=_DEPRECATION_VERSION):
    """Standard deprecation warning for legacy mixin methods."""
    log_deprecation(msg, version)
    warnings.warn(msg, DeprecationWarning, stacklevel=3)


class _AdaptMixin:
    """Adapt engine protocol — delete when Adapt support is dropped.

    Everything in this class is a backward-compatibility shim for the
    adapt intent engine (register_vocab, register_intent, add_context bus
    topics).  The munge_* helpers prefix namespacing is an adapt-era
    workaround for a flat keyword namespace; spec-compliant registration
    uses ``skill_id:intent_name`` dispatch keys and needs none of this.
    """

    # ------------------------------------------------------------------
    #  munging — adapt-era namespace hacks
    # ------------------------------------------------------------------

    @staticmethod
    def to_alnum(skill_id: str) -> str:
        return ''.join(c if c.isalnum() else '_' for c in str(skill_id))

    @staticmethod
    def munge_regex(regex: str, skill_id: str) -> str:
        base = '(?P<' + _AdaptMixin.to_alnum(skill_id)
        return base.join(regex.split('(?P<'))

    @staticmethod
    def munge_intent_parser(intent_parser, name, skill_id):
        if not name.startswith(str(skill_id) + ':'):
            intent_parser.name = str(skill_id) + ':' + name
        else:
            intent_parser.name = name
        sid = _AdaptMixin.to_alnum(skill_id)
        reqs = []
        for i in intent_parser.requires:
            if not i[0].startswith(sid):
                reqs.append((sid + i[0], sid + i[0]))
            else:
                reqs.append(i)
        intent_parser.requires = reqs
        opts = []
        for i in intent_parser.optional:
            if not i[0].startswith(sid):
                opts.append((sid + i[0], sid + i[0]))
            else:
                opts.append(i)
        intent_parser.optional = opts
        at_least_one = []
        for i in intent_parser.at_least_one:
            element = [sid + e.replace(sid, '') for e in i]
            at_least_one.append(tuple(element))
        intent_parser.at_least_one = at_least_one

    # ------------------------------------------------------------------
    #  adapt bus protocol
    # ------------------------------------------------------------------

    def register_adapt_keyword(self, vocab_type: str, entity: str,
                               aliases: Optional[List[str]] = None,
                               lang: str = None):
        _legacy_warn("register_adapt_keyword is deprecated, "
                     "migrate to spec-compliant keyword registration")
        self.register_keyword(vocab_type, entity, aliases, lang)

    def register_adapt_regex(self, regex: str, lang: str = None):
        _legacy_warn("register_adapt_regex is deprecated, "
                     "use register_regex")
        self.register_regex(regex, lang)

    def register_regex(self, regex: str, lang: str = None):
        """Register a regex intent (adapt-engine only).

        Regex intents are an adapt-era concept with no spec equivalent; this
        method and the adapt engine itself are slated for removal. Munging of
        named-group prefixes (the adapt flat-namespace workaround) is done
        here so callers never touch ``munge_regex`` directly.
        """
        _legacy_warn("register_regex is deprecated; regex intents are "
                     "adapt-engine only and will be removed with the adapt "
                     f"engine in {_DEPRECATION_VERSION}")
        regex = self.munge_regex(regex, self.skill_id)
        msg = dig_for_message() or Message("")
        self.bus.emit(msg.forward("register_vocab",
                                  {'regex': regex, 'lang': lang}))

    def register_adapt_intent(self, name: str, intent_parser: object):
        _legacy_warn("register_adapt_intent is deprecated, "
                     "use register_intent")
        # munging is an adapt-era namespace hack; it must stay inside the
        # adapt mixin so the spec-compliant register_intent never touches it.
        self.munge_intent_parser(intent_parser, name, self.skill_id)
        self.register_intent(name, intent_parser)

    def set_adapt_context(self, context: str, word: str, origin: str):
        _legacy_warn("set_adapt_context is deprecated")
        self.set_context(context, word, origin)

    def remove_adapt_context(self, context: str):
        _legacy_warn("remove_adapt_context is deprecated")
        self.remove_context(context)

    # ------------------------------------------------------------------
    #  deprecated lifecycle helpers
    # ------------------------------------------------------------------

    def detach_intent(self, intent_name: str):
        _legacy_warn("detach_intent is deprecated, use remove_intent")
        name = intent_name.split(':')[1]
        self.remove_intent(name)

    def get_intent_names(self):
        _legacy_warn("get_intent_names is deprecated, use intent_names property")
        return self.intent_names


class _PadatiousMixin:
    """Padatious engine protocol — delete when Padatious support is dropped."""

    def register_padatious_intent(self, intent_name: str, filename: str,
                                  lang: str,
                                  string_blacklist: Optional[List[str]] = None):
        _legacy_warn("register_padatious_intent is deprecated, "
                     "migrate to spec-compliant template registration")
        if not isinstance(filename, str):
            raise ValueError('Filename path must be a string')
        if not exists(filename):
            raise FileNotFoundError(f'Unable to find "{filename}"')
        samples = read_resource_file(Path(filename))
        self.register_template(intent_name, samples, lang, string_blacklist,
                               file_name=filename)

    def register_padatious_entity(self, entity_name: str, filename: str,
                                  lang: str):
        _legacy_warn("register_padatious_entity is deprecated, "
                     "migrate to spec-compliant entity registration")
        if not isinstance(filename, str):
            raise ValueError('Filename path must be a string')
        if not exists(filename):
            raise FileNotFoundError('Unable to find "{}"'.format(filename))
        samples = read_resource_file(Path(filename))
        self.register_entity(entity_name, samples, lang,
                             file_name=filename)


class IntentServiceInterface(_AdaptMixin, _PadatiousMixin):
    """OVOS-INTENT-4 producer — spec registration topics (INTENT-4 §§5-8).

    Skills interact with the intent service through this class.  Adapt and
    Padatious engine protocols live in the ``_AdaptMixin`` and
    ``_PadatiousMixin`` parent classes; remove those parents from the MRO
    when the corresponding engine support is dropped.
    """

    def __init__(self, bus=None):
        self._bus = bus
        self.skill_id = self.__class__.__name__
        self.registered_intents: List[tuple] = []
        self.detached_intents: List[tuple] = []
        self._iterator_lock = RLock()
        self._adapt_keyword_samples: dict = {}

    # -- bus plumbing ---------------------------------------------------

    @property
    def intent_names(self) -> List[str]:
        return [a[0] for a in self.registered_intents + self.detached_intents]

    @property
    def bus(self):
        if not self._bus:
            raise RuntimeError("bus not set. call `set_bus()` before trying to"
                               "interact with the Messagebus")
        return self._bus

    @bus.setter
    def bus(self, val):
        self.set_bus(val)

    def set_bus(self, bus=None):
        self._bus = bus or get_mycroft_bus()

    def set_id(self, skill_id: str):
        self.skill_id = skill_id

    # -- spec-compliant registration -----------------------------------

    def register_keyword(self, vocab_type: str, entity: str,
                         aliases: Optional[List[str]] = None,
                         lang: str = None):
        msg = dig_for_message() or Message("")
        aliases = aliases or []

        samples = self._adapt_keyword_samples.setdefault((vocab_type, lang), [])
        for value in [entity, *aliases]:
            if value and value not in samples:
                samples.append(value)

        entity_data = {'entity_value': entity,
                       'entity_type': vocab_type,
                       'lang': lang}
        compatibility_data = {'start': entity, 'end': vocab_type}
        self.bus.emit(msg.forward("register_vocab",
                                  {**entity_data, **compatibility_data}))
        for alias in aliases:
            alias_data = {
                'entity_value': alias,
                'entity_type': vocab_type,
                'alias_of': entity,
                'lang': lang}
            compatibility_data = {'start': alias, 'end': vocab_type}
            self.bus.emit(msg.forward("register_vocab",
                                      {**alias_data, **compatibility_data}))

    def _unmunge_vocab_name(self, vocab_type: str) -> str:
        prefix = _AdaptMixin.to_alnum(self.skill_id)
        if prefix and vocab_type.startswith(prefix):
            return vocab_type[len(prefix):]
        return vocab_type

    def _spec_keyword_descriptors(self, vocab_types: List[str], lang: str
                                  ) -> List[dict]:
        descriptors = []
        for vocab_type in vocab_types:
            samples = self._adapt_keyword_samples.get((vocab_type, lang))
            if not samples:
                continue
            descriptors.append({"name": self._unmunge_vocab_name(vocab_type),
                                "samples": list(samples)})
        return descriptors

    def _emit_spec_keyword_intent(self, msg: Message, name: str,
                                  intent_parser: object):
        required_names = [r[0] for r in getattr(intent_parser, "requires", [])]
        optional_names = [o[0] for o in getattr(intent_parser, "optional", [])]
        one_of_groups = [list(g) for g in getattr(intent_parser, "at_least_one", [])]
        excluded_names = list(getattr(intent_parser, "excludes", []))

        referenced = set(required_names) | set(optional_names) | \
                     set(excluded_names)
        for group in one_of_groups:
            referenced |= set(group)
        langs = {l for (vt, l) in self._adapt_keyword_samples
                 if vt in referenced}
        if not langs:
            LOG.debug(f"no cached adapt vocab samples for intent {name}; "
                      f"skipping {SpecMessage.INTENT_REGISTER_KEYWORD} emit")
            return

        intent_name = name.split(":")[-1] if name else name
        for lang in langs:
            payload = {
                "skill_id": self.skill_id,
                "intent_name": intent_name,
                "lang": lang,
                "required": self._spec_keyword_descriptors(required_names, lang),
                "optional": self._spec_keyword_descriptors(optional_names, lang),
                "one_of": [self._spec_keyword_descriptors(group, lang)
                           for group in one_of_groups],
                "excluded": self._spec_keyword_descriptors(excluded_names, lang),
            }
            payload["one_of"] = [g for g in payload["one_of"] if g]
            self.bus.emit(msg.forward(SpecMessage.INTENT_REGISTER_KEYWORD,
                                      payload))

    def register_intent(self, name: str, intent_parser: object):
        msg = dig_for_message() or Message("")
        self.bus.emit(msg.forward("register_intent", intent_parser.__dict__))
        self._emit_spec_keyword_intent(msg, name, intent_parser)
        self.registered_intents.append((name, intent_parser))
        self.detached_intents = [detached for detached in self.detached_intents
                                 if detached[0] != name]

    def register_entity(self, entity_name: str, samples: List[str],
                        lang: str,
                        blacklisted_words: Optional[List[str]] = None,
                        file_name: str = ''):
        msg = dig_for_message() or Message("")
        self.bus.emit(msg.forward("padatious:register_entity",
                                  {'file_name': file_name,
                                   "samples": samples,
                                   'name': entity_name,
                                   'lang': lang}))
        self.bus.emit(msg.forward(SpecMessage.ENTITY_REGISTER,
                                  {"skill_id": self.skill_id,
                                   "entity_name": entity_name.split(':')[-1],
                                   "lang": lang,
                                   "samples": samples}))

    def register_template(self, intent_name: str, samples: List[str],
                          lang: str,
                          blacklisted_words: Optional[List[str]] = None,
                          file_name: str = ''):
        msg = dig_for_message() or Message("")
        self.bus.emit(msg.forward("padatious:register_intent",
                                  {'file_name': file_name,
                                   "samples": samples,
                                   'name': intent_name,
                                   'lang': lang,
                                   'blacklisted_words': blacklisted_words}))
        self.bus.emit(msg.forward(SpecMessage.INTENT_REGISTER_TEMPLATE,
                                  {"skill_id": self.skill_id,
                                   "intent_name": intent_name.split(':')[-1],
                                   "lang": lang,
                                   "samples": samples,
                                   "blacklist": blacklisted_words or []}))
        self.registered_intents.append((intent_name.split(':')[-1],
                                        {'file_name': file_name,
                                         "samples": samples,
                                         'name': intent_name,
                                         'lang': lang,
                                         'blacklisted_words': blacklisted_words}))

    def set_context(self, context: str, word: str, origin: str):
        msg = dig_for_message() or Message("")
        self.bus.emit(msg.forward('add_context',
                                  {'context': context, 'word': word,
                                   'origin': origin}))

    def remove_context(self, context: str):
        msg = dig_for_message() or Message("")
        self.bus.emit(msg.forward('remove_context', {'context': context}))

    # -- lifecycle ------------------------------------------------------

    def remove_intent(self, intent_name: str):
        msg = dig_for_message() or Message("")
        if intent_name in self.intent_names:
            LOG.info(f"Detaching intent: {intent_name}")
            self.detached_intents.append((intent_name,
                                          self.get_intent(intent_name)))
            self.registered_intents = [pair for pair in self.registered_intents
                                       if pair[0] != intent_name]
        self.bus.emit(msg.forward(SpecMessage.INTENT_DEREGISTER,
                                  {"skill_id": self.skill_id,
                                   "intent_name": intent_name}))

    def intent_is_detached(self, intent_name: str) -> bool:
        is_detached = False
        with self._iterator_lock:
            for (name, _) in self.detached_intents:
                if name == intent_name:
                    is_detached = True
                    break
        return is_detached

    def detach_all(self):
        for name in self.intent_names:
            self.remove_intent(name)
        if self.registered_intents:
            LOG.error(f"Expected an empty list; got: {self.registered_intents}")
            self.registered_intents = []
        self.detached_intents = []

    def get_intent(self, intent_name: str) -> Optional[object]:
        to_return = None
        with self._iterator_lock:
            for name, intent in self.registered_intents:
                if name == intent_name:
                    to_return = intent
                    break
        if to_return is None:
            with self._iterator_lock:
                for name, intent in self.detached_intents:
                    if name == intent_name:
                        to_return = intent
                        break
        return to_return

    def __iter__(self):
        return iter(self.registered_intents)

    def __contains__(self, val):
        return val in [i[0] for i in self.registered_intents]


# ── backward-compat module-level aliases ──────────────────────────────
# External code that does ``from ovos_workshop.intents import munge_regex``
# still works; the real implementations are on _AdaptMixin.
to_alnum = _AdaptMixin.to_alnum
munge_regex = _AdaptMixin.munge_regex
munge_intent_parser = _AdaptMixin.munge_intent_parser