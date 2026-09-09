from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
import uuid
import wave
from pathlib import Path
from typing import Optional, Sequence

import numpy as np

WHISPER_SERVER_PORT = 8178


def find_whisper_cli() -> Optional[Path]:
    env = os.environ.get("WHISPER_CLI")
    if env and Path(env).is_file():
        return Path(env)
    which = shutil.which("whisper-cli") or shutil.which("whisper-cli.exe")
    if which:
        return Path(which)
    home = Path.home() / "tools" / "whisper" / "whisper-cli.exe"
    if home.is_file():
        return home
    return None


def find_whisper_server() -> Optional[Path]:
    env = os.environ.get("WHISPER_SERVER")
    if env and Path(env).is_file():
        return Path(env)
    which = shutil.which("whisper-server") or shutil.which("whisper-server.exe")
    if which:
        return Path(which)
    home = Path.home() / "tools" / "whisper" / "whisper-server.exe"
    if home.is_file():
        return home
    return None


def find_large_v3_model() -> Optional[Path]:
    env = os.environ.get("WHISPER_MODEL")
    if env and Path(env).is_file():
        return Path(env)
    home = Path.home() / "tools" / "whisper" / "models" / "ggml-large-v3.bin"
    if home.is_file():
        return home
    return None


def whisper_server_url() -> str:
    return os.environ.get("WHISPER_SERVER_URL", f"http://127.0.0.1:{WHISPER_SERVER_PORT}")


def whisper_server_up(url: Optional[str] = None, timeout: float = 1.5) -> bool:
    base = (url or whisper_server_url()).rstrip("/")
    try:
        urllib.request.urlopen(base + "/", timeout=timeout)
        return True
    except urllib.error.HTTPError:
        return True
    except Exception:
        return False


def ensure_whisper_server(
    model: Path,
    server_exe: Path,
    log_path: Optional[Path] = None,
) -> str:
    """Start whisper-server with the given model if it is not already up."""
    url = whisper_server_url()
    if whisper_server_up(url):
        return url
    port = WHISPER_SERVER_PORT
    if log_path is None:
        log_path = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "anki-voice-review" / "whisper-server.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_fh = open(log_path, "ab", buffering=0)
    subprocess.Popen(
        [
            str(server_exe),
            "-m",
            str(model),
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "-l",
            "en",
            "-sns",
            "-nth",
            "0.6",
        ],
        stdout=log_fh,
        stderr=log_fh,
        cwd=str(server_exe.parent),
    )
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        if whisper_server_up(url, timeout=2.0):
            return url
        time.sleep(1.0)
    raise RuntimeError(f"whisper-server did not come up on {url} (see {log_path})")


class WhisperServerSTT:
    """whisper.cpp HTTP server. Model stays loaded (needed for large-v3)."""

    def __init__(self, url: str) -> None:
        self.url = url.rstrip("/") + "/inference"

    def transcribe(self, audio: np.ndarray, sample_rate: int = 16000) -> str:
        candidates = self.transcribe_candidates(audio, sample_rate)
        return candidates[0] if candidates else ""

    def transcribe_candidates(self, audio: np.ndarray, sample_rate: int = 16000) -> list[str]:
        pcm = _to_pcm16(audio)
        with tempfile.TemporaryDirectory(prefix="anki-voice-") as tmp:
            wav_path = Path(tmp) / "clip.wav"
            _write_wav(wav_path, pcm, sample_rate)
            wav_bytes = wav_path.read_bytes()
        boundary = "----ankiVoice" + uuid.uuid4().hex
        fields = {
            "temperature": "0.0",
            "temperature_inc": "0.2",
            "response_format": "json",
            "language": "en",
        }
        body = bytearray()
        for key, value in fields.items():
            body.extend(
                f"--{boundary}\r\nContent-Disposition: form-data; name=\"{key}\"\r\n\r\n{value}\r\n".encode()
            )
        body.extend(
            (
                f"--{boundary}\r\n"
                'Content-Disposition: form-data; name="file"; filename="clip.wav"\r\n'
                "Content-Type: audio/wav\r\n\r\n"
            ).encode()
        )
        body.extend(wav_bytes)
        body.extend(f"\r\n--{boundary}--\r\n".encode())
        req = urllib.request.Request(
            self.url,
            data=bytes(body),
            method="POST",
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw)
            text = (parsed.get("text") or "").strip()
        except json.JSONDecodeError:
            text = raw.strip()
        text = text.strip(" \t\"'")
        return [text] if text else []


class WhisperCppSTT:
    """Local whisper.cpp tiny.en. Open vocab; the whitelist happens after."""

    def __init__(self, cli: Path, model: Path) -> None:
        self.cli = Path(cli)
        self.model = Path(model)

    def transcribe(self, audio: np.ndarray, sample_rate: int = 16000) -> str:
        candidates = self.transcribe_candidates(audio, sample_rate)
        return candidates[0] if candidates else ""

    def transcribe_candidates(self, audio: np.ndarray, sample_rate: int = 16000) -> list[str]:
        pcm = _to_pcm16(audio)
        with tempfile.TemporaryDirectory(prefix="anki-voice-") as tmp:
            wav_path = Path(tmp) / "clip.wav"
            _write_wav(wav_path, pcm, sample_rate)
            proc = subprocess.run(
                [
                    str(self.cli),
                    "-m",
                    str(self.model),
                    "-f",
                    str(wav_path),
                    "-l",
                    "en",
                    "-nt",
                    "-np",
                    "-sns",
                    "-ng",
                    "-nth",
                    "0.7",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
        text = (proc.stdout or "").strip()
        # whisper-cli sometimes still leaks a header line
        lines = [ln.strip(" \t\"'") for ln in text.splitlines() if ln.strip()]
        cleaned = []
        for line in lines:
            low = line.lower()
            if low.startswith("whisper") or low.startswith("ggml") or "vulkan" in low:
                continue
            cleaned.append(line)
        if not cleaned:
            return []
        return [cleaned[-1]]


class VoskSTT:
    """Open-vocab Vosk. Do not use a command grammar — it will invent commands."""

    def __init__(
        self,
        model_path: str | Path,
        phrases: Sequence[str] | None = None,
        sample_rate: int = 16000,
    ) -> None:
        from vosk import KaldiRecognizer, Model, SetLogLevel

        SetLogLevel(-1)
        self.sample_rate = sample_rate
        self.model = Model(str(model_path))
        self._Recognizer = KaldiRecognizer

    def transcribe(self, audio: np.ndarray) -> str:
        candidates = self.transcribe_candidates(audio)
        return candidates[0] if candidates else ""

    def transcribe_candidates(self, audio: np.ndarray) -> list[str]:
        pcm = _to_pcm16(audio)
        rec = self._Recognizer(self.model, float(self.sample_rate))
        rec.SetWords(False)
        rec.AcceptWaveform(pcm)
        text = (json.loads(rec.FinalResult()).get("text") or "").strip()
        return [text] if text else []


def _to_pcm16(audio: np.ndarray) -> bytes:
    samples = np.asarray(audio, dtype=np.float32).reshape(-1)
    samples = np.clip(samples, -1.0, 1.0)
    return (samples * 32767.0).astype(np.int16).tobytes()


def _write_wav(path: Path, pcm: bytes, sample_rate: int) -> None:
    with wave.open(str(path), "wb") as fh:
        fh.setnchannels(1)
        fh.setsampwidth(2)
        fh.setframerate(sample_rate)
        fh.writeframes(pcm)
