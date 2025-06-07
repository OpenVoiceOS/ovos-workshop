import abc
from inspect import signature
from typing import Dict, Optional, List

from langcodes import closest_match
from ovos_bus_client.message import Message
from ovos_bus_client.message import dig_for_message
from ovos_config.config import Configuration
from ovos_utils.lang import standardize_lang_tag
from ovos_utils.log import LOG
from ovos_utils.skills import get_non_properties
from padacioso import IntentContainer

from ovos_workshop.decorators.killable import AbortEvent, killable_event, AbortQuestion
from ovos_workshop.resource_files import ResourceFile
from ovos_workshop.skills.ovos import OVOSSkill


class ConversationalSkill(OVOSSkill):
    def __init__(self, *args, **kwargs):
        """
        Initializes the ConversationalSkill and sets up storage for language-specific converse intent matchers.
        """
        super().__init__(*args, **kwargs)
        self.converse_matchers = {}

    def activate(self, duration_minutes=None):
        """
        Activates the skill and sets it as the top active skill for a specified duration.
        
        Args:
            duration_minutes: Number of minutes the skill remains active; -1 for infinite duration. If not provided, uses the configured default.
        
        This allows the skill's converse method to be called even if it has not been used recently.
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
        Deactivates the skill and removes it from the list of active skills.
        
        Prevents the skill's converse method from being called until reactivated.
        """
        msg = dig_for_message() or Message("")
        if "skill_id" not in msg.context:
            msg.context["skill_id"] = self.skill_id
        self.bus.emit(msg.forward(f"intent.service.skills.deactivate",
                                  data={"skill_id": self.skill_id}))

    def _register_system_event_handlers(self):
        """
        Registers system event handlers for converse and activation-related messages.
        
        Adds event listeners for converse ping, converse request, activation, deactivation, and get response events specific to this skill.
        """
        super()._register_system_event_handlers()
        self.add_event(f"{self.skill_id}.converse.ping", self._handle_converse_ack, speak_errors=False)
        self.add_event(f"{self.skill_id}.converse.request", self._handle_converse_request, speak_errors=False)
        self.add_event(f"{self.skill_id}.activate", self.handle_activate, speak_errors=False)
        self.add_event(f"{self.skill_id}.deactivate", self.handle_deactivate, speak_errors=False)
        self.add_event(f"{self.skill_id}.converse.get_response", self.__handle_get_response, speak_errors=False)

    def _register_decorated(self):
        """
        Registers all decorated intent and converse handlers for the skill.
        
        Scans the skill for methods marked with intent or converse decorators, registering them as appropriate. Methods with a `converse` attribute are set as the skill's converse handler, while those with `converse_intents` attributes have their intents registered for conversational matching.
        """
        super()._register_decorated()
        for attr_name in get_non_properties(self):
            method = getattr(self, attr_name)

            # TODO support for multiple converse handlers (?)
            if hasattr(method, 'converse'):
                self.converse = method

            if hasattr(method, 'converse_intents'):
                for intent_file in getattr(method, 'converse_intents'):
                    self.register_converse_intent(intent_file, method)

    def register_converse_intent(self, intent_file, handler):
        """
        Registers a Padacioso-based converse intent for each supported language.
        
        Loads intent samples from resource files for each native language, adds them to the language-specific intent container, and associates the provided handler with the intent event.
        """
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
        """
        Finds the closest matching registered language for converse intents.
        
        Args:
            lang: The language code to match.
        
        Returns:
            The closest registered language code if the match score is less than 10, otherwise None.
        """
        if self.converse_matchers:
            lang = standardize_lang_tag(lang)
            closest, score = closest_match(lang, list(self.converse_matchers.keys()))
            # https://langcodes-hickford.readthedocs.io/en/sphinx/index.html#distance-values
            # 0 -> These codes represent the same language, possibly after filling in values and normalizing.
            # 1- 3 -> These codes indicate a minor regional difference.
            # 4 - 10 -> These codes indicate a significant but unproblematic regional difference.
            if score < 10:
                return closest
        return None

    def _handle_converse_ack(self, message: Message):
        """
        Responds to a converse ping message indicating the skill can handle converse requests.
        
        Emits a pong response with `can_handle=True` to inform the skills service of converse support. This does not affect the skill's active status.
        """
        self.bus.emit(message.reply(
            "skill.converse.pong",
            data={"skill_id": self.skill_id,
                  "can_handle": True},
            context={"skill_id": self.skill_id}))

    def _on_timeout(self):
        """
        Handles a timeout event for a converse request by emitting a killed message with a timeout error.
        """
        message = dig_for_message()
        self.bus.emit(message.forward(
            f"{self.skill_id}.converse.killed",
            data={"error": "timed out"}))

    @killable_event("ovos.skills.converse.force_timeout",
                    callback=_on_timeout, check_skill_id=True)
    def _handle_converse_request(self, message: Message):
        """
        Handles a converse request by processing user input with skill-specific converse intents or the skill's `converse` method.
        
        If a registered converse intent matches, it is handled directly. Otherwise, the skill's `converse` method is called with supported parameters. Emits a response message indicating whether the request was handled or if an error occurred.
        """
        # check if a conversational intent triggered
        # these are skill specific intents that may trigger instead of converse
        if self._handle_converse_intents(message):
            self.bus.emit(message.reply('skill.converse.response',
                                        {"skill_id": self.skill_id, "result": True}))
            return

        try:
            # converse can have multiple signatures
            params = signature(self.converse).parameters
            kwargs = {"message": message,
                      "utterances": message.data['utterances'],
                      "lang": standardize_lang_tag(message.data['lang'])}
            kwargs = {k: v for k, v in kwargs.items() if k in params}

            result = self.converse(**kwargs)

            self.bus.emit(message.reply('skill.converse.response',
                                        {"skill_id": self.skill_id,
                                         "result": result}))
        except (AbortQuestion, AbortEvent):
            self.bus.emit(message.reply('skill.converse.response',
                                        {"skill_id": self.skill_id,
                                         "error": "killed",
                                         "result": False}))
        except Exception as e:
            LOG.error(e)
            self.bus.emit(message.reply('skill.converse.response',
                                        {"skill_id": self.skill_id,
                                         "error": repr(e),
                                         "result": False}))

    def _handle_converse_intents(self, message):
        """
        Attempts to match utterances against registered converse intents for the closest language.
        
        If a matching intent is found with confidence above the configured threshold, emits the corresponding intent event and returns True. Returns False if no suitable intent is matched, or None if no intents are registered for the language.
        """
        lang = self._get_closest_lang(self.lang)
        if lang is None:  # no intents registered for this lang
            return None

        best_score = 0
        response = None

        for utt in message.data['utterances']:
            match = self.converse_matchers[self.lang].calc_intent(utt)
            if match.get("conf", 0) > best_score:
                best_score = match["conf"]
                response = message.forward(match["name"], match["entities"])

        if not response or best_score < self.settings.get("min_intent_conf", 0.5):
            return False

        # send intent event
        self.bus.emit(response)
        return True

    @abc.abstractmethod
    def can_answer(self, utterances: List[str], lang: str) -> bool:
        """
        Determines whether the skill can handle the provided utterances in the specified language during a converse session.
        
        Override this method to implement custom logic for assessing if the skill is capable of responding to the given utterances.
        """
        raise NotImplementedError

    @abc.abstractmethod
    def converse(self, message: Message) -> bool:
        """
        Handles an utterance before normal intent parsing when the skill is active.
        
        Override this method to process user utterances during the skill's active period. Return True if the utterance was handled and should not proceed to intent parsing; otherwise, return False.
        """
        raise NotImplementedError

    @abc.abstractmethod
    def handle_activate(self, message: Message):
        """
        Called when the skill is activated by the intent service.
        
        Override to perform any preparation needed when the skill becomes active and will receive utterances via the converse method.
        """
        raise NotImplementedError

    @abc.abstractmethod
    def handle_deactivate(self, message: Message):
        """
        Handles skill deactivation when it is no longer active.
        
        Called when the skill is deactivated by the intent service. Override to perform any necessary cleanup when the skill is no longer active and will not receive converse requests.
        
        Args:
            message: The deactivation message for this skill.
        """
        raise NotImplementedError

    # converse
    def _calc_intent(self, utterance: str, lang: str, timeout=1.0) -> Optional[Dict[str, str]]:
        """
        Queries the intent service to determine which intent would be selected for a given utterance and language.
        
        Args:
            utterance: The user utterance to evaluate.
            lang: The language code for intent parsing.
            timeout: Maximum time to wait for a response from the intent service.
        
        Returns:
            A dictionary representing the selected intent, or None if no intent is found.
        
        Note:
            This method does not consider converse, common_query, or fallback intents.
        """
        # let's see what intent ovos-core will assign to the utterance
        # NOTE: converse, common_query and fallbacks are not included in this check
        response = self.bus.wait_for_response(Message("intent.service.intent.get",
                                                      {"utterance": utterance, "lang": lang}),
                                              "intent.service.intent.reply",
                                              timeout=timeout)
        if not response:
            return None
        return response.data["intent"]

    def skill_will_trigger(self, utterance: str, lang: str, skill_id: Optional[str] = None, timeout=0.8) -> bool:
        """
        Determines if this skill would be triggered by the given utterance and language.
        
        Checks if the core intent parser would select this skill for the provided utterance and language. Useful for controlling whether to handle an utterance in the converse method or allow standard intent parsing.
        
        Args:
            utterance: The user utterance to evaluate.
            lang: The language code to use for intent parsing.
            skill_id: Optional skill ID to check against; defaults to this skill's ID.
            timeout: Maximum time in seconds to wait for the intent parser response.
        
        Returns:
            True if the skill would be triggered by the utterance; otherwise, False.
        """
        # determine if an intent from this skill
        # will be selected by ovos-core
        id_to_check = skill_id or self.skill_id
        intent = self._calc_intent(utterance, lang, timeout=timeout)
        if not intent:
            return False
        skill_id = intent["skill_id"] if intent else ""
        return skill_id == id_to_check
