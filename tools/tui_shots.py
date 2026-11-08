"""Opens every screen of the terminal app in every language, saves an SVG screenshot of each and checks it.

    python tools/tui_shots.py                 # all languages -> tui-shots/<lang>/<screen>.svg
    python tools/tui_shots.py de pl --out x   # only some languages, another folder

Runs offline: a temporary data folder, a fake key vault, a fake model and canned model lists — never your own
chats or keys. Exits with 1 when a screen fails to open, shows an error, or shows English text that has a
translation (a string that was not passed through t()).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

SIZE = (110, 40)
# words that are the same or that also appear inside normal text in another language
SAME = {"ok", "Terminal", "Status", "Version", "Model", "Mode", "Local", "Name", "Service", "Torrents", "Videos", "RAM",
        "Sync", "Score", "GB", "Updates", "Limits", "Programs", "Installed", "Memory", "Desktop", "Download"}
PRODUCTS = ("GitHub Models", "Google Drive")          # names, never translated
ENGLISH_ON_PURPOSE = {"bugpreview"}                   # the bug report is written in English for the developer
# the first screen asks in several languages at once; "Pause" is also a German word (a chat example says "eine Pause")
ALLOWED = {"01-language": {"Choose your language", "Choose", "language"}, "03-chat": {"Pause"},
           "04-settings": {"Documents"}}                     # the backup folder path: Documents/Lanterna backups


def fake_api(home: Path, lang: str, onboarded: bool = True):
    home.mkdir(parents=True, exist_ok=True)
    os.environ["LANTERNA_HOME"] = str(home)
    import httpx
    from lanterna import keys, limits
    from lanterna.app import Api
    from lanterna.i18n import t
    from lanterna.discovery import Candidate
    from lanterna.providers import PROVIDERS, Client
    from lanterna.router import Router
    from lanterna.store import Store

    limits.TRACKER = limits.Limits()
    vault = {"groq": "gsk_fake_key_for_screens"}
    keys.get_key = lambda p: vault.get(p)
    keys.set_key = lambda p, k: vault.__setitem__(p, k)
    keys.delete_key = lambda p: vault.pop(p, None)
    keys.stored_key = lambda p: vault.get(p) or ""

    def reply(req):
        body = "".join(f"data: {json.dumps({'choices': [{'delta': {'content': c}}]})}\n\n" for c in ("Ok", "!"))
        return httpx.Response(200, content=(body + "data: [DONE]\n\n").encode())

    api = Api(store=Store(home / "shots.db"), scheduler=False)
    s = api.settings
    s.lang, s.onboarded, s.sync_asked, s.update_check, s.name = lang, onboarded, True, False, "Mia"
    router = Router([Candidate("groq", "llama-3.3-70b", 90), Candidate("gemini", "gemini-2.5-flash", 80)],
                    client_for=lambda pid: Client(PROVIDERS["groq"], "k", transport=httpx.MockTransport(reply)))
    router.current = router.candidates[0]
    api._get_router = lambda refresh=False: router
    api.doctor = lambda network=True, _d=api.doctor: _d(network=False)
    api.local_status = lambda: {"running": False, "version": "", "models": [], "picks": {}, "pulls": {},
                                "download_page": "https://ollama.com/download", "fallback": True, "can_install": False}
    api.check_update = lambda: {"current": "0.3.4", "latest": "0.3.5", "newer": True, "url": "https://example.org",
                                "notes": ["-"], "steps": [t("Close Lanterna.", lang), t("Open a terminal and run:", lang)],
                                "command": "pipx upgrade lanterna", "download": ""}
    return api


def english_leftovers(lang: str) -> list[tuple[str, re.Pattern]]:
    """English strings that have a different translation: seeing one on screen means t() was skipped."""
    from lanterna import i18n
    out = []
    for key in set(i18n._T) | set(i18n.catalog(lang)):
        tr = i18n.t(key, lang)
        if "{" in key or tr == key or key in SAME or len(key) < 4 or not re.search("[A-Za-z]{3}", key):
            continue
        out.append((key, re.compile(r"(?<![\w-])" + re.escape(key) + r"(?![\w-])")))
    return out


def screen_text(app) -> str:
    parts = []
    for w in app.screen.walk_children(with_self=True):
        if w.id in ENGLISH_ON_PURPOSE:
            continue
        for attr in ("label", "placeholder"):
            v = getattr(w, attr, None)
            if isinstance(v, str) or hasattr(v, "plain"):
                parts.append(getattr(v, "plain", v))
        try:
            r = w.render()
        except Exception:  # noqa: BLE001 - some widgets only render inside a full layout
            continue
        parts.append(getattr(r, "plain", None) or (r if isinstance(r, str) else ""))
    text = "\n".join(p for p in parts if p)
    for name in PRODUCTS:
        text = text.replace(name, "")
    return text


async def shoot(lang: str, out: Path) -> list[str]:
    from lanterna import tui
    problems: list[str] = []
    out.mkdir(parents=True, exist_ok=True)
    leftovers = english_leftovers(lang)

    async def snap(app, pilot, name: str) -> None:
        await pilot.pause(0.6)
        app.save_screenshot(filename=f"{name}.svg", path=str(out))
        text = screen_text(app)
        for key, rx in leftovers:
            if key not in ALLOWED.get(name, ()) and rx.search(text):
                problems.append(f"{lang}/{name}: English text on screen: {key!r}")
        if "Traceback" in text or "Error:" in text:
            problems.append(f"{lang}/{name}: an error is shown")

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:      # Windows keeps the db open a moment
        api = fake_api(Path(tmp) / "a", lang, onboarded=False)
        app = tui.LanternaApp(api=api)
        async with app.run_test(size=SIZE) as pilot:
            await snap(app, pilot, "01-language")
            await pilot.click(f"#lang-{lang}")
            await snap(app, pilot, "02-name")

        api = fake_api(Path(tmp) / "b", lang)
        app = tui.LanternaApp(api=api)
        async with app.run_test(size=SIZE) as pilot:
            for _ in range(100):
                await pilot.pause(0.05)
                if type(app.screen).__name__ == "ChatScreen" and app.screen.query("#composer"):
                    break
            else:
                return problems + [f"{lang}: the chat screen did not open"]
            await snap(app, pilot, "03-chat")
            chat = app.screen
            screens = [("04-settings", tui.SettingsScreen), ("05-models", tui.ModelsScreen),
                       ("06-local", tui.LocalScreen), ("07-history", tui.HistoryScreen),
                       ("08-doctor", tui.DoctorScreen), ("09-about", tui.AboutScreen), ("10-bug", tui.BugScreen),
                       ("11-update", lambda: tui.UpdateScreen(api.check_update())),
                       ("12-key", lambda: tui.KeyScreen("gemini"))]
            for name, make in screens:
                try:
                    await app.push_screen(make())
                    await pilot.pause(1.0)
                    await snap(app, pilot, name)
                    app.pop_screen()
                    await pilot.pause(0.1)
                except Exception as e:  # noqa: BLE001 - report every broken screen, keep going
                    problems.append(f"{lang}/{name}: {type(e).__name__}: {e}")
                    while app.screen is not chat and len(app.screen_stack) > 1:
                        app.pop_screen()
    return problems


def main() -> int:
    from lanterna.i18n import LANGS
    ap = argparse.ArgumentParser()
    ap.add_argument("langs", nargs="*", default=list(LANGS))
    ap.add_argument("--out", default=str(ROOT / "tui-shots"))
    a = ap.parse_args()
    problems = []
    for lang in a.langs:
        found = asyncio.run(shoot(lang, Path(a.out) / lang))
        print(f"{lang}: {len(list((Path(a.out) / lang).glob('*.svg')))} screens, {len(found)} problems")
        problems += found
    for p in problems:
        print("  " + p)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
