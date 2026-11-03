"""Backend for the window app. The UI calls these methods (through pywebview, or HTTP in dev mode).

Replies are streamed by polling: send() starts a reply and returns a stream id, poll() returns the new pieces.
Every method returns plain JSON-friendly data and never raises into the UI.
"""
from __future__ import annotations

import re
import threading
import time
import uuid
import webbrowser
from dataclasses import asdict

from . import AUTHOR, HOMEPAGE, __version__, bugreport, hardware, keys, local
from .chat import Conversation, ToolUse
from .files import FileError, prepare
from .config import Settings
from .discovery import get_models
from .i18n import LANGS, t
from .providers import PROVIDERS, Client, ProviderError, Thought
from .router import Router, Switched
from .notify import notify
from .store import Store
from .sync import PREFS as SYNC_PREFS
from .thinking import Steps
from .tools import Toolbox
from .workspace import Actions, Workspace, folder_tools, too_broad

FIRST_CHOICES = ["groq", "gemini"]
_MODEL_NAME = re.compile(r"^[a-z0-9][a-z0-9._-]*(/[a-z0-9._-]+)?(:[a-z0-9._-]+)?$", re.I)


class _Stream:
    def __init__(self, lang: str = "en"):
        self.pieces: list[str] = []
        self.notes: list[str] = []
        self.tools: list[str] = []         # "🔎 web_search" chips
        self.cards: list[dict] = []        # changes waiting for the user's OK (working folder, Google Drive)
        self.steps = Steps(lang)           # "what I'm doing" line: thought summaries and tool steps
        self.done = False
        self.final = False                 # pieces now hold the cleaned full reply
        self.error: dict | None = None
        self.lock = threading.Lock()


class Api:
    def __init__(self, store: Store | None = None, scheduler: bool = True):
        self.settings = Settings.load()
        self.store = store or Store()
        from . import gdrive, github
        self.actions = Actions()
        self.workspace = Workspace(lambda: self._folder_for(self.actions.tid()), self.actions)
        self.drive = gdrive.Connector()
        self.github = github.Connector()
        self.toolbox = Toolbox(self.store, lang=lambda: self.settings.lang,
                               extra=lambda: folder_tools(self.workspace) + gdrive.drive_tools(self.drive, self.workspace, self.actions)
                               + github.github_tools(self.github, self.workspace, self.actions))
        self._router: Router | None = None
        self._streams: dict[str, _Stream] = {}
        self._lock = threading.Lock()
        self._alerts: list[dict] = []       # reminders that fired, waiting for the UI
        self._hw: hardware.Hardware | None = None
        self._downloads = local.Downloads()
        from . import updates
        self.updater = updates.Updater()
        self._update_asset: dict | None = None
        from .sync import Syncer
        self.syncer = Syncer(self.store, self.settings)
        self.syncer.extra_scope = gdrive.SCOPE_FILE
        self.syncer.on_token = lambda tok, account, granted: (
            self.drive.adopt(tok, account) if gdrive.SCOPE_FILE in granted.split() else None)
        self.syncer.on_sign_out = self.drive.forget
        self.syncer.on_change = self._synced_settings
        if scheduler:
            threading.Thread(target=self._reminder_loop, daemon=True).start()
            threading.Thread(target=self.syncer.loop, daemon=True).start()
            threading.Thread(target=updates.cleanup, daemon=True).start()

    # ---------------------------------------------------------------- state & settings
    def state(self) -> dict:
        s = self.settings
        return {
            "version": __version__, "author": AUTHOR, "homepage": HOMEPAGE,
            "settings": asdict(s), "langs": LANGS, "first": FIRST_CHOICES,
            "providers": [{"id": p.id, "name": p.name, "key_url": p.key_url, "local": p.local,
                           "has_key": bool(keys.get_key(p.id)), "masked": keys.mask(keys.get_key(p.id))}
                          for p in PROVIDERS.values()],
            "model": self._router.current.label if self._router and self._router.current else "",
        }

    def save_settings(self, patch: dict) -> dict:
        allowed = {"lang", "name", "mode", "provider", "onboarded", "auto_cloud", "update_check", "sync_asked"}
        for k, v in (patch or {}).items():
            if k in allowed:
                setattr(self.settings, k, v.strip()[:40] if isinstance(v, str) else bool(v) if k in ("onboarded", "auto_cloud", "update_check", "sync_asked") else v)
        if {"lang", "name"} & set(patch or {}):
            self.settings.profile_at = time.time()
        if set(SYNC_PREFS) & set(patch or {}):
            self.settings.prefs_at = time.time()
        if self.settings.lang not in LANGS:
            self.settings.lang = "en"
        if self.settings.mode not in ("cloud", "local", "auto"):
            self.settings.mode = "cloud"
        self.settings.save()
        if {"provider", "mode"} & set(patch or {}):
            self._router = None                            # chosen service / mode changes the model list
        return self.state()

    # ---------------------------------------------------------------- keys
    def check_key(self, provider: str, key: str) -> dict:
        """Checks the key with the provider; stores it in the system vault only if it works."""
        p = PROVIDERS.get(provider)
        key = (key or "").strip()
        if not p or not p.needs_key or not key:
            return {"ok": False, "error": "empty"}
        try:
            c = Client(p, key, timeout=20)
            c.list_models()
            c.close()
        except ProviderError as e:
            return {"ok": False, "error": e.kind, "message": str(e)[:200]}
        try:
            keys.set_key(provider, key)
            self._key_changed(provider)
        except Exception as e:                               # no system vault (e.g. a server without a keyring)
            return {"ok": False, "error": "vault", "message": str(e)[:200]}
        self._router = None
        return {"ok": True, "masked": keys.mask(key)}

    def delete_key(self, provider: str) -> dict:
        if provider in PROVIDERS:
            keys.delete_key(provider)
            self._key_changed(provider)
            self._router = None
        return self.state()

    def _key_changed(self, provider: str) -> None:
        self.settings.keys_at = {**(self.settings.keys_at or {}), provider: time.time()}
        self.settings.save()

    def _synced_settings(self) -> None:
        self._router = None                                # keys or the chosen service came from another device

    def open_url(self, url: str) -> bool:
        """Opens a link the user clicked in the system browser (https only)."""
        url = str(url or "")
        limit = bugreport.ISSUE_LIMIT if url.startswith(HOMEPAGE + "/" + "issues/new?") else 2000
        if url.startswith("https://") and len(url) <= limit and not any(c in url for c in "\n\r\"'<> "):
            webbrowser.open(url)
            return True
        return False

    # ---------------------------------------------------------------- Google sign-in & sync
    def sync_status(self) -> dict:
        return self.syncer.status()

    def sync_sign_in(self) -> dict:
        """Opens Google's sign-in page in the browser; poll sync_status for the result."""
        return self.syncer.start_sign_in()

    def sync_cancel(self) -> dict:
        return self.syncer.cancel_sign_in()

    def sync_password(self, password: str) -> dict:
        return self.syncer.set_password(password)

    def sync_now(self) -> dict:
        return self.syncer.sync()

    def sync_sign_out(self, delete_cloud: bool = False) -> dict:
        return self.syncer.sign_out(bool(delete_cloud))

    # ---------------------------------------------------------------- bug reports
    def bug_report(self, text: str, include_info: bool = True) -> dict:
        """The exact report text the user will send, with ready links (nothing is sent from here)."""
        model = self._router.current.label if self._router and self._router.current else ""
        return bugreport.compose(text, bool(include_info), self.settings, model)

    def open_mail(self, url: str) -> bool:
        """Opens the user's mail app with the ready letter; they press Send themselves."""
        if not bugreport.valid_mailto(url):
            return False
        webbrowser.open(url)
        return True

    # ---------------------------------------------------------------- models
    def _get_router(self, refresh: bool = False) -> Router:
        with self._lock:
            if self._router is None or refresh:
                s = self.settings
                cands = get_models(s.provider, refresh=refresh, mode=s.mode, picks=s.local_models)
                if not cands:
                    if s.mode == "local":
                        raise ProviderError("local", "no local models" if local.version() else "ollama not running")
                    raise ProviderError("auth", "no keys")
                self._router = Router(cands)
            return self._router

    def models(self, refresh: bool = False) -> dict:
        try:
            r = self._get_router(refresh)
        except ProviderError as e:
            return {"ok": False, "error": e.kind, "models": []}
        return {"ok": True, "current": r.current.label if r.current else "",
                "models": [{"provider": PROVIDERS[c.provider].name, "model": c.model, "score": c.score,
                            "status": c.status, "latency": c.latency, "vision": c.vision} for c in r.candidates]}

    def limits(self) -> list[dict]:
        """Free limits per model: used today, what the service says is left, resting after a limit."""
        from .limits import TRACKER
        rows = TRACKER.view(self._router.resting() if self._router else None)
        for x in rows:
            x["service"] = PROVIDERS[x["provider"]].name if x["provider"] in PROVIDERS else x["provider"]
        return rows

    def check_update(self) -> dict:
        """Latest release, plus what to do to update this copy (steps in the interface language)."""
        from . import updates
        res = updates.check()
        if res.get("newer"):
            lang = self.settings.lang
            how = updates.how_to(updates.install_kind(), res["latest"], res.get("assets"))
            res["steps"] = [t(s, lang, file=how["file"]) if "{file}" in s else t(s, lang) for s in how["steps"]]
            res["command"], res["download"] = how["command"], how["download"]
            self._update_asset = updates.setup_asset(res) if updates.install_kind() == "installer" else None
            res["auto"] = self._update_asset is not None
        res.pop("assets", None)
        res.pop("digests", None)
        return res

    def update_install(self) -> dict:
        """Update now: download the new installer, check it, install it over this copy and open Lanterna again."""
        if not self._update_asset:
            return {"phase": "error", "error": "no_auto", "done": 0, "total": 0, "version": ""}
        return self.updater.start(self._update_asset, self.settings.lang)

    def update_status(self) -> dict:
        return self.updater.status()

    def update_notice(self) -> dict:
        """Called once when the app starts: the same as check_update, or nothing when the user turned it off."""
        if not self.settings.update_check:
            return {"newer": False, "latest": "", "off": True}
        return self.check_update()

    # ---------------------------------------------------------------- local models (Ollama)
    def hardware(self) -> dict:
        """What this computer has and which local models fit (read locally, nothing is sent)."""
        if self._hw is None:
            self._hw = hardware.detect()
        adv = hardware.advise(self._hw)
        have = {m.name for m in local.installed()}
        out = adv.to_dict()
        for m in out["models"]:
            m["installed"] = m["name"] in have
        return {"hw": self._hw.to_dict(), "advice": out, "download_page": local.DOWNLOAD_PAGE}

    def local_status(self) -> dict:
        ver = local.version()
        models = [vars(m) for m in local.installed()] if ver else []
        return {"running": bool(ver), "version": ver or "", "models": [m for m in models if m["chat"]],
                "picks": self.settings.local_models, "download_page": local.DOWNLOAD_PAGE,
                "pulls": self._downloads.state()}

    def set_local_model(self, role: str, name: str) -> dict:
        if role in ("chat", "vision"):
            if name:
                self.settings.local_models[role] = str(name)[:80]
            else:
                self.settings.local_models.pop(role, None)
            self.settings.save()
            self._router = None
        return self.local_status()

    def pull_model(self, name: str) -> dict:
        """Starts a download. Only called when the user presses Download."""
        name = str(name or "").strip()
        if not _MODEL_NAME.match(name):
            return {"ok": False, "error": "name"}
        if not local.version():
            return {"ok": False, "error": "ollama"}
        self._downloads.start(name)
        self._router = None
        return {"ok": True}

    def pulls(self) -> list[dict]:
        done = [j for j in self._downloads.state() if j["status"] == "done"]
        if done:
            self._router = None                            # new model: rebuild the list on the next message
        return self._downloads.state()

    def cancel_pull(self, name: str) -> list[dict]:
        self._downloads.cancel(str(name))
        return self._downloads.state()

    # ---------------------------------------------------------------- chats
    def threads(self) -> list[dict]:
        return self.store.threads()

    def new_thread(self) -> dict:
        tid = self.store.new_thread()
        return {"id": tid, "title": ""}

    def messages(self, tid: int) -> list[dict]:
        """Messages for display: attached file contents are shown as a short 📎 line."""
        out = []
        for m in self.store.messages(int(tid)):
            if m["role"] == "user":
                m = {**m, "content": _short_files(m["content"])}
            out.append(m)
        return out

    def rename_thread(self, tid: int, title: str) -> bool:
        self.store.rename(int(tid), title)
        return True

    def delete_thread(self, tid: int) -> bool:
        self.store.delete_thread(int(tid))
        if self.settings.chat_dirs.pop(str(int(tid)), None) is not None:
            self.settings.save()
        return True

    def send(self, tid: int, text: str, files: list[dict] | None = None) -> dict:
        text = (text or "").strip()
        tid = int(tid)
        if (not text and not files) or not self.store.thread(tid):
            return {"ok": False, "error": "empty"}
        try:
            prep = prepare(files or [])
        except FileError as e:
            return {"ok": False, "error": "file", "message": str(e)}
        sid = uuid.uuid4().hex
        st = _Stream(self.settings.lang)
        self._streams[sid] = st
        history = [{"role": m["role"], "content": m["content"]} for m in self.store.messages(tid)]
        full = "\n\n".join(x for x in (text, prep.text) if x)
        self.store.add(tid, "user", full)
        if not self.store.thread(tid)["title"]:
            self.store.rename(tid, (text or ", ".join(prep.names)).splitlines()[0][:60])
        threading.Thread(target=self._run, args=(sid, tid, full, history, prep.images), daemon=True).start()
        return {"ok": True, "stream": sid}

    def _run(self, sid: str, tid: int, text: str, history: list[dict], images: list[str] | None = None) -> None:
        st = self._streams[sid]
        self.actions.bind(st.cards, tid)
        try:
            router = self._get_router()
            conv = Conversation(router, self.settings.name, history=history, toolbox=self.toolbox,
                                lang=self.settings.lang,
                                auto_cloud=self.settings.mode == "auto" and self.settings.auto_cloud)
            for p in conv.ask(text, images or None):
                with st.lock:
                    if isinstance(p, Switched):
                        st.notes.append(p.to.label)
                    elif isinstance(p, ToolUse):
                        st.tools.append(f"{p.label} {p.name}")
                        st.steps.tool(p.name, p.arguments)
                    elif isinstance(p, Thought):
                        st.steps.thought(p.text)
                    else:
                        st.pieces.append(p)
            self.store.add(tid, "assistant", conv.last_reply, router.current.label if router.current else "")
            with st.lock:
                st.pieces = [conv.last_reply]               # final cleaned text replaces the raw stream
                st.final = True
        except ProviderError as e:
            bugreport.remember_error(e.kind, str(e))
            with st.lock:
                st.error = {"kind": e.kind, "message": str(e)[:300]}
        except Exception as e:                              # never leave the UI waiting
            bugreport.remember_error(type(e).__name__, str(e))
            with st.lock:
                st.error = {"kind": "other", "message": str(e)[:300]}
        finally:
            self.actions.bind(None)
            with st.lock:
                st.done = True

    def poll(self, sid: str, offset: int = 0) -> dict:
        st = self._streams.get(sid)
        if not st:
            return {"done": True, "error": {"kind": "other", "message": "unknown stream"}}
        with st.lock:
            if st.final:
                out = {"final": st.pieces[0], "notes": st.notes, "tools": st.tools, "cards": list(st.cards),
                       **st.steps.view(),
                       "done": st.done, "error": st.error,
                       "model": self._router.current.label if self._router and self._router.current else ""}
            else:
                text = "".join(st.pieces)
                out = {"text": text[offset:], "offset": len(text), "notes": st.notes, "tools": st.tools,
                       "cards": list(st.cards), **st.steps.view(),
                       "done": st.done, "error": st.error}
        if out["done"]:
            self._streams.pop(sid, None)
        return out

    # ---------------------------------------------------------------- confirmations (working folder, Drive)
    def cards(self, tid: int) -> list[dict]:
        """Cards of this chat still waiting for an answer (shown again when the chat is opened or redrawn)."""
        tid = int(tid)
        return [a.card() for a in list(self.actions.items.values())
                if a.tid == tid and (self.actions.get(a.id) or a).state == "pending"]

    def action_confirm(self, aid: str) -> dict:
        a = self.actions.get(str(aid))
        if a and a.state == "pending" and a.details.get("folder"):
            from pathlib import Path
            now = self._folder_for(a.tid)
            if not now or Path(now).expanduser().resolve() != Path(a.details["folder"]):
                a.state, a.result = "failed", "the folder of this chat was changed after this card; ask again"
                return {**a.card(), "text": ""}
        return self._action_done(self.actions.confirm(str(aid)))

    def action_cancel(self, aid: str) -> dict:
        return self._action_done(self.actions.cancel(str(aid)))

    def _action_done(self, a) -> dict:
        if a is None:
            return {"id": "", "state": "expired", "result": "", "text": ""}
        lang = self.settings.lang
        what = action_title(a.kind, a.details, a.result if a.state == "done" else "", lang, done=a.state == "done")
        if a.state in ("done", "failed", "cancelled") and a.tid and not getattr(a, "noted", False):
            a.noted = True                              # the chat remembers what happened (and the model sees it)
            note = ("✅ " + what if a.state == "done" else "✖ " + t("Cancelled: {what}", lang, what=what)
                    if a.state == "cancelled" else "⚠️ " + t("Couldn't do it: {error}", lang, error=a.result))
            self.store.add(a.tid, "assistant", note)
        return {**a.card(), "text": what}

    # ---------------------------------------------------------------- working folder
    def workdir(self) -> dict:
        root = self.workspace.root()
        return {"path": str(root) if root else self.settings.work_dir, "name": root.name if root else "",
                "missing": bool(self.settings.work_dir and not root)}

    def pick_folder(self) -> dict:
        """Settings → Working folder (the default for new chats): system picker, then saved."""
        r = self.choose_folder(self.settings.work_dir)
        return self.set_workdir(r["path"]) if r["ok"] else r

    def choose_folder(self, start: str = "") -> dict:
        """Opens the system folder picker (window app). Returns {"ok", "path"} or {"ok": False, "error": "no_dialog"}."""
        try:
            import webview
            win = webview.windows[0] if webview.windows else None
        except ImportError:
            win = None
        if win is None:
            return {"ok": False, "error": "no_dialog"}
        kind = webview.FileDialog.FOLDER if hasattr(webview, "FileDialog") else webview.FOLDER_DIALOG
        res = win.create_file_dialog(kind, directory=start or self.settings.work_dir or "")
        if not res:
            return {"ok": False, "error": "cancelled"}
        return self._check_folder(res[0] if isinstance(res, (list, tuple)) else str(res))

    @staticmethod
    def _check_folder(path: str) -> dict:
        from pathlib import Path
        path = str(path or "").strip().strip(chr(34))
        if path:
            p = Path(path).expanduser()
            if not p.is_dir():
                return {"ok": False, "error": "not_found"}
            why = too_broad(p)
            if why:
                return {"ok": False, "error": "too_broad", "why": why}
            path = str(p.resolve())
        return {"ok": True, "path": path}

    def check_folder(self, path: str) -> dict:
        return self._check_folder(path)

    def set_workdir(self, path: str) -> dict:
        r = self._check_folder(path)
        if not r["ok"]:
            return r
        self.settings.work_dir = r["path"]
        self.settings.save()
        return {"ok": True, **self.workdir()}

    # ---------------------------------------------------------------- the folder of one chat (under the message box)
    def _folder_for(self, tid) -> str:
        key = str(int(tid or 0))
        return self.settings.chat_dirs[key] if key != "0" and key in self.settings.chat_dirs else self.settings.work_dir

    def chat_folder(self, tid) -> dict:
        from pathlib import Path
        f = self._folder_for(tid)
        p = Path(f).expanduser() if f else None
        ok = bool(p and p.is_dir())
        return {"path": str(p.resolve()) if ok else f, "name": (p.resolve().name or str(p)) if ok else "",
                "missing": bool(f and not ok), "own": str(int(tid or 0)) in self.settings.chat_dirs,
                "default": self.settings.work_dir}

    def set_chat_folder(self, tid, path: str = "", follow_default: bool = False) -> dict:
        """This chat's folder: a path, "" = no folder for this chat, follow_default = the one from Settings."""
        key = str(int(tid or 0))
        if key == "0":
            return {"ok": False, "error": "no_chat"}
        if follow_default:
            self.settings.chat_dirs.pop(key, None)
        else:
            r = self._check_folder(path)
            if not r["ok"]:
                return r
            self.settings.chat_dirs[key] = r["path"]
        self.settings.save()
        return {"ok": True, **self.chat_folder(tid)}

    # ---------------------------------------------------------------- the limit bar (under the message box)
    def limit_now(self) -> dict:
        """How much of the limit of the model in use is left (or of the model used last)."""
        from .limits import TRACKER
        cur = self._router.current if self._router else None
        if cur is not None:
            if PROVIDERS[cur.provider].local:
                return {"local": True, "label": cur.label}
            prov, model, label = cur.provider, cur.model, cur.label
        else:
            last = TRACKER.last_used()
            if not last:
                return {}
            prov, model = last
            label = f"{PROVIDERS[prov].name} · {model}" if prov in PROVIDERS else model
        rest = (self._router.resting() if self._router else {}).get(f"{prov}/{model}")
        return {"label": label, **TRACKER.current(prov, model, rest)}

    # ---------------------------------------------------------------- Google Drive connector
    def drive_status(self) -> dict:
        return self.drive.status()

    def drive_connect(self) -> dict:
        return self.drive.start()

    def drive_cancel(self) -> dict:
        return self.drive.cancel()

    def drive_disconnect(self) -> dict:
        return self.drive.disconnect()

    # ---------------------------------------------------------------- GitHub connector
    def github_status(self) -> dict:
        return self.github.status()

    def github_connect(self) -> dict:
        return self.github.start()

    def github_cancel(self) -> dict:
        return self.github.cancel()

    def github_disconnect(self) -> dict:
        return self.github.disconnect()

    # ---------------------------------------------------------------- memory & reminders
    def facts(self) -> list[dict]:
        return self.store.facts()

    def add_fact(self, text: str) -> list[dict]:
        text = " ".join(str(text or "").split())[:300]
        if text:
            self.store.add_fact(text)
        return self.store.facts()

    def delete_fact(self, fid: int) -> list[dict]:
        self.store.delete_fact(int(fid))
        return self.store.facts()

    def reminders(self) -> list[dict]:
        return [{**r, "when": time.strftime("%d.%m %H:%M", time.localtime(r["due"]))} for r in self.store.reminders()]

    def cancel_reminder(self, rid: int) -> list[dict]:
        self.store.cancel_reminder(int(rid))
        return self.reminders()

    def alerts(self) -> list[dict]:
        """Reminders that fired since the last call (the UI shows them inside the app too)."""
        with self._lock:
            out, self._alerts = self._alerts, []
        return out

    def check_reminders(self, now: float | None = None) -> list[dict]:
        due = self.store.take_due(now)
        for r in due:
            late = (time.time() if now is None else now) - r["due"] > 120
            r["late"] = late
            notify("Lanterna ⏰", r["text"] + (f" ({time.strftime('%H:%M', time.localtime(r['due']))})" if late else ""))
        if due:
            with self._lock:
                self._alerts += due
        return due

    def _reminder_loop(self) -> None:
        while True:
            try:
                self.check_reminders()
            except Exception:                               # noqa: BLE001  keep the scheduler alive
                pass
            time.sleep(15)


def action_title(kind: str, d: dict, result: str, lang: str, done: bool = False) -> str:
    """One line about a proposed (or, with done, finished) change in the interface language; stored in the chat too."""
    link = result.split("|", 1)[1] if "|" in (result or "") else ""
    keys = {"write_new": ("Create {path}", "Created {path}"), "write_replace": ("Rewrite {path}", "Rewrote {path}"),
            "write_append": ("Add to {path}", "Added to {path}"),
            "mkdir": ("Create the folder {path}", "Created the folder {path}"), "move": ("Move {path} → {to}", "Moved {path} → {to}"),
            "drive_folder": ("Create the folder {name} in Google Drive", "Created the folder {name} in Google Drive"),
            "drive_upload": ("Upload {path} to Google Drive", "Uploaded {path} to Google Drive"),
            "drive_text": ("Save {name} to Google Drive", "Saved {name} to Google Drive"),
            "github_push": ("Push {count} files to {repo}", "Pushed {count} files to {repo}"),
            "github_new_repo": ("Create the repository {name} on GitHub", "Opened GitHub to create {name}")}
    out = t(keys.get(kind, ("Change", "Done"))[int(done)], lang,
            **{k: str(d.get(k, "")) for k in ("path", "to", "name", "repo", "count")})
    if kind == "write_replace" and "(" in (result or ""):
        out += " " + result[result.index("("):]
    return out + (f" — {link}" if link.startswith("https://") else "")


_FILE_BLOCK = re.compile(r"\[File: ([^\]\n]+)\]\n```\n.*?\n```(?:\n\[…file cut, too long\])?", re.S)
_PHOTO = re.compile(r"\[Photo: ([^\]\n]+)\]")


def _short_files(text: str) -> str:
    return _PHOTO.sub(r"🖼 \1", _FILE_BLOCK.sub(r"📎 \1", text))
