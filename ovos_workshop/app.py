from typing import Optional
from ovos_config.locations import get_xdg_config_save_path
from ovos_bus_client.util import get_mycroft_bus
from ovos_spec_tools import find_lang_dir, standardize_lang
from ovos_bus_client.apis.gui import GUIInterface
from ovos_bus_client.client.client import MessageBusClient
from ovos_workshop.skills.ovos import OVOSSkill


class OVOSAbstractApplication(OVOSSkill):
    def __init__(self, skill_id: str, bus: Optional[MessageBusClient] = None,
                 resources_dir: Optional[str] = None,
                 gui: Optional[GUIInterface] = None, **kwargs):
        """
        Create an Application. An application is essentially a skill, but
        designed such that it may be run without an intent service.
        @param skill_id: Unique ID for this application
        @param bus: MessageBusClient to bind to application
        @param resources_dir: optional root resource directory (else defaults to
            application `root_dir`
        @param gui: GUIInterface to bind (if `None`, one is created)
        """
        self._dedicated_bus = False
        if bus:
            self._dedicated_bus = False
        else:
            self._dedicated_bus = True
            bus = get_mycroft_bus()

        super().__init__(skill_id=skill_id, bus=bus, gui=gui,
                         resources_dir=resources_dir,
                         **kwargs)
    @property
    def settings_path(self) -> str:
        """
        Overrides the default path to put settings in `apps` subdirectory.
        """
        return join(get_xdg_config_save_path(), 'apps', self.skill_id,
                    'settings.json')

    def default_shutdown(self):
        """
        Shutdown this application.
        """
        self.clear_intents()
        super().default_shutdown()
        if self._dedicated_bus:
            self.bus.close()

    def get_language_dir(self, base_path: Optional[str] = None,
                         lang: Optional[str] = None) -> Optional[str]:
        """
        Get the best matched language resource directory for the requested lang.

        Delegates to :func:`ovos_spec_tools.find_lang_dir` — case mismatch
        (``en-US`` vs ``en-us``), bare-language requests (``en`` against
        ``en-US/``) and minor regional fallback (``en-au`` -> ``en-us``)
        all resolve through one OVOS-INTENT-2 §2.2 predicate.

        @param base_path: root path to find resources (default res_dir)
        @param lang: language to get resources for (default self.lang)
        @return: path to language resources if they exist, else None
        """
        resolved = find_lang_dir(base_path or self.res_dir,
                                 standardize_lang(lang or self.lang))
        return str(resolved) if resolved is not None else None

    def clear_intents(self):
        """
        Remove bus event handlers and detach from the intent service to prevent
        multiple registered handlers.
        """
        for intent_name, _ in self.intent_service:
            event_name = f'{self.skill_id}:{intent_name}'
            self.remove_event(event_name)
        # delete old intents before re-registering
        self.intent_service.detach_all()
