"""Round 103: a stuck online model is left after a short wait, and a slow but working answer is not cut off."""
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from lanterna import providers, router
from lanterna.discovery import Candidate
from lanterna.providers import Client, Provider, ProviderError


class _Slow(BaseHTTPRequestHandler):
    """Model "stuck": headers only after 3 s. Model "slow": starts at once, then 1 s between pieces. Others: at once."""

    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if body["model"] == "stuck":
            time.sleep(3)
        try:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            for i, word in enumerate(("Hi", " there", "!")):
                if body["model"] == "slow" and i:
                    time.sleep(1)
                self.wfile.write(f"data: {json.dumps({'choices': [{'delta': {'content': word}}]})}\n\n".encode())
                self.wfile.flush()
            self.wfile.write(b"data: [DONE]\n\n")
        except OSError:                                     # the client gave up waiting
            pass


@pytest.fixture()
def server():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Slow)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}/v1"
    srv.shutdown()
    srv.server_close()


def _text(client, model):
    return "".join(p for p in client.stream_chat(model, [{"role": "user", "content": "hi"}]) if isinstance(p, str))


def test_stuck_online_model_is_left_quickly(server, monkeypatch):
    monkeypatch.setattr(providers, "FIRST_WAIT", 0.5)
    c = Client(Provider("t", "Test", server, needs_key=False), timeout=10)
    t0 = time.monotonic()
    with pytest.raises(ProviderError) as e:
        _text(c, "stuck")
    assert e.value.kind == "timeout" and time.monotonic() - t0 < 2.5
    c.close()


def test_slow_pieces_after_the_start_are_not_cut(server, monkeypatch):
    monkeypatch.setattr(providers, "FIRST_WAIT", 0.5)               # shorter than the 1 s between pieces
    c = Client(Provider("t", "Test", server, needs_key=False), timeout=10)
    assert _text(c, "slow") == "Hi there!"
    c.close()


def test_local_models_keep_the_long_wait(server, monkeypatch):
    monkeypatch.setattr(providers, "FIRST_WAIT", 0.5)               # loading a local model takes a while: no short wait
    c = Client(Provider("t", "Test", server, needs_key=False, local=True), timeout=10)
    assert _text(c, "stuck") == "Hi there!"
    c.close()


def test_router_moves_on_and_rests_the_stuck_model_for_an_hour(server, monkeypatch):
    monkeypatch.setattr(providers, "FIRST_WAIT", 0.5)
    p = Provider("t", "Test", server, needs_key=False)
    monkeypatch.setitem(providers.PROVIDERS, "t", p)
    monkeypatch.setitem(router.PROVIDERS, "t", p)
    cands = [Candidate("t", "stuck", 90), Candidate("t", "fast", 80)]
    r = router.Router(cands, client_for=lambda pid: Client(p, timeout=10))
    out = list(r.stream([{"role": "user", "content": "hi"}]))
    assert "".join(x for x in out if isinstance(x, str)) == "Hi there!"
    sw = [x for x in out if isinstance(x, router.Switched)]
    assert sw and sw[0].to.model == "fast" and sw[0].reason == "timeout"
    assert 3500 < r.resting()["t/stuck"] <= 3600
    assert [c.model for c in r.available()] == ["fast"]
    r.close()
