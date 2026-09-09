from __future__ import annotations

import logging
import time
from typing import Optional

import numpy as np

from anki_voice_review.anki import AnkiClient, AnkiConnectError
from anki_voice_review.audio import StreamTo16k, list_input_devices, normalize_for_stt, resolve_input_device
from anki_voice_review.commands import COMMAND_NAMES, CommandMatcher
from anki_voice_review.config import Settings
from anki_voice_review.gate import GateEvent, ShortBurstGate
from anki_voice_review.models import ensure_silero, ensure_vosk, ensure_whisper_tiny_en
from anki_voice_review.stt import (
    VoskSTT,
    WhisperCppSTT,
    WhisperServerSTT,
    ensure_whisper_server,
    find_large_v3_model,
    find_whisper_cli,
    find_whisper_server,
)
from anki_voice_review.vad import SileroVAD

log = logging.getLogger("anki_voice_review")

__all__ = ["list_input_devices", "run", "build_stt", "decode_16k", "BurstDetector"]


class BurstDetector:
    """Shared live/file path: Silero on raw frames, then the short-burst gate."""

    def __init__(self, settings: Settings) -> None:
        silero_path = ensure_silero(settings.silero_path, progress=log.info)
        self.vad = SileroVAD(
            silero_path,
            threshold=settings.vad_threshold,
            sample_rate=settings.sample_rate,
        )
        self.gate = ShortBurstGate(settings.gate_config())

    def feed(self, frame: np.ndarray) -> Optional[GateEvent]:
        is_speech = self.vad.is_speech(frame)
        return self.gate.process(is_speech, frame)


def build_stt(kind: str = "auto"):
    """kind: auto | large | tiny | vosk"""
    kind = (kind or "auto").lower()
    large = find_large_v3_model()
    server_exe = find_whisper_server()
    whisper_cli = find_whisper_cli()
    if kind in {"auto", "large"} and large is not None and server_exe is not None:
        log.info("starting whisper.cpp large-v3 server (%s)", large)
        url = ensure_whisper_server(large, server_exe)
        log.info("STT: whisper.cpp large-v3 @ %s", url)
        return WhisperServerSTT(url)
    if kind in {"auto", "tiny"} and whisper_cli is not None:
        log.info("loading whisper.cpp tiny.en via %s", whisper_cli)
        tiny = ensure_whisper_tiny_en(progress=log.info)
        log.info("STT: whisper.cpp tiny.en")
        return WhisperCppSTT(whisper_cli, tiny)
    if kind == "large":
        raise RuntimeError("large-v3 requested but whisper-server or ggml-large-v3.bin was not found")
    log.info("loading Vosk (open vocab, no command grammar)")
    vosk_path = ensure_vosk(progress=log.info)
    return VoskSTT(vosk_path, sample_rate=16000)


def _match_event(event: GateEvent, stt, matcher: CommandMatcher) -> dict:
    rec = {
        "kind": event.kind,
        "duration": event.duration_seconds,
        "text": "",
        "command": None,
    }
    if event.kind != "accepted" or event.audio is None:
        return rec
    clip = normalize_for_stt(event.audio)
    texts = stt.transcribe_candidates(clip)
    rec["text"] = texts[0] if texts else ""
    for text in texts:
        cmd = matcher.match(text)
        if cmd is not None:
            rec["command"] = cmd.name
            rec["text"] = text
            break
    return rec


def decode_16k(audio, settings: Settings, stt, matcher: CommandMatcher | None = None):
    """Run the live gate/VAD/STT/whitelist on a 16 kHz mono float32 buffer."""
    matcher = matcher or CommandMatcher(settings.phrases)
    detector = BurstDetector(settings)
    frame_n = settings.frame_samples
    samples = np.asarray(audio, dtype=np.float32).reshape(-1)
    hits = []
    for i in range(0, len(samples), frame_n):
        frame = samples[i : i + frame_n]
        if len(frame) < frame_n:
            frame = np.pad(frame, (0, frame_n - len(frame)))
        event = detector.feed(frame)
        if event is None:
            continue
        hits.append(_match_event(event, stt, matcher))
    return hits


def run(settings: Settings, stt_kind: str = "auto") -> int:
    matcher = CommandMatcher(settings.phrases)
    log.info(
        "gate min=%.2fs max=%.2fs pad=%.2fs vad=%.2f",
        settings.min_burst_seconds,
        settings.max_burst_seconds,
        settings.speech_pad_seconds,
        settings.vad_threshold,
    )
    log.info("loading Silero VAD")
    detector = BurstDetector(settings)

    stt = build_stt(stt_kind)

    client: Optional[AnkiClient] = None
    if settings.dry_run:
        log.info("dry-run: commands will be printed, not sent to Anki")
    else:
        client = AnkiClient(url=settings.anki_url, api_key=settings.anki_key)
        try:
            version = client.ping()
        except AnkiConnectError as exc:
            log.error("%s", exc)
            log.error(
                "Install the add-on (code 2055492159) or run: anki-voice-review --install-ankiconnect"
            )
            return 2
        log.info("AnkiConnect ok (version %s)", version)

    try:
        device = resolve_input_device(settings.input_device)
    except RuntimeError as exc:
        log.error("%s", exc)
        return 1

    words = " / ".join(COMMAND_NAMES)
    try:
        capture = StreamTo16k(device, frame_samples=settings.frame_samples)
    except Exception as exc:
        log.error("microphone error: %s", exc)
        print(list_input_devices(), file=__import__("sys").stderr)
        return 1

    log.info(
        "mic: %s @ %d Hz ch=%d (resampled to 16 kHz)",
        capture.name,
        capture.native_rate,
        capture.channels,
    )
    log.info("listening for %s", words)
    log.info("Ctrl+C to stop")

    frames = 0
    speech_frames = 0
    last_beat = time.monotonic()
    last_silent_warn = 0.0
    max_raw = 0.0

    try:
        with capture:
            while True:
                frame = capture.read_frame(timeout=0.5)
                if frame is None:
                    now = time.monotonic()
                    if now - last_beat >= 2.0:
                        log.warning(
                            "no audio frames from the mic — is another app using it exclusively?"
                        )
                        last_beat = now
                    continue
                frames += 1
                raw_rms = float((frame * frame).mean() ** 0.5)
                max_raw = max(max_raw, raw_rms)
                speaking_before = detector.vad._speaking
                event = detector.feed(frame)
                if detector.vad._speaking or speaking_before:
                    speech_frames += 1
                now = time.monotonic()
                if now - last_beat >= 2.0:
                    log.info(
                        "still listening  raw=%.4f  vad_frames=%d/%d  state=%s",
                        max_raw,
                        speech_frames,
                        frames,
                        detector.gate.state.value,
                    )
                    if max_raw < 0.02 and frames > 20 and now - last_silent_warn >= 15:
                        log.warning(
                            "mic is nearly silent. Talk, or pick another device with --test-mic / --list-devices"
                        )
                        last_silent_warn = now
                    frames = 0
                    speech_frames = 0
                    max_raw = 0.0
                    last_beat = now
                if event is None:
                    continue
                if event.kind == "too_long":
                    log.info("ignored long speech (%.1fs)", event.duration_seconds)
                    continue
                if event.kind == "too_short":
                    log.info("ignored short burst (%.2fs)", event.duration_seconds)
                    continue
                if event.audio is None:
                    continue
                clip = normalize_for_stt(event.audio)
                clip_rms = float((clip * clip).mean() ** 0.5)
                clip_peak = float(np.max(np.abs(clip))) if clip.size else 0.0
                log.info(
                    "burst %.2fs  peak=%.3f  rms=%.3f -> STT",
                    event.duration_seconds,
                    clip_peak,
                    clip_rms,
                )
                texts = stt.transcribe_candidates(clip)
                command = None
                text = ""
                for text in texts:
                    command = matcher.match(text)
                    if command is not None:
                        break
                if command is None:
                    shown = texts[0] if texts else "(empty)"
                    log.info("dropped %r (not a command)", shown)
                    continue
                log.info(
                    "heard %r (%.2fs) -> %s",
                    text,
                    event.duration_seconds,
                    command.name,
                )
                if client is None:
                    continue
                try:
                    result = client.dispatch(command.name)
                except AnkiConnectError as exc:
                    log.warning("AnkiConnect: %s", exc)
                    continue
                if result is False:
                    if command.name in {"again", "hard", "good", "easy"}:
                        log.warning(
                            "Anki ignored %s — say show first if the answer is still hidden",
                            command.name,
                        )
                    else:
                        log.warning(
                            "Anki ignored %s (not in review, or nothing to undo)",
                            command.name,
                        )
    except KeyboardInterrupt:
        log.info("stopped")
        return 0
