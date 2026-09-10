from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Callable, Optional

from anki_puppeteer.config import anki_addons_dir
from anki_puppeteer.models import extract_zip_to_temp

ANKICONNECT_ID = "2055492159"
ANKICONNECT_ZIP = (
    "https://github.com/FooSoft/anki-connect/archive/refs/heads/master.zip"
)

Progress = Optional[Callable[[str], None]]


def install_ankiconnect(progress: Progress = None) -> Path:
    """Install FooSoft/anki-connect into the local Anki add-ons folder."""
    addons = anki_addons_dir()
    addons.mkdir(parents=True, exist_ok=True)
    dest = addons / ANKICONNECT_ID
    tmpdir = extract_zip_to_temp(ANKICONNECT_ZIP, progress)
    try:
        plugin = _find_plugin_dir(tmpdir)
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(plugin, dest)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    meta = dest / "meta.json"
    if not meta.is_file():
        meta.write_text(
            json.dumps(
                {
                    "name": "AnkiConnect",
                    "mod": 0,
                    "disabled": False,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    return dest


def _find_plugin_dir(root: Path) -> Path:
    for candidate in root.rglob("__init__.py"):
        if candidate.parent.name in {"plugin", "AnkiConnect", ANKICONNECT_ID}:
            return candidate.parent
        # FooSoft layout: anki-connect-master/plugin/__init__.py
        if (candidate.parent / "config.md").is_file() or (
            candidate.parent / "config.json"
        ).is_file():
            return candidate.parent
    matches = list(root.rglob("__init__.py"))
    if len(matches) == 1:
        return matches[0].parent
    raise RuntimeError("could not find AnkiConnect plugin directory in the zip")
