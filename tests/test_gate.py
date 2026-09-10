import numpy as np

from anki_puppeteer.gate import GateConfig, GateState, ShortBurstGate

SR = 16000
FRAME = 512
DT = FRAME / SR


def _frame(level: float = 0.1) -> np.ndarray:
    return np.full(FRAME, level, dtype=np.float32)


def _feed(gate: ShortBurstGate, speech: bool, n: int):
    last = None
    for _ in range(n):
        event = gate.process(speech, _frame())
        if event is not None:
            last = event
    return last


def test_silence_never_emits():
    gate = ShortBurstGate(GateConfig(sample_rate=SR))
    assert _feed(gate, False, 100) is None
    assert gate.state is GateState.IDLE


def test_short_command_is_accepted():
    cfg = GateConfig(sample_rate=SR, min_burst_seconds=0.2, max_burst_seconds=1.8, end_silence_seconds=0.32)
    gate = ShortBurstGate(cfg)
    speech_frames = int(0.5 / DT)
    silence_frames = int(0.32 / DT) + 1
    assert _feed(gate, True, speech_frames) is None
    event = _feed(gate, False, silence_frames)
    assert event is not None
    assert event.kind == "accepted"
    assert event.audio is not None
    assert abs(event.duration_seconds - speech_frames * DT) < DT * 2
    assert gate.state is GateState.IDLE


def test_long_speech_is_aborted_and_needs_rearm():
    cfg = GateConfig(
        sample_rate=SR,
        max_burst_seconds=0.6,
        end_silence_seconds=0.32,
        rearm_silence_seconds=0.4,
    )
    gate = ShortBurstGate(cfg)
    event = _feed(gate, True, int(0.7 / DT) + 2)
    assert event is not None
    assert event.kind == "too_long"
    assert event.audio is None
    assert gate.state is GateState.COOLDOWN

    # still talking: stay in cooldown
    assert _feed(gate, True, 10) is None
    assert gate.state is GateState.COOLDOWN

    # not enough silence to re-arm
    _feed(gate, False, 2)
    assert gate.state is GateState.COOLDOWN

    _feed(gate, False, int(0.4 / DT) + 2)
    assert gate.state is GateState.IDLE


def test_click_is_too_short():
    cfg = GateConfig(sample_rate=SR, min_burst_seconds=0.25, end_silence_seconds=0.32)
    gate = ShortBurstGate(cfg)
    _feed(gate, True, 2)
    event = _feed(gate, False, int(0.32 / DT) + 2)
    assert event is not None
    assert event.kind == "too_short"
    assert gate.state is GateState.IDLE


def test_default_min_burst_accepts_short_command_word():
    """Silero default min_speech is 250 ms; 'show' is often ~300–400 ms."""
    cfg = GateConfig(sample_rate=SR, min_burst_seconds=0.25, end_silence_seconds=0.20)
    gate = ShortBurstGate(cfg)
    speech_frames = int(0.32 / DT)
    _feed(gate, True, speech_frames)
    event = _feed(gate, False, int(0.20 / DT) + 1)
    assert event is not None
    assert event.kind == "accepted"
    assert event.duration_seconds >= 0.25


def test_preroll_and_pad_are_not_counted_in_duration():
    pad = 0.128  # 4 frames at 512/16000
    cfg = GateConfig(
        sample_rate=SR,
        min_burst_seconds=0.2,
        max_burst_seconds=1.8,
        end_silence_seconds=0.32,
        speech_pad_seconds=pad,
    )
    gate = ShortBurstGate(cfg)
    _feed(gate, False, 20)
    speech_frames = int(0.5 / DT)
    _feed(gate, True, speech_frames)
    event = _feed(gate, False, int(0.32 / DT) + 2)
    assert event is not None
    assert event.kind == "accepted"
    assert abs(event.duration_seconds - speech_frames * DT) < DT * 2
    assert event.audio is not None
    assert len(event.audio) > speech_frames * FRAME


def test_command_after_aborted_conversation():
    cfg = GateConfig(
        sample_rate=SR,
        min_burst_seconds=0.2,
        max_burst_seconds=0.6,
        end_silence_seconds=0.32,
        rearm_silence_seconds=0.4,
    )
    gate = ShortBurstGate(cfg)
    abort = _feed(gate, True, int(0.7 / DT) + 2)
    assert abort.kind == "too_long"
    _feed(gate, False, int(0.4 / DT) + 2)
    assert gate.state is GateState.IDLE

    _feed(gate, True, int(0.4 / DT))
    event = _feed(gate, False, int(0.32 / DT) + 2)
    assert event.kind == "accepted"
