"""Signing in to a connector through the browser, the way MCP servers ask for it (OAuth 2.1).

The service shows its own sign-in page in the user's browser; Lanterna never sees the password. It works with
services that let an app register itself (most connectors made by the services themselves do):
1. the server answers 401 and says where its sign-in lives (RFC 9728, RFC 8414),
2. Lanterna registers itself there (RFC 7591) with a one-time address on this computer (127.0.0.1),
3. the browser comes back to that address with a one-time code (PKCE, RFC 7636),
4. the code becomes tokens, kept only in the system's secure vault (keys.set_long), renewed on their own.
"""
from __future__ import annotations

import base64
import hashlib
import http.server
import json
import os
import re
import secrets
import threading
import time
import urllib.parse

import httpx

from . import __version__, keys, quiet

SIGN_IN_TIMEOUT = 300
_UA = {"User-Agent": f"Lanterna/{__version__}"}
_INIT = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "Lanterna", "version": __version__}}}


class AuthError(Exception):
    """kind: cancelled · unsupported (no self-registration) · network · denied · other"""

    def __init__(self, kind: str, message: str = ""):
        super().__init__(message or kind)
        self.kind = kind


def _vault(sid: str) -> str:
    return f"mcp-oauth-{sid}"


def load(sid: str) -> dict:
    try:
        d = json.loads(keys.get_long(_vault(sid)) or "{}")
    except ValueError:
        d = {}
    return d if isinstance(d, dict) else {}


def store(sid: str, tok: dict) -> None:
    keys.set_long(_vault(sid), json.dumps(tok))


def forget(sid: str) -> None:
    keys.delete_long(_vault(sid))


# ---------------------------------------------------------------- where the sign-in lives
def _json(client: httpx.Client, url: str) -> dict | None:
    try:
        r = client.get(url, headers={"Accept": "application/json", **_UA})
        d = r.json() if r.status_code == 200 else None
    except (httpx.HTTPError, ValueError):
        return None
    return d if isinstance(d, dict) else None


def _https(url: str) -> bool:
    u = urllib.parse.urlsplit(url or "")
    return u.scheme == "https" or (u.scheme == "http" and u.hostname in ("localhost", "127.0.0.1"))


def probe(url: str, client: httpx.Client) -> dict:
    """What a web MCP server needs: {"kind": "open" | "oauth" | "token" | "down", "meta": {...}, "error": ""}.
    open: answers without signing in; oauth: browser sign-in works here; token: it wants a key the user pastes."""
    try:
        r = client.post(url, json=_INIT, headers={"Content-Type": "application/json",
                                                   "Accept": "application/json, text/event-stream", **_UA})
    except httpx.HTTPError as e:
        return {"kind": "down", "error": e.__class__.__name__}
    if r.status_code == 200:
        return {"kind": "open"}
    if r.status_code not in (401, 403):
        return {"kind": "down", "error": f"HTTP {r.status_code}"}
    try:
        return {"kind": "oauth", "meta": discover(url, client, r.headers.get("www-authenticate", ""))}
    except AuthError as e:
        return {"kind": "token", "error": str(e)}


def discover(url: str, client: httpx.Client, www_auth: str = "") -> dict:
    """The sign-in details of an MCP server, or AuthError("unsupported") when an app can't register itself."""
    u = urllib.parse.urlsplit(url)
    m = re.search(r'resource_metadata="([^"]+)"', www_auth or "")
    prm = _json(client, m.group(1)) if m and _https(m.group(1)) else None
    path = u.path.rstrip("/")
    for cand in ([f"{u.scheme}://{u.netloc}/.well-known/oauth-protected-resource{path}"] if path else []) + \
            [f"{u.scheme}://{u.netloc}/.well-known/oauth-protected-resource"]:
        if prm:
            break
        prm = _json(client, cand)
    prm = prm or {}
    issuers = [i for i in prm.get("authorization_servers") or [] if isinstance(i, str) and _https(i)] or \
        [f"{u.scheme}://{u.netloc}"]
    meta = None
    for iss in issuers:
        iu = urllib.parse.urlsplit(iss)
        ip = iu.path.rstrip("/")
        for w in dict.fromkeys([f"{iu.scheme}://{iu.netloc}/.well-known/oauth-authorization-server{ip}",
                                f"{iu.scheme}://{iu.netloc}/.well-known/openid-configuration{ip}",
                                f"{iss.rstrip('/')}/.well-known/openid-configuration",
                                f"{iu.scheme}://{iu.netloc}/.well-known/oauth-authorization-server"]):
            meta = _json(client, w)
            if meta and meta.get("authorization_endpoint") and meta.get("token_endpoint"):
                break
            meta = None
        if meta:
            break
    if not meta:
        raise AuthError("unsupported", "this server doesn't say how to sign in")
    if not meta.get("registration_endpoint"):
        raise AuthError("unsupported", "this service only lets apps it approved sign in")
    for k in ("authorization_endpoint", "token_endpoint", "registration_endpoint"):
        if not _https(str(meta[k])):
            raise AuthError("unsupported", "this service's sign-in isn't on https")
    sm = re.search(r'scope="([^"]*)"', www_auth or "")
    scope = sm.group(1) if sm else " ".join(str(s) for s in prm.get("scopes_supported") or [] if isinstance(s, str))
    return {"resource": str(prm.get("resource") or url), "scope": scope.strip(),
            "authorize": str(meta["authorization_endpoint"]), "token": str(meta["token_endpoint"]),
            "register": str(meta["registration_endpoint"]),
            "methods": [str(x) for x in meta.get("token_endpoint_auth_methods_supported") or []]}


# ---------------------------------------------------------------- the sign-in itself
def _pkce() -> tuple[str, str]:
    verifier = base64.urlsafe_b64encode(os.urandom(48)).rstrip(b"=").decode()
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


_PAGE = """<!doctype html><meta charset="utf-8"><title>Lanterna</title>
<body style="font:16px system-ui;background:#0b0d12;color:#ece8df;display:grid;place-items:center;height:90vh">
<div style="text-align:center"><div style="font-size:42px">🏮</div><h2>{title}</h2><p>{text}</p></div></body>"""


def register(meta: dict, redirect: str, client: httpx.Client) -> dict:
    body = {"client_name": "Lanterna", "redirect_uris": [redirect], "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"], "token_endpoint_auth_method": "none",
            "client_uri": "https://github.com/mikybuilds/lanterna", "software_id": "lanterna", "software_version": __version__}
    if meta.get("scope"):
        body["scope"] = meta["scope"]
    try:
        r = client.post(meta["register"], json=body, headers=_UA)
    except httpx.HTTPError as e:
        raise AuthError("network", f"couldn't reach the sign-in ({e.__class__.__name__})") from e
    if r.status_code not in (200, 201):
        raise AuthError("other", f"the service didn't accept Lanterna ({r.status_code}): {r.text[:120]}")
    try:
        d = r.json()
    except ValueError as e:
        raise AuthError("other", "the service's answer wasn't JSON") from e
    if not d.get("client_id"):
        raise AuthError("other", "the service gave no client id")
    return {"client_id": str(d["client_id"]), "client_secret": str(d.get("client_secret") or "")}


def sign_in(url: str, open_browser=quiet.open_url, cancel: threading.Event | None = None,
            client: httpx.Client | None = None, timeout: float = SIGN_IN_TIMEOUT, meta: dict | None = None) -> dict:
    """Runs the browser sign-in for an MCP server; returns the token record to keep (store())."""
    own = client is None
    client = client or httpx.Client(timeout=30, follow_redirects=False)
    try:
        meta = meta or probe(url, client).get("meta")
        if not meta:
            meta = discover(url, client)
        verifier, challenge = _pkce()
        state = secrets.token_urlsafe(24)
        got: dict = {}

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                if q.get("state", [""])[0] != state:
                    self.send_response(400)
                    self.end_headers()
                    return
                got.update({k: v[0] for k, v in q.items()})
                ok = "code" in got
                body = _PAGE.format(title="Connected" if ok else "Sign-in was cancelled",
                                    text="You can close this tab and go back to Lanterna." if ok else "You can close this tab.").encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):        # the address holds the one-time code: keep it out of the console
                pass

        srv = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        srv.timeout = 0.5
        redirect = f"http://127.0.0.1:{srv.server_address[1]}/callback"
        try:
            try:
                cl = register(meta, redirect, client)
            except AuthError:                   # some services only take "localhost" in the address
                redirect = f"http://localhost:{srv.server_address[1]}/callback"
                cl = register(meta, redirect, client)
            q = {"response_type": "code", "client_id": cl["client_id"], "redirect_uri": redirect, "state": state,
                 "code_challenge": challenge, "code_challenge_method": "S256", "resource": meta["resource"]}
            if meta.get("scope"):
                q["scope"] = meta["scope"]
            sep = "&" if "?" in meta["authorize"] else "?"
            open_browser(meta["authorize"] + sep + urllib.parse.urlencode(q))
            end = time.monotonic() + timeout
            while "code" not in got and "error" not in got:
                if time.monotonic() > end:
                    raise AuthError("cancelled", "no answer from the browser")
                if cancel is not None and cancel.is_set():
                    raise AuthError("cancelled", "cancelled")
                srv.handle_request()
        finally:
            srv.server_close()
        if "error" in got:
            raise AuthError("denied" if got["error"] == "access_denied" else "other", got.get("error_description") or got["error"])
        data = {"grant_type": "authorization_code", "code": got["code"], "redirect_uri": redirect,
                "code_verifier": verifier, "resource": meta["resource"]}
        rec = {"client_id": cl["client_id"], "client_secret": cl["client_secret"], "token_url": meta["token"],
               "resource": meta["resource"]}
        return {**rec, **_tokens(rec, data, client)}
    finally:
        if own:
            client.close()


def _tokens(rec: dict, data: dict, client: httpx.Client) -> dict:
    data = {**data, "client_id": rec["client_id"]}
    if rec.get("client_secret"):
        data["client_secret"] = rec["client_secret"]
    try:
        r = client.post(rec["token_url"], data=data, headers={"Accept": "application/json", **_UA})
    except httpx.HTTPError as e:
        raise AuthError("network", f"couldn't reach the sign-in ({e.__class__.__name__})") from e
    try:
        d = r.json()
    except ValueError:
        d = {}
    if r.status_code != 200 or not d.get("access_token"):
        raise AuthError("denied" if d.get("error") in ("invalid_grant", "invalid_client", "unauthorized_client") else "other",
                        f"sign-in: {d.get('error') or r.status_code}")
    exp = float(d["expires_in"]) if str(d.get("expires_in") or "").replace(".", "", 1).isdigit() else 0
    return {"access": str(d["access_token"]), "refresh": str(d.get("refresh_token") or data.get("refresh_token") or ""),
            "exp": time.time() + exp - 60 if exp else 0}


def access(sid: str, client: httpx.Client, force: bool = False) -> str:
    """A working access token for this server ("" when the user has to sign in again)."""
    rec = load(sid)
    if not rec.get("access"):
        return ""
    if not force and (not rec.get("exp") or rec["exp"] > time.time()):
        return rec["access"]
    if not rec.get("refresh"):
        return "" if force else rec["access"]
    try:
        rec.update(_tokens(rec, {"grant_type": "refresh_token", "refresh_token": rec["refresh"],
                                 "resource": rec.get("resource", "")}, client))
    except AuthError as e:
        if e.kind == "network":
            return rec["access"]
        return ""
    store(sid, rec)
    return rec["access"]
