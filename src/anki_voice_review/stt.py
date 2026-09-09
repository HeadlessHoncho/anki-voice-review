from __future__ import annotations

import json
from pathlib import Path
from typing import Sequence

import numpy as np


class VoskSTT:
    """One-shot Vosk recognizer constrained to a phrase grammar."""

    def __init__(
        self,
        model_path: str | Path,
        phrases: Sequence[str],
        sample_rate: int = 16000,
    ) -> None:
        from vosk import KaldiRecognizer, Model, SetLogLevel

        SetLogLevel(-1)
        self.sample_rate = sample_rate
        self.model = Model(str(model_path))
        grammar = list(phrases) + ["[unk]"]
        self._grammar = json.dumps(grammar)
        self._Recognizer = KaldiRecognizer

    def transcribe(self, audio: np.ndarray) -> str:
        rec = self._Recognizer(self.model, float(self.sample_rate), self._grammar)
        rec.SetWords(False)
        pcm = _to_pcm16(audio, self.sample_rate)
        rec.AcceptWaveform(pcm)
        result = json.loads(rec.FinalResult())
        return (result.get("text") or "").strip()


def _to_pcm16(audio: np.ndarray, sample_rate: int) -> bytes:
    samples = np.asarray(audio, dtype=np.float32).reshape(-1)
    pad = int(0.08 * sample_rate)
    if pad:
        samples = np.concatenate(
            [np.zeros(pad, dtype=np.float32), samples, np.zeros(pad, dtype=np.float32)]
        )
    samples = np.clip(samples, -1.0, 1.0)
    return (samples * 32767.0).astype(np.int16).tobytes()
