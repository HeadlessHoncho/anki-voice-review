import wave
from pathlib import Path

import numpy as np

from anki_voice_review.audio import load_wav_mono_16k, normalize_for_stt
from anki_voice_review.config import Settings
from anki_voice_review.loop import decode_16k


class FakeSTT:
    def __init__(self, text: str) -> None:
        self.text = text
        self.calls = 0

    def transcribe_candidates(self, audio):
        self.calls += 1
        return [self.text]


def _write_wav(path: Path, samples: np.ndarray, rate: int) -> None:
    pcm = np.clip(samples, -1.0, 1.0)
    data = (pcm * 32767.0).astype(np.int16).tobytes()
    with wave.open(str(path), "wb") as fh:
        fh.setnchannels(1)
        fh.setsampwidth(2)
        fh.setframerate(rate)
        fh.writeframes(data)


def _burst(seconds: float = 0.8, sr: int = 16000, amp: float = 0.2) -> np.ndarray:
    n = int(seconds * sr)
    t = np.arange(n, dtype=np.float32) / sr
    return (amp * np.sin(2 * np.pi * 220 * t)).astype(np.float32)


def test_normalize_for_stt_boosts_quiet_and_does_not_clip():
    quiet = _burst(0.2, amp=0.02)
    out = normalize_for_stt(quiet, target_rms=0.08, max_gain=4.0)
    assert float(np.max(np.abs(out))) < 0.95
    assert float(np.sqrt(np.mean(out * out))) > float(np.sqrt(np.mean(quiet * quiet)))
    loud = _burst(0.2, amp=0.9)
    clipped = normalize_for_stt(loud, target_rms=0.08, max_gain=4.0)
    assert float(np.max(np.abs(clipped))) <= 0.95


def test_load_wav_resamples_to_16k(tmp_path: Path):
    src_rate = 22050
    samples = _burst(0.5, sr=src_rate)
    path = tmp_path / "clip.wav"
    _write_wav(path, samples, src_rate)
    out = load_wav_mono_16k(path)
    assert out.dtype == np.float32
    assert abs(len(out) / 16000 - 0.5) < 0.02
    assert float(np.max(np.abs(out))) > 0.1


def _speech_audio(seconds: float = 0.8) -> np.ndarray:
    sr = 16000
    return np.concatenate(
        [
            np.zeros(int(0.4 * sr), dtype=np.float32),
            _burst(seconds, sr=sr),
            np.zeros(int(0.5 * sr), dtype=np.float32),
        ]
    )


def test_decode_known_phrase_matches_command(monkeypatch):
    monkeypatch.setattr(
        "anki_voice_review.vad.SileroVAD.is_speech",
        lambda self, frame: float(np.mean(frame * frame)) ** 0.5 > 0.05,
    )
    stt = FakeSTT("Show.")
    hits = decode_16k(_speech_audio(), Settings(), stt)
    accepted = [h for h in hits if h["kind"] == "accepted"]
    assert accepted
    assert accepted[0]["command"] == "show"
    assert stt.calls == 1


def test_decode_rejects_non_command_transcript(monkeypatch):
    monkeypatch.setattr(
        "anki_voice_review.vad.SileroVAD.is_speech",
        lambda self, frame: float(np.mean(frame * frame)) ** 0.5 > 0.05,
    )
    stt = FakeSTT("pizza please")
    hits = decode_16k(_speech_audio(), Settings(), stt)
    accepted = [h for h in hits if h["kind"] == "accepted"]
    assert accepted
    assert accepted[0]["command"] is None
    assert stt.calls == 1
