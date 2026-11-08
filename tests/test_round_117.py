"""Round 117: `lanterna ask`: one answer for scripts and pipes (git diff | lanterna ask "...")."""
import io
import json

import httpx

from lanterna import cli, keys
from lanterna.config import Settings
from lanterna.discovery import Candidate
from lanterna.providers import PROVIDERS, Client
from lanterna.router import Router


class _Pipe(io.TextIOWrapper):
    def isatty(self):
        return False


class _Tty(io.StringIO):
    def isatty(self):
        return True


def _setup(monkeypatch, tmp_path, reply="Fix typo in README", status=200):
    monkeypatch.setenv("LANTERNA_HOME", str(tmp_path))
    monkeypatch.setattr(keys, "get_key", lambda n: None)
    bodies = []

    def h(req):
        bodies.append(json.loads(req.content))
        if status != 200:
            return httpx.Response(status, json={"error": {"message": "slow down"}})
        return httpx.Response(200, content=("data: " + json.dumps({"choices": [{"delta": {"content": reply}}]})
                                            + "\n\ndata: [DONE]\n\n").encode())
    monkeypatch.setattr(cli, "get_models", lambda *a, **k: [Candidate("groq", "g1", 90)])
    real = Router

    def router(cands):
        return real(cands, client_for=lambda pid: Client(PROVIDERS[pid], "k", transport=httpx.MockTransport(h)),
                    sleep=lambda s: None)
    monkeypatch.setattr(cli, "Router", router)
    return bodies


def _run(question, piped=b"", **kw):
    out, err = io.StringIO(), io.StringIO()
    stdin = _Pipe(io.BytesIO(piped), encoding="utf-8") if piped is not None else _Tty()
    s = Settings()
    s.lang = "en"
    code = cli.ask_cmd(s, question, stdin=stdin, out=out, err=err, **kw)
    return code, out.getvalue(), err.getvalue()


def test_pipe_goes_with_the_question(monkeypatch, tmp_path):
    bodies = _setup(monkeypatch, tmp_path)
    diff = "diff --git a/README.md b/README.md\n-Lantrena\n+Lanterna\n".encode()
    code, out, err = _run("write a commit message", diff)
    assert (code, out, err) == (0, "Fix typo in README\n", "")
    user = bodies[0]["messages"][-1]["content"]
    assert "write a commit message" in user and "+Lanterna" in user and "input.txt" in user
    system = bodies[0]["messages"][0]["content"]
    assert "remember" not in {t["function"]["name"] for t in bodies[0].get("tools", [])}
    assert "web_search" in {t["function"]["name"] for t in bodies[0].get("tools", [])}
    assert system                                                     # memory isn't sent (no facts store)


def test_no_tools_role_and_save(monkeypatch, tmp_path):
    bodies = _setup(monkeypatch, tmp_path, reply="Ciao")
    code, out, _ = _run("hello", None, lookups=False, role="translator", save=True)
    assert code == 0 and out.strip() == "Ciao"
    assert "tools" not in bodies[0]
    assert "translat" in bodies[0]["messages"][0]["content"].lower()
    from lanterna.store import Store
    st = Store()
    th = st.threads()
    assert len(th) == 1 and [m["content"] for m in st.messages(th[0]["id"])] == ["hello", "Ciao"]
    st.close()


def test_nothing_saved_by_default(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path)
    _run("hi", b"")
    from lanterna.store import Store
    st = Store()
    assert st.threads() == []
    st.close()


def test_nothing_to_ask_and_failures(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path)
    code, out, err = _run("", b"  \n")
    assert code == 2 and out == "" and "Nothing to ask" in err
    monkeypatch.setattr(cli, "get_models", lambda *a, **k: [])
    code, out, err = _run("hi", None)
    assert code == 1 and out == "" and "No key" in err
    _setup(monkeypatch, tmp_path, status=429)
    code, out, err = _run("hi", None)
    assert code == 3 and out == "" and err.strip()


def test_pdf_by_first_bytes_and_parser(monkeypatch, tmp_path):
    assert cli._stdin_file(b"%PDF-1.7 ...")["name"] == "input.pdf"
    assert cli._stdin_file(b"plain")["name"] == "input.txt"
    seen = {}
    monkeypatch.setattr(cli, "ask_cmd", lambda s, q, f, **k: seen.update(q=q, f=f, **k) or 0)
    monkeypatch.setattr(cli.Settings, "load", classmethod(lambda c: Settings()))
    assert cli.main(["ask", "why", "blue?", "-f", "a.txt", "--role", "tutor", "--no-tools"]) == 0
    assert seen == {"q": "why blue?", "f": ["a.txt"], "save": False, "role": "tutor", "lookups": False}
