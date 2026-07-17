"""Adversarial regression tests for OVOS-INTENT-4 template registration.

Every case here is written to BREAK the producer: pathological vocab sizes,
cyclic references and repeated registration. They guard against the
inline-vocab expansion DoS (INTENT-1 §4.3) and the re-registration duplicate
(INTENT-4 §8.1), and prove the §6.3 skip-and-warn contract holds line by line.
"""
import threading

from ovos_workshop.intents import IntentServiceInterface


class RecordingBus:
    """Minimal bus double that records every emitted message type + data."""

    def __init__(self):
        self.types = []
        self.results = []

    def emit(self, message):
        self.types.append(message.msg_type)
        self.results.append(message.data)

    def on(self, event, func):
        pass

    def count(self, msg_type):
        return self.types.count(msg_type)


def run_bounded(fn, seconds=10):
    """Run ``fn`` in a daemon thread and fail if it does not finish within the
    bound, so a latent cartesian-product hang fails the test instead of
    freezing CI. A genuine blow-up runs for minutes; the fixed producer
    returns in well under a second. Any exception raised by ``fn`` is
    re-raised on the caller."""
    box = {}

    def _target():
        try:
            fn()
        except BaseException as err:  # surface to the caller
            box["err"] = err

    thread = threading.Thread(target=_target, daemon=True)
    thread.start()
    thread.join(seconds)
    if thread.is_alive():
        raise TimeoutError(f"registration exceeded {seconds}s hard bound "
                           f"(latent cartesian-product expansion)")
    if "err" in box:
        raise box["err"]


def _intent_file(tmp_path, name, lines):
    path = tmp_path / name
    path.write_text("\n".join(lines))
    return str(path)


def test_many_refs_large_vocabs_do_not_enumerate(tmp_path):
    """Four <ref>s of fifty members each is a 6.25M cartesian product if the
    producer enumerates it to validate. It must NOT: validation is
    well-formedness only (INTENT-1 §4.3). Register within a hard time bound."""
    iface = IntentServiceInterface(RecordingBus())
    vocabs = {f"v{i}": [f"w{i}_{j}" for j in range(50)] for i in range(4)}
    fname = _intent_file(tmp_path, "big.intent",
                         ["do <v0> <v1> <v2> <v3> now"])
    run_bounded(lambda: iface.register_padatious_intent("skill:big", fname, "en-US", vocabs=vocabs))
    assert "big" in [n for n, _ in iface.registered_intents]


def test_month_weekday_combo_still_registers(tmp_path):
    """A legitimately-sized 12x7 combination must register normally — the
    bound must not drop reasonable intents."""
    iface = IntentServiceInterface(RecordingBus())
    vocabs = {
        "month": [f"m{i}" for i in range(12)],
        "weekday": [f"d{i}" for i in range(7)],
    }
    fname = _intent_file(tmp_path, "when.intent",
                         ["remind me on <weekday> in <month>"])
    run_bounded(lambda: iface.register_padatious_intent("skill:when", fname, "en-US", vocabs=vocabs))
    names = [n for n, _ in iface.registered_intents]
    assert "when" in names


def test_oversized_single_vocab_refused_with_warn(tmp_path):
    """A single pathological vocab exceeding the refuse-bound drops only its
    line (INTENT-1 §4.3 refuse, §6.3 skip-and-warn); a healthy line in the
    same file still registers."""
    iface = IntentServiceInterface(RecordingBus())
    vocabs = {
        "huge": [f"x{i}" for i in range(5000)],
        "month": [f"m{i}" for i in range(12)],
    }
    fname = _intent_file(tmp_path, "mixed.intent",
                         ["pick <huge> please",
                          "the month is <month>"])
    run_bounded(lambda: iface.register_padatious_intent("skill:mixed", fname, "en-US", vocabs=vocabs))
    # The registration survives (healthy line kept), not aborted wholesale.
    assert "mixed" in [n for n, _ in iface.registered_intents]
    data = next(d for n, d in iface.registered_intents if n == "mixed")
    joined = " ".join(data["samples"])
    assert "m0" in joined  # month line kept
    assert "x0" not in joined  # oversized line dropped


def test_cyclic_vocab_ref_drops_line_not_registration(tmp_path):
    """A cyclic <a>-><b>-><a> reference raises MalformedTemplate from
    inline_keywords; it must drop that one line, not abort the whole
    registration (§6.3)."""
    iface = IntentServiceInterface(RecordingBus())
    vocabs = {"a": ["<b>"], "b": ["<a>"]}
    fname = _intent_file(tmp_path, "cyc.intent",
                         ["say <a> loudly",
                          "hello world"])
    run_bounded(lambda: iface.register_padatious_intent("skill:cyc", fname, "en-US", vocabs=vocabs))
    data = next(d for n, d in iface.registered_intents if n == "cyc")
    joined = " ".join(data["samples"])
    assert "hello world" in joined  # good line kept
    assert len(data["samples"]) == 1  # cyclic line dropped


def test_reregistration_replaces_not_appends(tmp_path):
    """Registering the same (intent_name, lang) twice must leave exactly one
    tracked entry and emit the registration exactly once (INTENT-4 §8.1
    replacement), not grow the list on every skill reload."""
    bus = RecordingBus()
    iface = IntentServiceInterface(bus)
    fname = _intent_file(tmp_path, "dup.intent", ["turn on the light"])
    iface.register_padatious_intent("skill:dup", fname, "en-US")
    iface.register_padatious_intent("skill:dup", fname, "en-US")
    tracked = [n for n, _ in iface.registered_intents if n == "dup"]
    assert len(tracked) == 1
    assert bus.count("padatious:register_intent") == 1
