from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Optional

EASE = {"again": 1, "hard": 2, "good": 3, "easy": 4}


class AnkiConnectError(Exception):
    pass


class AnkiClient:
    """Thin JSON client for the AnkiConnect add-on (127.0.0.1:8765)."""

    def __init__(
        self,
        url: str = "http://127.0.0.1:8765",
        api_key: Optional[str] = None,
        timeout: float = 5.0,
    ) -> None:
        self.url = url
        self.api_key = api_key
        self.timeout = timeout

    def invoke(self, action: str, **params: Any) -> Any:
        payload: dict[str, Any] = {"action": action, "version": 6, "params": params}
        if self.api_key:
            payload["key"] = self.api_key
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.url, data=data, headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise AnkiConnectError(
                f"Cannot reach AnkiConnect at {self.url}. "
                "Is Anki running with the AnkiConnect add-on?"
            ) from exc
        if body.get("error"):
            raise AnkiConnectError(str(body["error"]))
        return body.get("result")

    def ping(self) -> Any:
        return self.invoke("version")

    def dispatch(self, command_name: str) -> Any:
        if command_name == "show":
            return self.invoke("guiShowAnswer")
        if command_name == "undo":
            return self.invoke("guiUndo")
        if command_name in EASE:
            return self.invoke("guiAnswerCard", ease=EASE[command_name])
        raise AnkiConnectError(f"unknown command {command_name!r}")
