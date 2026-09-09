from __future__ import annotations

import time
from typing import Optional, Union

import numpy as np
import sounddevice as sd

DeviceSpec = Union[int, str, None]


def list_input_devices() -> str:
    lines = []
    default = sd.default.device[0] if sd.default.device else None
    for index, dev in enumerate(sd.query_devices()):
        if int(dev.get("max_input_channels") or 0) <= 0:
            continue
        host = sd.query_hostapis()[int(dev["hostapi"])]["name"]
        mark = " (default)" if index == default else ""
        lines.append(
            f"  {index:3d}  {dev['name']}  [{host}, {int(dev['default_samplerate'])} Hz]{mark}"
        )
    if not lines:
        return "No input devices found."
    return "Input devices:\n" + "\n".join(lines)


def resolve_input_device(spec: DeviceSpec) -> int:
    """Resolve a device index or name substring. Prefers WASAPI matches."""
    devices = list(sd.query_devices())
    if spec is None or spec == "":
        default = sd.default.device[0]
        if default is None or int(default) < 0:
            raise RuntimeError("no default input device")
        return int(default)
    if isinstance(spec, int) or (isinstance(spec, str) and spec.isdigit()):
        index = int(spec)
        info = sd.query_devices(index, "input")
        if int(info.get("max_input_channels") or 0) <= 0:
            raise RuntimeError(f"device {index} is not an input")
        return index

    needle = str(spec).lower()
    matches: list[int] = []
    for index, dev in enumerate(devices):
        if int(dev.get("max_input_channels") or 0) <= 0:
            continue
        if needle in str(dev["name"]).lower():
            matches.append(index)
    if not matches:
        raise RuntimeError(f"no input device matching {spec!r}\n{list_input_devices()}")
    for index in matches:
        host = sd.query_hostapis()[int(devices[index]["hostapi"])]["name"]
        if "wasapi" in host.lower():
            return index
    return matches[0]


def resample_linear(samples: np.ndarray, src_rate: int, dst_rate: int) -> np.ndarray:
    samples = np.asarray(samples, dtype=np.float32).reshape(-1)
    if src_rate == dst_rate or samples.size == 0:
        return samples
    n = int(round(samples.size * dst_rate / src_rate))
    if n < 1:
        return np.zeros(0, dtype=np.float32)
    t_src = np.linspace(0.0, 1.0, num=samples.size, endpoint=False)
    t_dst = np.linspace(0.0, 1.0, num=n, endpoint=False)
    return np.interp(t_dst, t_src, samples).astype(np.float32)


def load_wav_mono_16k(path) -> np.ndarray:
    import wave

    with wave.open(str(path), "rb") as fh:
        rate = fh.getframerate()
        nch = fh.getnchannels()
        sw = fh.getsampwidth()
        raw = fh.readframes(fh.getnframes())
    if sw == 2:
        pcm = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    elif sw == 4:
        pcm = np.frombuffer(raw, dtype=np.int32).astype(np.float32) / 2147483648.0
    else:
        raise ValueError(f"unsupported sample width {sw} in {path}")
    if nch > 1:
        pcm = pcm.reshape(-1, nch).mean(axis=1)
    return resample_linear(pcm, rate, 16000)


def _rms(frame: np.ndarray) -> float:
    x = np.asarray(frame, dtype=np.float32).reshape(-1)
    if x.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(x * x)))


class StreamTo16k:
    """Capture at the device native rate and emit 16 kHz / 512-sample frames."""

    def __init__(self, device: int, frame_samples: int = 512) -> None:
        self.device = device
        self.frame_samples = frame_samples
        self.info = sd.query_devices(device, "input")
        self.native_rate = int(self.info["default_samplerate"])
        self.target_rate = 16000
        self.step = self.native_rate / float(self.target_rate)
        self._raw = np.zeros(0, dtype=np.float32)
        self._pos = 0.0
        self._out = np.zeros(0, dtype=np.float32)
        extra = None
        if "wasapi" in sd.query_hostapis()[int(self.info["hostapi"])]["name"].lower():
            extra = sd.WasapiSettings(exclusive=False)
        max_in = int(self.info.get("max_input_channels") or 1)
        self.channels = 2 if max_in >= 2 else 1
        try:
            self.stream = sd.InputStream(
                samplerate=self.native_rate,
                device=device,
                channels=self.channels,
                dtype="float32",
                blocksize=0,
                extra_settings=extra,
            )
        except Exception:
            self.channels = 1
            self.stream = sd.InputStream(
                samplerate=self.native_rate,
                device=device,
                channels=1,
                dtype="float32",
                blocksize=0,
                extra_settings=extra,
            )

    @property
    def name(self) -> str:
        return str(self.info["name"])

    def __enter__(self) -> "StreamTo16k":
        self.stream.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.stream.stop()
        self.stream.close()

    def read_frame(self, timeout: float = 0.5) -> Optional[np.ndarray]:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            pending = self.stream.read_available
            if pending <= 0:
                time.sleep(0.01)
                continue
            data, overflowed = self.stream.read(pending)
            if overflowed:
                pass
            mono = data.mean(axis=1) if data.ndim == 2 and data.shape[1] > 1 else data.reshape(-1)
            self._push_native(mono)
            if len(self._out) >= self.frame_samples:
                frame = self._out[: self.frame_samples]
                self._out = self._out[self.frame_samples :]
                return frame
        return None

    def _push_native(self, samples: np.ndarray) -> None:
        samples = np.asarray(samples, dtype=np.float32).reshape(-1)
        if self.native_rate == self.target_rate:
            self._out = np.concatenate([self._out, samples])
            return
        self._raw = np.concatenate([self._raw, samples])
        out = []
        while self._pos + 1.0 < len(self._raw):
            i = int(self._pos)
            frac = self._pos - i
            out.append(self._raw[i] * (1.0 - frac) + self._raw[i + 1] * frac)
            self._pos += self.step
        drop = int(self._pos)
        if drop:
            self._raw = self._raw[drop:]
            self._pos -= drop
        if out:
            self._out = np.concatenate([self._out, np.asarray(out, dtype=np.float32)])


def normalize_for_stt(
    audio: np.ndarray,
    target_rms: float = 0.08,
    max_gain: float = 4.0,
    peak_limit: float = 0.95,
) -> np.ndarray:
    """Peak-limited RMS match on a finished clip. Never used on the live stream.

    Stream AGC was boosting hiss ~12x and clipping speech before VAD/STT.
    Whisper handles a quiet clip; it does not handle hard clipping.
    """
    x = np.asarray(audio, dtype=np.float32).reshape(-1)
    if x.size == 0:
        return x
    rms = _rms(x)
    peak = float(np.max(np.abs(x)))
    if rms < 1e-5 or peak < 1e-5:
        return x
    gain = min(target_rms / rms, peak_limit / peak, max_gain)
    return np.clip(x * gain, -1.0, 1.0).astype(np.float32)


class AutoGain:
    """Legacy per-frame AGC. Do not use on the live VAD stream."""

    def __init__(self, target_rms: float = 0.08, max_gain: float = 25.0) -> None:
        self.target_rms = target_rms
        self.max_gain = max_gain
        self.gain = 4.0

    def apply(self, frame: np.ndarray) -> np.ndarray:
        rms = _rms(frame)
        if rms > 1e-5:
            desired = min(self.target_rms / rms, self.max_gain)
            self.gain = 0.9 * self.gain + 0.1 * desired
        boosted = np.clip(frame * self.gain, -1.0, 1.0)
        boosted = boosted - float(np.mean(boosted))
        return boosted.astype(np.float32)


def test_mic(spec: DeviceSpec = None, seconds: float = 8.0) -> int:
    """Print a live level meter so you can see whether talking moves it."""
    index = resolve_input_device(spec)
    info = sd.query_devices(index, "input")
    host = sd.query_hostapis()[int(info["hostapi"])]["name"]
    print(f"Testing #{index}  {info['name']}  [{host}]")
    print("Talk now. The bar should jump. Ctrl+C to stop.\n")
    native = int(info["default_samplerate"])
    extra = None
    if "wasapi" in host.lower():
        extra = sd.WasapiSettings(exclusive=False)
    peak_all = 0.0
    t0 = time.monotonic()
    with sd.InputStream(
        samplerate=native,
        device=index,
        channels=1,
        dtype="float32",
        extra_settings=extra,
    ) as stream:
        while time.monotonic() - t0 < seconds:
            pending = max(stream.read_available, int(native * 0.15))
            data, _ = stream.read(pending)
            x = data[:, 0]
            rms = _rms(x)
            peak = float(np.max(np.abs(x))) if x.size else 0.0
            peak_all = max(peak_all, peak)
            width = min(40, int(rms * 400))
            bar = "#" * width
            print(f"\r  rms={rms:.4f}  peak={peak:.4f}  |{bar:<40}|", end="", flush=True)
            time.sleep(0.05)
    print()
    if peak_all < 0.02:
        print(
            "That mic barely moved. Windows may be capturing a different device "
            "than the one you are talking into. Try --list-devices and "
            "--device <index or name>."
        )
        return 2
    print(f"Heard a peak of {peak_all:.3f}. Use --device {index} if this is the right mic.")
    return 0
