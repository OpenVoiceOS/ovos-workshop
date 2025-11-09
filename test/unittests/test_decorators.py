import json
import unittest
from os.path import dirname
from unittest.mock import Mock
from time import sleep

from ovos_workshop.skill_launcher import SkillLoader
from ovos_utils.fakebus import FakeBus
from ovos_bus_client.message import Message


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

    def test_resting_screen_handler(self):
        from ovos_workshop.decorators import resting_screen_handler
        called = False

        @resting_screen_handler("test_homescreen")
        def show_homescreen():
            nonlocal called
            called = True

        self.assertEqual(show_homescreen.resting_handler, "test_homescreen")
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

    @unittest.skip("TODO - update/fix me")
    def test_skills_abort_event(self):
        self.bus.emitted_msgs = []
        # skill will enter a infinite loop unless aborted
        self.assertTrue(self.skill.instance.my_special_var == "default")
        self.bus.emit(Message(f"{self.skill.skill_id}:test.intent"))
        sleep(2)
        # check that intent triggered
        start_msg = {'type': 'mycroft.skill.handler.start',
                     'data': {'name': 'KillableSkill.handle_test_abort_intent'}}
        speak_msg = {'type': 'speak',
                     'data': {'utterance': 'still here', 'expect_response': False,
                              'meta': {'skill': 'abort.test'},
                              'lang': 'en-US'}}
        self.assertIn(start_msg, self.bus.emitted_msgs)
        self.assertIn(speak_msg, self.bus.emitted_msgs)
        self.assertTrue(self.skill.instance.my_special_var == "changed")

        # check that intent reacts to mycroft.skills.abort_execution
        # eg, gui can emit this event if some option was selected
        # on screen to abort the current voice interaction
        self.bus.emitted_msgs = []
        self.bus.emit(Message(f"mycroft.skills.abort_execution"))
        sleep(2)

        # check that stop method was called
        self.assertTrue(self.skill.instance.stop_called)

        # check that TTS stop message was emmited
        tts_stop = {'type': 'mycroft.audio.speech.stop', 'data': {}}
        self.assertIn(tts_stop, self.bus.emitted_msgs)

        # check that cleanup callback was called
        speak_msg = {'type': 'speak',
                     'data': {'utterance': 'I am dead', 'expect_response': False,
                              'meta': {'skill': 'abort.test'},
                              'lang': 'en-US'}}
        self.assertIn(speak_msg, self.bus.emitted_msgs)
        self.assertTrue(self.skill.instance.my_special_var == "default")

        # check that we are not getting speak messages anymore
        self.bus.emitted_msgs = []
        sleep(2)
        self.assertTrue(self.bus.emitted_msgs == [])

    @unittest.skip("TODO - update/fix me")
    def test_skill_stop(self):
        self.bus.emitted_msgs = []
        # skill will enter a infinite loop unless aborted
        self.assertTrue(self.skill.instance.my_special_var == "default")
        self.bus.emit(Message(f"{self.skill.skill_id}:test.intent"))
        sleep(2)
        # check that intent triggered
        start_msg = {'type': 'mycroft.skill.handler.start',
                     'data': {'name': 'KillableSkill.handle_test_abort_intent'}}
        speak_msg = {'type': 'speak',
                     'data': {'utterance': 'still here', 'expect_response': False,
                              'meta': {'skill': 'abort.test'}, 'lang': 'en-US'}}
        self.assertIn(start_msg, self.bus.emitted_msgs)
        self.assertIn(speak_msg, self.bus.emitted_msgs)
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
        speak_msg = {'type': 'speak',
                     'data': {'utterance': 'I am dead', 'expect_response': False,
                              'meta': {'skill': 'abort.test'},
                              'lang': 'en-US'}}

        self.assertIn(speak_msg, self.bus.emitted_msgs)
        self.assertTrue(self.skill.instance.my_special_var == "default")

        # check that we are not getting speak messages anymore
        self.bus.emitted_msgs = []
        sleep(2)
        self.assertTrue(self.bus.emitted_msgs == [])

    @unittest.skip("TODO - update/fix me")
    def test_get_response(self):
        """ send "mycroft.skills.abort_question" and
        confirm only get_response is aborted, speech after is still spoken"""
        self.bus.emitted_msgs = []
        # skill will enter a infinite loop unless aborted
        self.bus.emit(Message(f"{self.skill.skill_id}:test2.intent",
                              context={"session": {"session_id": "123"}}))
        sleep(2)
        # check that intent triggered
        start_msg = {'type': 'mycroft.skill.handler.start',
                     'data': {'name': 'KillableSkill.handle_test_get_response_intent'}}
        speak_msg = {'type': 'speak',
                     'data': {'utterance': 'this is a question',
                              'expect_response': True,
                              'meta': {'dialog': 'question', 'data': {}, 'skill': 'abort.test'},
                              'lang': 'en-US'}}
        activate_msg = {'type': 'intent.service.skills.activate', 'data': {'skill_id': 'abort.test'}}

        sleep(0.5)  # fake wait_while_speaking
        self.bus.emit(Message(f"recognizer_loop:audio_output_end",
                              context={"session": {"session_id": "123"}}))
        sleep(1)  # get_response is in a thread so it can be killed, let it capture msg above

        self.assertIn(start_msg, self.bus.emitted_msgs)
        self.assertIn(speak_msg, self.bus.emitted_msgs)
        self.assertIn(activate_msg, self.bus.emitted_msgs)

        # check that get_response loop is aborted
        # but intent continues executing
        self.bus.emitted_msgs = []
        self.bus.emit(Message(f"mycroft.skills.abort_question"))
        sleep(1)

        # check that stop method was NOT called
        self.assertFalse(self.skill.instance.stop_called)

        # check that speak message after get_response loop was spoken
        speak_msg = {'type': 'speak',
                     'data': {'utterance': 'question aborted',
                              'expect_response': False,
                              'meta': {'skill': 'abort.test'},
                              'lang': 'en-US'}}
        self.assertIn(speak_msg, self.bus.emitted_msgs)

    @unittest.skip("TODO - update/fix me")
    def test_developer_stop_msg(self):
        """ send "my.own.abort.msg" and confirm intent3 is aborted
        send "mycroft.skills.abort_execution" and confirm intent3 ignores it"""
        self.bus.emitted_msgs = []
        # skill will enter a infinite loop unless aborted
        self.bus.emit(Message(f"{self.skill.skill_id}:test3.intent"))
        sleep(2)
        # check that intent triggered
        start_msg = {'type': 'mycroft.skill.handler.start',
                     'data': {'name': 'KillableSkill.handle_test_msg_intent'}}
        speak_msg = {'type': 'speak',
                     'data': {'utterance': "you can't abort me",
                              'expect_response': False,
                              'meta': {'skill': 'abort.test'},
                              'lang': 'en-US'}}
        self.assertIn(start_msg, self.bus.emitted_msgs)
        self.assertIn(speak_msg, self.bus.emitted_msgs)

        # check that intent does NOT react to mycroft.skills.abort_execution
        # developer requested a dedicated abort message
        self.bus.emitted_msgs = []
        self.bus.emit(Message(f"mycroft.skills.abort_execution"))
        sleep(1)

        # check that stop method was NOT called
        self.assertFalse(self.skill.instance.stop_called)

        # check that intent reacts to my.own.abort.msg
        self.bus.emitted_msgs = []
        self.bus.emit(Message(f"my.own.abort.msg"))
        sleep(2)

        # check that stop method was called
        self.assertTrue(self.skill.instance.stop_called)

        # check that TTS stop message was emmited
        tts_stop = {'type': 'mycroft.audio.speech.stop', 'data': {}}
        self.assertIn(tts_stop, self.bus.emitted_msgs)

        # check that cleanup callback was called
        speak_msg = {'type': 'speak',
                     'data': {'utterance': 'I am dead', 'expect_response': False,
                              'meta': {'skill': 'abort.test'},
                              'lang': 'en-US'}}
        self.assertIn(speak_msg, self.bus.emitted_msgs)
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
