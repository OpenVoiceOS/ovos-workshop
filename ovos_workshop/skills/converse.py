import abc
from inspect import signature
from typing import Optional

from ovos_bus_client.message import Message
from ovos_bus_client.message import dig_for_message
from ovos_bus_client.session import SessionManager
from ovos_config.config import Configuration
from ovos_spec_tools import SpecMessage, closest_lang
from ovos_utils.lang import standardize_lang_tag
from ovos_utils.log import LOG
from ovos_utils.skills import get_non_properties
from padacioso import IntentContainer

from ovos_workshop.decorators.killable import AbortEvent, killable_event, AbortQuestion
from ovos_workshop.resource_files import ResourceFile
from ovos_workshop.skills.ovos import _core_owns_utterance_handled, OVOSSkill


class ConversationalSkill(OVOSSkill):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.converse_matchers = {}

    def activate(self, duration_minutes=None):
        """
        Mark this skill as active and push to the top of the active skills list.
        This enables converse method to be called even without skill being
        used in last 5 minutes.

        :param duration_minutes: duration in minutes for skill to remain active
         (-1 for infinite)
        """
        if duration_minutes is None:
            duration_minutes = Configuration().get("converse", {}).get("timeout", 300) / 60  # convert to minutes

        msg = dig_for_message() or Message("")
        if "skill_id" not in msg.context:
            msg.context["skill_id"] = self.skill_id

        m1 = msg.forward("intent.service.skills.activate",
                         data={"skill_id": self.skill_id,
                               "timeout": duration_minutes})
        self.bus.emit(m1)

    def deactivate(self):
        """
        Mark this skill as inactive and remove from the active skills list.
        This stops converse method from being called.
        """
        msg = dig_for_message() or Message("")
        if "skill_id" not in msg.context:
            msg.context["skill_id"] = self.skill_id
        self.bus.emit(msg.forward("intent.service.skills.deactivate",
                                  data={"skill_id": self.skill_id}))

    def _register_system_event_handlers(self):
        super()._register_system_event_handlers()
        # OVOS-CONVERSE-1 §6.2 broadcast poll: one static topic for every
        # candidate, membership decided by session.converse_handlers
        self.add_event("ovos.converse.ping", self._handle_converse_broadcast_ack, speak_errors=False)
        # V0 compat: pre-broadcast cores still address each candidate by topic
        self.add_event(f"{self.skill_id}.converse.ping", self._handle_converse_ack, speak_errors=False)
        self.add_event(f"{self.skill_id}.converse.request", self._handle_converse_request, speak_errors=False)
        self.add_event(f"{self.skill_id}.activate", self.handle_activate, speak_errors=False)
        self.add_event(f"{self.skill_id}.deactivate", self.handle_deactivate, speak_errors=False)
        self.add_event("intent.service.skills.deactivated", self._handle_skill_deactivated, speak_errors=False)
        self.add_event("intent.service.skills.activated", self._handle_skill_activated, speak_errors=False)

    def _register_decorated(self):
        """
        Register all intent handlers that are decorated with an intent.

        Looks for all functions that have been marked by a decorator
        and read the intent data from them.  The intent handlers aren't the
        only decorators used.  Skip properties as calling getattr on them
        executes the code which may have unintended side effects
        """
        super()._register_decorated()
        for attr_name in get_non_properties(self):
            method = getattr(self, attr_name)

            if hasattr(method, 'converse_intents'):
                for intent_file in getattr(method, 'converse_intents'):
                    self.register_converse_intent(intent_file, method)

    def register_converse_intent(self, intent_file, handler):
        """ converse padacioso intents """
        name = f'{self.skill_id}.converse:{intent_file}'
        fuzzy = not self.settings.get("strict_intents", False)

        for lang in self.native_langs:
            self.converse_matchers[lang] = IntentContainer(fuzz=fuzzy)

            resources = self.load_lang(self.res_dir, lang)
            resource_file = ResourceFile(resources.types.intent, intent_file)
            if resource_file.file_path is None:
                self.log.error(f'Unable to find "{intent_file}"')
                continue
            filename = str(resource_file.file_path)

            with open(filename) as f:
                samples = [l.strip() for l in f.read().split("\n")
                           if l and not l.startswith("#")]

            self.converse_matchers[lang].add_intent(name, samples)

        self.add_event(name, handler, 'mycroft.skill.handler')

    def _get_closest_lang(self, lang: str) -> Optional[str]:
        if self.converse_matchers:
            lang = standardize_lang_tag(lang)
            return closest_lang(lang, list(self.converse_matchers.keys()))
        return None

    def _handle_converse_ack(self, message: Message):
        """
        Inform skills service if we want to handle converse. Individual skills
        must implement self.can_converse
        @param message: `{self.skill_id}.converse.ping` Message
        """
        self.bus.emit(message.reply(
            "skill.converse.pong",
            data={"skill_id": self.skill_id,
                  "can_handle": self.can_converse(message)},
            context={"skill_id": self.skill_id}))

    def _handle_converse_broadcast_ack(self, message: Message):
        """
        Answer the OVOS-CONVERSE-1 §4.2 broadcast poll.

        The ping names no candidate. This skill decides whether it is one by
        testing its own skill_id against the session's recency list
        (`active_handlers`), and answers only when it is named (§9.3 — a skill
        that answers when not named is non-conformant).

        The candidacy test mirrors the one the emitter applies when it builds
        the round: named in `active_handlers`, and not the current
        `response_mode` holder. A skill holding the response window is excluded
        from the round by the emitter, so running `can_converse` for it here
        would wake user code for a contest it was never entered in. Expiry is
        deliberately not checked, because the emitter's own filter does not
        check it either — the two sides must agree on the candidate set.

        The claim decision itself is unchanged: the same `can_converse`
        callback the legacy per-skill ping uses.
        @param message: `ovos.converse.ping` Message
        """
        session = SessionManager.get(message)
        # canonical fields, not the deprecated `active_skills` /
        # `utterance_states` views — those log a deprecation warning per ping,
        # per skill, per utterance
        if not any(h.get("skill_id") == self.skill_id
                   for h in session.active_handlers):
            return  # not a candidate this round
        if (session.response_mode or {}).get("skill_id") == self.skill_id:
            return  # holds the response window; the emitter excluded us

        self.bus.emit(message.reply(
            "ovos.converse.pong",
            data={"skill_id": self.skill_id,
                  "result": self.can_converse(message)},
            context={"skill_id": self.skill_id}))

    def _handle_skill_activated(self, message: Message):
        """
        Intent service activated a skill. If it was this skill,
        emit a skill activation message.
        @param message: `intent.service.skills.activated` Message
        """
        if message.data.get("skill_id") == self.skill_id:
            self.bus.emit(message.forward(f"{self.skill_id}.activate"))

    def _handle_skill_deactivated(self, message):
        """
        Intent service deactivated a skill. If it was this skill,
        emit a skill deactivation message.
        @param message: `intent.service.skills.deactivated` Message
        """
        if message.data.get("skill_id") == self.skill_id:
            self.bus.emit(message.forward(f"{self.skill_id}.deactivate"))

    def _on_timeout(self):
        """_handle_converse_request timed out and was forcefully killed by ovos-core"""
        message = dig_for_message()
        self.bus.emit(message.forward(
            f"{self.skill_id}.converse.killed",
            data={"error": "timed out"}))

    @killable_event("ovos.skills.converse.force_timeout",
                    callback=_on_timeout, check_skill_id=True)
    def _handle_converse_request(self, message: Message):
        """
        If this skill is requested and supports converse, handle the user input
        with `converse`.
        @param message: `{self.skill_id}.converse.request` Message
        """
        # NOTE: there was a routing bug before ovos-core 2.0.3 that ovos-workshop depended on
        is_latest = True
        try:
            from ovos_core.version import OVOS_VERSION_TUPLE
            if OVOS_VERSION_TUPLE < (2, 0, 3):
                is_latest = False
        except ImportError:
            # Assume latest when ovos-core isn't available (eg. standalone skills)
            pass

        if is_latest:
            # swap source/destination in context (ensure skill emitted messages have correct routing)
            message = message.reply(message.msg_type, message.data)
            response_message = message.forward('skill.converse.response',
                                        {"skill_id": self.skill_id, "result": False})
        else:
            response_message = message.reply('skill.converse.response',
                                        {"skill_id": self.skill_id, "result": False})

        # check if a conversational intent triggered
        # these are skill specific intents that may trigger instead of converse
        if self._handle_converse_intents(message):
            response_message.data["result"] = True
        else:
            try:
                # converse can have multiple signatures
                params = signature(self.converse).parameters
                kwargs = {"message": message,
                          "utterances": message.data['utterances'],
                          "lang": standardize_lang_tag(message.data['lang'])}
                kwargs = {k: v for k, v in kwargs.items() if k in params}

                response_message.data["result"] = self.converse(**kwargs)
            except (AbortQuestion, AbortEvent):
                response_message.data["error"] = "killed"
            except Exception as e:
                LOG.error(e)
                response_message.data["error"] =  repr(e)

        self.bus.emit(response_message)
        if not _core_owns_utterance_handled():
            # PIPELINE-1 §9.5: skip if core (>=2.3.0a1) already owns this emit.
            if is_latest:
                self.bus.emit(message.forward(SpecMessage.UTTERANCE_HANDLED))
            else:
                self.bus.emit(message.reply(SpecMessage.UTTERANCE_HANDLED))

    def _handle_converse_intents(self, message):
        """ called before converse method
        this gives active skills a chance to parse their own intents and
        consume the utterance, see conversational_intent decorator for usage
        """
        lang = self._get_closest_lang(self.lang)
        if lang is None:  # no intents registered for this lang
            return None

        best_score = 0
        response = None

        for utt in message.data['utterances']:
            match = self.converse_matchers[lang].calc_intent(utt)
            if match.get("conf", 0) > best_score:
                best_score = match["conf"]
                response = message.forward(match["name"], match["entities"])

        if not response or best_score < self.settings.get("min_intent_conf", 0.5):
            return False

        # send intent event
        self.bus.emit(response)
        return True

    @abc.abstractmethod
    def can_converse(self, message: Message) -> bool:
        """
        Determine if the skill can handle the given utterance during the converse phase.

        Override this method to implement custom logic for assessing whether the skill
        is capable of answering the user's query based on the utterance and session context.

        Notes:
            - Utterance transcriptions are available via `message.data["utterances"]`.
            - The session (e.g., to access language) can be retrieved using:
              `session = SessionManager.get(message)`.

        Args:
            message (Message): The message containing user utterances and metadata.

        Returns:
            bool: True if the skill can handle the query during converse; False otherwise.
        """
        raise NotImplementedError

    @abc.abstractmethod
    def converse(self, message: Message):
        """
        Handle the user's utterance if this skill is active.

        This method is called only if `can_converse` returned True and the skill was chosen
        to handle the user's input during a conversation.

        Args:
            message (Message): The message containing the user utterances to process.
        """
        raise NotImplementedError

    def handle_activate(self, message: Message):
        """
        Called when this skill is considered active by the intent service;
        converse method will be called with every utterance.
        Override this method to do any optional preparation.
        @param message: `{self.skill_id}.activate` Message
        """

    def handle_deactivate(self, message: Message):
        """
        Called when this skill is no longer considered active by the intent
        service; converse method will not be called until skill is active again.
        Override this method to do any optional cleanup.
        @param message: `{self.skill_id}.deactivate` Message
        """
