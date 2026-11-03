"""GitHub connector: the assistant can push files from the chat's folder to the user's repositories.

Safety, by design:
- It is a GitHub App, not a password or a personal token. The user installs it only on the repositories they pick
  and it has one write permission: Contents (files and commits). It can't delete repositories, change settings,
  add people or see repositories it wasn't given.
- Sign-in is GitHub's device flow: Lanterna shows a short code, the user types it on github.com. No password and
  no app secret on the computer; the token is kept in the system vault and renewed on its own.
- Every push is a card: repository, branch, the list of files and the commit message. Nothing is sent before
  Confirm. Files that look like secrets (.env, keys, tokens inside) are never pushed.
- New repositories are created by the user on github.com (Lanterna opens the filled-in page), because the
  permission to create repositories would also allow deleting them.
"""
from __future__ import annotations

import base64
import json
import os
import re
import threading
import time
import webbrowser
from pathlib import Path
from urllib.parse import quote, urlencode

import httpx

from . import sync

# The public ID of the "Lanterna" GitHub App (not a secret: the device flow needs no secret).
CLIENT_ID = os.getenv("LANTERNA_GITHUB_CLIENT_ID", "Iv23lisqUKAubK0btDJn")
APP_SLUG = os.getenv("LANTERNA_GITHUB_APP", "lanterna-assistant")
API, WEB = "https://api.github.com", "https://github.com"
VAULT_TOKEN, VAULT_ACCOUNT = "github-token", "github-account"
COAUTHOR = "Co-Authored-By: Lanterna <mikybuilds@users.noreply.github.com>"

MAX_FILES, MAX_FILE, MAX_TOTAL = 300, 10 * 1024 * 1024, 50 * 1024 * 1024
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", ".idea", ".vs", "build", "dist", ".mypy_cache"}
SECRET_NAMES = re.compile(r"(^\.env(\..*)?$|\.pem$|\.key$|\.p12$|\.pfx$|^id_(rsa|ed25519|ecdsa|dsa)(\.pub)?$|"
                          r"^credentials(\.json)?$|^\.npmrc$|^\.pypirc$|^\.netrc$|secret)", re.I)
SECRET_TEXT = re.compile(r"(-----BEGIN [A-Z ]*PRIVATE KEY-----|\bgh[pousr]_[A-Za-z0-9]{30,}|\bgithub_pat_[A-Za-z0-9_]{40,}|"
                         r"\bgsk_[A-Za-z0-9]{40,}|\bAIza[0-9A-Za-z_-]{35}\b|\bsk-[A-Za-z0-9_-]{30,}|\bGOCSPX-[A-Za-z0-9_-]{20,}|"
                         r"\bxox[abpr]-[A-Za-z0-9-]{20,}|\bAKIA[0-9A-Z]{16}\b)")
REPO = re.compile(r"^[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}$")


class GitHubError(Exception):
    def __init__(self, kind: str, message: str = ""):
        super().__init__(message or kind)
        self.kind = kind                       # auth | missing | refused | other


def configured() -> bool:
    return bool(CLIENT_ID)


def install_url() -> str:
    return f"{WEB}/apps/{APP_SLUG}/installations/new" if APP_SLUG else f"{WEB}/settings/installations"


def looks_secret(name: str, data: bytes) -> bool:
    if SECRET_NAMES.search(name):
        return True
    try:
        return bool(SECRET_TEXT.search(data[:2_000_000].decode("utf-8", "ignore")))
    except Exception:                                   # noqa: BLE001
        return False


# ---------------------------------------------------------------- token (device flow)
def _token_load() -> dict:
    raw = sync._vault_get(VAULT_TOKEN)
    try:
        return json.loads(raw) if raw else {}
    except ValueError:
        return {}


def _token_save(tok: dict) -> None:
    now = time.time()
    data = {"access": tok["access_token"], "refresh": tok.get("refresh_token", ""),
            "exp": now + float(tok["expires_in"]) - 120 if tok.get("expires_in") else 0}
    sync._vault_set(VAULT_TOKEN, json.dumps(data))


class Hub:
    """GitHub REST calls with the user's token (renewed on its own)."""

    def __init__(self, http: httpx.Client | None = None):
        self.http = http or httpx.Client(timeout=60, follow_redirects=True)

    def _token(self) -> str:
        t = _token_load()
        if not t.get("access"):
            raise GitHubError("auth", "GitHub is not connected")
        if t.get("exp") and time.time() > t["exp"]:
            if not t.get("refresh"):
                raise GitHubError("auth", "GitHub sign-in expired")
            r = self.http.post(f"{WEB}/login/oauth/access_token", headers={"Accept": "application/json"},
                               data={"client_id": CLIENT_ID, "grant_type": "refresh_token", "refresh_token": t["refresh"]})
            d = r.json() if r.status_code == 200 else {}
            if not d.get("access_token"):
                raise GitHubError("auth", "GitHub sign-in expired")
            _token_save(d)
            t = _token_load()
        return t["access"]

    def call(self, method: str, path: str, **kw) -> httpx.Response:
        h = {"Authorization": f"Bearer {self._token()}", "Accept": "application/vnd.github+json",
             "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "Lanterna"}
        r = self.http.request(method, path if path.startswith("http") else API + path, headers=h, **kw)
        if r.status_code == 401:
            raise GitHubError("auth", "GitHub sign-in is no longer valid")
        if r.status_code in (403, 404) and "/repos/" in path:
            raise GitHubError("missing", "no access to that repository (is Lanterna installed on it?)")
        if r.status_code >= 400:
            try:
                msg = r.json().get("message", "")
            except ValueError:
                msg = r.text[:200]
            raise GitHubError("refused" if r.status_code in (403, 409, 422) else "other", f"GitHub {r.status_code}: {msg}")
        return r

    # -- reading
    def login(self) -> str:
        return self.call("GET", "/user").json().get("login", "")

    def repos(self) -> list[dict]:
        out = []
        for inst in self.call("GET", "/user/installations").json().get("installations", []):
            page = self.call("GET", f"/user/installations/{inst['id']}/repositories", params={"per_page": 100}).json()
            for r in page.get("repositories", []):
                out.append({"full_name": r["full_name"], "private": r.get("private", False),
                            "branch": r.get("default_branch") or "main", "url": r.get("html_url", "")})
        return out

    def list(self, repo: str, path: str = "", ref: str = "") -> list[dict]:
        r = self.call("GET", f"/repos/{repo}/contents/{quote(path.strip('/'))}", params={"ref": ref} if ref else None).json()
        return r if isinstance(r, list) else [r]

    def read(self, repo: str, path: str, ref: str = "") -> str:
        r = self.call("GET", f"/repos/{repo}/contents/{quote(path.strip('/'))}", params={"ref": ref} if ref else None).json()
        if isinstance(r, list):
            raise GitHubError("refused", f"'{path}' is a folder")
        if r.get("encoding") == "base64":
            return base64.b64decode(r.get("content", "")).decode("utf-8", "replace")
        return r.get("content", "")

    # -- writing: one commit with all the files
    def push(self, repo: str, files: list[tuple[str, bytes]], message: str, branch: str = "") -> dict:
        info = self.call("GET", f"/repos/{repo}").json()
        default = info.get("default_branch") or "main"
        branch = branch or default
        files = list(files)
        head = self._head(repo, branch)
        if head is None and self._head(repo, default) is None:       # an empty repository: the first file starts it
            path, data = files.pop(0)
            r = self.call("PUT", f"/repos/{repo}/contents/{quote(path)}",
                          json={"message": message, "content": base64.b64encode(data).decode(), "branch": branch}).json()
            head = r["commit"]["sha"]
            if not files:
                return {"sha": head, "url": r["commit"].get("html_url", f"{WEB}/{repo}/commit/{head}"), "branch": branch}
        elif head is None:                                            # a new branch from the default one
            base = self._head(repo, default)
            self.call("POST", f"/repos/{repo}/git/refs", json={"ref": f"refs/heads/{branch}", "sha": base})
            head = base
        base_tree = self.call("GET", f"/repos/{repo}/git/commits/{head}").json()["tree"]["sha"]
        tree = []
        for path, data in files:
            blob = self.call("POST", f"/repos/{repo}/git/blobs",
                             json={"content": base64.b64encode(data).decode(), "encoding": "base64"}).json()
            tree.append({"path": path, "mode": "100644", "type": "blob", "sha": blob["sha"]})
        t = self.call("POST", f"/repos/{repo}/git/trees", json={"base_tree": base_tree, "tree": tree}).json()
        c = self.call("POST", f"/repos/{repo}/git/commits", json={"message": message, "tree": t["sha"], "parents": [head]}).json()
        self.call("PATCH", f"/repos/{repo}/git/refs/heads/{quote(branch)}", json={"sha": c["sha"]})
        return {"sha": c["sha"], "url": c.get("html_url") or f"{WEB}/{repo}/commit/{c['sha']}", "branch": branch}

    def _head(self, repo: str, branch: str) -> str | None:
        try:
            return self.call("GET", f"/repos/{repo}/git/ref/heads/{quote(branch)}").json()["object"]["sha"]
        except GitHubError as e:
            if e.kind in ("missing", "refused"):              # no such branch, or an empty repository (409)
                return None
            raise


class Connector:
    """phase: off · waiting (the user types the code on github.com) · ready."""

    def __init__(self, http: httpx.Client | None = None, browser=webbrowser.open):
        self.http, self.browser = http, browser
        self.phase = "ready" if _token_load().get("access") else "off"
        self.account, self.error = sync._vault_get(VAULT_ACCOUNT), ""
        self.code, self.url = "", ""
        self._cancel = threading.Event()

    def hub(self) -> Hub:
        return Hub(self.http)

    def status(self) -> dict:
        return {"phase": self.phase, "account": self.account, "error": self.error, "configured": configured(),
                "code": self.code if self.phase == "waiting" else "", "url": self.url if self.phase == "waiting" else "",
                "install_url": install_url()}

    def start(self) -> dict:
        if not configured():
            self.error = "not_configured"
            return self.status()
        if self.phase != "waiting":
            self.error = ""
            try:
                http = self.http or httpx.Client(timeout=30)
                r = http.post(f"{WEB}/login/device/code", headers={"Accept": "application/json"}, data={"client_id": CLIENT_ID})
                d = r.json()
                self.code, self.url = d["user_code"], d.get("verification_uri") or f"{WEB}/login/device"
            except Exception as e:                       # noqa: BLE001
                self.error = f"GitHub: {e}"[:200]
                return self.status()
            self.phase = "waiting"
            self._cancel.clear()
            threading.Thread(target=self._wait, args=(d["device_code"], int(d.get("interval", 5)),
                                                      float(d.get("expires_in", 900))), daemon=True).start()
            try:
                self.browser(self.url)
            except Exception:                             # noqa: BLE001  the code is on screen anyway
                pass
        return self.status()

    def _wait(self, device_code: str, interval: int, expires: float) -> None:
        http = self.http or httpx.Client(timeout=30)
        end = time.time() + expires
        try:
            while time.time() < end:
                if self._cancel.wait(interval):
                    self.phase = "off"
                    return
                d = http.post(f"{WEB}/login/oauth/access_token", headers={"Accept": "application/json"},
                              data={"client_id": CLIENT_ID, "device_code": device_code,
                                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code"}).json()
                if d.get("access_token"):
                    _token_save(d)
                    self.account = self.hub().login()
                    if self.account:
                        sync._vault_set(VAULT_ACCOUNT, self.account)
                    self.phase = "ready"
                    return
                err = d.get("error")
                if err == "slow_down":
                    interval = int(d.get("interval", interval + 5))
                elif err != "authorization_pending":
                    self.phase, self.error = "off", {"access_denied": "", "expired_token": "expired"}.get(err, err or "failed")
                    return
            self.phase, self.error = "off", "expired"
        except Exception as e:                           # noqa: BLE001  never leave the UI waiting
            self.phase, self.error = "off", str(e)[:200]

    def cancel(self) -> dict:
        self._cancel.set()
        self.phase = "off"
        return self.status()

    def disconnect(self) -> dict:
        """Forgets the token here. (Revoking it on GitHub needs the app secret, which Lanterna doesn't have:
        the user can do it in GitHub → Settings → Applications.)"""
        for k in (VAULT_TOKEN, VAULT_ACCOUNT):
            sync._vault_del(k)
        self.phase, self.account, self.error = "off", "", ""
        return self.status()

    def _auth_lost(self, e: GitHubError) -> None:
        if e.kind == "auth":
            self.disconnect()
            self.error = "signed_out"


# ---------------------------------------------------------------- what the model sees
WAITING = ("Prepared. Nothing has been sent to GitHub yet: the user now sees a card with the repository, the files and "
           "the commit message, and a Confirm button. Tell them in one short sentence what will happen when they "
           "confirm (future tense).")


def collect(ws, paths: list[str], repo_folder: str = "") -> tuple[list[tuple[str, Path]], list[str]]:
    """Files to push: (path in the repository, file on disk), and the skipped ones with the reason."""
    picked, skipped, total = [], [], 0
    prefix = "/".join(x for x in str(repo_folder or "").replace("\\", "/").split("/") if x not in ("", ".", ".."))

    def add(p: Path, rel: str) -> None:
        nonlocal total
        name = p.name
        try:
            size = p.stat().st_size
        except OSError:
            return
        if size > MAX_FILE:
            skipped.append(f"{rel} (bigger than 10 MB)")
            return
        data = p.read_bytes()
        if looks_secret(name, data):
            skipped.append(f"{rel} (looks like a password or key)")
            return
        if len(picked) >= MAX_FILES or total + size > MAX_TOTAL:
            skipped.append(f"{rel} (too many files at once)")
            return
        total += size
        picked.append(((prefix + "/" if prefix else "") + rel, p))

    for raw in paths or ["."]:
        p = ws.path(raw)
        if p.is_file():
            add(p, ws.rel(p))                           # a file keeps its place in the folder
        elif p.is_dir():
            for dirpath, dirs, files in os.walk(p):
                dirs[:] = sorted(x for x in dirs if x not in SKIP_DIRS and not x.startswith("."))
                for name in sorted(files):
                    f = Path(dirpath) / name
                    add(f, f.relative_to(p).as_posix())
        else:
            skipped.append(f"{raw} (not found in the folder)")
    return picked, skipped


def github_tools(conn: Connector, ws, actions, coauthor) -> list:
    """The tools the model sees while GitHub is connected. coauthor: callable -> bool (settings)."""
    from .tools import Tool, _obj
    if conn.phase != "ready":
        return []
    s = {"type": "string"}

    def guard(fn):
        def run(*a, **kw):
            try:
                return fn(*a, **kw)
            except GitHubError as e:
                conn._auth_lost(e)
                return f"Error: {e}"
            except Exception as e:                       # noqa: BLE001
                return f"Error: {e}"
        return run

    def _repo(repo: str) -> str:
        repo = str(repo or "").strip().removeprefix(WEB + "/").removesuffix(".git").strip("/")
        if not REPO.match(repo):
            raise GitHubError("refused", "give the repository as owner/name")
        names = [r["full_name"] for r in conn.hub().repos()]
        exact = next((n for n in names if n.lower() == repo.lower()), None)
        if exact:
            return exact
        raise GitHubError("refused", f"Lanterna has no access to '{repo}'. It can write only to: "
                          + (", ".join(names) or "nothing yet") + ". If the repository is right, the user adds it "
                          "here: " + install_url())

    @guard
    def github_repos() -> str:
        rs = conn.hub().repos()
        if not rs:
            return ("Lanterna isn't installed on any repository yet. Tell the user to choose repositories here: "
                    + install_url())
        return "\n".join(f"{r['full_name']} ({'private' if r['private'] else 'public'}, branch {r['branch']})" for r in rs)

    @guard
    def github_list(repo: str, path: str = "") -> str:
        items = conn.hub().list(_repo(repo), path)
        return "\n".join(("📁 " if i.get("type") == "dir" else "📄 ") + i.get("path", "") for i in items) or "(empty)"

    @guard
    def github_read(repo: str, path: str) -> str:
        text = conn.hub().read(_repo(repo), path)
        return f"File '{path}' in {repo}:\n{text[:12000]}" + ("\n[…cut]" if len(text) > 12000 else "")

    @guard
    def github_push(repo: str, paths: list | None = None, message: str = "", branch: str = "", repo_folder: str = "") -> str:
        repo = _repo(repo)
        if ws.root() is None:
            return "Error: this chat has no working folder. Ask the user to choose one under the message box."
        if isinstance(paths, str):
            paths = [paths]
        files, skipped = collect(ws, [str(x) for x in (paths or ["."])], repo_folder)
        if not files:
            return "Error: nothing to push." + (" Skipped: " + "; ".join(skipped) if skipped else "")
        msg = (str(message or "").strip() or "Update from Lanterna")[:2000]
        with_co = bool(coauthor())
        full = msg + (f"\n\n{COAUTHOR}" if with_co else "")
        branch = str(branch or "").strip()
        root = str(ws.root())
        listing = [(name, str(p.relative_to(ws.root()))) for name, p in files]

        def run() -> str:
            if str(ws.root()) != root:
                raise GitHubError("refused", "the folder of this chat was changed after this card; ask again")
            data = [(name, (ws.root() / local).read_bytes()) for name, local in listing]
            r = conn.hub().push(repo, data, full, branch)
            return f"{repo}@{r['branch']} {r['sha'][:7]}|{r['url']}"

        actions.propose("github_push", {"repo": repo, "branch": branch, "files": [n for n, _ in files][:40],
                                        "count": len(files), "size": sum(p.stat().st_size for _, p in files),
                                        "message": msg, "coauthor": with_co, "skipped": skipped[:20]}, run)
        return WAITING + (" Some files were left out: " + "; ".join(skipped[:10]) if skipped else "")

    @guard
    def github_new_repo(name: str, private: bool = False, description: str = "") -> str:
        name = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(name or "").strip())[:100].strip("-") or "new-project"
        q = urlencode({"name": name, "description": str(description or "")[:300],
                       "visibility": "private" if private else "public"})
        new, inst = f"{WEB}/new?{q}", install_url()

        def run() -> str:
            conn.browser(new)
            return f"{name}|{new}"
        actions.propose("github_new_repo", {"name": name, "private": bool(private), "install": inst}, run)
        return ("Prepared. When the user confirms, GitHub's 'new repository' page opens filled in; they press "
                "'Create repository' there, then add it to Lanterna (a button on the card), and ask again to push. "
                "Tell them this in one or two short sentences.")

    return [
        Tool("github_repos", "List the user's GitHub repositories that Lanterna may write to.", _obj({}), github_repos, "🐙"),
        Tool("github_list", "List files in a folder of a GitHub repository (repo: owner/name, path: '' = top).",
             _obj({"repo": s, "path": s}, ["repo"]), github_list, "🐙"),
        Tool("github_read", "Read a file from a GitHub repository.", _obj({"repo": s, "path": s}, ["repo", "path"]),
             github_read, "🐙"),
        Tool("github_push", "Push files from the chat's working folder to a GitHub repository as one commit (paths: "
             "files or folders inside the working folder, default everything; repo_folder: where to put them in the "
             "repository, default the top; branch: default the main branch). The user confirms it on a card (no need "
             "to ask first). Write the files into the working folder first.",
             _obj({"repo": s, "paths": {"type": "array", "items": s}, "message": s, "branch": s, "repo_folder": s},
                  ["repo", "message"]), github_push, "🐙"),
        Tool("github_new_repo", "Help the user create a new GitHub repository (opens github.com filled in; Lanterna "
             "itself can't create or delete repositories).",
             _obj({"name": s, "private": {"type": "boolean"}, "description": s}, ["name"]), github_new_repo, "🐙"),
    ]
