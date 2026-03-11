import threading
from functools import wraps
from inspect import signature
from typing import Optional, Type

from ovos_bus_client.session import SessionManager
from ovos_utils import create_killable_daemon
from ovos_bus_client.message import Message
from ovos_utils.log import LOG


class AbortEvent(StopIteration):
    """ abort bus event handler """


class AbortIntent(AbortEvent):
    """ abort intent parsing """


class AbortQuestion(AbortEvent):
    """ gracefully abort get_response queries """


def killable_intent(msg: str = "mycroft.skills.abort_execution",
                    callback: Optional[callable] = None,
                    react_to_stop: bool = True,
                    call_stop: bool = True, stop_tts: bool = True) -> callable:
    """
    Decorator to mark an intent that can be terminated during execution.
    @param msg: Message name to terminate on
    @param callback: Optional function or method to call on termination
    @param react_to_stop: If true, also terminate on `stop` Messages
    @param call_stop: If true, also call `Class.stop` method
    @param stop_tts: If true, emit message to stop TTS audio playback
    """
    return killable_event(msg, AbortIntent, callback, react_to_stop,
                          call_stop, stop_tts)


def killable_event(msg: str = "mycroft.skills.abort_execution",
                   exc: Type[Exception] = AbortEvent,
                   callback: Optional[callable] = None,
                   react_to_stop: bool = False, call_stop: bool = False,
                   stop_tts: bool = False,
                   check_skill_id: bool = False):
    """
    Decorator to mark a method that can be terminated during execution.
    @param msg: Message name to terminate on
    @param exc: Exception to raise in killed thread
    @param callback: Optional function or method to call on termination
    @param react_to_stop: If true, also terminate on `stop` Messages
    @param call_stop: If true, also call `Class.stop` method
    @param stop_tts: If true, emit message to stop TTS audio playback
    @param check_skill_id: If true, require skill_id in message.data to match this skill
    """
    # Begin wrapper
    def create_killable(func):

        @wraps(func)
        def call_function(*args, **kwargs):
            skill = args[0]

            # Wrap func so AbortEvent exits the thread cleanly rather than
            # propagating as an unhandled thread exception (which pytest ≥3.11
            # treats as a test failure via its threadexception plugin).
            def _guarded(*a, **kw):
                try:
                    func(*a, **kw)
                except AbortEvent:
                    pass  # intentional kill — not an error

            t = create_killable_daemon(_guarded, args, kwargs, autostart=False)
            sess = SessionManager.get()

            def abort(m: Message):
                if not t.is_alive():
                    return
                # check if session matches (dont kill events from other sessions)
                sess2 = SessionManager.get(m)
                if sess.session_id != sess2.session_id:
                    LOG.debug(f"ignoring '{msg}' kill event, event listener not created by this session")
                    return
                if check_skill_id:
                    skill_id = m.data.get("skill_id", "")
                    if skill_id and skill_id != skill.skill_id:
                        LOG.debug(f"ignoring '{msg}' kill event, event targeted to {skill_id}")
                        return

                if stop_tts:
                    skill.bus.emit(Message("mycroft.audio.speech.stop"))
                if call_stop:
                    # call stop on parent skill
                    skill.stop()

                LOG.debug(f"killing {func} - callback {callback}")

                def cb():
                    if callback is not None:
                        if len(signature(callback).parameters) == 1:
                            # class method, needs self
                            callback(skill)
                        else:
                            callback()

                try:
                    while t.is_alive():
                        t.raise_exc(exc)
                        t.join(1)
                except threading.ThreadError:
                    pass  # already killed
                except AssertionError:
                    pass  # could not determine thread id ?
                except exc:
                    # this is the exception we raised ourselves to kill the thread
                    # usually it doesnt propagate this far, if it does we need to re-raise it
                    # (reproducible with killable get_response)
                    LOG.debug(f"Killed thread {t}")
                    cb()
                    raise
                cb()

            # save reference to threads so they can be killed later
            if not hasattr(skill, "_threads"):
                skill._threads = []
            skill._threads.append(t)
            skill.bus.once(msg, abort)
            if react_to_stop:
                skill.bus.once(skill.skill_id + ".stop", abort)
            t.start()
            return t

        return call_function

    return create_killable
