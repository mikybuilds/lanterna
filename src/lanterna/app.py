"""Backend for the window app. The UI calls these methods (through pywebview, or HTTP in dev mode).

Replies are streamed by polling: send() starts a reply and returns a stream id, poll() returns the new pieces.
Every method returns plain JSON-friendly data and never raises into the UI.
"""
from __future__ import annotations

import datetime as dt
import re
import threading
import shutil
import time
import uuid
from dataclasses import asdict

from . import AUTHOR, HOMEPAGE, __version__, bugreport, hardware, keys, local, quiet
from .chat import (MAX_HISTORY, KEEP_RECENT, Conversation, Questions, ToolUse, about_me, chat_title, follow_ups,
                   learn_facts, summarize, summary_due)
from .files import FileError, prepare
from .config import Settings
from .discovery import get_models
from .i18n import LANGS, catalog, t
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
        self.titling = False               # a side model is naming the chat: the UI asks wait_title()
        self.suggesting = False            # follow-up buttons are coming: the UI asks wait_follow_ups()
        self.learning = False              # a side model looks for facts to remember: the UI asks wait_memory()
        self.questions: list[dict] = []    # the model asked these before a big task (the UI shows a form)
        self.error: dict | None = None
        self.files: list[str] = []         # attached file names
        self.used: list[tuple[str, str]] = []   # (tool, arguments) for “what went to the model”
        self.sent = ""
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
        from . import apps, pcfiles, pcsys
        self.places = pcfiles.Places(self.actions, lang=lambda: self.settings.lang)
        self.apps = apps.Apps(self.actions)
        self.system = pcsys.System(self.actions)
        from . import mcp
        self.mcp = mcp.Hub(self.actions)                      # outside tools the user added (off until they turn it on)
        self.mcp.start()
        import atexit
        atexit.register(self.mcp.stop_all)
        self.toolbox = Toolbox(self.store, lang=lambda: self.settings.lang,
                               extra=lambda: folder_tools(self.workspace) + gdrive.drive_tools(self.drive, self.workspace, self.actions)
                               + github.github_tools(self.github, self.workspace, self.actions) + self._pc_tools()
                               + self.mcp.tools())
        self._router: Router | None = None
        self._streams: dict[str, _Stream] = {}
        self._titling: dict[int, threading.Event] = {}   # chats whose name a side model is writing now
        self._saved: set[str] = set()                         # files saved by export (show_saved may open these)
        self._desk = None                                      # Windows window app: tray, hotkey, quick window (gui.Desk)
        from . import voice
        from .config import data_dir
        self._recorder = voice.Recorder()                     # voice input (the mic button / F2 in the terminal)
        self._whisper = voice.LocalWhisper(data_dir() / "whisper")
        self._follow: dict[int, tuple[threading.Event, list[str]]] = {}   # follow-up ideas being written
        self._learned: dict[int, tuple[threading.Event, list[dict]]] = {}  # facts the side model added after an answer
        self._lock = threading.Lock()
        self._alerts: list[dict] = []       # reminders that fired, waiting for the UI
        self._hw: hardware.Hardware | None = None
        self._downloads = local.Downloads()
        from . import updates
        self.updater = updates.Updater()
        self._update_asset: dict | None = None
        self._last_doctor: list | None = None
        from .history import History
        self.history = History()
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
            "settings": asdict(s), "langs": LANGS, "first": FIRST_CHOICES, "strings": catalog(s.lang),
            "providers": [{"id": p.id, "name": p.name, "key_url": p.key_url, "local": p.local,
                           "has_key": bool(keys.get_key(p.id)), "masked": keys.mask(keys.get_key(p.id))}
                          for p in PROVIDERS.values()],
            "model": self._router.current.label if self._router and self._router.current else "",
        }

    _BOOLS = {"onboarded", "auto_cloud", "update_check", "sync_asked", "pc_access", "tidy_weekly", "space_help",
              "local_fallback", "ai_titles", "follow_ups", "compact_chats", "ask_first", "auto_memory", "tray", "tray_told"}

    def save_settings(self, patch: dict) -> dict:
        from . import shell
        from . import voice
        allowed = {"lang", "name", "mode", "provider", "hotkey", "voice", "voice_model"} | self._BOOLS
        if patch.get("voice", "off") not in voice.ENGINES:
            patch.pop("voice")
        if patch.get("voice_model", "small") not in voice.MODELS:
            patch.pop("voice_model")
        patch = dict(patch or {})
        if "autostart" in patch:                           # lives in Windows (the Run key), not in our settings
            from . import autostart
            autostart.set_enabled(bool(patch.pop("autostart")))
        if "hotkey" in patch and patch["hotkey"] not in shell.HOTKEYS:
            patch.pop("hotkey")
        for k, v in patch.items():
            if k in allowed:
                setattr(self.settings, k, bool(v) if k in self._BOOLS else v.strip()[:40] if isinstance(v, str) else v)
        if "hotkey" in patch and self._desk and self._desk.shell:
            self._desk.shell.set_hotkey(self.settings.hotkey)
        if {"lang", "name"} & set(patch or {}):
            self.settings.profile_at = time.time()
        if set(SYNC_PREFS) & set(patch or {}):
            self.settings.prefs_at = time.time()
        if self.settings.lang not in LANGS:
            self.settings.lang = "en"
        if self.settings.mode not in ("cloud", "local", "auto"):
            self.settings.mode = "cloud"
        self.settings.save()
        if {"provider", "mode", "local_fallback"} & set(patch or {}):
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

    def _pc_tools(self) -> list:
        if not self.settings.pc_access:
            return []
        from .apps import app_tools
        from .pcfiles import place_tools, space_tools
        from .pcsys import system_tools
        out = []
        for group, make in (("pc", lambda: place_tools(self.places)), ("pc", lambda: space_tools(self.places) if self.settings.space_help else []),
                            ("apps", lambda: app_tools(self.apps)),
                            ("sys", lambda: system_tools(self.system))):
            try:
                tools = make()
            except Exception:                              # noqa: BLE001  a missing tool never breaks the chat
                tools = []
            for tl in tools:
                tl.group = group
            out += tools
        return out

    def pc_undo(self, sort_id: str) -> dict:
        """The Undo button of a finished sort card (works after a restart too: the history keeps the moves)."""
        entry = self.history.find_undo("undo", str(sort_id))
        if entry and not entry["undone"] and entry.get("undo"):
            self.places.undo.pop(str(sort_id), None)
            return self.history_undo(entry["id"])
        lang = self.settings.lang
        return {"ok": False, "text": t("This sort can't be undone any more (Lanterna was restarted or it was undone already).", lang)}

    # ---------------------------------------------------------------- what Lanterna did
    def history_list(self) -> list[dict]:
        """Confirmed changes on this computer, newest first, in the interface language."""
        lang = self.settings.lang
        return [{"id": x["id"], "kind": x["kind"], "at": x["at"], "undone": x["undone"], "note": x.get("note", ""),
                 "can_undo": bool(x.get("undo")) and not x["undone"],
                 "title": action_title(x["kind"], x.get("details", {}), x.get("result", ""), lang, done=True)}
                for x in self.history.items()]

    def history_clear(self) -> list[dict]:
        self.history.clear()
        return []

    def history_undo(self, hid: str) -> dict:
        """Undo one change from the history. Files come back, settings switch back, a program is removed again."""
        from . import history as hist
        from .pcfiles import restore_from_trash
        lang = self.settings.lang
        x = self.history.get(str(hid))
        if not x or x["undone"] or not x.get("undo"):
            return {"ok": False, "text": t("This change can't be undone.", lang)}
        u = x["undo"]
        try:
            if u["type"] == "moves":
                back, left = hist.undo_moves(u["moves"], self.places.roots())
                text = t("{n} files are back where they were.", lang, n=back)
                if left:
                    text += " " + t("{n} had been moved or changed since and stayed.", lang, n=left)
                ok = back > 0 or not left
            elif u["type"] == "trash":
                back, gone = restore_from_trash(u["paths"])
                text = t("{n} files are back from the Recycle Bin.", lang, n=back)
                if gone:
                    text += " " + t("{n} weren't in the Recycle Bin any more (or something with that name is there again).", lang, n=gone)
                ok = back > 0
            elif u["type"] == "rmdir":
                ok = hist.undo_rmdir(u["path"])
                text = t("The folder was removed." if ok else "The folder isn't empty any more, so it stayed.", lang)
            elif u["type"] == "restore_backup":
                ok = hist.undo_restore_backup(u["path"], u["backup"])
                text = t("The old version is back." if ok else "The saved old version is gone.", lang)
            else:
                propose = {"theme": lambda: self.system.propose_theme(u["to"]),
                           "power": lambda: self.system.propose_power(u["to"]),
                           "startup": lambda: self.system.propose_startup(u["name"], u["on"]),
                           "app": lambda: self.apps.propose(u["op"], u["id"], u.get("source", ""))}[u["type"]]
                a = self.actions.run_now(propose)
                ok = bool(a and a.state == "done")
                text = (t("Changed back.", lang) if ok else
                        t("Couldn't do it: {error}", lang, error=(a.result if a else "") or "?"))
        except Exception as e:                               # noqa: BLE001  shown to the user, the entry stays
            return {"ok": False, "text": t("Couldn't do it: {error}", lang, error=str(e)[:200])}
        if ok:
            self.history.mark(x["id"], text)
        return {"ok": ok, "text": text}

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
            quiet.open_url(url)
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
        extra = []
        if include_info:
            from . import doctor
            try:                                     # the quick checks (no network): what works on this computer
                extra = ["Check:"] + ["  " + ln for ln in doctor.summary(self._last_doctor or doctor.run(self, network=False))]
            except Exception:                        # noqa: BLE001  a report must never fail because of a check
                extra = []
        return bugreport.compose(text, bool(include_info), self.settings, model, extra)

    def doctor(self, network: bool = True) -> dict:
        """Check Lanterna: every part with ok / warn / fail and a plain sentence, plus English text to copy."""
        from . import doctor
        checks = doctor.run(self, network=bool(network))
        if network:
            self._last_doctor = checks
        lang = self.settings.lang
        rows = [{"title": t(c.title, lang), "status": c.status, "detail": t(c.detail, lang, **c.vars) if c.detail else ""}
                for c in checks]
        worst = "fail" if any(c.status == "fail" for c in checks) else "warn" if any(c.status == "warn" for c in checks) else "ok"
        return {"checks": rows, "worst": worst, "text": "\n".join(doctor.summary(checks))}

    def open_mail(self, url: str) -> bool:
        """Opens the user's mail app with the ready letter; they press Send themselves."""
        if not bugreport.valid_mailto(url):
            return False
        quiet.open_url(url)
        return True

    # ---------------------------------------------------------------- models
    def _get_router(self, refresh: bool = False) -> Router:
        with self._lock:
            if self._router is None or refresh:
                s = self.settings
                cands = get_models(s.provider, refresh=refresh, mode=s.mode, picks=s.local_models,
                                   fallback=s.local_fallback)
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
            kind = updates.install_kind()
            self._update_asset = (updates.setup_asset(res) if kind == "installer" else
                                  updates.pipx_asset(res, kind) if kind == "pipx" else None)
            res["auto_kind"] = "pipx" if self._update_asset and self._update_asset.get("pipx") else "setup"
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
                "pulls": self._downloads.state(), "fallback": self.settings.local_fallback,
                "can_install": not ver and "winget" in self.apps.managers()}

    def install_ollama(self) -> dict:
        """Settings → Local models → Install Ollama (Windows, winget): after the user confirmed in the dialog."""
        lang = self.settings.lang
        if "winget" not in self.apps.managers():
            return {"ok": False, "text": t("Install it from the Ollama website.", lang)}
        a = self.actions.run_now(lambda: self.apps.propose("install", "Ollama.Ollama", "winget"))
        if not a or a.state != "done":
            return {"ok": False, "text": t("Couldn't do it: {error}", lang, error=(a.result if a else "") or "?")}
        try:
            self.history.add(a.kind, a.details, a.result, a.undo)
        except OSError:
            pass
        self._router = None
        return {"ok": True, "text": t("Ollama is installed. Now download a model below.", lang)}

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
        from . import sent
        out, lang = [], self.settings.lang
        upto = self.store.summary(int(tid))[1] if self.settings.compact_chats else 0
        for i, m in enumerate(self.store.messages(int(tid))):
            if upto and i == upto:
                m["after_summary"] = True                   # the window draws "older messages are summarized" here
            if m["role"] == "user":
                m = {**m, "content": _short_files(m["content"])}
            m["sent"] = sent.view(m.pop("sent", ""), lang) if m["role"] == "assistant" else []
            out.append(m)
        return out

    def rename_thread(self, tid: int, title: str) -> bool:
        self.store.rename(int(tid), title)
        return True

    def wait_title(self, tid: int, timeout: float = 10) -> str:
        """After the first answer: waits (a few seconds at most) for the model-written chat name, then returns
        the chat's title. The window and the terminal call it so the list shows the new name."""
        ev = self._titling.get(int(tid))
        if ev:
            ev.wait(timeout)
        th = self.store.thread(int(tid))
        return th["title"] if th else ""

    def _compact(self, tid: int, router: Router, old: str, upto: int, total: int) -> None:
        """Background: the older part of a long chat becomes a summary; the newest KEEP_RECENT stay as they are."""
        try:
            msgs = self.store.messages(tid)
            new_upto = min(total, len(msgs)) - KEEP_RECENT
            text = summarize(router.quick, old, msgs[upto:new_upto]) if new_upto > upto else ""
            if text and self.store.summary(tid)[1] == upto:   # nobody else summarized it meanwhile
                self.store.set_summary(tid, text, new_upto)
        except Exception as e:                              # noqa: BLE001  the chat goes on without it
            bugreport.remember_error(type(e).__name__, str(e))

    def wait_follow_ups(self, tid: int, timeout: float = 15) -> list[str]:
        """Up to 3 follow-up messages for the last answer of this chat ([] if none came in time)."""
        item = self._follow.get(int(tid))
        if not item:
            return []
        item[0].wait(timeout)
        return list(item[1])

    def _suggest(self, tid: int, router: Router, question: str, reply: str, out: list[str], ev: threading.Event) -> None:
        try:
            out += follow_ups(router.quick, question, reply)
        except Exception as e:                              # noqa: BLE001  never worth an error
            bugreport.remember_error(type(e).__name__, str(e))
        finally:
            ev.set()

    def _start_side_jobs(self, st: "_Stream", tid: int, router: Router, question: str, reply: str, first: bool) -> None:
        """After an answer: the chat's name (first answer) and follow-up buttons, both from a fast side model."""
        th = self.store.thread(tid)
        if first and self.settings.ai_titles and th:
            self._titling[tid] = threading.Event()
            st.titling = True
            threading.Thread(target=self._name_chat, args=(tid, router, question, reply, th["title"]),
                             daemon=True).start()
        self._follow.pop(tid, None)
        side = router.quick_order()
        # follow-ups come after every answer: only from an online model that isn't Gemini (its limit is for
        # answers), and not while a card waits for the user's Confirm
        if (self.settings.follow_ups and side and side[0].provider != "gemini" and not PROVIDERS[side[0].provider].local
                and not st.cards and not st.questions):
            ev, out = threading.Event(), []
            self._follow[tid] = (ev, out)
            st.suggesting = True
            threading.Thread(target=self._suggest, args=(tid, router, question, reply, out, ev), daemon=True).start()
        # memory that updates itself (off by default): only when the user said something about themself,
        # never with Gemini (its limit is for answers); a local side model is fine (it stays on this PC)
        self._learned.pop(tid, None)
        if (self.settings.auto_memory and side and side[0].provider != "gemini" and about_me(question)
                and not st.questions):
            ev2, got = threading.Event(), []
            self._learned[tid] = (ev2, got)
            st.learning = True
            threading.Thread(target=self._learn, args=(router, question, reply, got, ev2), daemon=True).start()

    def wait_memory(self, tid: int, timeout: float = 20) -> list[dict]:
        """Facts the side model just added to Memory after the last answer: [{"id", "text"}] (the UI offers Undo)."""
        item = self._learned.get(int(tid))
        if not item:
            return []
        item[0].wait(timeout)
        return list(item[1])

    def _learn(self, router: Router, question: str, reply: str, out: list[dict], ev: threading.Event) -> None:
        try:
            for text in learn_facts(router.quick, question, reply, [f["text"] for f in self.store.facts()]):
                fid = self.store.add_fact(text)
                if fid:
                    out.append({"id": fid, "text": text})
        except Exception as e:                              # noqa: BLE001  memory is never worth an error
            bugreport.remember_error(type(e).__name__, str(e))
        finally:
            ev.set()

    def _name_chat(self, tid: int, router: Router, question: str, reply: str, auto: str) -> None:
        """Background: a fast side model names the chat, unless the user renamed it meanwhile."""
        try:
            title = chat_title(router.quick, question, reply)
            th = self.store.thread(tid)
            if title and th and th["title"] == auto:
                self.store.rename(tid, title)
        except Exception as e:                              # noqa: BLE001  a name is never worth an error
            bugreport.remember_error(type(e).__name__, str(e))
        finally:
            ev = self._titling.pop(tid, None)
            if ev:
                ev.set()

    def delete_thread(self, tid: int) -> bool:
        self.store.delete_thread(int(tid))
        if self.settings.chat_dirs.pop(str(int(tid)), None) is not None:
            self.settings.save()
        return True

    def _undo_last(self, tid: int) -> str:
        """Takes back the last question (and its answer, if there is one); returns the question as it was saved."""
        msgs = self.store.messages(tid)
        if msgs and msgs[-1]["role"] == "assistant" and len(msgs) > 1 and msgs[-2]["role"] == "user":
            self.store.trim_tail(tid, 2)
            return msgs[-2]["content"]
        if msgs and msgs[-1]["role"] == "user":                 # a question left without an answer (an error)
            self.store.trim_tail(tid, 1)
            return msgs[-1]["content"]
        return ""

    # ---------------------------------------------------------------- saving chats (export)
    def _save_folder(self):
        from pathlib import Path
        d = self.places.folders().get("downloads")
        return d if d and d.is_dir() else Path.home()

    # ---------------------------------------------------------------- voice input
    def voice_status(self) -> dict:
        from . import voice
        s = self.settings
        return {"engine": s.voice, "model": s.voice_model, "recording": self._recorder.recording,
                "has_groq": bool(keys.get_key("groq")), "local": self._whisper.status(s.voice_model),
                "models": [{"id": k, "mb": round(v[2] / 1e6)} for k, v in voice.MODELS.items()],
                "engine_mb": round(voice.ENGINE_FILES.get(__import__("sys").platform, ("", "", 0))[2] / 1e6)}

    def voice_start(self) -> dict:
        """The mic button: starts recording (nothing is sent anywhere until voice_stop)."""
        from . import voice
        if self.settings.voice not in ("groq", "local"):
            return {"ok": False, "error": "off"}
        if self.settings.voice == "local" and not all(self._whisper.status(self.settings.voice_model)[k] for k in ("engine", "model")):
            return {"ok": False, "error": "no_engine"}
        if self.settings.voice == "groq" and not keys.get_key("groq"):
            return {"ok": False, "error": "no_key"}
        try:
            self._recorder.start()
        except voice.VoiceError as e:
            return {"ok": False, "error": e.kind}
        return {"ok": True}

    def voice_stop(self) -> dict:
        """Stops recording and turns the speech into text with the chosen engine."""
        from . import voice
        wav = self._recorder.stop()
        if voice.speech_seconds(wav) < 0.4:
            return {"ok": False, "error": "empty", "text": ""}
        lang = self.settings.lang
        try:
            if self.settings.voice == "local":
                text = self._whisper.transcribe(wav, self.settings.voice_model, lang)
            else:
                text = voice.transcribe_groq(wav, keys.get_key("groq") or "", lang)
        except voice.VoiceError as e:
            bugreport.remember_error("VoiceError", str(e))
            return {"ok": False, "error": e.kind, "text": ""}
        return {"ok": bool(text), "error": "" if text else "empty", "text": text}

    def voice_cancel(self) -> None:
        self._recorder.stop(cancel=True)

    def voice_setup(self) -> dict:
        """Settings → Voice → Download: the whisper.cpp engine and the chosen model (pinned files, checked)."""
        return self._whisper.setup(self.settings.voice_model)

    def voice_setup_cancel(self) -> None:
        self._whisper.cancel()

    # ---------------------------------------------------------------- MCP servers (Settings → MCP servers)
    def mcp_status(self) -> dict:
        return self.mcp.status()

    def mcp_enable(self, on: bool) -> dict:
        """Called only after the risk window (the UI shows it; "I understand" is required)."""
        self.mcp.set_enabled(bool(on))
        return self.mcp.status()

    def mcp_add(self, item: dict) -> dict:
        """item: {name, kind: stdio|http, where: command line or URL, secret_name, secret}. Secrets go to the
        system's secure store: an env variable for a program, a header (Authorization: Bearer …) for a web address."""
        from . import mcp
        if not self.mcp.cfg["enabled"]:
            return {"ok": False, "error": "MCP servers are off."}
        item = item if isinstance(item, dict) else {}
        kind = "http" if item.get("kind") == "http" else "stdio"
        secret, sname = str(item.get("secret") or "").strip(), str(item.get("secret_name") or "").strip()
        env, headers = {}, {}
        if secret:
            if kind == "http":
                headers[sname or "Authorization"] = secret if sname or secret.lower().startswith("bearer ") else "Bearer " + secret
            elif re.match(r"^[A-Za-z_][A-Za-z0-9_]{0,60}$", sname):
                env[sname] = secret
            else:
                return {"ok": False, "error": "Name the variable for the key, for example GITHUB_TOKEN."}
        try:
            sid = self.mcp.add(str(item.get("name") or ""), kind, str(item.get("where") or ""), env, headers)
        except mcp.McpError as e:
            return {"ok": False, "error": str(e)}
        except Exception as e:                                # noqa: BLE001  (secure store unavailable)
            return {"ok": False, "error": f"{e.__class__.__name__}: {e}"}
        return {"ok": True, "id": sid, **self.mcp.status()}

    def mcp_import(self, text: str) -> dict:
        """Settings → MCP servers → Paste JSON: the {"mcpServers": {...}} block many server pages show."""
        from . import mcp
        if not self.mcp.cfg["enabled"]:
            return {"ok": False, "error": "MCP servers are off."}
        try:
            found = mcp.parse_import(str(text or ""))
            for s in found:
                self.mcp.add(s["name"], s["kind"], s.get("url") or s.get("command"), s.get("env"), s.get("headers"))
        except mcp.McpError as e:
            return {"ok": False, "error": str(e)}
        return {"ok": True, "added": len(found), **self.mcp.status()}

    def mcp_update(self, sid: str, fields: dict) -> dict:
        fields = {k: v for k, v in (fields or {}).items() if k in ("on", "allow")}
        self.mcp.update(str(sid), **fields)
        return self.mcp.status()

    def mcp_remove(self, sid: str) -> dict:
        self.mcp.remove(str(sid))
        return self.mcp.status()

    def mcp_restart(self, sid: str) -> dict:
        self.mcp.restart(str(sid))
        return self.mcp.status()

    # ---------------------------------------------------------------- always at hand (Windows window app)
    def desktop_status(self) -> dict:
        """For Settings: is the tray there, did Windows give us the hotkey, does Lanterna start with Windows."""
        from . import autostart, shell
        sh = self._desk.shell if self._desk else None
        return {"available": bool(sh and sh.hwnd), "hotkey": self.settings.hotkey, "hotkey_ok": bool(sh and sh.hotkey_ok),
                "hotkeys": [{"id": h, "label": shell.pretty_hotkey(h)} for h in shell.HOTKEYS],
                "autostart": autostart.enabled(), "quick": False}

    def quick_hide(self) -> None:
        if self._desk:
            self._desk.hide_quick()

    def open_in_main(self, tid: int | None = None) -> None:
        if self._desk:
            threading.Thread(target=self._desk.open_in_main, args=(int(tid) if tid else None,), daemon=True).start()

    def screenshot(self) -> dict:
        """The screen as an attachment for the quick window ({} when there is no window app)."""
        return self._desk.screenshot() if self._desk else {}

    def export_chat(self, tid: int) -> dict:
        """The chat as a Markdown file in Downloads."""
        from . import export
        th = self.store.thread(int(tid))
        if not th:
            return {"ok": False}
        msgs = [{**m, "content": _short_files(m["content"])} for m in self.store.messages(int(tid))]
        if not msgs:
            return {"ok": False}
        p = export.free_path(self._save_folder(), export.safe_name(th["title"]), ".md")
        p.write_text(export.chat_markdown(th["title"], msgs, self.settings.lang, self.settings.name), encoding="utf-8")
        self._saved.add(str(p))
        return {"ok": True, "path": str(p), "name": p.name}

    def export_all(self) -> dict:
        """A backup of all chats, memory and reminders as one JSON file in Downloads."""
        from . import export
        p = export.write_backup(self.store, self._save_folder())
        self._saved.add(str(p))
        return {"ok": True, "path": str(p), "name": p.name}

    def show_saved(self, path: str) -> bool:
        """Opens the folder of a file Lanterna has just saved (only those: the window can't open any path)."""
        from pathlib import Path
        if str(path) not in self._saved:
            return False
        from . import pcfiles
        pcfiles._open_in_file_manager(Path(path))
        return True

    def edit_last(self, tid: int) -> dict:
        """"Edit": the last question and its answer go; the question comes back to the message box."""
        if any(not s.done for s in self._streams.values()):
            return {"ok": False, "text": ""}
        return {"ok": True, "text": _short_files(self._undo_last(int(tid)))}

    def send(self, tid: int, text: str, files: list[dict] | None = None, again: bool = False) -> dict:
        """again: answer the last question again (Retry) — it replaces the old answer instead of piling up."""
        text = (text or "").strip()
        tid = int(tid)
        if again and self.store.thread(tid):
            old = self._undo_last(tid)
            if not text and not files:
                text = old
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
        st.files = list(prep.names)
        threading.Thread(target=self._run, args=(sid, tid, full, history, prep.images), daemon=True).start()
        return {"ok": True, "stream": sid}

    def _run(self, sid: str, tid: int, text: str, history: list[dict], images: list[str] | None = None) -> None:
        st = self._streams[sid]
        first = not history                                 # the chat's first answer (ask() extends history)
        summary, upto = self.store.summary(tid) if self.settings.compact_chats else ("", 0)
        if upto > len(history):                             # messages were removed: the summary no longer fits
            summary, upto = "", 0
        total = len(history) + 2                            # with this question and its answer
        earlier = min(len(history) - upto, MAX_HISTORY)     # earlier messages that really go to the model
        self.actions.bind(st.cards, tid)
        try:
            router = self._get_router()
            conv = Conversation(router, self.settings.name, history=history[upto:], toolbox=self.toolbox, summary=summary,
                                lang=self.settings.lang, ask_first=self.settings.ask_first,
                                ask_header=t("Questions for you:", self.settings.lang),
                                auto_cloud=self.settings.mode == "auto" and self.settings.auto_cloud)
            for p in conv.ask(text, images or None):
                with st.lock:
                    if isinstance(p, Switched):
                        st.notes.append(p.to.label)
                    elif isinstance(p, ToolUse):
                        st.tools.append(f"{p.label} {p.name}")
                        st.used.append((p.name, p.arguments))
                        st.steps.tool(p.name, p.arguments)
                    elif isinstance(p, Questions):
                        st.questions = p.items
                    elif isinstance(p, Thought):
                        st.steps.thought(p.text)
                    else:
                        st.pieces.append(p)
            if not conv.last_reply.strip():
                raise ProviderError("empty", "the model sent no answer")
            from . import sent
            cur = router.current
            st.sent = sent.dumps(sent.build(
                cur.label if cur else "", bool(cur and PROVIDERS[cur.provider].local), earlier,
                bool(self.settings.name), len(self.store.facts()),
                [n for n in st.files if not n.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".gif"))],
                len(images or []), st.used, summary=bool(summary)))
            self.store.add(tid, "assistant", conv.last_reply, cur.label if cur else "", st.sent)
            self._start_side_jobs(st, tid, router, text, conv.last_reply, first)
            if self.settings.compact_chats and summary_due(total, upto):
                threading.Thread(target=self._compact, args=(tid, router, summary, upto, total), daemon=True).start()
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
                from . import sent
                out = {"final": st.pieces[0], "notes": st.notes, "tools": st.tools, "cards": list(st.cards),
                       "sent": sent.view(st.sent, self.settings.lang), "titling": st.titling, "suggesting": st.suggesting, "learning": st.learning, "questions": st.questions,
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
        if a.state == "done" and not getattr(a, "logged", False):
            a.logged = True                                 # Settings → What Lanterna did
            try:
                self.history.add(a.kind, a.details, a.result, a.undo, a.tid)
            except OSError:
                pass
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

    # ---------------------------------------------------------------- regular tasks
    def check_tasks(self, now: float | None = None) -> int:
        """Starts the tasks whose time has come (each in its own thread); a run missed by hours is skipped."""
        from . import tasks as tk
        now = time.time() if now is None else now
        started = 0
        for task in self.store.due_tasks(now):
            nxt = tk.next_run(task["every"], task["at"], task["day"], dt.datetime.fromtimestamp(now)).timestamp()
            self.store.update_task(task["id"], next=nxt)   # moved first: a slow run is never started twice
            if now - task["next"] > tk.LATE_LIMIT:
                continue
            threading.Thread(target=self._run_task, args=(task,), daemon=True).start()
            started += 1
        return started

    def _run_task(self, task: dict) -> str:
        """One run: the model does the task with safe tools only; the result goes to the task's chat,
        a notification and the in-app notice. "" when there is nothing to tell (or it failed)."""
        from . import tasks as tk
        lang = self.settings.lang
        try:
            conv = Conversation(self._get_router(), self.settings.name, lang=lang,
                                toolbox=tk.safe_toolbox(self.store, lambda: lang))
            for _ in conv.ask(tk.TASK_SYSTEM + "\n\n" + tk.prompt(task, dt.datetime.now())):
                pass
            reply = (conv.last_reply or "").strip()
            model = conv.router.current.label if conv.router.current else ""
        except Exception as e:                              # noqa: BLE001  no internet, no keys…: try next time
            self.store.update_task(task["id"], last=time.time(), last_result="⚠ " + str(e)[:200])
            bugreport.remember_error(type(e).__name__, str(e))
            return ""
        if not reply or tk.is_skip(reply):
            self.store.update_task(task["id"], last=time.time(), last_result="")
            return ""
        th = task.get("thread")
        if not th or not self.store.thread(th):
            th = self.store.new_thread("🔁 " + task["text"][:60])
        self.store.add(th, "assistant", reply, model)
        self.store.update_task(task["id"], last=time.time(), last_result=reply[:300], thread=th)
        notify("Lanterna 🔁", reply[:300])
        with self._lock:
            self._alerts.append({"kind": "task", "text": reply[:240], "tid": th})
        return reply

    def task_list(self) -> list[dict]:
        from . import tasks as tk
        lang = self.settings.lang
        tr = lambda s, **kw: t(s, lang, **kw)              # noqa: E731
        out = []
        for x in self.store.tasks():
            out.append({**x, "when": tk.describe(x, tr),
                        "next_text": "" if x["paused"] else time.strftime("%d.%m %H:%M", time.localtime(x["next"])),
                        "last_text": time.strftime("%d.%m %H:%M", time.localtime(x["last"])) if x["last"] else ""})
        return out

    def task_add(self, item: dict) -> dict:
        """The Settings form: {text, every, at, day, only_if}."""
        from . import tasks as tk
        item = item or {}
        try:
            tk.add(self.store, item.get("text", ""), item.get("every", "day"), item.get("at", "08:00"),
                   int(item.get("day") or 0), item.get("only_if", ""), dt.datetime.now())
        except ValueError as e:
            return {"ok": False, "error": str(e), "tasks": self.task_list()}
        return {"ok": True, "tasks": self.task_list()}

    def task_delete(self, task_id: int) -> list[dict]:
        self.store.delete_task(int(task_id))
        return self.task_list()

    def task_pause(self, task_id: int, paused: bool) -> list[dict]:
        from . import tasks as tk
        x = self.store.task(int(task_id))
        if x:
            nxt = tk.next_run(x["every"], x["at"], x["day"], dt.datetime.now()).timestamp()
            self.store.update_task(x["id"], paused=int(bool(paused)), next=nxt)
        return self.task_list()

    def task_run(self, task_id: int) -> dict:
        """"Run now" in Settings: does the task at once and says what came out."""
        x = self.store.task(int(task_id))
        if not x:
            return {"ok": False, "text": "", "tasks": self.task_list()}
        text = self._run_task(x)
        x = self.store.task(int(task_id)) or {}
        failed = str(x.get("last_result", "")).startswith("⚠")
        return {"ok": not failed, "text": text or x.get("last_result", ""), "tid": x.get("thread"), "tasks": self.task_list()}

    # ---------------------------------------------------------------- weekly tidy-up and a full disk (both opt-in)
    def maintenance(self, now: float | None = None) -> list[dict]:
        """Settings → Computer: once a week a sort card for Downloads; a note when the disk is almost full."""
        now = time.time() if now is None else now
        s, lang, out = self.settings, self.settings.lang, []
        if not s.pc_access:
            return out
        if s.tidy_weekly and now - s.tidy_last >= 7 * 86400:
            s.tidy_last = now
            s.save()
            n = self.places.loose_count("downloads") if "downloads" in self.places.folders() else 0
            if n >= 5:
                tid = self.store.new_thread(t("Weekly tidy-up", lang))
                sink: list = []
                self.actions.bind(sink, tid)
                try:
                    self.places.propose_sort("downloads", "", "type")
                except Exception:                           # noqa: BLE001  nothing to sort after all
                    sink = []
                finally:
                    self.actions.bind(None, 0)
                for c in sink:
                    a = self.actions.get(c["id"])
                    if a:
                        a.ttl = 3 * 86400                   # the user may see it days later
                text = t("A week has passed: {n} new files are lying loose in Downloads. Shall I sort them into folders? "
                         "Check the card below. (Turn this off in Settings → Computer.)", lang, n=n)
                self.store.add(tid, "assistant", text)
                notify("Lanterna 🧹", t("{n} new files in Downloads: sort them?", lang, n=n))
                out.append({"id": f"tidy-{int(now)}", "text": t("{n} new files in Downloads: sort them?", lang, n=n),
                            "tid": tid, "kind": "tidy"})
        if s.space_help and now - s.space_last >= 86400:
            s.space_last = now
            s.save()
            low = []
            for name, p in self.places.folders().items():
                try:
                    du = shutil.disk_usage(p)
                except OSError:
                    continue
                if (du.free < du.total * 0.08 or du.free < 5 * 1024 ** 3) and (du.total, du.free) not in [x[1] for x in low]:
                    low.append((name, (du.total, du.free)))
            if low:
                free = low[0][1][1] / 1024 ** 3
                msg = t("The disk is almost full: {gb} GB left. Ask me “what takes up space?” and I'll show what can go.",
                        lang, gb=f"{free:.1f}")
                notify("Lanterna 💾", msg)
                out.append({"id": f"space-{int(now)}", "text": msg, "kind": "space"})
        if out:
            with self._lock:
                self._alerts += out
        return out

    def _reminder_loop(self) -> None:
        last_check = 0.0
        while True:
            try:
                self.check_reminders()
                self.check_tasks()
                if time.time() - last_check > 3600:
                    last_check = time.time()
                    self.maintenance()
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
            "github_new_repo": ("Create the repository {name} on GitHub", "Opened GitHub to create {name}"),
            "pc_sort": ("Sort {count} files in {place}", "Sorted {count} files in {place}"),
            "pc_move": ("Move {count} items to {to}", "Moved {count} items to {to}"),
            "pc_rename": ("Rename {path} → {to}", "Renamed {path} → {to}"),
            "pc_mkdir": ("Create the folder {path}", "Created the folder {path}"),
            "pc_trash": ("Move {count} items to the Recycle Bin", "Moved {count} items to the Recycle Bin"),
            "app_install": ("Install {name}", "Installed {name}"), "app_upgrade": ("Update {name}", "Updated {name}"),
            "app_uninstall": ("Remove {name}", "Removed {name}"),
            "sys_theme": (f"Switch to the {d.get('theme')} theme", f"Switched to the {d.get('theme')} theme"),
            "sys_power": ("Switch the power plan to {name}", "Power plan: {name}"),
            "mcp_call": ("Use {name}", "Used {name}"),
            "sys_startup": (("Start {name} with the computer", "{name} starts with the computer") if d.get("on") else
                            ("Don't start {name} with the computer", "{name} no longer starts with the computer"))}
    place = t(str(d.get("place", "")).title(), lang) if d.get("place") else ""
    to = d.get("to", "")
    if kind == "pc_move" and d.get("to_place"):
        to = t(str(d["to_place"]).title(), lang) + ("" if to in ("", ".") else "/" + to)
    out = t(keys.get(kind, ("Change", "Done"))[int(done)], lang, place=place,
            **{k: str(to if k == "to" else d.get(k, "")) for k in ("path", "to", "name", "repo", "count")})
    if kind == "write_replace" and "(" in (result or ""):
        out += " " + result[result.index("("):]
    return out + (f" — {link}" if link.startswith("https://") else "")


def card_text(kind: str, d: dict, lang: str) -> str:
    """The body of a card in plain text (terminal app)."""
    lines = []
    if kind == "pc_sort":
        for g in d.get("groups", []):
            lines.append(f"📁 {g['to']} — {g['count']}: " + ", ".join(g["files"][:6]) + (" …" if g["count"] > 6 else ""))
        if d.get("skipped"):
            lines.append(t("{n} files still downloading are left alone.", lang, n=d["skipped"]))
        lines.append(t("You can undo the sort afterwards.", lang))
    elif kind in ("pc_move", "pc_trash"):
        files = d.get("files", [])
        lines.append(", ".join(files[:12]) + (f" … +{d.get('count', 0) - 12}" if d.get("count", 0) > 12 else ""))
        if kind == "pc_trash":
            if d.get("reason"):
                lines.append(t("Reason: {r}", lang, r=d["reason"]))
            lines.append(t("They go to the Recycle Bin: you can restore them from there.", lang))
    elif kind.startswith("app_"):
        bits = [t("Publisher: {p}", lang, p=d["publisher"]) if d.get("publisher") else "",
                t("Version {v}", lang, v=d["version"]) if d.get("version") else "", t("from {s}", lang, s=d.get("source", ""))]
        lines.append(" · ".join(b for b in bits if b))
        if d.get("description"):
            lines.append(d["description"][:200])
        lines.append(f"$ {d.get('command', '')}")
        if d.get("admin"):
            lines.append(t("Windows may ask for administrator rights." if d.get("source") == "winget"
                           else "The system will ask for your password.", lang))
    elif kind == "sys_startup":
        lines.append(d.get("command", "")[:160])
        lines.append(t("It can be turned back on the same way.", lang))
    elif kind in ("sys_theme", "sys_power") and d.get("was"):
        lines.append(t("Now: {x}", lang, x=t(d["was"], lang)))
    elif kind == "mcp_call":
        lines.append(t("MCP server: {s}", lang, s=d.get("server", "")) + " · " +
                     t("a web address" if d.get("kind") == "http" else "a program on this computer", lang))
        lines.append(t("What goes to the server:", lang))
    return "\n".join(x for x in lines if x)


_FILE_BLOCK = re.compile(r"\[File: ([^\]\n]+)\]\n```\n.*?\n```(?:\n\[…file cut, too long\])?", re.S)
_PHOTO = re.compile(r"\[Photo: ([^\]\n]+)\]")


def _short_files(text: str) -> str:
    return _PHOTO.sub(r"🖼 \1", _FILE_BLOCK.sub(r"📎 \1", text))
