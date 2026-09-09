Working live listener on the analog jack mic.

## What works

- Say `show` / `again` / `hard` / `good` / `easy` / `undo` while another app is focused. AnkiConnect grades the card; no keystrokes to the focused window.
- Silero VAD on **raw** audio (no stream AGC). Gate defaults match whisper.cpp / Silero: threshold 0.5, min speech 250 ms, 300 ms pad.
- STT is whisper.cpp `tiny.en` behind an exact six-word whitelist. Conversation is dropped.
- `--wav` and `--self-test` feed known samples through the same detector as the live loop.

## Requirements

This release is **source only**. It does **not** ship speech-to-text models: no `ggml-tiny.en.bin`, no `ggml-large-v3.bin`, no Vosk zip, no Silero ONNX. GitHub’s source zip/tarball is the Python project only.

You provide (or let first run download) the models on the machine:

- Python 3.10+
- Anki 2.1+ with [AnkiConnect](https://ankiweb.net/shared/info/2055492159) (add-on code `2055492159`)
- A microphone
- [whisper.cpp](https://github.com/ggml-org/whisper.cpp) `whisper-cli` on `PATH` or at `%USERPROFILE%\tools\whisper\whisper-cli.exe`
- First `--stt tiny` run downloads `ggml-tiny.en.bin` (~75 MB) and Silero VAD ONNX into `%LOCALAPPDATA%\anki-voice-review\`

`--stt vosk` downloads the small English Vosk model (~40 MB) instead of using whisper.cpp.
`--stt large` uses a **local** `whisper-server` + `ggml-large-v3.bin` if you already have them; those files are not in this repo or this release.

## Install

```bash
python -m pip install git+https://github.com/HeadlessHoncho/anki-voice-review.git@v0.9.0
anki-voice-review --stt tiny
```
