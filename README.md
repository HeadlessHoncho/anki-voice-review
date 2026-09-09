# anki-voice-review

Review Anki cards by voice **while another app is focused**. No cloud speech API, and no keystrokes sent to whichever window happens to be in front.

Windows Speech Recognition and Voice Access can hear `show` / `good`. They send those keys to the **focused** window. If you are in a game, editor, or browser, “press 3” hits that app, not Anki. This project talks to Anki over [AnkiConnect](https://foosoft.net/projects/anki-connect/) on `127.0.0.1:8765` instead.

## How it avoids false positives

Open-ended speech-to-text mapped to actions will grade a card when you order a pizza. The pipeline is gated **before** recognition, then constrained **during** recognition, then checked **after**:

1. **Silero VAD** (ONNX Runtime) — cheap always-on listen. Fans, keyboard noise, and hush never reach STT.
2. **Short-burst gate** — buffer about 1–2 seconds of speech. If it keeps going, **abort**, wait for quiet, re-arm. Conversation never calls the recognizer.
3. **Vosk grammar STT** — the small English model is told the phrase list (`show`, `again`, `hard`, `good`, `easy`, `undo`, plus `[unk]`). It is a command recognizer, not a dictation engine.
4. **Exact whitelist** — the whole phrase must be one command. `good job` is not `good`.
5. **AnkiConnect** — `guiShowAnswer` / `guiAnswerCard` / `guiUndo`. Anki can stay in the background.

Wake-word and push-to-talk are intentionally omitted for now. The short-burst rule is the first line of defense.

```
mic ──► Silero VAD ──► short-burst gate ──► Vosk (grammar) ──► exact match ──► AnkiConnect
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

- Python 3.10+
- Anki 2.1+ with [AnkiConnect](https://ankiweb.net/shared/info/2055492159) (add-on code `2055492159`)
- A microphone
- First run downloads (~40 MB Vosk small English model + Silero VAD ONNX)

No GPU. This is on purpose: a six-word command set does not need Whisper large-v3.

## Install

```bash
python -m pip install git+https://github.com/HeadlessHoncho/anki-voice-review.git
```

From a clone:

```bash
python -m pip install -e ".[dev]"
```

Install AnkiConnect, then restart Anki:

```bash
anki-voice-review --install-ankiconnect
```

Or in Anki: Tools → Add-ons → Get Add-ons → `2055492159`.

## Usage

Start Anki, open a deck, start reviewing. Then:

```bash
anki-voice-review
```

Useful flags:

```bash
anki-voice-review --dry-run          # recognize only; do not call Anki
anki-voice-review --check            # ping AnkiConnect
anki-voice-review --list-devices     # microphone indices
anki-voice-review --device 2         # pick a mic
anki-voice-review --download-models  # prefetch Silero + Vosk
anki-voice-review -c config.toml
```

Copy `config.example.toml` to `config.toml` (or `%LOCALAPPDATA%\anki-voice-review\config.toml` on Windows) to change burst length, VAD threshold, AnkiConnect URL, or extra spoken aliases.

## Libraries (not reinvented)

| Piece | Project | License |
| --- | --- | --- |
| Microphone | [sounddevice](https://python-sounddevice.readthedocs.io/) / PortAudio | MIT |
| Voice activity | [Silero VAD](https://github.com/snakers4/silero-vad) via [ONNX Runtime](https://onnxruntime.ai/) | MIT |
| Speech-to-text | [Vosk](https://alphacephei.com/vosk/) small `en-us` with a phrase grammar | Apache-2.0 |
| Anki I/O | [AnkiConnect](https://github.com/FooSoft/anki-connect) | AGPL-3.0 (add-on; this repo only HTTP-calls it) |

The short-burst gate and exact-phrase whitelist are the small amount of original logic.

## Privacy

Audio never leaves the machine. AnkiConnect is called on localhost. Do not bind AnkiConnect to `0.0.0.0` unless you know why you are doing that.

## Development

```bash
python -m pip install -e ".[dev]"
pytest
```

Unit tests cover the gate, whitelist, and AnkiConnect client. They do not need a microphone or Anki.

## License

MIT. Anki, AnkiConnect, Vosk, and Silero keep their own licenses.
