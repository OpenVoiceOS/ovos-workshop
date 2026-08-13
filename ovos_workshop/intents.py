import re
from os.path import exists
from pathlib import Path
from threading import RLock
from typing import Dict, List, Optional
import re
import warnings
from ovos_bus_client.message import Message, dig_for_message
from ovos_bus_client.util import get_mycroft_bus
from ovos_utils.log import LOG, log_deprecation

# OVOS-INTENT-4 keyword-intent definition primitives, re-exported from ovos-spec-tools.
from ovos_spec_tools import (Intent, IntentBuilder, open_intent_envelope,
                             SpecMessage, INTENT_FILE_SUFFIX,
                             inline_keywords, expand, MalformedTemplate)
from ovos_spec_tools.resources import read_resource_file

from ovos_workshop.version import VERSION_MAJOR

# Deprecated adapt/padatious shims are removed in the next MAJOR release.
_DEPRECATION_VERSION = f"{VERSION_MAJOR + 1}.0.0"

# OVOS-INTENT-1 §4.3: bound on inline <name> vocabulary size.
_MAX_INLINE_VOCAB_VALUES = 100


def _drop_malformed_samples(samples: List[str], name: str, lang: str,
                            skill_id: str) -> List[str]:
    """Skip-and-warn sample lines that are not valid OVOS-INTENT-1 templates,
    so one broken locale line cannot abort the whole registration.

    ``<name>`` vocabulary references resolve downstream at match time; they
    are replaced by a literal placeholder for validation only, and the
    returned samples keep the original lines.
    """
    valid = []
    for sample in samples:
        try:
            expand(re.sub(r"<\s*([a-z0-9_]+)\s*>", "placeholder", sample))
            valid.append(sample)
        except MalformedTemplate as err:
            LOG.warning(f"Skipping malformed template line in '{name}' "
                        f"(skill_id={skill_id}, lang={lang}): "
                        f"{sample!r} ({err})")
    return valid


def _legacy_warn(msg, version=_DEPRECATION_VERSION):
    """Standard deprecation warning for legacy engine-API methods."""
    log_deprecation(msg, version)
    warnings.warn(msg, DeprecationWarning, stacklevel=3)


class _AdaptIntentApi:
    """Adapt engine protocol — delete when Adapt support is dropped."""

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
        for e in intent_parser.excludes:
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

        TODO: drop once the adapt pipeline consumes ovos.intent.register.keyword (INTENT-4 §5) directly.
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

        TODO: drop once the adapt pipeline consumes ovos.intent.register.keyword (INTENT-4 §5) directly.
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
        """Register a regex intent (adapt-engine only)."""
        _legacy_warn("register_adapt_regex is deprecated; regex intents are "
                     "adapt-engine only and will be removed with the adapt "
                     f"engine in {_DEPRECATION_VERSION}")
        regex = self.munge_regex(regex, self.skill_id)
        msg = dig_for_message() or Message("")
        if "skill_id" not in msg.context:
            msg.context["skill_id"] = self.skill_id
        self.bus.emit(msg.forward("register_vocab",
                                  {'regex': regex, 'lang': lang}))

    def register_adapt_intent(self, name: str, intent_parser: object):
        _legacy_warn("register_adapt_intent is deprecated, "
                     "use register_intent")
        self.munge_intent_parser(intent_parser, name, self.skill_id)
        self._iface.register_intent(name, intent_parser)

    def set_context(self, context: str, word: str, origin: str,
                     original_key: Optional[str] = None):
        """Add adapt-engine context (adapt-engine only).

        `context` is the munged (alphanumeric_skill_id + context) legacy
        ADAPT key. `original_key`, when provided, is the unmunged context
        name as passed by the caller, carried alongside so consumers can
        also resolve it against the declarative (OVOS-CONTEXT-1) private
        context key.
        """
        msg = dig_for_message() or Message("")
        if "skill_id" not in msg.context:
            msg.context["skill_id"] = self.skill_id
        data = {'context': context, 'word': word, 'origin': origin}
        if original_key is not None:
            data['key'] = original_key
            # Round 2 (C1): the resolved-key mirror's owner MUST be the
            # skill actually calling set_context, never whatever ambient
            # message happens to be on the digger stack (e.g. a handler
            # for a DIFFERENT skill's message, which already carries that
            # skill's skill_id and would otherwise leave it untouched).
            # Build a forward/copy and stamp it unconditionally, never
            # mutate the dug ambient message's context.
            out = msg.forward('add_context', data)
            out.context["skill_id"] = self.skill_id
            self.bus.emit(out)
            return
        self.bus.emit(msg.forward('add_context', data))

    def remove_context(self, context: str, original_key: Optional[str] = None):
        """Remove adapt-engine context (adapt-only; see set_context)."""
        msg = dig_for_message() or Message("")
        if "skill_id" not in msg.context:
            msg.context["skill_id"] = self.skill_id
        data = {'context': context}
        if original_key is not None:
            data['key'] = original_key
            # Round 2 (C1): see set_context - stamp the true owner
            # unconditionally on a forward/copy, never the ambient message.
            out = msg.forward('remove_context', data)
            out.context["skill_id"] = self.skill_id
            self.bus.emit(out)
            return
        self.bus.emit(msg.forward('remove_context', data))

    def set_adapt_context(self, context: str, word: str, origin: str):
        _legacy_warn("set_adapt_context is deprecated")
        # Round 2 (C4): this shortcut applies no skill-id munging - `context`
        # IS the original/unmunged key, so thread it through as such too,
        # so legacy-API callers also open the OVOS-CONTEXT-1 gate.
        self.set_context(context, word, origin, original_key=context)

    def remove_adapt_context(self, context: str):
        _legacy_warn("remove_adapt_context is deprecated")
        # Round 2 (C4): symmetric with set_adapt_context above.
        self.remove_context(context, original_key=context)

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
    """Padatious engine protocol — delete when Padatious support is dropped."""

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
                                     file_name: str = '',
                                     blacklist: Optional[List[str]] = None):
        """Emit the legacy ``padatious:register_entity`` topic.

        TODO: drop once the padatious pipeline consumes ovos.entity.register (INTENT-4 §7) directly.
        """
        self.bus.emit(msg.forward("padatious:register_entity",
                                  {'file_name': file_name,
                                   "samples": samples,
                                   'name': entity_name,
                                   'lang': lang,
                                   'blacklist': blacklist or []}))

    def emit_legacy_register_template(self, msg: Message, intent_name: str,
                                       samples: List[str], lang: str,
                                       blacklisted_words: Optional[List[str]] = None,
                                       file_name: str = '',
                                       slot_blacklist: Optional[Dict[str, List[str]]] = None):
        """Emit the legacy ``padatious:register_intent`` topic.

        TODO: drop once the padatious pipeline consumes ovos.intent.register.template (INTENT-4 §6) directly.
        """
        self.bus.emit(msg.forward("padatious:register_intent",
                                  {'file_name': file_name,
                                   "samples": samples,
                                   'name': intent_name,
                                   'lang': lang,
                                   'blacklisted_words': blacklisted_words,
                                   'slot_blacklist': slot_blacklist or {}}))

    # ------------------------------------------------------------------
    #  padatious bus protocol
    # ------------------------------------------------------------------

    def register_padatious_intent(self, intent_name: str, filename: str,
                                  lang: str,
                                  string_blacklist: Optional[List[str]] = None,
                                  slot_blacklist: Optional[Dict[str, List[str]]] = None,
                                  vocabs: Optional[Dict[str, List[str]]] = None):
        _legacy_warn("register_padatious_intent is deprecated, "
                     "migrate to spec-compliant template registration")
        if not isinstance(filename, str):
            raise ValueError('Filename path must be a string')
        if not exists(filename):
            raise FileNotFoundError(f'Unable to find "{filename}"')
        samples = read_resource_file(Path(filename))
        self._iface.register_template(intent_name, samples, lang, string_blacklist,
                                      file_name=filename,
                                      slot_blacklist=slot_blacklist,
                                      vocabs=vocabs)

    def register_padatious_entity(self, entity_name: str, filename: str,
                                  lang: str,
                                  blacklist: Optional[List[str]] = None):
        _legacy_warn("register_padatious_entity is deprecated, "
                     "migrate to spec-compliant entity registration")
        if not isinstance(filename, str):
            raise ValueError('Filename path must be a string')
        if not exists(filename):
            raise FileNotFoundError('Unable to find "{}"'.format(filename))
        samples = read_resource_file(Path(filename))
        self._iface.register_entity(entity_name, samples, lang,
                                    blacklisted_words=blacklist,
                                    file_name=filename)


class IntentServiceInterface:
    """OVOS-INTENT-4 / OVOS-CONTEXT-1 producer — spec registration and
    session intent-context topics (INTENT-4 §§5-8, CONTEXT-1 §5.3).

    Adapt/Padatious engine protocols live on the composed ``self._adapt`` /
    ``self._padatious`` objects; delete them when those engines are dropped.
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

        # TODO: drop once _AdaptIntentApi.emit_legacy_register_vocab is removed.
        self._adapt.emit_legacy_register_vocab(vocab_type, entity, aliases, lang)

    def _unmunge_vocab_name(self, vocab_type: str) -> str:
        prefix = _AdaptIntentApi.to_alnum(self.skill_id)
        if prefix and vocab_type.startswith(prefix):
            return vocab_type[len(prefix):]
        return vocab_type

    def _get_keyword_samples(self, vocab_type: str, lang: str
                             ) -> Optional[List[str]]:
        """Look up cached samples for a (possibly munged) vocab type."""
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
                                  intent_parser: object):
        required_names = [r[0] for r in intent_parser.requires]
        optional_names = [o[0] for o in intent_parser.optional]
        one_of_groups = [list(g) for g in intent_parser.at_least_one]
        excluded_names = list(intent_parser.excludes)

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
            # A vocabulary with no cached samples cannot be described in the
            # INTENT-4 payload. Dropping it from `required` / `optional` /
            # `one_of` / `excluded` would register a *weaker* intent than the
            # skill declared -- notably an adapt `.require()` or
            # `.optionally()` naming a context keyword (OVOS-CONTEXT-1),
            # whose vocabulary is never registered. The consumer would then
            # match the intent with the gate (or slot) removed, so skip the
            # emit entirely and let the legacy registration (which carries
            # the full definition) stand.
            missing = self._unsampled_vocab(
                required_names + optional_names + excluded_names +
                [n for group in one_of_groups for n in group], lang)
            if missing:
                LOG.warning(
                    f"not emitting {SpecMessage.INTENT_REGISTER_KEYWORD} for "
                    f"intent {name} (lang={lang}): no vocabulary samples for "
                    f"{sorted(missing)}; emitting would register the intent "
                    f"without those constraints")
                continue
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

    def _unsampled_vocab(self, vocab_types: List[str], lang: str) -> List[str]:
        """Names among ``vocab_types`` with no registered samples for ``lang``."""
        return [vt for vt in vocab_types
                if not self._get_keyword_samples(vt, lang)]

    def register_intent(self, name: str, intent_parser: object):
        msg = dig_for_message() or Message("")
        if "skill_id" not in msg.context:
            msg.context["skill_id"] = self.skill_id
        # INTENT-4 §8.1: replace any prior registration under this name.
        slot = None
        for i, (registered_name, _) in enumerate(self.registered_intents):
            if registered_name == name:
                slot = i
                break
        if slot is not None and self.registered_intents[slot] == (name, intent_parser):
            return
        self._adapt.emit_legacy_register_intent(msg, intent_parser)
        self._emit_spec_keyword_intent(msg, name, intent_parser)
        if slot is None:
            self.registered_intents.append((name, intent_parser))
        else:
            self.registered_intents[slot] = (name, intent_parser)
        self.detached_intents = [detached for detached in self.detached_intents
                                 if detached[0] != name]

    @staticmethod
    def _clean_padatious_name(name: str) -> str:
        """Strip the ``<skill_id>:`` prefix, a trailing ``.intent`` suffix
        and a trailing ``_<md5>`` hash munge (``register_entity_file``
        internal naming).

        Current ``register_intent_file`` already passes a canonical name, so
        the suffix strip only fires for a caller that still uses the legacy
        spelling (the deprecated ``register_padatious_intent`` API)."""
        name = name.split(':')[-1]
        if name.endswith(INTENT_FILE_SUFFIX):
            name = name[:-len(INTENT_FILE_SUFFIX)]
        name = re.sub(r'_[0-9a-f]{32}$', '', name)
        return name

    def register_entity(self, entity_name: str, samples: List[str],
                        lang: str,
                        blacklisted_words: Optional[List[str]] = None,
                        file_name: str = ''):
        # INTENT-4 §7.2: skip empty/non-string/malformed entries, don't abort.
        samples = [s for s in samples or [] if isinstance(s, str) and s.strip()]
        samples = _drop_malformed_samples(samples, entity_name, lang,
                                          self.skill_id)
        if not samples:
            LOG.warning(f"{self.skill_id}: not registering entity "
                        f"'{entity_name}' ({lang}), it has no valid samples")
            return
        msg = dig_for_message() or Message("")
        if "skill_id" not in msg.context:
            msg.context["skill_id"] = self.skill_id
        # TODO: drop once _PadatiousIntentApi.emit_legacy_register_entity is removed.
        self._padatious.emit_legacy_register_entity(msg, entity_name, samples,
                                                     lang, file_name,
                                                     blacklist=blacklisted_words)
        self.bus.emit(msg.forward(SpecMessage.ENTITY_REGISTER,
                                  {"skill_id": self.skill_id,
                                   "entity_name": self._clean_padatious_name(entity_name),
                                   "lang": lang,
                                   "samples": samples}))

    def register_template(self, intent_name: str, samples: List[str],
                          lang: str,
                          blacklisted_words: Optional[List[str]] = None,
                          file_name: str = '',
                          slot_blacklist: Optional[Dict[str, List[str]]] = None,
                          vocabs: Optional[Dict[str, List[str]]] = None):
        # INTENT-4 §6.3: skip empty and non-string entries, don't abort.
        samples = [s for s in samples or [] if isinstance(s, str) and s.strip()]
        if not samples:
            LOG.warning(f"{self.skill_id}: not registering template "
                        f"'{intent_name}' ({lang}), it has no valid samples")
            return
        # OVOS-INTENT-1 §3.6/§3.7: validate with <name> refs held by a placeholder.
        samples = _drop_malformed_samples(samples, intent_name, lang,
                                          self.skill_id)
        if vocabs:
            # OVOS-INTENT-1 §3.7/§4.3/§6.3: inline <name> refs, dropping oversized/cyclic ones.
            inlined = []
            for sample in samples:
                try:
                    inlined.append(inline_keywords(
                        sample, vocabs,
                        max_values=_MAX_INLINE_VOCAB_VALUES))
                except MalformedTemplate as err:
                    LOG.warning(f"Skipping template line in '{intent_name}' "
                                f"(skill_id={self.skill_id}, lang={lang}): "
                                f"{sample!r} ({err})")
            samples = inlined
        if not samples:
            LOG.warning(f"{self.skill_id}: not registering template "
                        f"'{intent_name}' ({lang}), it has no valid samples")
            return
        name = intent_name.split(':')[-1]
        data = {'file_name': file_name,
                "samples": samples,
                'name': intent_name,
                'lang': lang,
                'blacklisted_words': blacklisted_words}
        # INTENT-4 §8.1: replace any prior registration of this (intent_name, lang).
        slot = None
        for i, (registered_name, registered_data) in enumerate(self.registered_intents):
            if (registered_name == name and isinstance(registered_data, dict)
                    and registered_data.get('lang') == lang):
                slot = i
                break
        if slot is not None and self.registered_intents[slot][1] == data:
            return
        msg = dig_for_message() or Message("")
        if "skill_id" not in msg.context:
            msg.context["skill_id"] = self.skill_id
        # TODO: drop once _PadatiousIntentApi.emit_legacy_register_template is removed.
        self._padatious.emit_legacy_register_template(msg, intent_name, samples,
                                                       lang, blacklisted_words,
                                                       file_name,
                                                       slot_blacklist=slot_blacklist)
        self.bus.emit(msg.forward(SpecMessage.INTENT_REGISTER_TEMPLATE,
                                  {"skill_id": self.skill_id,
                                   "intent_name": self._clean_padatious_name(intent_name),
                                   "lang": lang,
                                   "samples": samples,
                                   "blacklist": blacklisted_words or []}))
        if slot is None:
            self.registered_intents.append((name, data))
        else:
            self.registered_intents[slot] = (name, data)
        # mirror register_intent: a template that had been detach()ed (e.g.
        # via disable_intent) must be dropped from detached_intents once it
        # is re-registered, otherwise enable_intent()/intent_is_detached()
        # keep reporting it as detached forever.
        self.detached_intents = [detached for detached in self.detached_intents
                                 if detached[0] != name]

    # -- lifecycle ------------------------------------------------------

    def remove_intent(self, intent_name: str):
        msg = dig_for_message() or Message("")
        if "skill_id" not in msg.context:
            msg.context["skill_id"] = self.skill_id
        # registered_intents/detached_intents are keyed by the bare canonical
        # name (register_intent/register_template strip any "<skill_id>:"
        # prefix before storing, see register_intent/register_template
        # above). Callers (e.g. OVOSSkill.disable_intent) may pass the bare
        # name, the "<skill_id>:"-prefixed one, or the author-facing
        # ".intent"-suffixed spelling, so normalize with the same helper
        # register_template uses for padatious names -- otherwise a
        # differently-spelled form never matches the bare key and the intent
        # is never actually detached.
        key = self._clean_padatious_name(intent_name)
        if key in self.intent_names:
            LOG.info(f"Detaching intent: {key}")
            self.detached_intents.append((key, self.get_intent(key)))
            self.registered_intents = [pair for pair in self.registered_intents
                                       if pair[0] != key]
        self.bus.emit(msg.forward(SpecMessage.INTENT_DEREGISTER,
                                  {"skill_id": self.skill_id,
                                   "intent_name": intent_name}))

    def intent_is_detached(self, intent_name: str) -> bool:
        # normalize the same way remove_intent() does when it stores the
        # detached entry -- callers may pass the bare, "<skill_id>:"-prefixed
        # or ".intent"-suffixed spelling of the name.
        key = self._clean_padatious_name(intent_name)
        is_detached = False
        with self._iterator_lock:
            for (name, _) in self.detached_intents:
                if name == key:
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
        # same normalization as remove_intent()/intent_is_detached() --
        # registered_intents/detached_intents are keyed by the bare
        # canonical name.
        key = self._clean_padatious_name(intent_name)
        to_return = None
        with self._iterator_lock:
            for name, intent in self.registered_intents:
                if name == key:
                    to_return = intent
                    break
        if to_return is None:
            with self._iterator_lock:
                for name, intent in self.detached_intents:
                    if name == key:
                        to_return = intent
                        break
        return to_return

    def __iter__(self):
        return iter(self.registered_intents)

    def __contains__(self, val):
        return val in [i[0] for i in self.registered_intents]

    # -- backward-compat facade: thin delegates to self._adapt/self._padatious --

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

    def register_adapt_intent(self, name: str, intent_parser: object):
        _legacy_warn("IntentServiceInterface.register_adapt_intent is "
                     "deprecated; migrate to spec-compliant intent "
                     "registration (register_intent)")
        return self._adapt.register_adapt_intent(name, intent_parser)

    def set_context(self, context: str, word: str, origin: str,
                     original_key: Optional[str] = None):
        _legacy_warn("IntentServiceInterface.set_context is deprecated; "
                     "adapt-engine context is engine-specific")
        return self._adapt.set_context(context, word, origin,
                                        original_key=original_key)

    def remove_context(self, context: str, original_key: Optional[str] = None):
        _legacy_warn("IntentServiceInterface.remove_context is deprecated; "
                     "adapt-engine context is engine-specific")
        return self._adapt.remove_context(context, original_key=original_key)

    def set_adapt_context(self, context: str, word: str, origin: str):
        _legacy_warn("IntentServiceInterface.set_adapt_context is "
                     "deprecated; adapt-engine context is engine-specific")
        return self._adapt.set_adapt_context(context, word, origin)

    def remove_adapt_context(self, context: str):
        _legacy_warn("IntentServiceInterface.remove_adapt_context is "
                     "deprecated; adapt-engine context is engine-specific")
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
                                  string_blacklist: Optional[List[str]] = None,
                                  slot_blacklist: Optional[Dict[str, List[str]]] = None,
                                  vocabs: Optional[Dict[str, List[str]]] = None):
        _legacy_warn("IntentServiceInterface.register_padatious_intent is "
                     "deprecated; migrate to spec-compliant template "
                     "registration (register_template)")
        return self._padatious.register_padatious_intent(
            intent_name, filename, lang, string_blacklist, slot_blacklist,
            vocabs=vocabs)

    def register_padatious_entity(self, entity_name: str, filename: str,
                                  lang: str,
                                  blacklist: Optional[List[str]] = None):
        _legacy_warn("IntentServiceInterface.register_padatious_entity is "
                     "deprecated; migrate to spec-compliant entity registration")
        return self._padatious.register_padatious_entity(entity_name, filename,
                                                         lang, blacklist)


# -- backward-compat module-level aliases --
to_alnum = _AdaptIntentApi.to_alnum
munge_regex = _AdaptIntentApi.munge_regex
munge_intent_parser = _AdaptIntentApi.munge_intent_parser
