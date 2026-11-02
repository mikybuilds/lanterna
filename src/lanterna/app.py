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
from .providers import PROVIDERS, Client, ProviderError
from .router import Router, Switched
from .notify import notify
from .store import Store
from .tools import Toolbox

FIRST_CHOICES = ["groq", "gemini"]
_MODEL_NAME = re.compile(r"^[a-z0-9][a-z0-9._-]*(/[a-z0-9._-]+)?(:[a-z0-9._-]+)?$", re.I)


class _Stream:
    def __init__(self):
        self.pieces: list[str] = []
        self.notes: list[str] = []
        self.tools: list[str] = []         # "🔎 web_search" chips
        self.done = False
        self.final = False                 # pieces now hold the cleaned full reply
        self.error: dict | None = None
        self.lock = threading.Lock()


class Api:
    def __init__(self, store: Store | None = None, scheduler: bool = True):
        self.settings = Settings.load()
        self.store = store or Store()
        self.toolbox = Toolbox(self.store, lang=lambda: self.settings.lang)
        self._router: Router | None = None
        self._streams: dict[str, _Stream] = {}
        self._lock = threading.Lock()
        self._alerts: list[dict] = []       # reminders that fired, waiting for the UI
        self._hw: hardware.Hardware | None = None
        self._downloads = local.Downloads()
        if scheduler:
            threading.Thread(target=self._reminder_loop, daemon=True).start()

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
        allowed = {"lang", "name", "mode", "provider", "onboarded", "auto_cloud", "update_check"}
        for k, v in (patch or {}).items():
            if k in allowed:
                setattr(self.settings, k, v.strip()[:40] if isinstance(v, str) else bool(v) if k in ("onboarded", "auto_cloud", "update_check") else v)
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
        except Exception as e:                               # no system vault (e.g. a server without a keyring)
            return {"ok": False, "error": "vault", "message": str(e)[:200]}
        self._router = None
        return {"ok": True, "masked": keys.mask(key)}

    def delete_key(self, provider: str) -> dict:
        if provider in PROVIDERS:
            keys.delete_key(provider)
            self._router = None
        return self.state()

    def open_url(self, url: str) -> bool:
        """Opens a link the user clicked in the system browser (https only)."""
        url = str(url or "")
        limit = bugreport.ISSUE_LIMIT if url.startswith(HOMEPAGE + "/" + "issues/new?") else 2000
        if url.startswith("https://") and len(url) <= limit and not any(c in url for c in "\n\r\"'<> "):
            webbrowser.open(url)
            return True
        return False

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

    def check_update(self) -> dict:
        """Latest release, plus what to do to update this copy (steps in the interface language)."""
        from . import updates
        res = updates.check()
        if res.get("newer"):
            lang = self.settings.lang
            how = updates.how_to(updates.install_kind(), res["latest"], res.get("assets"))
            res["steps"] = [t(s, lang, file=how["file"]) if "{file}" in s else t(s, lang) for s in how["steps"]]
            res["command"], res["download"] = how["command"], how["download"]
        res.pop("assets", None)
        return res

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
        st = _Stream()
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
            with st.lock:
                st.done = True

    def poll(self, sid: str, offset: int = 0) -> dict:
        st = self._streams.get(sid)
        if not st:
            return {"done": True, "error": {"kind": "other", "message": "unknown stream"}}
        with st.lock:
            if st.final:
                out = {"final": st.pieces[0], "notes": st.notes, "tools": st.tools, "done": st.done, "error": st.error,
                       "model": self._router.current.label if self._router and self._router.current else ""}
            else:
                text = "".join(st.pieces)
                out = {"text": text[offset:], "offset": len(text), "notes": st.notes, "tools": st.tools,
                       "done": st.done, "error": st.error}
        if out["done"]:
            self._streams.pop(sid, None)
        return out

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


_FILE_BLOCK = re.compile(r"\[File: ([^\]\n]+)\]\n```\n.*?\n```(?:\n\[…file cut, too long\])?", re.S)
_PHOTO = re.compile(r"\[Photo: ([^\]\n]+)\]")


def _short_files(text: str) -> str:
    return _PHOTO.sub(r"🖼 \1", _FILE_BLOCK.sub(r"📎 \1", text))
