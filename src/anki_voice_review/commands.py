from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping, Optional, Sequence

DEFAULT_PHRASES: dict[str, tuple[str, ...]] = {
    "show": ("show",),
    "again": ("again",),
    "hard": ("hard",),
    "good": ("good",),
    "easy": ("easy",),
    "undo": ("undo",),
}

COMMAND_NAMES = tuple(DEFAULT_PHRASES.keys())

_PUNCT = re.compile(r"[^\w\s]+", re.UNICODE)
_SPACE = re.compile(r"\s+")


def normalize(text: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace."""
    text = text.strip().lower().replace("[unk]", "unk")
    text = _PUNCT.sub(" ", text)
    text = _SPACE.sub(" ", text).strip()
    return text


@dataclass(frozen=True)
class Command:
    name: str


class CommandMatcher:
    """Exact whole-phrase matcher. 'good job' is not 'good'."""

    def __init__(self, phrases: Mapping[str, Sequence[str]] | None = None) -> None:
        source = phrases or DEFAULT_PHRASES
        self._lookup: dict[str, str] = {}
        for name, variants in source.items():
            if name not in DEFAULT_PHRASES:
                raise ValueError(f"unknown command {name!r}")
            for variant in variants:
                key = normalize(variant)
                if not key:
                    continue
                self._lookup[key] = name

    def phrases_for_grammar(self) -> list[str]:
        return sorted(self._lookup)

    def match(self, text: str) -> Optional[Command]:
        key = normalize(text)
        if not key or key == "unk":
            return None
        name = self._lookup.get(key)
        if name is None:
            return None
        return Command(name=name)
