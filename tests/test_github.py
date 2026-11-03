"""GitHub connector against a fake GitHub: device sign-in, pushing as one commit, secrets left out."""
import base64
import json
import time

import httpx
import pytest

from lanterna import github, sync
from lanterna.workspace import Actions, Workspace

G = github.WEB


class FakeGitHub:
    def __init__(self, empty=False):
        self.empty = empty
        self.polls = 0
        self.calls = []
        self.blobs, self.commits, self.refs = {}, {}, ({} if empty else {"main": "c0"})
        self.contents = {}
        self.commits["c0"] = {"tree": "t0", "message": "init", "parents": []}

    def __call__(self, req):
        url, m = str(req.url), req.method
        path = req.url.path
        self.calls.append((m, path))
        if url.startswith(G + "/login/device/code"):
            return httpx.Response(200, json={"device_code": "DC", "user_code": "ABCD-1234", "interval": 0,
                                             "expires_in": 900, "verification_uri": G + "/login/device"})
        if url.startswith(G + "/login/oauth/access_token"):
            body = dict(x.split("=", 1) for x in req.content.decode().split("&"))
            assert "client_secret" not in body
            if body["grant_type"] == "refresh_token":
                return httpx.Response(200, json={"access_token": "ghu_new", "refresh_token": "ghr_2", "expires_in": 28800})
            self.polls += 1
            if self.polls < 2:
                return httpx.Response(200, json={"error": "authorization_pending"})
            return httpx.Response(200, json={"access_token": "ghu_1", "refresh_token": "ghr_1", "expires_in": 28800})
        assert req.headers["Authorization"].startswith("Bearer ghu_")
        if path == "/user":
            return httpx.Response(200, json={"login": "anna"})
        if path == "/user/installations":
            return httpx.Response(200, json={"installations": [{"id": 7}]})
        if path == "/user/installations/7/repositories":
            return httpx.Response(200, json={"repositories": [{"full_name": "anna/mod", "private": False, "default_branch": "main"}]})
        if not path.startswith("/repos/anna/mod"):
            return httpx.Response(404, json={"message": "Not Found"})
        rest = path[len("/repos/anna/mod"):]
        d = json.loads(req.content) if req.content else {}
        if rest == "" and m == "GET":
            return httpx.Response(200, json={"default_branch": "main", "size": 0 if self.empty else 1})
        if rest.startswith("/git/ref/heads/") and m == "GET":
            b = rest.rsplit("/", 1)[1]
            if not self.refs:
                return httpx.Response(409, json={"message": "Git Repository is empty."})
            if b not in self.refs:
                return httpx.Response(404, json={"message": "Not Found"})
            return httpx.Response(200, json={"object": {"sha": self.refs[b]}})
        if rest.startswith("/contents/") and m == "PUT":
            name = rest[len("/contents/"):]
            self.contents[name] = base64.b64decode(d["content"])
            self.refs[d["branch"]] = "c1"
            self.commits["c1"] = {"tree": "t1", "message": d["message"], "parents": []}
            return httpx.Response(201, json={"commit": {"sha": "c1", "html_url": G + "/anna/mod/commit/c1"}})
        if rest.startswith("/git/commits/") and m == "GET":
            return httpx.Response(200, json={"tree": {"sha": self.commits[rest.rsplit("/", 1)[1]]["tree"]}})
        if rest == "/git/blobs":
            sha = f"b{len(self.blobs)}"
            self.blobs[sha] = base64.b64decode(d["content"])
            return httpx.Response(201, json={"sha": sha})
        if rest == "/git/trees":
            self.tree = d
            return httpx.Response(201, json={"sha": "t9"})
        if rest == "/git/commits" and m == "POST":
            self.commit = d
            return httpx.Response(201, json={"sha": "c9abcdef", "html_url": G + "/anna/mod/commit/c9abcdef"})
        if rest.startswith("/git/refs/heads/") and m == "PATCH":
            self.refs[rest.rsplit("/", 1)[1]] = d["sha"]
            return httpx.Response(200, json={})
        if rest == "/git/refs" and m == "POST":
            self.refs[d["ref"].rsplit("/", 1)[1]] = d["sha"]
            return httpx.Response(201, json={})
        return httpx.Response(500, json={"message": f"unexpected {m} {rest}"})


@pytest.fixture
def vault(monkeypatch):
    v = {}
    monkeypatch.setattr(sync, "_vault_get", lambda k: v.get(k, ""))
    monkeypatch.setattr(sync, "_vault_set", lambda k, val: v.__setitem__(k, val))
    monkeypatch.setattr(sync, "_vault_del", lambda k: v.pop(k, None))
    monkeypatch.setattr(github, "CLIENT_ID", "Iv23test")
    return v


def _conn(fake, opened=None):
    return github.Connector(http=httpx.Client(transport=httpx.MockTransport(fake)),
                            browser=(opened.append if opened is not None else (lambda u: None)))


def _signed_in(fake, vault):
    c = _conn(fake)
    st = c.start()
    assert c.code == "ABCD-1234" and st["phase"] in ("waiting", "ready")      # the fake answers at once
    for _ in range(200):
        if c.phase != "waiting":
            break
        time.sleep(0.01)
    assert c.phase == "ready" and c.account == "anna"
    return c


def test_device_sign_in_needs_no_secret_and_keeps_the_token_in_the_vault(vault):
    c = _signed_in(FakeGitHub(), vault)
    tok = json.loads(vault[github.VAULT_TOKEN])
    assert tok["access"] == "ghu_1" and tok["refresh"] == "ghr_1" and vault[github.VAULT_ACCOUNT] == "anna"
    tok["exp"] = time.time() - 1                                # expired: renewed with the refresh token
    vault[github.VAULT_TOKEN] = json.dumps(tok)
    assert c.hub().login() == "anna" and json.loads(vault[github.VAULT_TOKEN])["access"] == "ghu_new"
    c.disconnect()
    assert github.VAULT_TOKEN not in vault and c.phase == "off"


def test_not_set_up(monkeypatch, vault):
    monkeypatch.setattr(github, "CLIENT_ID", "")
    st = _conn(FakeGitHub()).start()
    assert st["error"] == "not_configured" and not st["configured"]


def _ws(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path.anchor) + "no-such-appdata")
    work = tmp_path / "work"
    (work / "src").mkdir(parents=True)
    (work / "src" / "mod.wh.cpp").write_text("// ==WindhawkMod==\nint x;\n", encoding="utf-8")
    (work / "README.md").write_text("# mod\n", encoding="utf-8")
    (work / ".env").write_text("KEY=1\n", encoding="utf-8")
    (work / "notes.txt").write_text("my key gsk_" + "a" * 50 + "\n", encoding="utf-8")
    (work / ".git").mkdir()
    (work / ".git" / "config").write_text("x", encoding="utf-8")
    acts = Actions()
    cards = []
    acts.bind(cards, 1)
    return Workspace(lambda: str(work), acts), acts, cards


def test_push_is_one_commit_after_confirm_and_secrets_stay_home(tmp_path, monkeypatch, vault):
    fake = FakeGitHub()
    c = _signed_in(fake, vault)
    ws, acts, cards = _ws(tmp_path, monkeypatch)
    tools = {t.name: t for t in github.github_tools(c, ws, acts)}
    assert "anna/mod" in tools["github_repos"].run()
    out = tools["github_push"].run(repo=G + "/anna/mod.git", message="Add the mod")
    assert out.startswith("Prepared") and not fake.blobs                       # nothing sent before Confirm
    card = cards[-1]
    assert card["kind"] == "github_push" and card["details"]["count"] == 2
    assert sorted(card["details"]["files"]) == ["README.md", "src/mod.wh.cpp"]
    assert any(".env" in x for x in card["details"]["skipped"]) and any("notes.txt" in x for x in card["details"]["skipped"])
    a = acts.confirm(card["id"])
    assert a.state == "done", a.result
    assert a.result.endswith("|" + G + "/anna/mod/commit/c9abcdef")
    assert fake.commit["parents"] == ["c0"] and fake.commit["message"].endswith(github.COAUTHOR)
    assert {x["path"] for x in fake.tree["tree"]} == {"README.md", "src/mod.wh.cpp"} and fake.tree["base_tree"] == "t0"
    assert fake.refs["main"] == "c9abcdef"
    assert all(b"gsk_" not in b and b"KEY=" not in b for b in fake.blobs.values())


def test_push_into_an_empty_repository_and_a_subfolder(tmp_path, monkeypatch, vault):
    fake = FakeGitHub(empty=True)
    c = _signed_in(fake, vault)
    ws, acts, cards = _ws(tmp_path, monkeypatch)
    tools = {t.name: t for t in github.github_tools(c, ws, acts)}
    tools["github_push"].run(repo="anna/mod", paths=["src", "README.md"], message="First", repo_folder="mods/")
    a = acts.confirm(cards[-1]["id"])
    assert a.state == "done", a.result
    first = next(iter(fake.contents))
    assert first.startswith("mods/") and fake.commit["message"].endswith(github.COAUTHOR)
    assert {x["path"] for x in fake.tree["tree"]} | {first} == {"mods/mod.wh.cpp", "mods/README.md"}


def test_push_needs_a_folder_and_a_real_repo_name(tmp_path, monkeypatch, vault):
    fake = FakeGitHub()
    c = _signed_in(fake, vault)
    acts = Actions()
    tools = {t.name: t for t in github.github_tools(c, Workspace(lambda: "", acts), acts)}
    assert "no working folder" in tools["github_push"].run(repo="anna/mod", message="x")
    assert "owner/name" in tools["github_push"].run(repo="not a repo", message="x")


def test_new_repository_opens_github_filled_in(tmp_path, monkeypatch, vault):
    opened = []
    c = _conn(FakeGitHub(), opened)
    c.phase = "ready"
    ws, acts, cards = _ws(tmp_path, monkeypatch)
    tools = {t.name: t for t in github.github_tools(c, ws, acts)}
    tools["github_new_repo"].run(name="My Windhawk mod", private=True)
    assert cards[-1]["details"]["name"] == "My-Windhawk-mod" and not opened
    acts.confirm(cards[-1]["id"])
    assert opened == [G + "/new?name=My-Windhawk-mod&description=&visibility=private"]


def test_secret_check():
    assert github.looks_secret("id_rsa", b"")
    assert github.looks_secret("config.py", b"TOKEN = 'ghp_" + b"x" * 36 + b"'")
    assert github.looks_secret("a.txt", b"-----BEGIN OPENSSH " + b"PRIVATE KEY-----")
    assert not github.looks_secret("mod.wh.cpp", b"// a normal file with sk- in a comment")
