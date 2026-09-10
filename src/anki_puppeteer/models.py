from __future__ import annotations

import shutil
import tempfile
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable, Optional

from anki_puppeteer.config import cache_dir

SILERO_URL = (
    "https://github.com/snakers4/silero-vad/raw/master/"
    "src/silero_vad/data/silero_vad.onnx"
)
VOSK_URL = "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip"
VOSK_DIRNAME = "vosk-model-small-en-us-0.15"
WHISPER_TINY_EN_URL = (
    "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-tiny.en.bin"
)

Progress = Optional[Callable[[str], None]]


def _log(progress: Progress, message: str) -> None:
    if progress:
        progress(message)


def _download(url: str, dest: Path, progress: Progress = None) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    _log(progress, f"downloading {url}")
    req = urllib.request.Request(
        url, headers={"User-Agent": "anki-puppeteer/0.9"}
    )
    with urllib.request.urlopen(req, timeout=120) as resp, tmp.open("wb") as out:
        shutil.copyfileobj(resp, out)
    tmp.replace(dest)


def ensure_silero(path: Optional[Path] = None, progress: Progress = None) -> Path:
    dest = path or (cache_dir() / "silero_vad.onnx")
    if dest.is_file() and dest.stat().st_size > 1000:
        return dest
    _download(SILERO_URL, dest, progress)
    return dest


def _vosk_ready(dest: Path) -> bool:
    return (dest / "am" / "final.mdl").is_file() or (dest / "conf" / "model.conf").is_file()


def ensure_vosk(path: Optional[Path] = None, progress: Progress = None) -> Path:
    dest = path or (cache_dir() / VOSK_DIRNAME)
    if _vosk_ready(dest):
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    zip_path = dest.parent / f"{VOSK_DIRNAME}.zip"
    if not zip_path.is_file():
        _download(VOSK_URL, zip_path, progress)
    _log(progress, f"extracting {zip_path.name}")
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(dest.parent)
    extracted = dest.parent / VOSK_DIRNAME
    if extracted.resolve() != dest.resolve() and extracted.is_dir():
        if dest.exists():
            shutil.rmtree(dest)
        extracted.rename(dest)
    if not _vosk_ready(dest):
        raise RuntimeError(f"Vosk model missing expected files in {dest}")
    return dest


def ensure_whisper_tiny_en(path: Optional[Path] = None, progress: Progress = None) -> Path:
    dest = path or (cache_dir() / "ggml-tiny.en.bin")
    if dest.is_file() and dest.stat().st_size > 20_000_000:
        return dest
    _download(WHISPER_TINY_EN_URL, dest, progress)
    return dest


def extract_zip_to_temp(url: str, progress: Progress = None) -> Path:
    """Download a zip and extract it to a new temporary directory."""
    tmpdir = Path(tempfile.mkdtemp(prefix="anki-puppeteer-"))
    zip_path = tmpdir / "download.zip"
    _download(url, zip_path, progress)
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(tmpdir)
    zip_path.unlink(missing_ok=True)
    return tmpdir
