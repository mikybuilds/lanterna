"""Takes the README screenshots of the window app with headless Chrome (dev server, temporary settings).

    python tools/screenshots.py            # writes docs/screen-*.png

Uses a temporary settings folder, so your own chats, memory and keys are never shown.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHROME = [r"C:\Program Files\Google\Chrome\Application\chrome.exe", "google-chrome", "chromium", "chromium-browser"]
SHOTS = {"local": "screen-local.png", "settings": "screen-modes.png", "about": "screen-about.png"}


def main() -> int:
    home = tempfile.mkdtemp(prefix="lanterna_shots_")
    os.environ["LANTERNA_HOME"] = home
    Path(home, "settings.json").write_text(json.dumps({"lang": "en", "name": "Anna", "mode": "auto",
                                                       "provider": "groq", "onboarded": True}), encoding="utf-8")
    sys.path.insert(0, str(ROOT / "src"))
    from lanterna.app import Api
    from lanterna.gui import make_server

    srv, url = make_server(Api(scheduler=False), 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    chrome = next((c for c in CHROME if Path(c).exists() or shutil.which(c)), None)
    if not chrome:
        print("Chrome not found")
        return 1
    for view, name in SHOTS.items():
        out = ROOT / "docs" / name
        subprocess.run([chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--window-size=1120,780",
                        "--virtual-time-budget=9000", f"--user-data-dir={home}\\chrome", f"--screenshot={out}",
                        f"{url}&view={view}"], capture_output=True, timeout=120)
        print(out, out.exists())
    srv.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
