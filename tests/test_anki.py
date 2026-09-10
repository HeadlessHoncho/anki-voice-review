import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest

from anki_puppeteer.anki import AnkiClient, AnkiConnectError


class _Handler(BaseHTTPRequestHandler):
    store: dict = {}

    def log_message(self, format, *args):  # noqa: A003
        return

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        _Handler.store["last"] = payload
        action = payload.get("action")
        if action == "version":
            result = 6
        elif action == "guiShowAnswer":
            result = True
        elif action == "guiAnswerCard":
            result = payload.get("params", {}).get("ease") == 3
        elif action == "guiUndo":
            result = True
        elif action == "fail":
            self._send({"result": None, "error": "boom"})
            return
        else:
            result = None
        self._send({"result": result, "error": None})

    def _send(self, body):
        data = json.dumps(body).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


@pytest.fixture()
def anki_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    yield f"http://{host}:{port}"
    server.shutdown()


def test_ping_and_dispatch(anki_server):
    client = AnkiClient(url=anki_server)
    assert client.ping() == 6
    assert client.dispatch("show") is True
    assert _Handler.store["last"]["action"] == "guiShowAnswer"
    assert client.dispatch("good") is True
    assert _Handler.store["last"]["params"]["ease"] == 3
    assert client.dispatch("undo") is True


def test_unreachable():
    client = AnkiClient(url="http://127.0.0.1:1", timeout=0.2)
    with pytest.raises(AnkiConnectError):
        client.ping()


def test_unknown_command(anki_server):
    client = AnkiClient(url=anki_server)
    with pytest.raises(AnkiConnectError):
        client.dispatch("pizza")
