# Anki Puppeteer

Review Anki cards by voice **while another app is focused**. No cloud speech API, and no keystrokes sent to whichever window happens to be in front.

Windows Speech Recognition and Voice Access can hear `show` / `good`. They send those keys to the **focused** window. If you are in a game, editor, or browser, “press 3” hits that app, not Anki. This project talks to Anki over [AnkiConnect](https://foosoft.net/projects/anki-connect/) on `127.0.0.1:8765` instead.

## How it avoids false positives

Open-ended speech-to-text mapped to actions will grade a card when you order a pizza. The pipeline is gated **before** recognition, then checked **after**:

1. **Silero VAD** (ONNX Runtime) — cheap always-on listen on the raw mic stream. Fans, keyboard noise, and hush never reach STT.
2. **Short-burst gate** — keep about 0.25–1.8 seconds of speech, with 300 ms of pad so a word is not clipped. If it keeps going, **abort**, wait for quiet, re-arm. Conversation never calls the recognizer.
3. **Local STT** — [whisper.cpp](https://github.com/ggml-org/whisper.cpp) `tiny.en` by default (open vocabulary). Vosk is a fallback. A command grammar is **not** used; it invented commands.
4. **Exact whitelist** — the whole phrase must be one command. `good job` is not `good`. `sure` is not `show`.
5. **AnkiConnect** — `guiShowAnswer` / `guiAnswerCard` / `guiUndo`. Anki can stay in the background.

Wake-word and push-to-talk are intentionally omitted. The short-burst rule is the first line of defense.

```
mic ──► Silero VAD ──► short-burst gate ──► whisper.cpp tiny.en ──► exact match ──► AnkiConnect
              │                 │
          silence: drop    too long: drop, wait for quiet
```

## Commands

| You say | AnkiConnect action |
| --- | --- |
| `show` | `guiShowAnswer` |
| `again` | `guiAnswerCard` ease 1 |
| `hard` | `guiAnswerCard` ease 2 |
| `good` | `guiAnswerCard` ease 3 |
| `easy` | `guiAnswerCard` ease 4 |
| `undo` | `guiUndo` |

Say `show` before a grade. Anki rejects a grade while the question is still up; the listener logs that and waits.

## Requirements

This repo and the GitHub release are **source only**. Speech models are **not** published (`ggml-*.bin`, Vosk zips, Silero ONNX). They download to `%LOCALAPPDATA%\anki-puppeteer\` (or your existing whisper.cpp folder) on first use.

- Python 3.10+
- Anki 2.1+ with [AnkiConnect](https://ankiweb.net/shared/info/2055492159) (add-on code `2055492159`)
- A microphone
- [whisper.cpp](https://github.com/ggml-org/whisper.cpp) `whisper-cli` on `PATH` or at `%USERPROFILE%\tools\whisper\whisper-cli.exe`
- First run of `--stt tiny` fetches `ggml-tiny.en.bin` (~75 MB) and Silero VAD ONNX

`--stt vosk` downloads the small English Vosk model (~40 MB) instead of whisper.cpp. `--stt large` uses a **local** `whisper-server` + `ggml-large-v3.bin` if you already have them; those files are not in this project.

## Install

```bash
python -m pip install git+https://github.com/HeadlessHoncho/anki-puppeteer.git
```

From a clone:

```bash
python -m pip install -e ".[dev]"
```

Install AnkiConnect, then restart Anki:

```bash
anki-puppeteer --install-ankiconnect
```

Or in Anki: Tools → Add-ons → Get Add-ons → `2055492159`.

## Usage

Start Anki, open a deck, start reviewing. Then:

```bash
anki-puppeteer --stt tiny
```

Useful flags:

```bash
anki-puppeteer --dry-run                 # recognize only; do not call Anki
anki-puppeteer --check                   # ping AnkiConnect
anki-puppeteer --list-devices            # microphone indices
anki-puppeteer --device realtek          # pick a mic by name substring
anki-puppeteer --test-mic                # live level meter
anki-puppeteer --self-test --stt tiny    # Windows TTS samples through the same gate/STT/whitelist
anki-puppeteer --wav show.wav --expect show --stt tiny
anki-puppeteer --stt tiny|large|vosk|auto
anki-puppeteer -c config.toml
```

Copy `config.example.toml` to `config.toml` (or `%LOCALAPPDATA%\anki-puppeteer\config.toml` on Windows) to change burst length, VAD threshold, AnkiConnect URL, or extra spoken aliases.

Gate defaults follow Silero VAD / whisper.cpp: threshold `0.5`, min speech 250 ms, end silence 200 ms, 300 ms speech pad. VAD runs on raw audio; a clip is normalized only after the gate accepts it.

## Libraries (not reinvented)

| Piece | Project | License |
| --- | --- | --- |
| Microphone | [sounddevice](https://python-sounddevice.readthedocs.io/) / PortAudio | MIT |
| Voice activity | [Silero VAD](https://github.com/snakers4/silero-vad) via [ONNX Runtime](https://onnxruntime.ai/) | MIT |
| Speech-to-text | [whisper.cpp](https://github.com/ggml-org/whisper.cpp) `tiny.en` (Vosk fallback) | MIT / Apache-2.0 |
| Anki I/O | [AnkiConnect](https://github.com/FooSoft/anki-connect) | AGPL-3.0 (add-on; this repo only HTTP-calls it) |

The short-burst gate and exact-phrase whitelist are the small amount of original logic.

## Privacy

Audio never leaves the machine. AnkiConnect is called on localhost. Do not bind AnkiConnect to `0.0.0.0` unless you know why you are doing that.

## Development

```bash
python -m pip install -e ".[dev]"
pytest
```

Unit tests cover the gate, whitelist, WAV feed, and AnkiConnect client. They do not need a microphone or Anki.

## License

MIT. Anki, AnkiConnect, whisper.cpp, Vosk, and Silero keep their own licenses.
