from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from anki_voice_review import __version__
from anki_voice_review.addon import install_ankiconnect
from anki_voice_review.anki import AnkiClient, AnkiConnectError
from anki_voice_review.config import load_settings
from anki_voice_review.loop import list_input_devices, run
from anki_voice_review.models import ensure_silero, ensure_vosk


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="anki-voice-review",
        description=(
            "Review Anki cards by voice while another app is focused. "
            "Local VAD + short-burst gate + Vosk grammar + AnkiConnect."
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
        type=int,
        default=None,
        help="Input device index (see --list-devices)",
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
        "--verbose",
        "-v",
        action="store_true",
        help="Debug logging",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s  %(message)s",
        datefmt="%H:%M:%S",
    )
    log = logging.getLogger("anki_voice_review")

    if args.list_devices:
        print(list_input_devices())
        return 0

    settings = load_settings(args.config)
    if args.dry_run:
        settings.dry_run = True
    if args.device is not None:
        settings.input_device = args.device

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

    return run(settings)


if __name__ == "__main__":
    sys.exit(main())
