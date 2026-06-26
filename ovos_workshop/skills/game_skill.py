import abc
from typing import Optional, Dict, Iterable

from ovos_bus_client.message import Message
from ovos_bus_client.util import get_message_lang
from ovos_utils.ocp import MediaType, MediaEntry, PlaybackType, Playlist, PlayerState
from ovos_utils.parse import match_one, MatchStrategy

from ovos_workshop.decorators import ocp_featured_media, ocp_search
from ovos_workshop.skills.common_play import OVOSCommonPlaybackSkill


class OVOSGameSkill(OVOSCommonPlaybackSkill):
    """ To integrate with the OpenVoiceOS Common Playback framework

    "play" intent is shared with media and managed by OCP pipeline

    The class makes the skill available to queries from OCP
        - "skill_voc_filename" keyword argument is mandatory
          it defines the .voc file containing the keywords to match the game name

    bus events emitted to trigger this skill:
    - 'ovos.common_play.{self.skill_id}.play'
    - 'ovos.common_play.{self.skill_id}.pause'
    - 'ovos.common_play.{self.skill_id}.resume'
    - 'ovos.common_play.{self.skill_id}.stop'
    - 'ovos.common_play.{self.skill_id}.save'
    - 'ovos.common_play.{self.skill_id}.load'

    """

    def __init__(self, skill_voc_filename: str,
                 *args,
                 skill_icon: str = "",
                 game_image: str = "",
                 **kwargs):
        """IMPORTANT: contents of skill_voc_filename are crucial for intent matching
        without that ocp_pipeline might not recognize the skill as a game"""
        self.game_image = game_image
        super().__init__(skill_icon=skill_icon, skill_voc_filename=skill_voc_filename,
                         supported_media=[MediaType.GAME],
                         playback_handler=self.on_play_game,
                         pause_handler=self.on_pause_game,
                         resume_handler=self.on_resume_game,
                         *args, **kwargs)

    @ocp_featured_media()
    def _ocp_featured(self) -> Playlist:
        """ensure skill shows up in OCP GUI menu
        report the game as the only featured_track"""
        entry = MediaEntry(
            uri=f"skill:{self.skill_id}",
            title=self.skill_aliases[0],
            image=self.game_image,
            playback=PlaybackType.SKILL,
            media_type=MediaType.GAME,
            match_confidence=100,
            skill_icon=self.skill_icon
        )
        pl = Playlist(
            title=self.skill_aliases[0],
            image=self.game_image,
            playback=PlaybackType.SKILL,
            media_type=MediaType.GAME,
            match_confidence=100,
            skill_icon=self.skill_icon)
        pl.add_entry(entry)
        return pl

    @ocp_search()
    def _ocp_search(self, phrase: str, media_type: MediaType) -> Iterable[MediaEntry]:
        """match the game name when OCP is searching"""
        if media_type != MediaType.GAME:
            # only match if ocp_pipeline determined a game was wanted
            return

        _, score = match_one(phrase, self.skill_aliases,
                             strategy=MatchStrategy.DAMERAU_LEVENSHTEIN_SIMILARITY)
        conf = int(score * 100)
        if conf >= 50:
            entry = self._ocp_featured()[0]
            entry.match_confidence = conf
            yield entry

    @property
    def is_playing(self) -> bool:
        return self._playing.is_set()

    @property
    def is_paused(self) -> bool:
        return self._paused.is_set()

    @abc.abstractmethod
    def on_play_game(self):
        """called by ocp_pipeline when 'play XXX' matches the game"""

    @abc.abstractmethod
    def on_pause_game(self):
        """called by ocp_pipeline on 'pause' if game is being played"""

    @abc.abstractmethod
    def on_resume_game(self):
        """called by ocp_pipeline on 'resume/unpause' if game is being played and paused"""

    @abc.abstractmethod
    def on_stop_game(self):
        """called when game is stopped for any reason
        auto-save may be implemented here"""

    @abc.abstractmethod
    def on_save_game(self):
        """if your game has no save/load functionality you should
        speak a error dialog here"""

    @abc.abstractmethod
    def on_load_game(self):
        """if your game has no save/load functionality you should
        speak a error dialog here"""

    def stop_game(self):
        """to be called by skills if they want to stop game programatically"""
        if self.is_playing:
            self._paused.clear()
            self.gui.release()
            self.log.debug("changing OCP state: PlayerState.STOPPED ")
            self.bus.emit(Message("ovos.common_play.player.state",
                                  {"state": PlayerState.STOPPED}))
            self._playing.clear()
            self.on_stop_game()
            return True
        return False

    def stop(self) -> bool:
        """NOTE: not meant to be called by the skill, this is a callback"""
        return self.stop_game()

    def calc_intent(self, utterance: str, lang: str, timeout=1.0) -> Optional[Dict[str, str]]:
        """helper to check what intent would be selected by ovos-core"""
        # let's see what intent ovos-core will assign to the utterance
        # NOTE: converse, common_query and fallbacks are not included in this check
        response = self.bus.wait_for_response(Message("intent.service.intent.get",
                                                      {"utterance": utterance, "lang": lang}),
                                              "intent.service.intent.reply",
                                              timeout=timeout)
        if not response:
            return None
        return response.data["intent"]


class ConversationalGameSkill(OVOSGameSkill):

    def on_save_game(self):
        """skills can override method to implement functioonality"""
        self.speak_dialog("cant_save_game")

    def on_load_game(self):
        """skills can override method to implement functioonality"""
        self.speak_dialog("cant_load_game")

    def on_pause_game(self):
        """called by ocp_pipeline on 'pause' if game is being played"""
        self._paused.set()
        self.acknowledge()
        # individual skills can change default value if desired
        if self.settings.get("pause_dialog", False):
            self.speak_dialog("game_pause")

    def on_resume_game(self):
        """called by ocp_pipeline on 'resume/unpause' if game is being played and paused"""
        self._paused.clear()
        self.acknowledge()
        # individual skills can change default value if desired
        if self.settings.get("pause_dialog", False):
            self.speak_dialog("game_unpause")

    @abc.abstractmethod
    def on_play_game(self):
        """called by ocp_pipeline when 'play XXX' matches the game"""

    @abc.abstractmethod
    def on_stop_game(self):
        """called when game is stopped for any reason
        auto-save may be implemented here"""

    @abc.abstractmethod
    def on_game_command(self, utterance: str, lang: str):
        """pipe user input that wasnt caught by intents to the game
        do any intent matching or normalization here
        don't forget to self.speak the game output too!
        """

    def on_abandon_game(self):
        """user abandoned game mid interaction

        auto-save is done before this method is called
        (if enabled in self.settings)

        on_game_stop will be called after this handler"""

    # converse
    def skill_will_trigger(self, utterance: str, lang: str, skill_id: Optional[str] = None, timeout=0.8) -> bool:
        """helper to check if this skill would be selected by ovos-core with the given utterance

        useful in converse method
            eg. return not self.will_trigger

        this example allows the utterance to be consumed via converse of using ovos-core intent parser
        ensuring it is always handled by the game skill regardless
        """
        # determine if an intent from this skill
        # will be selected by ovos-core
        id_to_check = skill_id or self.skill_id
        intent = self.calc_intent(utterance, lang, timeout=timeout)
        skill_id = intent["skill_id"] if intent else ""
        return skill_id == id_to_check

    @property
    def save_is_implemented(self) -> bool:
        """
        True if this skill implements a `save` method
        """
        return self.__class__.on_save_game is not ConversationalGameSkill.on_save_game

    def _autosave(self):
        """helper to save the game automatically if enabled in settings.json and implemented by skill"""
        if self.settings.get("auto_save", False) and self.save_is_implemented:
            self.on_save_game()

    def _async_cmd(self, message: Message):
        utterance = message.data["utterances"][0]
        lang = get_message_lang(message)
        self.log.debug(f"Piping utterance to game: {utterance}")
        self.on_game_command(utterance, lang)

    def converse(self, message: Message) -> bool:
        try:
            utterance = message.data["utterances"][0]
            lang = get_message_lang(message)
            # let the user implemented intents do the job if they can handle the utterance
            # otherwise pipe utterance to the game handler
            if self.skill_will_trigger(utterance, lang):
                self.log.debug("Skill intent will trigger, don't pipe utterance to game")
                return False

            if self.is_paused:
                self.log.debug("game is paused")
                # let ocp_pipeline unpause as appropriate
                return False

            try:
                self._autosave()
            except Exception as e:
                self.log.error(f"Autosave failed: {e}")

            if self.is_playing:
                # do this async so converse executes faster
                self.bus.once(f"{self.skill_id}.game_cmd", self._async_cmd)
                self.bus.emit(message.forward(f"{self.skill_id}.game_cmd", message.data))
                return True

            return False
        except (KeyError, IndexError) as e:
            self.log.error(f"Error processing game converse message: {e}")
            return False
        except Exception as e:
            self.log.exception(f"Unexpected error in game converse: {e}")
            return False

    def handle_deactivate(self, message: Message):
        """
        Called when this skill is no longer considered active by the intent service;
        means the user didn't interact with the game for a long time and intent parser will be released
        """
        try:
            if self.is_paused:
                self.log.info("Game is paused, keeping it active")
                self.activate()  # keep the game in active skills list so it can still converse
            elif self.is_playing:
                self._autosave()
                self.log.info("Game abandoned due to inactivity")
                self.on_abandon_game()
                self.stop_game()
        except Exception as e:
            self.log.exception(f"Error during game deactivation: {e}")

    def stop(self) -> bool:
        self._autosave()
        return super().stop()
