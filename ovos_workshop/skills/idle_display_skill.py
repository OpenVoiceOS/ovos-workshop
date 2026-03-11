# Copyright 2021 Mycroft AI Inc.
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
import abc

from ovos_bus_client.message import Message
from ovos_utils.log import LOG
from ovos_workshop.skills.ovos import OVOSSkill


class IdleDisplaySkill(OVOSSkill):
    """
    equivalent to using @resting_handler decorator in a regular OVOSSkill

    Helper class for skills that define an idle display.

    An idle display is what shows on a device's screen when it is not in use
    by other skills. i.e. a Home Screen skill.

    The idle display should show when no other skill is using the display. Some
    skills use the display for a defined period of time before returning to the
    idle display (e.g. Weather Skill). Some skills take control of the display
    indefinitely (e.g. Timer Skill).

    The display could be a touch screen (such as on the Mark II), or an
    Arduino LED array (such as on the Mark I), or any other type of display.
    This base class is meant to be agnostic to the type of display.
    """

    @abc.abstractmethod
    def handle_idle(self):
        """
        Override this method to display the idle screen.
        """
        raise NotImplementedError("Subclass must override the handle_idle method")

    def _register_system_event_handlers(self):
        """
        Defines the bus events handled in this skill and their handlers.
        """
        super()._register_system_event_handlers()
        self.add_event("homescreen.manager.activate.display", self.handle_homescreen_request)
        self.add_event("homescreen.manager.reload.list", self.register_homescreen)
        self.add_event("mycroft.skills.shutdown", self._remove_homescreen_on_shutdown)
        self.register_homescreen()

    def register_homescreen(self, message: Message = None):
        """
        Update the internal _homescreen_entry object
        for this skill and send it to the Home Screen Manager.
        @param message: optional Message associated with request
        """
        LOG.debug(f"Registering Homescreen {self.skill_id}")
        self.bus.emit(Message("homescreen.manager.add",
                              {"class": "IdleDisplaySkill",  # TODO - rm in ovos-gui, only for compat
                               "id": self.skill_id}))

    def remove_homescreen(self, message: Message):
        """
        Remove this skill's homescreen_entry from the Home Screen Manager
        @param message: `mycroft.skills.shutdown` message
        """
        LOG.debug(f"Requesting homescreen removal of {self.skill_id}")
        msg = message.forward("homescreen.manager.remove",
                              {"id": self.skill_id})
        self.bus.emit(msg)

    def _remove_homescreen_on_shutdown(self, message: Message):
        """
        Remove this homescreen from the Home Screen Manager if requested
        @param message: `mycroft.skills.shutdown` message
        """
        if message.data["id"] == self.skill_id:
            self.remove_homescreen(message)

    def handle_homescreen_request(self, message: Message):
        """
        Display this home screen if requested by the Home Screen Manager
        @param message: `homescreen.manager.activate.display` message
        """
        if message.data["homescreen_id"] == self.skill_id:
            self.handle_idle()
            self.bus.emit(message.reply("skill.idle.displayed"))
