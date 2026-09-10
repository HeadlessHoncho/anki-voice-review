from pathlib import Path

from anki_puppeteer.config import load_settings


def test_toml_overrides(tmp_path: Path):
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        """
[gate]
max_burst_seconds = 2.5

[anki]
url = "http://127.0.0.1:9999"

[commands]
show = ["show", "show answer"]
""",
        encoding="utf-8",
    )
    settings = load_settings(cfg)
    assert settings.max_burst_seconds == 2.5
    assert settings.anki_url == "http://127.0.0.1:9999"
    assert "show answer" in settings.phrases["show"]
    assert settings.phrases["good"] == ("good",)
