"""Adversarial regression tests for the OVOS-INTENT-4 template producer.

Every case here is written to BREAK ``register_template`` (and the deprecated
``register_padatious_intent`` shim that feeds it): pathological vocab sizes,
cyclic references, non-string samples and repeated registration. They guard the
inline-vocab expansion DoS (INTENT-1 §4.3), the re-registration duplicate
(INTENT-4 §8.1) and the §6.3 skip-and-warn contract line by line.
"""
import threading

import pytest
from ovos_spec_tools import SpecMessage

from ovos_workshop.intents import IntentServiceInterface

# Deliberate legacy-coverage suite: adversarially exercises the deprecated
# register_padatious_intent shim on purpose.
pytestmark = pytest.mark.filterwarnings(
    "ignore:(IntentServiceInterface\\.)?register_(adapt|padatious)_\\w+ "
    "is deprecated:DeprecationWarning"
)


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


def _templates(iface, name="skill:big"):
    return [d for n, d in iface.registered_intents
            if n == name.split(":")[-1]]


def _intent_file(tmp_path, name, lines):
    path = tmp_path / name
    path.write_text("\n".join(lines))
    return str(path)


# ---------------------------------------------------------------------------
#  register_template — the spec producer choke-point
# ---------------------------------------------------------------------------

def test_many_refs_large_vocabs_do_not_enumerate():
    """Four <ref>s of fifty members each is a 6.25M cartesian product if the
    producer enumerates it to validate. It must NOT: validation is
    well-formedness only (INTENT-1 §4.3)."""
    iface = IntentServiceInterface(RecordingBus())
    vocabs = {f"v{i}": [f"w{i}_{j}" for j in range(50)] for i in range(4)}
    run_bounded(lambda: iface.register_template(
        "skill:big", ["do <v0> <v1> <v2> <v3> now"], "en-US", vocabs=vocabs))
    assert _templates(iface)


def test_month_weekday_combo_still_registers():
    """A legitimately-sized 12x7 combination must register normally."""
    iface = IntentServiceInterface(RecordingBus())
    vocabs = {"month": [f"m{i}" for i in range(12)],
              "weekday": [f"d{i}" for i in range(7)]}
    run_bounded(lambda: iface.register_template(
        "skill:when", ["remind me on <weekday> in <month>"], "en-US",
        vocabs=vocabs))
    assert _templates(iface, "skill:when")


def test_oversized_single_vocab_refused_with_warn():
    """A single pathological vocab exceeding the refuse-bound drops only its
    line (INTENT-1 §4.3 refuse, §6.3 skip-and-warn); a healthy line in the
    same registration still registers."""
    iface = IntentServiceInterface(RecordingBus())
    vocabs = {"huge": [f"x{i}" for i in range(5000)],
              "month": [f"m{i}" for i in range(12)]}
    run_bounded(lambda: iface.register_template(
        "skill:mixed", ["pick <huge> please", "the month is <month>"],
        "en-US", vocabs=vocabs))
    data = _templates(iface, "skill:mixed")[0]
    joined = " ".join(data["samples"])
    assert "m0" in joined  # month line kept
    assert "x0" not in joined  # oversized line dropped


def test_cyclic_vocab_ref_drops_line_not_registration():
    """A cyclic <a>-><b>-><a> reference raises MalformedTemplate from
    inline_keywords; it must drop that one line, not abort the whole
    registration (§6.3)."""
    iface = IntentServiceInterface(RecordingBus())
    vocabs = {"a": ["<b>"], "b": ["<a>"]}
    run_bounded(lambda: iface.register_template(
        "skill:cyc", ["say <a> loudly", "hello world"], "en-US",
        vocabs=vocabs))
    data = _templates(iface, "skill:cyc")[0]
    joined = " ".join(data["samples"])
    assert "hello world" in joined
    assert len(data["samples"]) == 1


def test_non_string_sample_is_skipped():
    """An int/dict smuggled into the samples list must be skipped (§6.3), not
    crash the whole registration on ``.strip()``."""
    iface = IntentServiceInterface(RecordingBus())
    run_bounded(lambda: iface.register_template(
        "skill:junk", [42, {"nope": 1}, "turn on the light"], "en-US"))
    data = _templates(iface, "skill:junk")[0]
    assert data["samples"] == ["turn on the light"]


def test_reregistration_replaces_not_appends():
    """Registering the same (intent_name, lang) twice must leave exactly one
    tracked entry and emit the template topic exactly once (INTENT-4 §8.1
    replacement)."""
    bus = RecordingBus()
    iface = IntentServiceInterface(bus)
    iface.register_template("skill:dup", ["turn on the light"], "en-US")
    iface.register_template("skill:dup", ["turn on the light"], "en-US")
    tracked = [n for n, _ in iface.registered_intents if n == "dup"]
    assert len(tracked) == 1
    assert bus.count(SpecMessage.INTENT_REGISTER_TEMPLATE) == 1


# ---------------------------------------------------------------------------
#  register_padatious_intent — the deprecated file-based shim skills still
#  call; it reads the file then feeds the same choke-point, so the DoS/dedup
#  guarantees must hold through the legacy entry point too.
# ---------------------------------------------------------------------------

def test_many_refs_large_vocabs_do_not_enumerate_via_padatious_api(tmp_path):
    iface = IntentServiceInterface(RecordingBus())
    vocabs = {f"v{i}": [f"w{i}_{j}" for j in range(50)] for i in range(4)}
    fname = _intent_file(tmp_path, "big.intent",
                         ["do <v0> <v1> <v2> <v3> now"])
    run_bounded(lambda: iface.register_padatious_intent(
        "skill:big", fname, "en-US", vocabs=vocabs))
    assert _templates(iface)


def test_oversized_single_vocab_refused_with_warn_via_padatious_api(tmp_path):
    iface = IntentServiceInterface(RecordingBus())
    vocabs = {"huge": [f"x{i}" for i in range(5000)],
              "month": [f"m{i}" for i in range(12)]}
    fname = _intent_file(tmp_path, "mixed.intent",
                         ["pick <huge> please", "the month is <month>"])
    run_bounded(lambda: iface.register_padatious_intent(
        "skill:mixed", fname, "en-US", vocabs=vocabs))
    data = _templates(iface, "skill:mixed")[0]
    joined = " ".join(data["samples"])
    assert "m0" in joined  # month line kept
    assert "x0" not in joined  # oversized line dropped


def test_reregistration_replaces_not_appends_via_padatious_api(tmp_path):
    bus = RecordingBus()
    iface = IntentServiceInterface(bus)
    fname = _intent_file(tmp_path, "dup.intent", ["turn on the light"])
    iface.register_padatious_intent("skill:dup", fname, "en-US")
    iface.register_padatious_intent("skill:dup", fname, "en-US")
    tracked = [n for n, _ in iface.registered_intents if n == "dup"]
    assert len(tracked) == 1
    assert bus.count("padatious:register_intent") == 1
