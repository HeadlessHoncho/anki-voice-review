from __future__ import annotations

import logging
import queue
import sys
from typing import Optional

import numpy as np
import sounddevice as sd

from anki_voice_review.anki import AnkiClient, AnkiConnectError
from anki_voice_review.commands import COMMAND_NAMES, CommandMatcher
from anki_voice_review.config import Settings
from anki_voice_review.gate import ShortBurstGate
from anki_voice_review.models import ensure_silero, ensure_vosk
from anki_voice_review.stt import VoskSTT
from anki_voice_review.vad import SileroVAD

log = logging.getLogger("anki_voice_review")


def list_input_devices() -> str:
    lines = []
    devices = sd.query_devices()
    default = sd.default.device[0] if sd.default.device else None
    for index, dev in enumerate(devices):
        if int(dev.get("max_input_channels") or 0) <= 0:
            continue
        mark = " (default)" if index == default else ""
        lines.append(f"  {index:3d}  {dev['name']}{mark}")
    if not lines:
        return "No input devices found."
    return "Input devices:\n" + "\n".join(lines)


def run(settings: Settings) -> int:
    matcher = CommandMatcher(settings.phrases)
    gate = ShortBurstGate(settings.gate_config())

    log.info("loading Silero VAD")
    silero_path = ensure_silero(settings.silero_path, progress=log.info)
    vad = SileroVAD(
        silero_path,
        threshold=settings.vad_threshold,
        sample_rate=settings.sample_rate,
    )

    log.info("loading Vosk model")
    vosk_path = ensure_vosk(settings.vosk_path, progress=log.info)
    stt = VoskSTT(
        vosk_path,
        matcher.phrases_for_grammar(),
        sample_rate=settings.sample_rate,
    )

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

    words = " / ".join(COMMAND_NAMES)
    device = settings.input_device
    try:
        dev_info = sd.query_devices(device, "input")
        dev_name = dev_info["name"]
    except Exception:
        dev_name = "default"

    log.info("mic: %s @ %d Hz", dev_name, settings.sample_rate)
    log.info("listening for %s", words)
    log.info("Ctrl+C to stop")

    audio_q: queue.Queue[np.ndarray] = queue.Queue(maxsize=64)

    def callback(indata, frames, time_info, status) -> None:  # noqa: ANN001
        if status:
            log.debug("audio status: %s", status)
        try:
            audio_q.put_nowait(np.copy(indata[:, 0]))
        except queue.Full:
            pass

    try:
        with sd.InputStream(
            samplerate=settings.sample_rate,
            blocksize=settings.frame_samples,
            device=device,
            channels=1,
            dtype="float32",
            callback=callback,
        ):
            while True:
                try:
                    frame = audio_q.get(timeout=0.5)
                except queue.Empty:
                    continue
                event = gate.process(vad.is_speech(frame), frame)
                if event is None:
                    continue
                if event.kind == "too_long":
                    log.info("ignored long speech (%.1fs)", event.duration_seconds)
                    continue
                if event.kind == "too_short":
                    log.debug("ignored short burst (%.2fs)", event.duration_seconds)
                    continue
                if event.audio is None:
                    continue
                text = stt.transcribe(event.audio)
                command = matcher.match(text)
                if command is None:
                    shown = text or "(empty)"
                    log.info("dropped %r (not a command)", shown)
                    continue
                log.info(
                    "heard %r (%.1fs) -> %s",
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
                    log.warning(
                        "Anki ignored %s (not in review, or answer not shown yet)",
                        command.name,
                    )
    except KeyboardInterrupt:
        log.info("stopped")
        return 0
    except sd.PortAudioError as exc:
        log.error("microphone error: %s", exc)
        print(list_input_devices(), file=sys.stderr)
        return 1
