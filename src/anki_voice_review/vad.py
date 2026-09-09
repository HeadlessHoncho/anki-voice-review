from __future__ import annotations

from pathlib import Path

import numpy as np
import onnxruntime as ort


class SileroVAD:
    """Streaming Silero VAD via ONNX Runtime. No PyTorch required.

    Frame size is 512 samples at 16 kHz (32 ms). Hysteresis matches the
    upstream Silero iterator: enter speech at `threshold`, leave at
    `threshold - 0.15`.
    """

    def __init__(
        self,
        model_path: str | Path,
        threshold: float = 0.5,
        sample_rate: int = 16000,
    ) -> None:
        if sample_rate not in (8000, 16000):
            raise ValueError("Silero VAD supports 8000 or 16000 Hz")
        opts = ort.SessionOptions()
        opts.inter_op_num_threads = 1
        opts.intra_op_num_threads = 1
        self.session = ort.InferenceSession(
            str(model_path),
            providers=["CPUExecutionProvider"],
            sess_options=opts,
        )
        self.threshold = float(threshold)
        self.neg_threshold = max(self.threshold - 0.15, 0.01)
        self.sample_rate = sample_rate
        self.frame_samples = 512 if sample_rate == 16000 else 256
        self.context_size = 64 if sample_rate == 16000 else 32
        self.reset()

    def reset(self) -> None:
        self._state = np.zeros((2, 1, 128), dtype=np.float32)
        self._context = np.zeros((1, self.context_size), dtype=np.float32)
        self._speaking = False

    def prob(self, frame: np.ndarray) -> float:
        x = np.asarray(frame, dtype=np.float32).reshape(1, -1)
        if x.shape[1] < self.frame_samples:
            x = np.pad(x, ((0, 0), (0, self.frame_samples - x.shape[1])))
        elif x.shape[1] > self.frame_samples:
            x = x[:, : self.frame_samples]
        x = np.concatenate([self._context, x], axis=1)
        out, state = self.session.run(
            None,
            {
                "input": x,
                "state": self._state,
                "sr": np.array(self.sample_rate, dtype=np.int64),
            },
        )
        self._state = state
        self._context = x[:, -self.context_size :]
        return float(np.asarray(out).reshape(-1)[0])

    def is_speech(self, frame: np.ndarray) -> bool:
        p = self.prob(frame)
        if self._speaking:
            if p < self.neg_threshold:
                self._speaking = False
        elif p >= self.threshold:
            self._speaking = True
        return self._speaking
