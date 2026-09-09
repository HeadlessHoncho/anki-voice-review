Working live listener on the analog jack mic.

## What works

- Say `show` / `again` / `hard` / `good` / `easy` / `undo` while another app is focused. AnkiConnect grades the card; no keystrokes to the focused window.
- Silero VAD on **raw** audio (no stream AGC). Gate defaults match whisper.cpp / Silero: threshold 0.5, min speech 250 ms, 300 ms pad.
- STT is whisper.cpp `tiny.en` behind an exact six-word whitelist. Conversation is dropped.
- `--wav` and `--self-test` feed known samples through the same detector as the live loop.

## Install

```bash
python -m pip install git+https://github.com/HeadlessHoncho/anki-voice-review.git@v0.9.0
anki-voice-review --stt tiny
```

## Notes

- Put `whisper-cli` on PATH or at `%USERPROFILE%\\tools\\whisper\\whisper-cli.exe`.
- `--stt vosk` is a fallback. `--stt large` uses a local whisper-server + ggml-large-v3 if you already have them.
