"""Backend for the window app. The UI calls these methods (through pywebview, or HTTP in dev mode).

Replies are streamed by polling: send() starts a reply and returns a stream id, poll() returns the new pieces.
Every method returns plain JSON-friendly data and never raises into the UI.
"""
from __future__ import annotations

import threading
import uuid
import webbrowser
from dataclasses import asdict

from . import AUTHOR, HOMEPAGE, __version__, keys
from .chat import Conversation
from .config import Settings
from .discovery import get_models
from .i18n import LANGS
from .providers import PROVIDERS, Client, ProviderError
from .router import Router, Switched
from .store import Store

FIRST_CHOICES = ["groq", "gemini"]


class _Stream:
    def __init__(self):
        self.pieces: list[str] = []
        self.notes: list[str] = []
        self.done = False
        self.final = False                 # pieces now hold the cleaned full reply
        self.error: dict | None = None
        self.lock = threading.Lock()


class Api:
    def __init__(self, store: Store | None = None):
        self.settings = Settings.load()
        self.store = store or Store()
        self._router: Router | None = None
        self._streams: dict[str, _Stream] = {}
        self._lock = threading.Lock()

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
        allowed = {"lang", "name", "mode", "provider", "onboarded"}
        for k, v in (patch or {}).items():
            if k in allowed:
                setattr(self.settings, k, v.strip()[:40] if isinstance(v, str) else bool(v) if k == "onboarded" else v)
        if self.settings.lang not in LANGS:
            self.settings.lang = "en"
        self.settings.save()
        if "provider" in (patch or {}):
            self._router = None                            # chosen service leads the list
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
        keys.set_key(provider, key)
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
        if url.startswith("https://") and len(url) < 2000 and not any(c in url for c in "\n\r\"'<> "):
            webbrowser.open(url)
            return True
        return False

    # ---------------------------------------------------------------- models
    def _get_router(self, refresh: bool = False) -> Router:
        with self._lock:
            if self._router is None or refresh:
                cands = get_models(self.settings.provider, refresh=refresh)
                if not cands:
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

    # ---------------------------------------------------------------- chats
    def threads(self) -> list[dict]:
        return self.store.threads()

    def new_thread(self) -> dict:
        tid = self.store.new_thread()
        return {"id": tid, "title": ""}

    def messages(self, tid: int) -> list[dict]:
        return self.store.messages(int(tid))

    def rename_thread(self, tid: int, title: str) -> bool:
        self.store.rename(int(tid), title)
        return True

    def delete_thread(self, tid: int) -> bool:
        self.store.delete_thread(int(tid))
        return True

    def send(self, tid: int, text: str) -> dict:
        text = (text or "").strip()
        tid = int(tid)
        if not text or not self.store.thread(tid):
            return {"ok": False, "error": "empty"}
        sid = uuid.uuid4().hex
        st = _Stream()
        self._streams[sid] = st
        history = [{"role": m["role"], "content": m["content"]} for m in self.store.messages(tid)]
        self.store.add(tid, "user", text)
        if not self.store.thread(tid)["title"]:
            self.store.rename(tid, text.splitlines()[0][:60])
        threading.Thread(target=self._run, args=(sid, tid, text, history), daemon=True).start()
        return {"ok": True, "stream": sid}

    def _run(self, sid: str, tid: int, text: str, history: list[dict]) -> None:
        st = self._streams[sid]
        try:
            router = self._get_router()
            conv = Conversation(router, self.settings.name, history=history)
            for p in conv.ask(text):
                with st.lock:
                    if isinstance(p, Switched):
                        st.notes.append(p.to.label)
                    else:
                        st.pieces.append(p)
            self.store.add(tid, "assistant", conv.last_reply, router.current.label if router.current else "")
            with st.lock:
                st.pieces = [conv.last_reply]               # final cleaned text replaces the raw stream
                st.final = True
        except ProviderError as e:
            with st.lock:
                st.error = {"kind": e.kind, "message": str(e)[:300]}
        except Exception as e:                              # never leave the UI waiting
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
                out = {"final": st.pieces[0], "notes": st.notes, "done": st.done, "error": st.error,
                       "model": self._router.current.label if self._router and self._router.current else ""}
            else:
                text = "".join(st.pieces)
                out = {"text": text[offset:], "offset": len(text), "notes": st.notes, "done": st.done, "error": st.error}
        if out["done"]:
            self._streams.pop(sid, None)
        return out
