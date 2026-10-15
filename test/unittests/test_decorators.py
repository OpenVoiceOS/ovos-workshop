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

    def test_intent_handler_context_gating(self):
        """OVOS-CONTEXT-1 §6/§6.1: requires_context/excludes_context land on
        the decorated function verbatim, short-form (bare key) and
        long-form ({"key":..., "scope":...}) entries alike."""
        from ovos_workshop.decorators import intent_handler

        @intent_handler("confirm.intent",
                        requires_context=["confirming_milk"],
                        excludes_context=[{"key": "active_room", "scope": "shared"}])
        def test_handler():
            pass

        self.assertEqual(test_handler.requires_context, ["confirming_milk"])
        self.assertEqual(test_handler.excludes_context,
                         [{"key": "active_room", "scope": "shared"}])

    def test_intent_handler_context_gating_undeclared(self):
        from ovos_workshop.decorators import intent_handler

        @intent_handler("plain.intent")
        def test_handler():
            pass

        self.assertEqual(test_handler.requires_context, [])
        self.assertEqual(test_handler.excludes_context, [])

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
        tts_stop = {'type': 'mycroft.audio.speech.stop', 'data': {}}
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
        tts_stop = {'type': 'mycroft.audio.speech.stop', 'data': {}}
        self.assertIn(tts_stop, self.bus.emitted_msgs)

        # check that cleanup callback was called
        self._assert_spoken('I am dead')
        self.assertTrue(self.skill.instance.my_special_var == "default")

        # check that we are not getting speak messages anymore
        self.bus.emitted_msgs = []
        sleep(2)
        self.assertTrue(self.bus.emitted_msgs == [])

    def test_skill_stop_ovos_stop_broadcast(self):
        """STOP-1 §5.3/§9: a skill performing user-visible activity MUST
        subscribe to the `ovos.stop` global broadcast, not only its own
        targeted `<skill_id>.stop` dispatch, and abort in-flight killable
        activity on it exactly the same way."""
        self.bus.emitted_msgs = []
        self.assertTrue(self.skill.instance.my_special_var == "default")
        self.bus.emit(Message(f"{self.skill.skill_id}:test"))
        sleep(2)
        start_msg = {'type': 'mycroft.skill.handler.start',
                     'data': {'name': 'TestAbortSkill.handle_test_abort_intent'}}
        self.assertIn(start_msg, self.bus.emitted_msgs)
        self._assert_spoken('still here')
        self.assertTrue(self.skill.instance.my_special_var == "changed")

        # check that intent reacts to the ovos.stop global broadcast
        self.bus.emitted_msgs = []
        self.bus.emit(Message("ovos.stop"))
        sleep(2)

        # check that stop method was called
        self.assertTrue(self.skill.instance.stop_called)

        # check that TTS stop message was emmited
        tts_stop = {'type': 'mycroft.audio.speech.stop', 'data': {}}
        self.assertIn(tts_stop, self.bus.emitted_msgs)

        # check that cleanup callback was called
        self._assert_spoken('I am dead')
        self.assertTrue(self.skill.instance.my_special_var == "default")

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
        tts_stop = {'type': 'mycroft.audio.speech.stop', 'data': {}}
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

    def test_no_leak_on_natural_completion(self):
        """Regression test for ovos-skill-alerts#138: a killable_intent /
        killable_event wrapped handler that finishes on its own (eg. a
        get_response() waiter whose abort message never arrives, or any
        quick handler that simply returns) must not leave its
        `mycroft.skills.abort_execution` `.once` bus listener registered
        forever, and must not leave a dead thread behind in
        `skill._threads`. Before the fix, every call leaked one listener
        (and one stale Thread reference) that never got cleaned up, which
        is exactly the kind of accumulation a long-lived/shared skill
        instance (eg. a test suite reusing one skill across many calls,
        or an embedded/CI process) hits repeatedly.
        """
        self.bus.emitted_msgs = []
        msg_type = "mycroft.skills.abort_execution"
        stop_msg_type = f"{self.skill.skill_id}.stop"
        global_stop_msg_type = "ovos.stop"
        before = len(self.bus.ee.listeners(msg_type))
        stop_before = len(self.bus.ee.listeners(stop_msg_type))
        global_stop_before = len(self.bus.ee.listeners(global_stop_msg_type))
        threads_before = len(self.skill.instance._threads)

        self.bus.emit(Message(f"{self.skill.skill_id}:test4"))
        sleep(2)

        self._assert_spoken("quick done")

        after = len(self.bus.ee.listeners(msg_type))
        self.assertEqual(before, after,
                         "killable_intent leaked a bus listener after the "
                         "wrapped handler finished on its own")

        stop_after = len(self.bus.ee.listeners(stop_msg_type))
        self.assertEqual(stop_before, stop_after,
                         "killable_intent leaked a bus listener on "
                         f"'{stop_msg_type}' after the wrapped handler "
                         "finished on its own")

        # STOP-1 §5.3/§9: killable_intent also listens on the global
        # `ovos.stop` broadcast (react_to_stop=True by default); that
        # listener must be cleaned up on natural completion too, same as
        # the legacy `<skill_id>.stop` listener above.
        global_stop_after = len(self.bus.ee.listeners(global_stop_msg_type))
        self.assertEqual(global_stop_before, global_stop_after,
                         "killable_intent leaked a bus listener on "
                         f"'{global_stop_msg_type}' after the wrapped "
                         "handler finished on its own")

        threads_after = len(self.skill.instance._threads)
        self.assertEqual(threads_before, threads_after,
                         "killable_intent left a dead thread behind in "
                         "skill._threads after natural completion")


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
