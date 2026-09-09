from __future__ import annotations

import logging
import subprocess
from pathlib import Path

import numpy as np

from anki_voice_review.audio import load_wav_mono_16k
from anki_voice_review.commands import COMMAND_NAMES
from anki_voice_review.config import Settings, cache_dir
from anki_voice_review.loop import build_stt, decode_16k

log = logging.getLogger("anki_voice_review")

_COMMANDS = list(COMMAND_NAMES)
_NEGATIVES = ("pizza please", "hello there")


def samples_dir() -> Path:
    path = cache_dir() / "samples"
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_sapi_wav(text: str, dest: Path, rate: int = -4) -> Path:
    """Windows SAPI TTS to a 16-bit PCM wav.

    Rate -4 is slow enough for the burst gate but still transcribes as the
    intended word. Slower than that, tiny.en hears "show" as "Shuuuuh".
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    ps = f"""
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$s.Rate = {int(rate)}
$s.Volume = 100
$s.SetOutputToWaveFile('{str(dest).replace("'", "''")}')
$s.Speak('{text.replace("'", "''")}')
$s.Dispose()
"""
    subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps],
        check=True,
        capture_output=True,
        text=True,
    )
    return dest


def _pad(audio: np.ndarray, seconds: float = 0.5, sr: int = 16000) -> np.ndarray:
    z = np.zeros(int(seconds * sr), dtype=np.float32)
    return np.concatenate([z, audio, z])


def _speech_duration(audio: np.ndarray, sr: int = 16000) -> float:
    absx = np.abs(audio)
    if absx.size == 0:
        return 0.0
    thresh = max(0.02, float(np.max(absx)) * 0.15)
    idx = np.where(absx >= thresh)[0]
    if idx.size == 0:
        return 0.0
    return float(idx[-1] - idx[0] + 1) / sr


def run_wav(path: Path, settings: Settings, stt, expect: str | None = None) -> dict:
    audio = _pad(load_wav_mono_16k(path))
    peak = float(np.max(np.abs(audio))) if audio.size else 0.0
    speech_s = _speech_duration(audio)
    hits = decode_16k(audio, settings, stt)
    commands = [h["command"] for h in hits if h.get("command")]
    texts = [h["text"] for h in hits if h.get("text")]
    kinds = [h["kind"] for h in hits]
    ok = True
    if expect == "":
        ok = not commands
    elif expect:
        ok = commands == [expect] or (len(commands) == 1 and commands[0] == expect)
    rec = {
        "path": str(path),
        "peak": peak,
        "speech_s": speech_s,
        "kinds": kinds,
        "texts": texts,
        "commands": commands,
        "expect": expect,
        "ok": ok,
    }
    log.info(
        "wav %s  speech=%.2fs  peak=%.3f  gate=%s  stt=%s  match=%s  expect=%s  %s",
        path.name,
        speech_s,
        peak,
        kinds or ["(none)"],
        texts or ["(none)"],
        commands or ["(none)"],
        expect,
        "OK" if ok else "FAIL",
    )
    return rec


def run_self_test(settings: Settings, stt_kind: str = "tiny") -> int:
    """Generate known TTS clips and run them through the live pipeline."""
    stt = build_stt(stt_kind)
    root = samples_dir()
    results = []
    log.info(
        "self-test STT=%s  min_burst=%.2fs  max_burst=%.2fs  (Windows TTS, not a virtual mic)",
        stt_kind,
        settings.min_burst_seconds,
        settings.max_burst_seconds,
    )
    for word in _COMMANDS:
        wav = root / f"{word}.wav"
        log.info("synthesizing %s", word)
        write_sapi_wav(word, wav)
        results.append(run_wav(wav, settings, stt, expect=word))
    for phrase in _NEGATIVES:
        slug = phrase.replace(" ", "_")
        wav = root / f"{slug}.wav"
        log.info("synthesizing %s", phrase)
        write_sapi_wav(phrase, wav)
        results.append(run_wav(wav, settings, stt, expect=""))
    failed = [r for r in results if not r["ok"]]
    log.info("%d/%d clips matched the expected command", len(results) - len(failed), len(results))
    return 0 if not failed else 1
