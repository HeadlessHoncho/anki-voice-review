"""Add 1-3 basic vocab words under furigana on JLPT Kanji cards."""
from __future__ import annotations

import json
import re
import time
import urllib.request
from collections import defaultdict

ANKI = "http://127.0.0.1:8765"
KANJI_MODEL = "JLPT Kanji"
SEP = "\x1f"
KANJI_RE = re.compile(r"[\u4e00-\u9fff]")
DAY_COUNTER = re.compile(r"^[一二三四五六七八九十]+日$")
LEVEL_RANK = {"N5": 0, "N4": 1, "N3": 2, "N2": 3, "N1": 4}


def anki(action: str, **params):
    payload = json.dumps({"action": action, "version": 6, "params": params}).encode()
    req = urllib.request.Request(ANKI, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        out = json.loads(resp.read().decode())
    if out.get("error"):
        raise RuntimeError(f"{action}: {out['error']}")
    return out["result"]


def kata_to_hira(text: str) -> str:
    out = []
    for ch in text:
        o = ord(ch)
        if 0x30A1 <= o <= 0x30F6:
            out.append(chr(o - 0x60))
        else:
            out.append(ch)
    return "".join(out)


def first_reading(kun: str, on: str) -> str:
    for raw in (kun or "").replace("、", ",").split(","):
        piece = raw.strip().lstrip("-").rstrip("-")
        piece = piece.replace(".", "").replace("-", "")
        if piece:
            return piece
    for raw in (on or "").replace("、", ",").split(","):
        piece = kata_to_hira(raw.strip())
        if piece:
            return piece
    return ""


def vocab_score(kanji: str, level: str, word: str) -> tuple:
    rank = LEVEL_RANK.get(level, 9)
    penalty = 0
    if word == kanji:
        penalty += 8
    if DAY_COUNTER.match(word):
        penalty += 25
    if len(word) >= 5:
        penalty += 4
    return (rank, penalty, len(word), word)


def pick_vocab(kanji: str, items: list[tuple[str, str, str]]) -> str:
    # items: (level, word, reading)
    seen = set()
    ranked = sorted(items, key=lambda it: vocab_score(kanji, it[0], it[1]))
    chosen = []
    for level, word, reading in ranked:
        if word in seen:
            continue
        seen.add(word)
        if reading:
            chosen.append(f"{word}[{reading}]")
        else:
            chosen.append(word)
        if len(chosen) == 3:
            break
    return " · ".join(chosen)


def notes_info(ids: list[int], chunk: int = 250) -> list[dict]:
    out = []
    for i in range(0, len(ids), chunk):
        out.extend(anki("notesInfo", notes=ids[i : i + chunk]))
        print(f"  loaded {min(i + chunk, len(ids))}/{len(ids)}")
    return out


def load_from_anki() -> tuple[list[tuple[int, str, str, str]], dict[str, list]]:
    print("loading JLPT Kanji notes")
    kanji_ids = anki("findNotes", query='note:"JLPT Kanji"')
    vocab_ids = anki("findNotes", query='note:"JLPT Vocab"')
    notes = []
    for n in notes_info(kanji_ids):
        f = n["fields"]
        notes.append(
            (
                n["noteId"],
                f["Character"]["value"],
                f["Onyomi"]["value"],
                f["Kunyomi"]["value"],
            )
        )
    print("loading JLPT Vocab notes")
    by_k: dict[str, list] = defaultdict(list)
    for n in notes_info(vocab_ids):
        f = n["fields"]
        word = f["Word"]["value"]
        reading = f["Reading"]["value"]
        level = f["Level"]["value"]
        for ch in set(KANJI_RE.findall(word)):
            by_k[ch].append((level, word, reading))
    return notes, by_k


CSS = """
.card { font-family: "Noto Sans JP", "Yu Gothic", "Meiryo", sans-serif; text-align: center; background: #111; color: #eee; }
.kanji { font-size: 96px; line-height: 1.35; margin: 24px 0 6px; }
.kanji rt { font-size: 22px; color: #9bd; }
.vocab { font-size: 22px; margin: 2px 0 18px; color: #ddd; }
.vocab ruby { margin: 0 0.5em; }
.vocab rt { font-size: 12px; color: #8ac; }
.mean { font-size: 28px; margin: 12px 0; }
.mean.q { font-size: 32px; margin-top: 40px; }
.lvl { color: #888; font-size: 16px; }
.row { font-size: 22px; margin: 8px 0; }
.k { color: #7ab; font-size: 14px; margin-right: 8px; text-transform: uppercase; }
.meta { color: #666; font-size: 14px; margin-top: 16px; }
"""

RECOG_FRONT = """<div class="kanji"><ruby>{{Character}}<rt>{{Furigana}}</rt></ruby></div>
{{#Vocab}}<div class="vocab">{{furigana:Vocab}}</div>{{/Vocab}}
<div class="lvl">{{Level}}</div>"""

RECOG_BACK = """{{FrontSide}}
<hr>
<div class="mean">{{Meanings}}</div>
<div class="row"><span class="k">On</span> {{Onyomi}}</div>
<div class="row"><span class="k">Kun</span> {{Kunyomi}}</div>
<div class="meta">{{Strokes}} strokes · grade {{Grade}} · freq {{Freq}}</div>"""

RECALL_FRONT = """<div class="mean q">{{Meanings}}</div><div class="lvl">{{Level}} · which kanji?</div>"""

RECALL_BACK = """{{FrontSide}}
<hr>
<div class="kanji"><ruby>{{Character}}<rt>{{Furigana}}</rt></ruby></div>
{{#Vocab}}<div class="vocab">{{furigana:Vocab}}</div>{{/Vocab}}
<div class="row"><span class="k">On</span> {{Onyomi}}</div>
<div class="row"><span class="k">Kun</span> {{Kunyomi}}</div>"""


def main() -> None:
    anki("version")
    notes, by_k = load_from_anki()
    fields = anki("modelFieldNames", modelName=KANJI_MODEL)
    for name in ("Furigana", "Vocab"):
        if name not in fields:
            print("adding field", name)
            anki("modelFieldAdd", modelName=KANJI_MODEL, fieldName=name)
    anki(
        "updateModelStyling",
        model={"name": KANJI_MODEL, "css": CSS},
    )
    anki(
        "updateModelTemplates",
        model={
            "name": KANJI_MODEL,
            "templates": {
                "Recognition": {"Front": RECOG_FRONT, "Back": RECOG_BACK},
                "Recall": {"Front": RECALL_FRONT, "Back": RECALL_BACK},
            },
        },
    )
    filled = 0
    empty = 0
    for i, (nid, ch, on, kun) in enumerate(notes, 1):
        furi = first_reading(kun, on)
        vocab = pick_vocab(ch, by_k.get(ch, []))
        if vocab:
            filled += 1
        else:
            empty += 1
        anki(
            "updateNoteFields",
            note={"id": nid, "fields": {"Furigana": furi, "Vocab": vocab}},
        )
        if i % 100 == 0:
            print(f"updated {i}/{len(notes)}")
    print(f"done. {filled} with vocab, {empty} without, {len(notes)} kanji")


if __name__ == "__main__":
    t0 = time.time()
    main()
    print(f"elapsed {time.time() - t0:.1f}s")
