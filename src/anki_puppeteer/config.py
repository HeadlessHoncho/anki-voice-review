from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from anki_puppeteer.commands import DEFAULT_PHRASES
from anki_puppeteer.gate import GateConfig

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib


_APP_DIR = "anki-puppeteer"
_LEGACY_DIR = "anki-voice-review"


def default_config_path() -> Path:
    local = Path("config.toml")
    if local.is_file():
        return local
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
        new = base / _APP_DIR / "config.toml"
        old = base / _LEGACY_DIR / "config.toml"
        if old.is_file() and not new.is_file():
            return old
        return new
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    new = base / _APP_DIR / "config.toml"
    old = base / _LEGACY_DIR / "config.toml"
    if old.is_file() and not new.is_file():
        return old
    return new


def cache_dir() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
    else:
        xdg = os.environ.get("XDG_CACHE_HOME")
        base = Path(xdg) if xdg else Path.home() / ".cache"
    new = base / _APP_DIR
    old = base / _LEGACY_DIR
    if old.is_dir() and not new.exists():
        return old
    return new


def anki_addons_dir() -> Path:
    if os.name == "nt":
        appdata = Path(os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming")))
        return appdata / "Anki2" / "addons21"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Anki2" / "addons21"
    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg:
        return Path(xdg) / "Anki2" / "addons21"
    return Path.home() / ".local" / "share" / "Anki2" / "addons21"


@dataclass
class Settings:
    sample_rate: int = 16000
    frame_samples: int = 512
    input_device: Optional[int | str] = None
    min_burst_seconds: float = 0.25
    max_burst_seconds: float = 1.8
    end_silence_seconds: float = 0.20
    rearm_silence_seconds: float = 0.50
    speech_pad_seconds: float = 0.30
    vad_threshold: float = 0.4
    anki_url: str = "http://127.0.0.1:8765"
    anki_key: Optional[str] = None
    phrases: dict[str, tuple[str, ...]] = field(
        default_factory=lambda: {k: tuple(v) for k, v in DEFAULT_PHRASES.items()}
    )
    dry_run: bool = False
    silero_path: Optional[Path] = None
    vosk_path: Optional[Path] = None

    def gate_config(self) -> GateConfig:
        return GateConfig(
            sample_rate=self.sample_rate,
            min_burst_seconds=self.min_burst_seconds,
            max_burst_seconds=self.max_burst_seconds,
            end_silence_seconds=self.end_silence_seconds,
            rearm_silence_seconds=self.rearm_silence_seconds,
            speech_pad_seconds=self.speech_pad_seconds,
        )


def _as_optional_device(value: Any) -> Optional[int | str]:
    if value is None or value == "":
        return None
    if isinstance(value, int):
        return value
    text = str(value)
    if text.isdigit():
        return int(text)
    return text


def load_settings(path: Optional[Path] = None) -> Settings:
    settings = Settings()
    cfg_path = path or default_config_path()
    if cfg_path.is_file():
        with cfg_path.open("rb") as fh:
            data = tomllib.load(fh)
        _apply_toml(settings, data)
    env_key = os.environ.get("ANKI_CONNECT_KEY")
    if env_key:
        settings.anki_key = env_key
    env_url = os.environ.get("ANKI_CONNECT_URL")
    if env_url:
        settings.anki_url = env_url
    return settings


def _apply_toml(settings: Settings, data: dict[str, Any]) -> None:
    audio = data.get("audio") or {}
    if "sample_rate" in audio:
        settings.sample_rate = int(audio["sample_rate"])
    if "device" in audio:
        settings.input_device = _as_optional_device(audio["device"])

    gate = data.get("gate") or {}
    for name in (
        "min_burst_seconds",
        "max_burst_seconds",
        "end_silence_seconds",
        "rearm_silence_seconds",
        "speech_pad_seconds",
    ):
        if name in gate:
            setattr(settings, name, float(gate[name]))

    vad = data.get("vad") or {}
    if "threshold" in vad:
        settings.vad_threshold = float(vad["threshold"])

    anki = data.get("anki") or {}
    if "url" in anki:
        settings.anki_url = str(anki["url"])
    if anki.get("key"):
        settings.anki_key = str(anki["key"])

    models = data.get("models") or {}
    if models.get("silero"):
        settings.silero_path = Path(models["silero"])
    if models.get("vosk"):
        settings.vosk_path = Path(models["vosk"])

    commands = data.get("commands")
    if commands:
        phrases: dict[str, tuple[str, ...]] = {
            k: tuple(v) for k, v in DEFAULT_PHRASES.items()
        }
        for name, variants in commands.items():
            if isinstance(variants, str):
                phrases[name] = (variants,)
            else:
                phrases[name] = tuple(str(v) for v in variants)
        settings.phrases = phrases
