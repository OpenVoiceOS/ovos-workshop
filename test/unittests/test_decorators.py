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
import json
import unittest
from os.path import dirname
from unittest.mock import Mock
from time import sleep

from ovos_workshop.skill_launcher import SkillLoader
from ovos_utils.fakebus import FakeBus
from ovos_bus_client.message import Message
from ovos_spec_tools import SpecMessage


class TestDecorators(unittest.TestCase):
    def test_adds_context(self):
        from ovos_workshop.decorators import adds_context
        # TODO

    def test_removes_context(self):
        from ovos_workshop.decorators import removes_context
        # TODO

    def test_intent_handler(self):
        from ovos_workshop.decorators import intent_handler
        mock_intent = Mock()
        called = False

        @intent_handler(mock_intent)
        @intent_handler("test_intent")
        def test_handler():
            nonlocal called
            called = True

        self.assertEqual(test_handler.intents, ["test_intent", mock_intent])
        self.assertFalse(called)

    def test_skill_api_method(self):
        from ovos_workshop.decorators import skill_api_method
        called = False

        @skill_api_method
        def api_method():
            nonlocal called
            called = True

        self.assertTrue(api_method.api_method)
        self.assertFalse(called)

    def test_converse_handler(self):
        from ovos_workshop.decorators import converse_handler
        called = False

        @converse_handler
        def handle_converse():
            nonlocal called
            called = True

        self.assertTrue(handle_converse.converse)
        self.assertFalse(called)

    def test_fallback_handler(self):
        from ovos_workshop.decorators import fallback_handler
        called = False

        @fallback_handler()
        def medium_prio_fallback():
            nonlocal called
            called = True

        @fallback_handler(1)
        def high_prio_fallback():
            nonlocal called
            called = True

        self.assertEqual(medium_prio_fallback.fallback_priority, 50)
        self.assertEqual(high_prio_fallback.fallback_priority, 1)
        self.assertFalse(called)


class TestKillableIntents(unittest.TestCase):
    def setUp(self):
        self.bus = FakeBus()
        self.bus.emitted_msgs = []

        def get_msg(msg):
            m = json.loads(msg)
            m.pop("context")
            self.bus.emitted_msgs.append(m)

        self.bus.on("message", get_msg)

        self.skill = SkillLoader(self.bus, f"{dirname(__file__)}/ovos_tskill_abort")
        self.skill.skill_id = "abort.test"
        self.skill.load()

    def _assert_spoken(self, utterance: str) -> None:
        """Assert that a speak message with the given utterance was emitted,
        regardless of the active language tag."""
        spoken = [m for m in self.bus.emitted_msgs
                  if m.get("type") == SpecMessage.SPEAK.value
                  and m.get("data", {}).get("utterance") == utterance]
        self.assertTrue(spoken, f"No speak message with utterance {utterance!r} found "
                                f"in: {self.bus.emitted_msgs}")

    def test_skills_abort_event(self):
        self.bus.emitted_msgs = []
        # skill will enter a infinite loop unless aborted
        self.assertTrue(self.skill.instance.my_special_var == "default")
        self.bus.emit(Message(f"{self.skill.skill_id}:test"))
        sleep(2)
        # check that intent triggered
        start_msg = {'type': 'mycroft.skill.handler.start',
                     'data': {'name': 'TestAbortSkill.handle_test_abort_intent'}}
        self.assertIn(start_msg, self.bus.emitted_msgs)
        self._assert_spoken('still here')
        self.assertTrue(self.skill.instance.my_special_var == "changed")

        # check that intent reacts to mycroft.skills.abort_execution
        # eg, gui can emit this event if some option was selected
        # on screen to abort the current voice interaction
        self.bus.emitted_msgs = []
        self.bus.emit(Message("mycroft.skills.abort_execution"))
        sleep(2)

        # check that stop method was called
        self.assertTrue(self.skill.instance.stop_called)

        # check that TTS stop message was emmited
        tts_stop = {'type': SpecMessage.AUDIO_STOP.value, 'data': {}}
        self.assertIn(tts_stop, self.bus.emitted_msgs)

        # check that cleanup callback was called
        self._assert_spoken('I am dead')
        self.assertTrue(self.skill.instance.my_special_var == "default")

        # check that we are not getting speak messages anymore
        self.bus.emitted_msgs = []
        sleep(2)
        self.assertTrue(self.bus.emitted_msgs == [])

    def test_skill_stop(self):
        self.bus.emitted_msgs = []
        # skill will enter a infinite loop unless aborted
        self.assertTrue(self.skill.instance.my_special_var == "default")
        self.bus.emit(Message(f"{self.skill.skill_id}:test"))
        sleep(2)
        # check that intent triggered
        start_msg = {'type': 'mycroft.skill.handler.start',
                     'data': {'name': 'TestAbortSkill.handle_test_abort_intent'}}
        self.assertIn(start_msg, self.bus.emitted_msgs)
        self._assert_spoken('still here')
        self.assertTrue(self.skill.instance.my_special_var == "changed")

        # check that intent reacts to skill specific stop message
        # this is also emitted on mycroft.stop if using OvosSkill class
        self.bus.emitted_msgs = []
        self.bus.emit(Message(f"{self.skill.skill_id}.stop"))
        sleep(2)

        # check that stop method was called
        self.assertTrue(self.skill.instance.stop_called)

        # check that TTS stop message was emmited
        tts_stop = {'type': SpecMessage.AUDIO_STOP.value, 'data': {}}
        self.assertIn(tts_stop, self.bus.emitted_msgs)

        # check that cleanup callback was called
        self._assert_spoken('I am dead')
        self.assertTrue(self.skill.instance.my_special_var == "default")

        # check that we are not getting speak messages anymore
        self.bus.emitted_msgs = []
        sleep(2)
        self.assertTrue(self.bus.emitted_msgs == [])

    def test_get_response(self):
        """ send "mycroft.skills.abort_question" and
        confirm only get_response is aborted, speech after is still spoken.

        IMPORTANT: abort_question must carry the SAME session_id that the skill
        used when it started get_response.  The killable_event decorator captures
        the session via SessionManager.get() / dig_for_message() at the time
        _real_wait_response is started; a session mismatch silently ignores the
        abort message.
        """
        self.bus.emitted_msgs = []
        session_ctx = {"session": {"session_id": "test_gr_123"}}

        # Trigger the intent with an explicit session so we can match it later
        self.bus.emit(Message(f"{self.skill.skill_id}:test2",
                              context=session_ctx))
        sleep(2)

        # check that intent triggered and get_response is waiting
        start_msg = {'type': 'mycroft.skill.handler.start',
                     'data': {'name': 'TestAbortSkill.handle_test_get_response_intent'}}
        # get_response signals readiness via skill.converse.get_response.enable
        get_response_msg = {'type': 'skill.converse.get_response.enable',
                            'data': {'skill_id': 'abort.test'}}

        sleep(0.5)  # fake wait_while_speaking
        self.bus.emit(Message("recognizer_loop:audio_output_end",
                              context=session_ctx))
        sleep(1)  # get_response is in a thread so it can be killed

        self.assertIn(start_msg, self.bus.emitted_msgs)
        self._assert_spoken('this is a question')
        self.assertIn(get_response_msg, self.bus.emitted_msgs)

        # Abort ONLY get_response — must carry matching session context so that
        # the killable_event session check passes (sess from dig_for_message == "test_gr_123")
        self.bus.emitted_msgs = []
        self.bus.emit(Message("mycroft.skills.abort_question", context=session_ctx))
        sleep(3)

        # check that stop method was NOT called (only get_response, not full intent)
        self.assertFalse(self.skill.instance.stop_called)

        # speech after get_response must still be spoken
        self._assert_spoken('question aborted')

    def test_developer_stop_msg(self):
        """ send "my.own.abort.msg" and confirm intent3 is aborted
        send "mycroft.skills.abort_execution" and confirm intent3 ignores it"""
        self.bus.emitted_msgs = []
        # skill will enter a infinite loop unless aborted
        self.bus.emit(Message(f"{self.skill.skill_id}:test3"))
        sleep(2)
        # check that intent triggered
        start_msg = {'type': 'mycroft.skill.handler.start',
                     'data': {'name': 'TestAbortSkill.handle_test_msg_intent'}}
        self.assertIn(start_msg, self.bus.emitted_msgs)
        self._assert_spoken("you can't abort me")

        # check that intent does NOT react to mycroft.skills.abort_execution
        # developer requested a dedicated abort message
        self.bus.emitted_msgs = []
        self.bus.emit(Message("mycroft.skills.abort_execution"))
        sleep(1)

        # check that stop method was NOT called
        self.assertFalse(self.skill.instance.stop_called)

        # check that intent reacts to my.own.abort.msg
        self.bus.emitted_msgs = []
        self.bus.emit(Message("my.own.abort.msg"))
        sleep(2)

        # check that stop method was called
        self.assertTrue(self.skill.instance.stop_called)

        # check that TTS stop message was emmited
        tts_stop = {'type': SpecMessage.AUDIO_STOP.value, 'data': {}}
        self.assertIn(tts_stop, self.bus.emitted_msgs)

        # check that cleanup callback was called
        self._assert_spoken('I am dead')
        self.assertTrue(self.skill.instance.my_special_var == "default")

        # check that we are not getting speak messages anymore
        self.bus.emitted_msgs = []
        sleep(2)
        self.assertTrue(self.bus.emitted_msgs == [])

    def test_killable_event(self):
        from ovos_workshop.decorators.killable import killable_event
        # TODO


class TestLayers(unittest.TestCase):
    def test_dig_for_skill(self):
        from ovos_workshop.decorators.layers import dig_for_skill
        # TODO

    def test_enables_layer(self):
        from ovos_workshop.decorators.layers import enables_layer
        # TODO

    def test_disables_layer(self):
        from ovos_workshop.decorators.layers import disables_layer
        # TODO

    def test_replaces_layer(self):
        from ovos_workshop.decorators.layers import replaces_layer
        # TODO

    def test_removes_layer(self):
        from ovos_workshop.decorators.layers import removes_layer
        # TODO

    def test_resets_layers(self):
        from ovos_workshop.decorators.layers import resets_layers
        # TODO

    def test_layer_intent(self):
        from ovos_workshop.decorators.layers import layer_intent
        # TODO

    def test_intent_layers(self):
        from ovos_workshop.decorators.layers import IntentLayers
        # TODO


class TestOCP(unittest.TestCase):
    def test_ocp_search(self):
        from ovos_workshop.decorators.ocp import ocp_search
        called = False

        @ocp_search()
        def test_search():
            nonlocal called
            called = True

        self.assertTrue(test_search.is_ocp_search_handler)
        self.assertFalse(called)

    def test_ocp_play(self):
        from ovos_workshop.decorators.ocp import ocp_play
        called = False

        @ocp_play()
        def test_play():
            nonlocal called
            called = True

        self.assertTrue(test_play.is_ocp_playback_handler)
        self.assertFalse(called)

    def test_ocp_previous(self):
        from ovos_workshop.decorators.ocp import ocp_previous
        called = False

        @ocp_previous()
        def test_previous():
            nonlocal called
            called = True

        self.assertTrue(test_previous.is_ocp_prev_handler)
        self.assertFalse(called)

    def test_ocp_next(self):
        from ovos_workshop.decorators.ocp import ocp_next
        called = False

        @ocp_next()
        def test_next():
            nonlocal called
            called = True

        self.assertTrue(test_next.is_ocp_next_handler)
        self.assertFalse(called)

    def test_ocp_pause(self):
        from ovos_workshop.decorators.ocp import ocp_pause
        called = False

        @ocp_pause()
        def test_pause():
            nonlocal called
            called = True

        self.assertTrue(test_pause.is_ocp_pause_handler)
        self.assertFalse(called)

    def test_ocp_resume(self):
        from ovos_workshop.decorators.ocp import ocp_resume
        called = False

        @ocp_resume()
        def test_resume():
            nonlocal called
            called = True

        self.assertTrue(test_resume.is_ocp_resume_handler)
        self.assertFalse(called)

    def test_ocp_featured_media(self):
        from ovos_workshop.decorators.ocp import ocp_featured_media
        called = False

        @ocp_featured_media()
        def test_featured_media():
            nonlocal called
            called = True

        self.assertTrue(test_featured_media.is_ocp_featured_handler)
        self.assertFalse(called)
