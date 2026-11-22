"""The window with made-up chats, for design work and screenshots: no keys, no model requests, nothing changes.

    python tools/ui_demo.py [port] [lang]      # then open http://127.0.0.1:<port>/?token=demo in a browser

It runs on a new temporary settings folder and never reads or writes the system's key vault. Every call that
would reach the internet, open a program or change something on this computer gets a made-up answer instead.
Sending a message plays a made-up answer: the lantern thinks, a tool step counts the disk, the words come in,
and a card waits for Confirm (confirming it changes nothing either).
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8766
LANG = sys.argv[2] if len(sys.argv) > 2 else "uk"
HOME = Path(tempfile.mkdtemp(prefix="lanterna_demo_"))
os.environ["LANTERNA_HOME"] = str(HOME)
sys.path.insert(0, str(ROOT / "src"))

import keyring  # noqa: E402  the system's vault: never read or written here

keyring.get_password = lambda *a, **k: None
keyring.set_password = lambda *a, **k: None
keyring.delete_password = lambda *a, **k: None

from lanterna import keys  # noqa: E402

keys.get_key = lambda p: "demo" if p == "groq" else None     # the window shows one service as set up
keys.stored_key = lambda p: ""
keys.set_key = lambda *a: None
keys.delete_key = lambda *a: None

UK = LANG == "uk"
NAME = "Олена" if UK else "Anna"
MODEL = "Groq · llama-3.3-70b-versatile"
HOUR = 3600

Path(HOME, "settings.json").write_text(json.dumps({
    "lang": LANG, "name": NAME, "mode": "cloud", "provider": "groq", "onboarded": True, "pc_access": True,
    "space_help": True, "update_check": False, "sync_asked": True, "tray_told": True, "follow_ups": True,
}), encoding="utf-8")

from lanterna import __version__, diskmap, gui, plans, sent, sources  # noqa: E402
from lanterna import local as ollama  # noqa: E402
from lanterna.hardware import Hardware, advise  # noqa: E402
from lanterna.app import Api  # noqa: E402
from lanterna.workspace import Action  # noqa: E402

GB = 1024 ** 3

# ---------------------------------------------------------------- the made-up chats
DISK_Q = ("Чому на диску C: майже не лишилось місця? Що можна прибрати?" if UK
          else "Why is my C: drive almost full? What can I remove?")
DISK_A = ("""Порахувала весь диск C:. Зайнято **383 ГБ із 445**, вільно 61 ГБ. Найбільше займає ось що:

| Що | Де | Розмір |
|---|---|---:|
| Гра Cities: Skylines | Steam | 68,9 ГБ |
| Windows | C:\\Windows | 50,8 ГБ |
| Моделі Ollama | .ollama | 43,9 ГБ |
| Кеш відеодрайвера | NVIDIA | 15,9 ГБ |
| Кеш браузера | Chrome | 14,9 ГБ |

**Що можна прибрати без шкоди:**

1. **Кеш відеодрайвера (15,9 ГБ).** Ігри створять його знову, коли він знадобиться.
2. **Моделі Ollama, якими ти не користуєшся.** Їх можна завантажити знову в Налаштуваннях.
3. **Гру, у яку давно не грала.** Steam сам її видалить і зможе завантажити знову.

Windows краще не чіпати: там системні файли. Нижче картка для гри: нічого не зміниться, поки ти не натиснеш «Підтвердити».""" if UK else
          """I counted the whole C: drive. **383 GB of 445** are used, 61 GB are free. These take the most:

| What | Where | Size |
|---|---|---:|
| Cities: Skylines (game) | Steam | 68.9 GB |
| Windows | C:\\Windows | 50.8 GB |
| Ollama models | .ollama | 43.9 GB |
| Graphics driver cache | NVIDIA | 15.9 GB |
| Browser cache | Chrome | 14.9 GB |

**What you can remove safely:**

1. **The graphics driver cache (15.9 GB).** Games make it again when they need it.
2. **Ollama models you don't use.** They can be downloaded again in Settings.
3. **A game you haven't played for a long time.** Steam removes it and can download it again.

Better leave Windows alone: those are system files. The card below is for the game: nothing changes until you press Confirm.""")

SORT_Q = "Розклади мої Завантаження по папках" if UK else "Sort my Downloads into folders"
SORT_A = ("У Завантаженнях 174 файли. Пропоную розкласти їх по папках за типом: нічого не видаляється, файли тільки "
          "переїдуть. Якщо результат не сподобається, сортування можна скасувати одним натиском." if UK else
          "There are 174 files in Downloads. I suggest sorting them into folders by type: nothing is deleted, the files "
          "only move. If you don't like the result, one click undoes the sort.")

PLAN_Q = ("Допоможи спланувати тиждень: іспит у п'ятницю, тренування у вівторок і четвер, і треба купити подарунок мамі."
          if UK else "Help me plan my week: an exam on Friday, training on Tuesday and Thursday, and a present for Mum.")
PLAN_A = ("""Ось тиждень, у якому все вміщається:

### Понеділок
- Повторити перші дві теми до іспиту (1,5 год)
- Подумати, що подарувати мамі: записати 3 ідеї

### Вівторок
- Тренування о 18:00
- Ще одна тема до іспиту вранці

### Середа
- **Купити подарунок** після навчання
- Пробний тест: 40 хвилин без підказок

### Четвер
- Тренування о 18:00
- Легке повторення ввечері, без нових тем

### П'ятниця
- **Іспит.** Лягти спати в четвер до 23:00

Додати нагадування на кожен пункт?""" if UK else
          """Here is a week where everything fits:

### Monday
- Revise the first two exam topics (1.5 h)
- Think about Mum's present: write down 3 ideas

### Tuesday
- Training at 6 pm
- One more exam topic in the morning

### Wednesday
- **Buy the present** after school
- A practice test: 40 minutes, no hints

### Thursday
- Training at 6 pm
- Light revision in the evening, no new topics

### Friday
- **The exam.** Be in bed by 11 pm on Thursday

Shall I add a reminder for each item?""")
PLAN_STEPS = (["Зібрати всі справи тижня", "Розкласти їх по днях", "Додати нагадування", "Перевірити, чи все встигаєш"] if UK
              else ["Collect the week's tasks", "Put them on days", "Add reminders", "Check that everything fits"])

MATH_Q = "Як порахувати площу кола? І покажи, як це зробити на Python." if UK else "How do I find the area of a circle? Show it in Python too."
MATH_A = ("""Площа кола залежить лише від радіуса:

$$S = \\pi r^2$$

де $r$ — радіус, а $\\pi \\approx 3{,}1416$. Для кола з радіусом 3 см виходить приблизно **28,27 см²**.

На Python:

```python
import math

def area(r: float) -> float:
    return math.pi * r ** 2

print(round(area(3), 2))  # 28.27
```

Якщо знаєш діаметр, поділи його навпіл: `area(d / 2)`.""" if UK else
          """The area of a circle depends only on its radius:

$$S = \\pi r^2$$

where $r$ is the radius and $\\pi \\approx 3.1416$. A circle with a 3 cm radius is about **28.27 cm²**.

In Python:

```python
import math

def area(r: float) -> float:
    return math.pi * r ** 2

print(round(area(3), 2))  # 28.27
```

If you know the diameter, halve it first: `area(d / 2)`.""")

WEATHER_Q = "Яка погода буде у Львові на вихідних?" if UK else "What's the weather in Lviv this weekend?"
WEATHER_A = ("У **суботу** у Львові до +8 °C, хмарно, без дощу. У **неділю** прохолодніше, до +5 °C, після обіду можливий "
             "дощ, тож краще взяти парасольку. Вітер слабкий в обидва дні." if UK else
             "On **Saturday** Lviv gets up to +8 °C, cloudy, no rain. **Sunday** is cooler, up to +5 °C, with rain likely "
             "in the afternoon, so take an umbrella. Light wind on both days.")
WEATHER_SRC = {"read": [{"title": "Open-Meteo: Lviv, 7 days" if not UK else "Open-Meteo: Львів, 7 днів",
                         "url": "https://open-meteo.com/en/docs"}],
               "found": [{"title": "Львів — Вікіпедія" if UK else "Lviv - Wikipedia",
                          "url": "https://uk.wikipedia.org/wiki/Львів" if UK else "https://en.wikipedia.org/wiki/Lviv"}]}

OLD = ([("Рецепт сирників", "Як зробити пухкі сирники?", "Візьми сухий сир, одне яйце і дві ложки борошна на 400 г сиру…"),
        ("Чому ноутбук гріється", "Ноутбук дуже гріється, що робити?", "Найчастіше винен пил у вентиляторі або програма, що працює у фоні…"),
        ("Лист англійською", "Переклади лист англійською, ввічливо", "Dear Mr Brown, thank you for your quick reply…"),
        ("Ідеї подарунка мамі", "Що подарувати мамі до 1000 грн?", "Ось кілька ідей, які зазвичай радують…"),
        ("Як працює фотосинтез", "Поясни фотосинтез простими словами", "Рослина бере світло, воду й вуглекислий газ і робить з них цукор…")]
       if UK else
       [("Fluffy pancakes", "How do I make fluffy pancakes?", "Separate the eggs and whip the whites…"),
        ("Why the laptop gets hot", "My laptop gets very hot, what can I do?", "Most often it's dust in the fan or a program running in the background…"),
        ("A letter in Italian", "Translate this letter into polite Italian", "Gentile signor Rossi, grazie per la risposta…"),
        ("Present ideas for Mum", "What can I give Mum for under 40 euros?", "Here are a few ideas that usually make people happy…"),
        ("How photosynthesis works", "Explain photosynthesis simply", "A plant takes light, water and carbon dioxide and makes sugar…")])

SORT_GROUPS = ([("Документи", 34, ["Договір оренди.pdf", "Розклад на семестр.docx", "Квитанція.pdf"]),
                ("Фото", 96, ["IMG_2041.jpg", "IMG_2042.jpg", "Скріншот 2026-11-12.png"]),
                ("Інсталятори", 12, ["VSCodeUserSetup-x64.exe", "Steam-Setup.exe"]),
                ("Музика", 24, ["Океан Ельзи — Обійми.mp3"]),
                ("Архіви", 8, ["Курсова.zip", "Фото з моря.rar"])] if UK else
               [("Documents", 34, ["Lease agreement.pdf", "Term timetable.docx", "Receipt.pdf"]),
                ("Photos", 96, ["IMG_2041.jpg", "IMG_2042.jpg", "Screenshot 2026-11-12.png"]),
                ("Installers", 12, ["VSCodeUserSetup-x64.exe", "Steam-Setup.exe"]),
                ("Music", 24, ["Track 01.mp3"]),
                ("Archives", 8, ["Coursework.zip", "Holiday photos.rar"])])

FIX_GAME = "S.T.A.L.K.E.R. 2: Heart of Chornobyl"
FIX_Q = ("Сталкер 2 запускається, але після логотипа тільки чорний екран. Що не так?" if UK
         else "Stalker 2 starts, but after the logo there is only a black screen. What's wrong?")
FIX_A = ("""Знайшла причину. У папці гри є **Content\\Movies_old**, а звичайної папки **Movies** немає. Так роблять, щоб пропустити заставки, але Stalker 2 після цього часто зависає на чорному екрані: гра чекає відео, якого не бачить.

Гра зараз закрита, тож папці можна повернути стару назву. Картка нижче: нічого не зміниться, поки ти не натиснеш «Підтвердити».

Потім запусти гру. Якщо чорний екран лишиться, перевір файли гри в Steam: він сам завантажить те, чого бракує.""" if UK else
         """I found the cause. The game's folder has **Content\\Movies_old** and no usual **Movies** folder. People do this to skip the intro videos, but Stalker 2 then often stops at a black screen: the game waits for videos it can't see.

The game is closed now, so the folder can get its old name back. The card is below: nothing changes until you press Confirm.

Then start the game. If the black screen stays, check the game's files in Steam: it downloads again whatever is missing.""")
FIX_WHY = ("Відео гри сховано перейменуванням папки, через це чорний екран" if UK
           else "The game's videos are hidden by a renamed folder: that causes the black screen")
FOLLOW = (["Як очистити кеш NVIDIA?", "Які моделі Ollama можна видалити?", "Покажи найбільші файли"] if UK
          else ["How do I clear the NVIDIA cache?", "Which Ollama models can I remove?", "Show me the biggest files"])
THINK = ("Думаю, що саме займає диск" if UK else "Thinking about what fills the disk")
# the figure pc_disk leaves for the window (made by the real diskmap.figure, of a made-up C: drive)
DISK_FIG = diskmap.figure("C:\\", diskmap.Disk(int(445 * GB), int(383.6 * GB), int(61.4 * GB)),
                          [(int(n * GB), "C:\\" + name) for n, name in [(155.1, "Users"), (86.4, "Program Files (x86)"),
                                                                         (50.8, "Windows"), (31.2, "Program Files"),
                                                                         (14.6, "ProgramData"), (8.1, "Games")]],
                          int(22.0 * GB), int(368.2 * GB), True)
COUNT = ("Дивлюсь, що займає диск — пораховано: {s} ГБ, файлів: {n}" if UK
         else "Looking at what takes up the disk — counted so far: {s} GB, files: {n}")
FACTS = (["Олена вчиться на третьому курсі", "Любить короткі відповіді без зайвих слів"] if UK
         else ["Anna is in her third year at university", "Likes short answers"])
HOMEWORK = "домашка.pdf" if UK else "homework.pdf"


def seed(api: Api) -> dict[str, int]:
    """Writes the made-up chats into the temporary database; returns the chats' ids by name."""
    st, now, ids = api.store, time.time(), {}

    def chat(key: str, title: str, pairs: list[tuple[str, str, str]], ago: float, model: str = MODEL,
             files: tuple = (), tools: tuple = ()) -> int:
        tid = st.new_thread(title)
        for i, (q, a, src) in enumerate(pairs):
            st.add(tid, "user", q)
            # "What went to the model" under the answer, written the way the real app writes it
            box = sent.build(model, False, 2 * i, True, len(FACTS), list(files), 0, list(tools))
            st.add(tid, "assistant", a, model, sent.dumps(box), src)
        st._q("UPDATE threads SET updated=?, created=? WHERE id=?", (now - ago, now - ago, tid))
        ids[key] = tid
        return tid

    for i, (title, q, a) in enumerate(reversed(OLD)):
        chat(f"old{i}", title, [(q, a, "")], (12 + i * 70) * HOUR)
    chat("weather", "Погода на вихідні" if UK else "Weekend weather", [(WEATHER_Q, WEATHER_A, sources.dumps(WEATHER_SRC))],
         26 * HOUR, tools=(("weather", json.dumps({"city": "Львів" if UK else "Lviv"})),))
    chat("math", "Площа кола" if UK else "Area of a circle",
         [(MATH_Q + "\n\n📎 " + HOMEWORK, MATH_A, "")], 5 * HOUR, files=(HOMEWORK,))
    tid = chat("theme", "Темна тема" if UK else "Dark theme",
               [("Увімкни темну тему" if UK else "Turn on the dark theme", "Картка нижче: підтвердь, і я перемкну." if UK
                 else "The card is below: confirm it and I'll switch.", "")], 4 * HOUR)
    st.add(tid, "assistant", "✅ " + ("Увімкнено темну тему" if UK else "Switched to the dark theme"), "")   # a card's note
    tid = chat("plan", "План на тиждень" if UK else "Plan for the week", [(PLAN_Q, PLAN_A, "")], 3 * HOUR)
    st.set_plan(tid, plans.dumps({"steps": [{"text": s, "done": i < 2} for i, s in enumerate(PLAN_STEPS)], "project": ""}))
    tid = chat("sort", "Розібрати Завантаження" if UK else "Sort the Downloads", [(SORT_Q, SORT_A, "")], 1.5 * HOUR,
               tools=(("pc_list", json.dumps({"place": "downloads"})),))
    card(api, tid, "pc_sort", {"place": "downloads", "count": 174, "size": 2_468_000_000, "skipped": 1,
                               "groups": [{"to": to, "count": n, "files": fs} for to, n, fs in SORT_GROUPS]})
    tid = chat("fix", "Чорний екран у Сталкері" if UK else "Black screen in Stalker 2", [(FIX_Q, FIX_A, "")], 0.6 * HOUR,
               tools=(("fix_check", json.dumps({"what": FIX_GAME})),
                      ("web_search", json.dumps({"query": "stalker 2 black screen Movies_old"}))))
    card(api, tid, "fix_rename", {"name": FIX_GAME, "place": "install", "path": "Stalker2/Content/Movies_old",
                                  "to": "Movies", "is_dir": True, "why": FIX_WHY})
    tid = chat("disk", "Куди поділось місце на диску" if UK else "Where the disk space went",
               [(DISK_Q, DISK_A, sources.dumps({"disk": DISK_FIG}))], 0.2 * HOUR)
    card(api, tid, "game_remove", {"name": "Cities: Skylines", "appid": "255710", "size": "68.9 GB"})
    st.pin(ids["plan"])
    for fact in FACTS:
        st.add_fact(fact, force=True)
    return ids


def card(api: Api, tid: int, kind: str, details: dict) -> Action:
    """A card waiting for Confirm; confirming it changes nothing on this computer."""
    a = Action(uuid.uuid4().hex[:12], kind, details, lambda: "", tid)
    api.actions.items[a.id] = a
    return a


# ---------------------------------------------------------------- a made-up answer that comes in like a real one
class Play:
    def __init__(self, api: Api, tid: int, second: bool):
        self.api, self.tid, self.second, self.t0 = api, tid, second, time.monotonic()
        self.text = (("Друга думка: згодна, найбільше місця звільнить гра й кеш відеодрайвера." if UK
                      else "A second opinion: agreed, the game and the graphics driver cache free the most space.")
                     if second else DISK_A)
        self.cards: list[dict] = []
        self.kept = False

    def poll(self, offset: int) -> dict:
        el = time.monotonic() - self.t0
        steps = [{"kind": "think", "text": THINK}]
        live = THINK
        if el >= 1.2:
            steps.append({"kind": "tool", "text": COUNT.format(s="", n="").split(" — ")[0]})
            done = min(1.0, (el - 1.2) / 2.2)
            n = f"{int(1_071_509 * done):,}".replace(",", " ")
            live = COUNT.format(s=f"{368.2 * done:.1f}".replace(".", "," if UK else "."), n=n)
        tools = ["📊 " + COUNT.format(s="", n="").split(" — ")[0]] if el >= 1.2 else []   # as app.py sends it: label + step
        disk = {"disk": DISK_FIG} if el >= 3.4 and not self.second else {}     # counted: the window draws the disk
        writing = max(0.0, el - 3.6)
        if writing < 3.2:
            text = self.text[:int(len(self.text) * writing / 3.2)]
            return {"text": text[offset:], "offset": len(text), "notes": [], "weak": "", "tools": tools, "cards": [],
                    "steps": steps, "live": live, "done": False, "error": None, **disk}
        if not self.kept:
            self.kept = True
            self.api.store.add(self.tid, "assistant", self.text, MODEL, "", sources.dumps(disk))
            if not self.second:
                self.cards = [card(self.api, self.tid, "game_remove",
                                   {"name": "Cities: Skylines", "appid": "255710", "size": "68.9 GB"}).card()]
        return {"final": self.text, "notes": [], "weak": "", "tools": tools, "cards": self.cards, "sent": [],
                "sources": {}, "titling": False, "suggesting": not self.second, "learning": False, "questions": [],
                "steps": steps, "live": "", "done": True, "error": None, "model": MODEL, "second": self.second,
                "stopped": False, **disk}


# ---------------------------------------------------------------- the calls the window makes
REAL = {"state", "threads", "messages", "new_thread", "rename_thread", "pin_thread", "delete_thread", "search_chats",
        "facts", "add_fact", "delete_fact", "reminders", "cancel_reminder", "snooze_reminder", "alerts", "cards",
        "plan", "clear_plan", "chat_folder", "chat_role", "set_chat_role", "auto_status", "auto_stop",
        "history_list", "history_clear", "limits", "limit_now", "task_list", "task_add", "task_delete", "task_pause",
        "check_private", "forget_private", "edit_last", "workdir", "backup_status", "sync_status", "github_status",
        "drive_status", "mail_status", "mcp_status", "mcp_presets", "connectors", "voice_status", "tts_status",
        "desktop_status", "action_cancel", "action_confirm", "pulls"}
DEMO_HW = Hardware(gpu="NVIDIA GeForce RTX 3060", vram_gb=12.0, vram_exact=True, ram_gb=32.0,
                   disk_free_gb=61.4, disk_total_gb=445.0, os="win32")     # the same disk as DISK_FIG
DEMO_OLLAMA = [{"name": "qwen3:8b", "size_gb": 5.2, "vision": False, "tools": True, "chat": True}]


class Demo:
    def __init__(self, api: Api):
        self.api, self.plays, self.lock = api, {}, threading.Lock()

    def __getattr__(self, name: str):
        if name in REAL:
            return getattr(self.api, name)
        return lambda *a, **k: {"ok": False, "error": "demo", "message": "Not in the demo."}

    def save_settings(self, patch: dict) -> dict:
        patch = {k: v for k, v in (patch or {}).items() if k not in ("autostart", "hotkey")}
        return self.api.save_settings(patch)

    def models(self, refresh: bool = False) -> dict:
        rows = [("Groq", "llama-3.3-70b-versatile", "ok", 0.42), ("Groq", "openai/gpt-oss-120b", "ok", 0.61),
                ("Groq", "qwen/qwen3-32b", "ok", 0.55), ("Groq", "llama-3.1-8b-instant", "ok", 0.18)]
        return {"ok": True, "current": MODEL, "models": [{"provider": p, "model": m, "score": 1.0, "status": s,
                                                         "latency": lat, "vision": False} for p, m, s, lat in rows]}

    def limits(self) -> list[dict]:
        day = {"kind": "requests", "period": "day", "reset_in": 9 * HOUR}
        return [{"provider": "groq", "service": "Groq", "model": "llama-3.3-70b-versatile", "used": 212, "refused": 0,
                 "limit": None, "left": [{**day, "remaining": 788, "limit": 1000}], "resting": None, "at": 0},
                {"provider": "groq", "service": "Groq", "model": "qwen/qwen3-32b", "used": 41, "refused": 0, "limit": None,
                 "left": [{**day, "remaining": 160, "limit": 1000},
                          {"kind": "tokens", "period": "minute", "remaining": 5200, "limit": 6000, "reset_in": 20}],
                 "resting": None, "at": 0},
                {"provider": "gemini", "service": "Google Gemini", "model": "gemini-2.5-flash", "used": 250, "refused": 3,
                 "limit": 250, "left": [], "resting": 5 * HOUR, "at": 0}]

    def limit_now(self) -> dict:
        return {"label": MODEL, "used": 212, "limit": 1000, "left": 788, "reset_in": 9 * HOUR, "approx": False,
                "period": "day"}

    def hardware(self) -> dict:          # a made-up computer: the screenshots show no real machine
        adv = advise(DEMO_HW).to_dict()
        for m in adv["models"]:
            m["installed"] = m["name"] in {x["name"] for x in DEMO_OLLAMA}
        return {"hw": DEMO_HW.to_dict(), "advice": adv, "download_page": ollama.DOWNLOAD_PAGE}

    def local_status(self) -> dict:      # Ollama "running" with one model, nothing asked of the real one
        s = self.api.settings
        return {"running": True, "version": "0.12.6", "models": DEMO_OLLAMA, "picks": s.local_models,
                "download_page": ollama.DOWNLOAD_PAGE, "pulls": [], "fallback": s.local_fallback, "can_install": False}

    def check_update(self) -> dict:
        return {"newer": False, "latest": __version__}

    def update_notice(self) -> dict:
        return {"newer": False, "latest": "", "off": True}

    def send(self, tid: int, text: str, files=None, again: bool = False) -> dict:
        if not again and str(text or "").strip():
            self.api.store.add(int(tid), "user", str(text))
        return self._play(int(tid), False)

    def second_opinion(self, tid: int) -> dict:
        return self._play(int(tid), True)

    def _play(self, tid: int, second: bool) -> dict:
        sid = uuid.uuid4().hex[:10]
        with self.lock:
            self.plays[sid] = Play(self.api, tid, second)
        return {"ok": True, "stream": sid}

    def poll(self, sid: str, offset: int = 0) -> dict:
        p = self.plays.get(str(sid))
        if not p:
            return {"done": True, "error": {"kind": "other", "message": "unknown stream"}}
        out = p.poll(int(offset or 0))
        if out["done"]:
            self.plays.pop(str(sid), None)
        return out

    def stop_answer(self, sid: str) -> bool:
        return True

    def wait_title(self, tid: int, timeout: float = 10) -> str:
        th = self.api.store.thread(int(tid))
        if th and not th["title"]:
            self.api.store.rename(int(tid), "Демо-чат" if UK else "Demo chat")
        th = self.api.store.thread(int(tid))
        return th["title"] if th else ""

    def wait_follow_ups(self, tid: int, timeout: float = 15) -> list[str]:
        time.sleep(0.6)
        return FOLLOW

    def wait_memory(self, tid: int, timeout: float = 15) -> list:
        return []


def main() -> int:
    api = Api(scheduler=False)
    seed(api)
    gui.secrets.token_urlsafe = lambda n=16: "demo"  # a fixed token: only made-up data is served here
    srv, _ = gui.make_server(Demo(api), PORT)
    print(f"http://127.0.0.1:{PORT}/?token=demo  ({LANG}, settings in {HOME})", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
