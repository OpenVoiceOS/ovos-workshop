"""
IdleDisplaySkill is no longer supported.

The homescreen / idle display is now a built-in responsibility of the shell
client (e.g. ovos-shell).  Skills must not attempt to register as a homescreen.

Use `homescreen.register.app` to add an icon to the shell's app launcher, and
`homescreen.register.examples` to contribute example utterances to the idle screen.
"""
from ovos_utils.log import log_deprecation


class IdleDisplaySkill:
    def __init__(self, *args, **kwargs):
        log_deprecation(
            "IdleDisplaySkill is no longer supported. "
            "The homescreen is managed by the shell and adapter plugin.",
            "1.0.0",
        )
        super().__init__(*args, **kwargs)
