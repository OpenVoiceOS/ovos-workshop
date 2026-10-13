"""Exceptions that ovos-workshop raises to skill code."""


class DialogNotFound(FileNotFoundError):
    """A skill asked to speak a dialog that has no phrase to render.

    OVOS-INTENT-2 §2: "a missing `.dialog` leaves the handler with nothing to
    speak for that response in that language". The file is absent in every
    searched directory, or it exists and no renderer can produce a sentence
    from it.
    """

    def __init__(self, name: str, lang: str, searched=(), reason: str = ""):
        self.name = name
        self.lang = lang
        self.reason = reason
        self.searched = [str(path) for path in searched]
        where = ", ".join(self.searched) or "no directory"
        message = (f"no dialog {name!r} for language {lang!r}"
                   f"{': ' + reason if reason else ''}; searched {where}")
        super().__init__(message)
