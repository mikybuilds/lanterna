"""Takes the README screenshots in English: window app (headless Chrome) and terminal app (Textual SVG -> PNG).

    GROQ_API_KEY=... python tools/screenshots.py     # writes docs/screen-*.png

Uses a temporary settings folder, so your own chats, memory and keys are never shown. With a Groq key in the
environment it first has a short real conversation, so the chat screenshots show a real answer.
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
CHROME = [r"C:\Program Files\Google\Chrome\Application\chrome.exe", "google-chrome", "chromium", "chromium-browser"]
QUESTIONS = ["Hi! Give me 3 quick tips for learning new words in a foreign language, as a short list.",
             "What's 17.5% of 2380?"]


def chrome_shot(chrome: str, url: str, out: Path, size: str, profile: str) -> None:
    subprocess.run([chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars", f"--window-size={size}",
                    "--virtual-time-budget=9000", f"--user-data-dir={profile}", f"--screenshot={out}", url],
                   capture_output=True, timeout=120)
    print(out.name, out.exists())


def talk(api) -> None:
    tid = api.new_thread()["id"]
    for q in QUESTIONS:
        sid = api.send(tid, q)["stream"]
        for _ in range(600):
            p = api.poll(sid)
            if p.get("done"):
                if p.get("error"):
                    print("model error:", p["error"])
                break
            time.sleep(0.1)


async def tui_shots(api, folder: Path) -> None:
    from lanterna.tui import LanternaApp, LocalScreen
    app = LanternaApp(api=api)
    async with app.run_test(size=(110, 34)) as pilot:
        for _ in range(100):
            await pilot.pause(0.1)
            if type(app.screen).__name__ == "ChatScreen" and app.screen.query("#composer"):
                break
        await pilot.pause(1.0)
        app.save_screenshot("tui_chat.svg", path=str(folder))
        api.save_settings({"mode": "auto"})
        app.push_screen(LocalScreen())
        for _ in range(100):
            await pilot.pause(0.1)
            if app.screen.query("#pull-0"):
                break
        await pilot.pause(0.8)
        app.save_screenshot("tui_local.svg", path=str(folder))


def main() -> int:
    home = tempfile.mkdtemp(prefix="lanterna_shots_")
    os.environ["LANTERNA_HOME"] = home
    Path(home, "settings.json").write_text(json.dumps({"lang": "en", "name": "Anna", "mode": "cloud",
                                                       "provider": "groq", "onboarded": True}), encoding="utf-8")
    sys.path.insert(0, str(ROOT / "src"))
    from lanterna.app import Api
    from lanterna.gui import make_server

    chrome = next((c for c in CHROME if Path(c).exists() or shutil.which(c)), None)
    if not chrome:
        print("Chrome not found")
        return 1
    api = Api(scheduler=False)
    if os.getenv("GROQ_API_KEY"):
        talk(api)
    srv, url = make_server(api, 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    profile = str(Path(home, "chrome"))
    if os.getenv("GROQ_API_KEY"):
        chrome_shot(chrome, url, DOCS / "screen-chat.png", "1120,760", profile)
    api.save_settings({"mode": "auto"})
    for view, name in {"local": "screen-local.png", "settings": "screen-modes.png", "about": "screen-about.png"}.items():
        chrome_shot(chrome, f"{url}&view={view}", DOCS / name, "1120,780", profile)
    srv.shutdown()

    svg = Path(home, "svg")
    svg.mkdir()
    api.save_settings({"mode": "cloud"})                 # the chat answers above came from the cloud
    asyncio.run(tui_shots(api, svg))
    for name, out in (("tui_chat.svg", "screen-terminal.png"), ("tui_local.svg", "screen-terminal-local.png")):
        chrome_shot(chrome, (svg / name).as_uri(), DOCS / out, "1400,1000", profile)
    return 0


if __name__ == "__main__":
    sys.exit(main())
