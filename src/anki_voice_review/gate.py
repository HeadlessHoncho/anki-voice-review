from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional

import numpy as np


class GateState(str, Enum):
    IDLE = "idle"
    CAPTURING = "capturing"
    COOLDOWN = "cooldown"


@dataclass(frozen=True)
class GateConfig:
    sample_rate: int = 16000
    min_burst_seconds: float = 0.25
    max_burst_seconds: float = 1.8
    end_silence_seconds: float = 0.40
    rearm_silence_seconds: float = 0.80


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
    """

    def __init__(self, config: GateConfig | None = None) -> None:
        self.config = config or GateConfig()
        self.state = GateState.IDLE
        self._frames: List[np.ndarray] = []
        self._silence_frames = 0
        self._frame_samples: Optional[int] = None

    def reset(self) -> None:
        self.state = GateState.IDLE
        self._frames.clear()
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

        if self.state is GateState.IDLE:
            if is_speech:
                self.state = GateState.CAPTURING
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
            audio = np.concatenate(self._frames[:keep]) if keep else None
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
        self._silence_frames = 0
