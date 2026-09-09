from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from enum import Enum
from typing import Deque, List, Optional

import numpy as np


class GateState(str, Enum):
    IDLE = "idle"
    CAPTURING = "capturing"
    COOLDOWN = "cooldown"


@dataclass(frozen=True)
class GateConfig:
    """Burst window aligned with Silero VAD / whisper.cpp defaults.

    Silero `get_speech_timestamps` and whisper.cpp `--vad-*`:
      threshold 0.5, min_speech 250 ms, min_silence 100–200 ms, speech_pad 30–400 ms.
    Command-word presets keep min_speech short and cap max_speech so conversation
    never reaches STT.
    """

    sample_rate: int = 16000
    min_burst_seconds: float = 0.25
    max_burst_seconds: float = 1.8
    end_silence_seconds: float = 0.20
    rearm_silence_seconds: float = 0.50
    speech_pad_seconds: float = 0.30


@dataclass(frozen=True)
class GateEvent:
    """Result of feeding one VAD-labelled audio frame into the gate."""

    kind: str  # accepted | too_long | too_short
    duration_seconds: float
    audio: Optional[np.ndarray] = None


class ShortBurstGate:
    """Only short utterances reach STT.

    Speech that keeps going (conversation, a pizza order) is dropped, then
    the gate waits for a stretch of silence before it will listen again.

    Leading/trailing `speech_pad_seconds` are attached to accepted clips so
    STT sees the start of a word (the "sh" in "show"). Pad is not counted
    toward min/max burst duration.
    """

    def __init__(self, config: GateConfig | None = None) -> None:
        self.config = config or GateConfig()
        self.state = GateState.IDLE
        self._frames: List[np.ndarray] = []
        self._prefix: List[np.ndarray] = []
        self._preroll: Deque[np.ndarray] = deque()
        self._silence_frames = 0
        self._frame_samples: Optional[int] = None

    def reset(self) -> None:
        self.state = GateState.IDLE
        self._frames.clear()
        self._prefix.clear()
        self._preroll.clear()
        self._silence_frames = 0
        self._frame_samples = None

    def process(self, is_speech: bool, frame: np.ndarray) -> Optional[GateEvent]:
        frame = np.asarray(frame, dtype=np.float32).reshape(-1)
        if self._frame_samples is None:
            self._frame_samples = int(frame.shape[0])
        elif int(frame.shape[0]) != self._frame_samples:
            raise ValueError(
                f"frame size changed: {frame.shape[0]} != {self._frame_samples}"
            )

        dt = self._frame_samples / float(self.config.sample_rate)
        pad_n = max(0, int(round(self.config.speech_pad_seconds / dt)))

        if self.state is GateState.IDLE:
            if not is_speech:
                if pad_n:
                    self._preroll.append(frame.copy())
                    while len(self._preroll) > pad_n:
                        self._preroll.popleft()
                return None
            self.state = GateState.CAPTURING
            self._prefix = list(self._preroll)
            self._preroll.clear()
            self._frames = [frame.copy()]
            self._silence_frames = 0
            return None

        if self.state is GateState.CAPTURING:
            self._frames.append(frame.copy())
            total = len(self._frames) * dt
            if is_speech:
                self._silence_frames = 0
                if total >= self.config.max_burst_seconds:
                    event = GateEvent(kind="too_long", duration_seconds=total)
                    self._enter_cooldown()
                    return event
                return None

            self._silence_frames += 1
            if self._silence_frames * dt < self.config.end_silence_seconds:
                return None
            keep = len(self._frames) - self._silence_frames
            speech_dur = keep * dt
            if speech_dur < self.config.min_burst_seconds:
                event = GateEvent(kind="too_short", duration_seconds=speech_dur)
                self.reset()
                return event
            speech = self._frames[:keep]
            suffix_n = min(self._silence_frames, pad_n)
            suffix = self._frames[keep : keep + suffix_n]
            parts = list(self._prefix) + speech + suffix
            audio = np.concatenate(parts) if parts else None
            event = GateEvent(
                kind="accepted",
                duration_seconds=speech_dur,
                audio=audio,
            )
            self.reset()
            return event

        if self.state is GateState.COOLDOWN:
            if is_speech:
                self._silence_frames = 0
            else:
                self._silence_frames += 1
                if self._silence_frames * dt >= self.config.rearm_silence_seconds:
                    self.reset()
            return None

        return None

    def _enter_cooldown(self) -> None:
        self.state = GateState.COOLDOWN
        self._frames.clear()
        self._prefix.clear()
        self._preroll.clear()
        self._silence_frames = 0
