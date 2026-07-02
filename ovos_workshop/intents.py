from os.path import exists
from pathlib import Path
from threading import RLock
from typing import List, Optional
import re
import warnings
from ovos_bus_client.message import Message, dig_for_message
from ovos_bus_client.session import Session, SessionManager
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
    """Standard deprecation warning for legacy engine-API methods."""
    log_deprecation(msg, version)
    warnings.warn(msg, DeprecationWarning, stacklevel=3)


class _AdaptIntentApi:
    """Adapt engine protocol — delete when Adapt support is dropped.

    Everything in this class is a backward-compatibility shim for the
    adapt intent engine (register_vocab, register_intent, add_context bus
    topics). The munge_* helpers prefix namespacing is an adapt-era
    workaround for a flat keyword namespace; spec-compliant registration
    uses ``skill_id:intent_name`` dispatch keys and needs none of this.

    Composed onto ``IntentServiceInterface`` as ``self._adapt`` (not
    inherited): the dependency runs one way, from the spec-compliant
    producer into this legacy shim (for dual-emit), never the reverse.
    """

    def __init__(self, iface: "IntentServiceInterface"):
        self._iface = iface

    @property
    def bus(self):
        return self._iface.bus

    @property
    def skill_id(self) -> str:
        return self._iface.skill_id

    # ------------------------------------------------------------------
    #  munging — adapt-era namespace hacks
    # ------------------------------------------------------------------

    @staticmethod
    def to_alnum(skill_id: str) -> str:
        return ''.join(c if c.isalnum() else '_' for c in str(skill_id))

    @staticmethod
    def munge_regex(regex: str, skill_id: str) -> str:
        base = '(?P<' + _AdaptIntentApi.to_alnum(skill_id)
        return base.join(regex.split('(?P<'))

    @staticmethod
    def munge_intent_parser(intent_parser, name, skill_id):
        if not name.startswith(str(skill_id) + ':'):
            intent_parser.name = str(skill_id) + ':' + name
        else:
            intent_parser.name = name
        sid = _AdaptIntentApi.to_alnum(skill_id)
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
        excludes = []
        for e in getattr(intent_parser, "excludes", []):
            if not e.startswith(sid):
                excludes.append(sid + e)
            else:
                excludes.append(e)
        intent_parser.excludes = excludes

    # ------------------------------------------------------------------
    #  legacy bus emits — called by the spec-compliant producer for
    #  dual-emit (see IntentServiceInterface.register_keyword/register_intent)
    # ------------------------------------------------------------------

    def emit_legacy_register_vocab(self, vocab_type: str, entity: str,
                                   aliases: Optional[List[str]] = None,
                                   lang: str = None):
        """Emit the legacy adapt ``register_vocab`` topic (entity + aliases).

        # TODO: remove this call (and this method) once the adapt pipeline
        # plugin consumes ``ovos.intent.register.keyword`` (INTENT-4 §5)
        # directly instead of the legacy per-value ``register_vocab`` topic.
        """
        aliases = aliases or []
        msg = dig_for_message() or Message("")
        if "skill_id" not in msg.context:
            msg.context["skill_id"] = self.skill_id
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

    def emit_legacy_register_intent(self, msg: Message, intent_parser: object):
        """Emit the legacy adapt ``register_intent`` topic.

        # TODO: remove this call (and this method) once the adapt pipeline
        # plugin consumes ``ovos.intent.register.keyword`` (INTENT-4 §5)
        # directly instead of the legacy serialized-parser ``register_intent``
        # topic.
        """
        self.bus.emit(msg.forward("register_intent", intent_parser.__dict__))

    # ------------------------------------------------------------------
    #  adapt bus protocol
    # ------------------------------------------------------------------

    def register_adapt_keyword(self, vocab_type: str, entity: str,
                               aliases: Optional[List[str]] = None,
                               lang: str = None):
        _legacy_warn("register_adapt_keyword is deprecated, "
                     "migrate to spec-compliant keyword registration")
        self._iface.register_keyword(vocab_type, entity, aliases, lang)

    def register_adapt_regex(self, regex: str, lang: str = None):
        """Register a regex intent (adapt-engine only).

        Regex intents are an adapt-era concept with no spec equivalent; this
        method and the adapt engine itself are slated for removal. Munging of
        named-group prefixes (the adapt flat-namespace workaround) is done
        here so callers never touch ``munge_regex`` directly.
        """
        _legacy_warn("register_adapt_regex is deprecated; regex intents are "
                     "adapt-engine only and will be removed with the adapt "
                     f"engine in {_DEPRECATION_VERSION}")
        regex = self.munge_regex(regex, self.skill_id)
        msg = dig_for_message() or Message("")
        if "skill_id" not in msg.context:
            msg.context["skill_id"] = self.skill_id
        self.bus.emit(msg.forward("register_vocab",
                                  {'regex': regex, 'lang': lang}))

    def register_adapt_intent(self, name: str, intent_parser: object,
                              requires_context: Optional[List] = None,
                              excludes_context: Optional[List] = None):
        _legacy_warn("register_adapt_intent is deprecated, "
                     "use register_intent")
        # munging is an adapt-era namespace hack; it must stay inside the
        # adapt API so the spec-compliant register_intent never touches it.
        self.munge_intent_parser(intent_parser, name, self.skill_id)
        self._iface.register_intent(name, intent_parser,
                                    requires_context, excludes_context)

    def set_context(self, context: str, word: str, origin: str):
        """Add adapt-engine context (adapt-only; no OVOS-CONTEXT-1 spec
        equivalent — see IntentServiceInterface.set_intent_context for the
        session-based, engine-agnostic spec mechanism)."""
        msg = dig_for_message() or Message("")
        if "skill_id" not in msg.context:
            msg.context["skill_id"] = self.skill_id
        self.bus.emit(msg.forward('add_context',
                                  {'context': context, 'word': word,
                                   'origin': origin}))

    def remove_context(self, context: str):
        """Remove adapt-engine context (adapt-only; see set_context)."""
        msg = dig_for_message() or Message("")
        if "skill_id" not in msg.context:
            msg.context["skill_id"] = self.skill_id
        self.bus.emit(msg.forward('remove_context', {'context': context}))

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
        self._iface.remove_intent(name)

    def get_intent_names(self):
        _legacy_warn("get_intent_names is deprecated, use intent_names property")
        return self._iface.intent_names


class _PadatiousIntentApi:
    """Padatious engine protocol — delete when Padatious support is dropped.

    Composed onto ``IntentServiceInterface`` as ``self._padatious`` (not
    inherited): the dependency runs one way, from the spec-compliant
    producer into this legacy shim (for dual-emit), never the reverse.
    """

    def __init__(self, iface: "IntentServiceInterface"):
        self._iface = iface

    @property
    def bus(self):
        return self._iface.bus

    @property
    def skill_id(self) -> str:
        return self._iface.skill_id

    # ------------------------------------------------------------------
    #  legacy bus emits — called by the spec-compliant producer for
    #  dual-emit (see IntentServiceInterface.register_entity/register_template)
    # ------------------------------------------------------------------

    def emit_legacy_register_entity(self, msg: Message, entity_name: str,
                                     samples: List[str], lang: str,
                                     file_name: str = ''):
        """Emit the legacy ``padatious:register_entity`` topic.

        # TODO: remove this call (and this method) once the padatious
        # pipeline plugin consumes ``ovos.entity.register`` (INTENT-4 §7)
        # directly instead of the legacy ``padatious:register_entity`` topic.
        """
        self.bus.emit(msg.forward("padatious:register_entity",
                                  {'file_name': file_name,
                                   "samples": samples,
                                   'name': entity_name,
                                   'lang': lang}))

    def emit_legacy_register_template(self, msg: Message, intent_name: str,
                                       samples: List[str], lang: str,
                                       blacklisted_words: Optional[List[str]] = None,
                                       file_name: str = ''):
        """Emit the legacy ``padatious:register_intent`` topic.

        # TODO: remove this call (and this method) once the padatious
        # pipeline plugin consumes ``ovos.intent.register.template``
        # (INTENT-4 §6) directly instead of the legacy
        # ``padatious:register_intent`` topic.
        """
        self.bus.emit(msg.forward("padatious:register_intent",
                                  {'file_name': file_name,
                                   "samples": samples,
                                   'name': intent_name,
                                   'lang': lang,
                                   'blacklisted_words': blacklisted_words}))

    # ------------------------------------------------------------------
    #  padatious bus protocol
    # ------------------------------------------------------------------

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
        self._iface.register_template(intent_name, samples, lang, string_blacklist,
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
        self._iface.register_entity(entity_name, samples, lang,
                                    file_name=filename)


class IntentServiceInterface:
    """OVOS-INTENT-4 / OVOS-CONTEXT-1 producer — spec registration and
    session intent-context topics (INTENT-4 §§5-8, CONTEXT-1 §5.3).

    Skills interact with the intent service through this class, which
    exclusively implements the official spec surface. Adapt and Padatious
    engine protocols (and every other deprecated/backwards-compatibility
    method) live on the composed ``self._adapt`` / ``self._padatious``
    objects (``_AdaptIntentApi`` / ``_PadatiousIntentApi``) — delete those
    attributes and the classes backing them when the corresponding engine
    support is dropped.
    """

    def __init__(self, bus=None):
        self._bus = bus
        self.skill_id = self.__class__.__name__
        self.registered_intents: List[tuple] = []
        self.detached_intents: List[tuple] = []
        self._iterator_lock = RLock()
        self._adapt_keyword_samples: dict = {}
        self._adapt = _AdaptIntentApi(self)
        self._padatious = _PadatiousIntentApi(self)

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
        if "skill_id" not in msg.context:
            msg.context["skill_id"] = self.skill_id
        aliases = aliases or []

        samples = self._adapt_keyword_samples.setdefault((vocab_type, lang), [])
        for value in [entity, *aliases]:
            if value and value not in samples:
                samples.append(value)

        # TODO: remove this call — legacy adapt dual-emit, see
        # _AdaptIntentApi.emit_legacy_register_vocab
        self._adapt.emit_legacy_register_vocab(vocab_type, entity, aliases, lang)

    def _unmunge_vocab_name(self, vocab_type: str) -> str:
        prefix = _AdaptIntentApi.to_alnum(self.skill_id)
        if prefix and vocab_type.startswith(prefix):
            return vocab_type[len(prefix):]
        return vocab_type

    def _get_keyword_samples(self, vocab_type: str, lang: str
                             ) -> Optional[List[str]]:
        """Look up cached samples for a (possibly munged) vocab type.

        The intent parser's requires/optional/at_least_one/excludes always
        carry the munged (skill_id-prefixed) name (munge_intent_parser), but
        the vocab cache may hold either form depending on whether the caller
        pre-munged before calling register_adapt_keyword (the real skill flow
        does; direct/legacy callers may not) — try both.
        """
        samples = self._adapt_keyword_samples.get((vocab_type, lang))
        if samples is None:
            samples = self._adapt_keyword_samples.get(
                (self._unmunge_vocab_name(vocab_type), lang))
        return samples

    def _spec_keyword_descriptors(self, vocab_types: List[str], lang: str
                                  ) -> List[dict]:
        descriptors = []
        for vocab_type in vocab_types:
            samples = self._get_keyword_samples(vocab_type, lang)
            if not samples:
                continue
            descriptors.append({"name": self._unmunge_vocab_name(vocab_type),
                                "samples": list(samples)})
        return descriptors

    def _emit_spec_keyword_intent(self, msg: Message, name: str,
                                  intent_parser: object,
                                  requires_context: Optional[List] = None,
                                  excludes_context: Optional[List] = None):
        required_names = [r[0] for r in getattr(intent_parser, "requires", [])]
        optional_names = [o[0] for o in getattr(intent_parser, "optional", [])]
        one_of_groups = [list(g) for g in getattr(intent_parser, "at_least_one", [])]
        excluded_names = list(getattr(intent_parser, "excludes", []))

        referenced = set(required_names) | set(optional_names) | \
                     set(excluded_names)
        for group in one_of_groups:
            referenced |= set(group)
        langs = {l for vt in referenced
                 for l in {l for (cvt, l) in self._adapt_keyword_samples
                          if cvt == vt or cvt == self._unmunge_vocab_name(vt)}}
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
                # OVOS-CONTEXT-1 §6/§6.1 — optional gating declarations, each a
                # list of bare-string keys or {"key", "scope"} mappings
                "requires_context": list(requires_context or []),
                "excludes_context": list(excludes_context or []),
            }
            payload["one_of"] = [g for g in payload["one_of"] if g]
            self.bus.emit(msg.forward(SpecMessage.INTENT_REGISTER_KEYWORD,
                                      payload))

    def register_intent(self, name: str, intent_parser: object,
                        requires_context: Optional[List] = None,
                        excludes_context: Optional[List] = None):
        msg = dig_for_message() or Message("")
        if "skill_id" not in msg.context:
            msg.context["skill_id"] = self.skill_id
        # TODO: remove this call — legacy adapt dual-emit, see
        # _AdaptIntentApi.emit_legacy_register_intent
        self._adapt.emit_legacy_register_intent(msg, intent_parser)
        self._emit_spec_keyword_intent(msg, name, intent_parser,
                                       requires_context, excludes_context)
        self.registered_intents.append((name, intent_parser))
        self.detached_intents = [detached for detached in self.detached_intents
                                 if detached[0] != name]

    @staticmethod
    def _clean_padatious_name(name: str) -> str:
        """Strip the ``<skill_id>:`` prefix, a trailing ``.intent`` suffix
        (``register_intent_file`` internal naming) and a trailing
        ``_<md5>`` hash munge (``register_entity_file`` internal naming)."""
        name = name.split(':')[-1]
        if name.endswith('.intent'):
            name = name[:-len('.intent')]
        name = re.sub(r'_[0-9a-f]{32}$', '', name)
        return name

    def register_entity(self, entity_name: str, samples: List[str],
                        lang: str,
                        blacklisted_words: Optional[List[str]] = None,
                        file_name: str = ''):
        msg = dig_for_message() or Message("")
        if "skill_id" not in msg.context:
            msg.context["skill_id"] = self.skill_id
        # TODO: remove this call — legacy padatious dual-emit, see
        # _PadatiousIntentApi.emit_legacy_register_entity
        self._padatious.emit_legacy_register_entity(msg, entity_name, samples,
                                                     lang, file_name)
        self.bus.emit(msg.forward(SpecMessage.ENTITY_REGISTER,
                                  {"skill_id": self.skill_id,
                                   "entity_name": self._clean_padatious_name(entity_name),
                                   "lang": lang,
                                   "samples": samples}))

    def register_template(self, intent_name: str, samples: List[str],
                          lang: str,
                          blacklisted_words: Optional[List[str]] = None,
                          file_name: str = '',
                          requires_context: Optional[List] = None,
                          excludes_context: Optional[List] = None):
        msg = dig_for_message() or Message("")
        if "skill_id" not in msg.context:
            msg.context["skill_id"] = self.skill_id
        # TODO: remove this call — legacy padatious dual-emit, see
        # _PadatiousIntentApi.emit_legacy_register_template
        self._padatious.emit_legacy_register_template(msg, intent_name, samples,
                                                       lang, blacklisted_words,
                                                       file_name)
        self.bus.emit(msg.forward(SpecMessage.INTENT_REGISTER_TEMPLATE,
                                  {"skill_id": self.skill_id,
                                   "intent_name": self._clean_padatious_name(intent_name),
                                   "lang": lang,
                                   "samples": samples,
                                   "blacklist": blacklisted_words or [],
                                   # OVOS-CONTEXT-1 §6/§6.1 gating declarations
                                   "requires_context": list(requires_context or []),
                                   "excludes_context": list(excludes_context or [])}))
        self.registered_intents.append((intent_name.split(':')[-1],
                                        {'file_name': file_name,
                                         "samples": samples,
                                         'name': intent_name,
                                         'lang': lang,
                                         'blacklisted_words': blacklisted_words}))

    @staticmethod
    def _intent_context_key(owner_id: str, key: str, scope: str) -> str:
        if scope not in ("private", "shared"):
            raise ValueError("scope must be 'private' or 'shared'")
        return key if scope == "shared" else f"{owner_id}:{key}"

    def _sync_intent_context(self, msg: Message, delta: dict):
        """OVOS-CONTEXT-1 §5.3 — apply `delta` to the local session copy and
        broadcast it as the `ovos.session.sync` sync payload.

        `delta` maps stored keys (already scope-prefixed) to either an entry
        object (set/replace) or None (delete) — the spec's entry-level merge
        semantics (`SessionManager.merge_intent_context`).
        """
        session = Session.from_message(msg)
        # update the local copy so a caller chaining set_intent_context calls
        # within the same handler sees its own writes immediately
        session.intent_context = SessionManager.merge_intent_context(
            dict(session.intent_context or {}), delta)
        # the sync payload carries ONLY the delta (§5.3 entry-level merge —
        # the orchestrator treats every other key as unchanged); a full
        # snapshot of the local `intent_context` would wrongly signal
        # "unchanged" for every key this call didn't touch, and any key this
        # call *removed* would simply be absent rather than null-deleted
        sync_session = session.serialize()
        sync_session["intent_context"] = delta
        # OVOS-SESSION-2 §2.7: the sync content is the explicit
        # `Message.data.session`; `Message.context.session` is the ambient
        # MSG-1 carrier and is refreshed (to the full local copy) so
        # downstream forwards of this very Message also see the update.
        derived = msg.forward(SpecMessage.SESSION_SYNC, {"session": sync_session})
        derived.context["session"] = session.serialize()
        self.bus.emit(derived)

    def set_intent_context(self, key: str, value: Optional[str] = None,
                           scope: str = "private",
                           turns_remaining: Optional[int] = None,
                           expires_at: Optional[float] = None):
        """OVOS-CONTEXT-1 §5.3 — write/replace a session intent-context
        entry and sync it to the orchestrator.

        @param key: caller-chosen sub-key (no ``:``). Stored under
            ``<skill_id>:<key>`` for the default ``scope="private"`` (§3),
            visible only to this skill's own intents; ``scope="shared"``
            stores the bare ``key``, visible to every skill.
        @param value: entry value, or None for a presence-only flag (§2).
        @param turns_remaining: entry survives this many more utterance
            dispatches (§2, §4).
        @param expires_at: absolute Unix-seconds wall-clock expiry (§2, §4).
        """
        msg = dig_for_message() or Message("")
        if "skill_id" not in msg.context:
            msg.context["skill_id"] = self.skill_id
        stored_key = self._intent_context_key(self.skill_id, key, scope)
        entry = {"value": value}
        if turns_remaining is not None:
            entry["turns_remaining"] = turns_remaining
        if expires_at is not None:
            entry["expires_at"] = expires_at
        self._sync_intent_context(msg, {stored_key: entry})

    def remove_intent_context(self, key: str, scope: str = "private"):
        """OVOS-CONTEXT-1 §5.3 — remove a session intent-context entry.

        @param key: the same caller-chosen sub-key passed to
            :meth:`set_intent_context`.
        @param scope: the same scope passed to :meth:`set_intent_context`
            for this key.
        """
        msg = dig_for_message() or Message("")
        if "skill_id" not in msg.context:
            msg.context["skill_id"] = self.skill_id
        stored_key = self._intent_context_key(self.skill_id, key, scope)
        self._sync_intent_context(msg, {stored_key: None})

    # -- lifecycle ------------------------------------------------------

    def remove_intent(self, intent_name: str):
        msg = dig_for_message() or Message("")
        if "skill_id" not in msg.context:
            msg.context["skill_id"] = self.skill_id
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

    # -- backward-compat facade ------------------------------------------
    # Composition (self._adapt / self._padatious), not inheritance, means
    # these do not resolve automatically via MRO. External callers
    # (OVOSSkill, existing tests) call them directly on IntentServiceInterface,
    # so keep them as thin delegates rather than breaking that surface.

    def register_adapt_keyword(self, vocab_type: str, entity: str,
                               aliases: Optional[List[str]] = None,
                               lang: str = None):
        _legacy_warn("IntentServiceInterface.register_adapt_keyword is "
                     "deprecated; migrate to spec-compliant keyword "
                     "registration (register_keyword)")
        return self._adapt.register_adapt_keyword(vocab_type, entity, aliases, lang)

    def register_adapt_regex(self, regex: str, lang: str = None):
        _legacy_warn("IntentServiceInterface.register_adapt_regex is "
                     "deprecated; regex intents are adapt-engine only and "
                     f"will be removed with the adapt engine in {_DEPRECATION_VERSION}")
        return self._adapt.register_adapt_regex(regex, lang)

    def register_adapt_intent(self, name: str, intent_parser: object,
                              requires_context: Optional[List] = None,
                              excludes_context: Optional[List] = None):
        _legacy_warn("IntentServiceInterface.register_adapt_intent is "
                     "deprecated; migrate to spec-compliant intent "
                     "registration (register_intent)")
        return self._adapt.register_adapt_intent(name, intent_parser,
                                                 requires_context,
                                                 excludes_context)

    def set_context(self, context: str, word: str, origin: str):
        _legacy_warn("IntentServiceInterface.set_context is deprecated; use "
                     "set_intent_context (OVOS-CONTEXT-1, engine-agnostic)")
        return self._adapt.set_context(context, word, origin)

    def remove_context(self, context: str):
        _legacy_warn("IntentServiceInterface.remove_context is deprecated; use "
                     "remove_intent_context (OVOS-CONTEXT-1, engine-agnostic)")
        return self._adapt.remove_context(context)

    def set_adapt_context(self, context: str, word: str, origin: str):
        _legacy_warn("IntentServiceInterface.set_adapt_context is deprecated; "
                     "use set_intent_context (OVOS-CONTEXT-1, engine-agnostic)")
        return self._adapt.set_adapt_context(context, word, origin)

    def remove_adapt_context(self, context: str):
        _legacy_warn("IntentServiceInterface.remove_adapt_context is "
                     "deprecated; use remove_intent_context (OVOS-CONTEXT-1)")
        return self._adapt.remove_adapt_context(context)

    def detach_intent(self, intent_name: str):
        _legacy_warn("IntentServiceInterface.detach_intent is deprecated; "
                     "migrate to spec-compliant deregistration")
        return self._adapt.detach_intent(intent_name)

    def get_intent_names(self):
        _legacy_warn("IntentServiceInterface.get_intent_names is deprecated")
        return self._adapt.get_intent_names()

    def register_padatious_intent(self, intent_name: str, filename: str,
                                  lang: str,
                                  string_blacklist: Optional[List[str]] = None):
        _legacy_warn("IntentServiceInterface.register_padatious_intent is "
                     "deprecated; migrate to spec-compliant template "
                     "registration (register_template)")
        return self._padatious.register_padatious_intent(
            intent_name, filename, lang, string_blacklist)

    def register_padatious_entity(self, entity_name: str, filename: str,
                                  lang: str):
        _legacy_warn("IntentServiceInterface.register_padatious_entity is "
                     "deprecated; migrate to spec-compliant entity registration")
        return self._padatious.register_padatious_entity(entity_name, filename, lang)


# ── backward-compat module-level aliases ──────────────────────────────
# External code that does ``from ovos_workshop.intents import munge_regex``
# still works; the real implementations are on _AdaptIntentApi.
to_alnum = _AdaptIntentApi.to_alnum
munge_regex = _AdaptIntentApi.munge_regex
munge_intent_parser = _AdaptIntentApi.munge_intent_parser
