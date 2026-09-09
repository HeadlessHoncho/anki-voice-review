from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from anki_voice_review import __version__
from anki_voice_review.addon import install_ankiconnect
from anki_voice_review.anki import AnkiClient, AnkiConnectError
from anki_voice_review.audio import list_input_devices, test_mic
from anki_voice_review.config import cache_dir, load_settings
from anki_voice_review.loop import build_stt, run
from anki_voice_review.models import ensure_silero, ensure_vosk
from anki_voice_review.selftest import run_self_test, run_wav


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="anki-voice-review",
        description=(
            "Review Anki cards by voice while another app is focused. "
            "Local VAD + short-burst gate + whisper.cpp + exact whitelist + AnkiConnect."
        ),
    )
    parser.add_argument("--config", "-c", type=Path, help="TOML config file")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Recognize commands but do not call Anki",
    )
    parser.add_argument(
        "--device",
        default=None,
        help="Input device index or name substring (see --list-devices)",
    )
    parser.add_argument(
        "--test-mic",
        action="store_true",
        help="Live level meter so you can see if talking moves the bar",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Ping AnkiConnect and exit",
    )
    parser.add_argument(
        "--list-devices",
        action="store_true",
        help="List microphone devices and exit",
    )
    parser.add_argument(
        "--download-models",
        action="store_true",
        help="Download Silero VAD and Vosk models, then exit",
    )
    parser.add_argument(
        "--install-ankiconnect",
        action="store_true",
        help="Install the AnkiConnect add-on into Anki's add-ons folder",
    )
    parser.add_argument(
        "--wav",
        type=Path,
        help="Feed a WAV through the same gate/STT/whitelist (no microphone)",
    )
    parser.add_argument(
        "--expect",
        help="With --wav, the command name that should match (show/again/hard/good/easy/undo)",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Synthesize the six commands with Windows TTS and run them through the pipeline",
    )
    parser.add_argument(
        "--stt",
        choices=("auto", "large", "tiny", "vosk"),
        default="auto",
        help="Speech engine. self-test defaults to tiny unless you pass --stt",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Debug logging",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = parser.parse_args(argv)

    fmt = logging.Formatter("%(asctime)s  %(message)s", datefmt="%H:%M:%S")
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if args.verbose else logging.INFO)
    sh = logging.StreamHandler(sys.stderr)
    sh.setFormatter(fmt)
    root.addHandler(sh)
    log_path = cache_dir() / "listen.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setFormatter(fmt)
    root.addHandler(fh)
    log = logging.getLogger("anki_voice_review")

    if args.list_devices:
        print(list_input_devices())
        return 0

    if args.test_mic:
        spec = args.device
        if spec is not None and str(spec).isdigit():
            spec = int(spec)
        return test_mic(spec)

    settings = load_settings(args.config)
    if args.dry_run:
        settings.dry_run = True
    if args.device is not None:
        settings.input_device = int(args.device) if str(args.device).isdigit() else args.device

    if args.self_test:
        kind = "tiny" if args.stt == "auto" else args.stt
        return run_self_test(settings, stt_kind=kind)

    if args.wav:
        stt = build_stt(args.stt)
        rec = run_wav(args.wav, settings, stt, expect=args.expect)
        return 0 if rec["ok"] else 1

    if args.download_models:
        ensure_silero(settings.silero_path, progress=log.info)
        ensure_vosk(settings.vosk_path, progress=log.info)
        log.info("models ready")
        return 0

    if args.install_ankiconnect:
        dest = install_ankiconnect(progress=log.info)
        log.info("installed AnkiConnect at %s", dest)
        log.info("Restart Anki if it is already running.")
        return 0

    if args.check:
        client = AnkiClient(url=settings.anki_url, api_key=settings.anki_key)
        try:
            version = client.ping()
        except AnkiConnectError as exc:
            log.error("%s", exc)
            return 2
        log.info("AnkiConnect ok (version %s)", version)
        return 0

    return run(settings, stt_kind=args.stt)


if __name__ == "__main__":
    sys.exit(main())
