"""Terminal interface: first-run setup and a streaming chat.

  lanterna                 full-screen app (runs setup the first time)
  lanterna chat            simple line-by-line chat (also: --plain)
  lanterna models          free models available right now, best first (--refresh to search again)
  lanterna setup           run setup again
  lanterna key set groq    store a key in the system vault
  lanterna key list        show which keys are stored (masked)
  lanterna about
  lanterna update          is there a new version, and how to install it
"""
from __future__ import annotations

import argparse
import getpass
import sys
import time

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from . import AUTHOR, HOMEPAGE, __version__, keys
from .chat import Conversation
from .config import Settings
from .discovery import Candidate, get_models
from .i18n import LANGS, t
from .providers import PROVIDERS, Client, ProviderError
from .router import Router, Switched

console = Console()
AMBER = "#F5B544"
FIRST_CHOICES = [  # (provider id, tagline, details)
    ("groq", "Fastest", "Replies almost instantly · strong open models (GPT-OSS, Qwen) · smaller daily limit"),
    ("gemini", "Smartest & most generous", "Big free limits · understands photos and documents · long memory · needs a Google account"),
]


def banner(lang: str) -> None:
    console.print(Panel.fit(f"[bold {AMBER}]🏮 Lanterna[/]  v{__version__}\n[dim]{t('Made by {author}', lang, author=AUTHOR)} · {HOMEPAGE}[/]",
                            border_style=AMBER))


def ask_key(pid: str, lang: str) -> bool:
    p = PROVIDERS[pid]
    console.print(t("Get a free key here: {url}", lang, url=f"[link={p.key_url}]{p.key_url}[/link]"))
    hint = t("Create an account, press “Create API key”, copy it and paste it below. It is stored in your system's secure vault.", lang)
    console.print(f"[dim]{hint}[/]")
    for _ in range(3):
        key = getpass.getpass(t("Paste key (hidden)", lang) + ": ").strip()
        if not key:
            return False
        console.print(f"[dim]{t('Checking the key…', lang)}[/]")
        try:
            c = Client(p, key)
            c.list_models()
            c.close()
        except ProviderError as e:
            msg = t("The key didn't work: {err}", lang, err=e)
            console.print(f"[red]{msg}[/]")
            continue
        keys.set_key(pid, key)
        console.print(f"[green]{t('Key works ✓', lang)}[/]")
        return True
    return False


def setup(s: Settings) -> Settings:
    lang = Prompt.ask("Language / Мова / Lingua", choices=list(LANGS), default=s.lang or "en")
    s.lang = lang
    banner(lang)
    s.name = Prompt.ask(t("What should I call you?", lang), default=s.name or "").strip()
    console.print(f"\n[bold]{t('Pick your first free service:', lang)}[/]")
    for i, (pid, tag, det) in enumerate(FIRST_CHOICES, 1):
        console.print(Panel(f"[dim]{t(det, lang)}[/]", title=f"[bold]{i}. {PROVIDERS[pid].name} — {t(tag, lang)}[/]",
                            title_align="left", border_style=AMBER if i == 1 else "grey50"))
    console.print(f"[dim]{t('You can add the other services later as backups.', lang)}[/]")
    choice = Prompt.ask("1 / 2", choices=["1", "2"], default="1")
    s.provider = FIRST_CHOICES[int(choice) - 1][0]
    if not keys.get_key(s.provider):
        ask_key(s.provider, lang)
    s.onboarded = True
    s.save()
    return s


def find_models(s: Settings, refresh: bool = False) -> list[Candidate]:
    with console.status(t("Looking for free models…", s.lang), spinner="dots"):
        return get_models(s.provider, refresh=refresh, mode=s.mode, picks=s.local_models)


def show_models(s: Settings, refresh: bool) -> int:
    cands = find_models(s, refresh)
    if not cands:
        console.print(f"[red]{t('No free models found. Add a key: lanterna key set groq', s.lang)}[/]")
        return 1
    tb = Table(box=None, header_style=f"bold {AMBER}")
    for col in ("#", t("Service", s.lang), t("Model", s.lang), t("Score", s.lang), t("Status", s.lang)):
        tb.add_column(col)
    style = {"ok": "green", "limited": "yellow", "untested": "dim"}
    for i, c in enumerate(cands, 1):
        st = t(c.status, s.lang) + (f" · {c.latency:.1f}s" if c.latency else "")
        tb.add_row(str(i), PROVIDERS[c.provider].name, c.model + (" 👁" if c.vision else ""), str(c.score), f"[{style.get(c.status, '')}]{st}[/]")
    console.print(tb)
    return 0


def run_chat(s: Settings) -> int:
    lang = s.lang
    cands = find_models(s)
    if not cands:
        p = PROVIDERS[s.provider or "groq"]
        console.print(f"[red]{t('No key for {p}. Run: lanterna key set {id}', lang, p=p.name, id=p.id)}[/]")
        return 1
    router = Router(cands)
    conv = Conversation(router, s.name, lang=s.lang, auto_cloud=s.mode == "auto" and s.auto_cloud)
    banner(lang)
    console.print(f"[dim]{cands[0].label}\n{t('Type a message. /exit to quit, /new for a new chat.', lang)}[/]\n")
    while True:
        try:
            text = console.input(f"[bold {AMBER}]› [/]").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not text:
            continue
        if text in ("/exit", "/quit", "/q"):
            break
        if text == "/new":
            conv.history.clear()
            console.print(f"[dim]{t('New chat.', lang)}[/]")
            continue
        try:
            for piece in conv.ask(text):
                if isinstance(piece, Switched):
                    console.print(f"[dim]↪ {t('switched to {m}', lang, m=piece.to.label)}[/]")
                elif isinstance(piece, str):                 # thoughts and tool steps are for the window apps
                    console.print(piece, end="", markup=False, highlight=False)
            console.print("\n")
        except ProviderError as e:
            msg = (t("All free models are busy or out of limits. Try again in a minute.", lang)
                   if e.kind == "rate" else t("Network problem: {err}", lang, err=e) if e.kind == "network" else t("Error: {err}", lang, err=e))
            console.print(f"\n[red]{msg}[/]\n")
        except KeyboardInterrupt:
            console.print()
    console.print(f"[dim]{t('Bye!', lang)}[/]")
    router.close()
    return 0


def local_cmd(s: Settings, action: str, value: str | None) -> int:
    from . import hardware, local
    lang = s.lang
    if action == "mode":
        if value not in ("cloud", "local", "auto"):
            console.print("cloud | local | auto")
            return 1
        s.mode = value
        s.save()
        console.print(t("Saved.", lang))
        return 0
    if action == "pull":
        if not value:
            console.print(t("Model name?", lang))
            return 1
        if not local.version():
            console.print(f"[red]{t('Ollama is not running. Install it from {url}', lang, url=local.DOWNLOAD_PAGE)}[/]")
            return 1
        from rich.progress import BarColumn, DownloadColumn, Progress, TextColumn
        dl = local.Downloads()
        job = dl.start(value)
        with Progress(TextColumn(value), BarColumn(), DownloadColumn(), console=console) as bar:
            task = bar.add_task("pull", total=None)
            while job.status in ("starting", "downloading", "verifying"):
                bar.update(task, completed=job.done_bytes, total=job.total_bytes or None)
                time.sleep(0.4)
            bar.update(task, completed=job.total_bytes, total=job.total_bytes or 1)
        if job.status != "done":
            console.print(f"[red]{t('Download failed: {e}', lang, e=job.error)}[/]")
            return 1
        console.print(f"[green]✓ {value}[/]")
        return 0
    hw = hardware.detect()
    adv = hardware.advise(hw)
    gpu = hw.gpu or t("No graphics card found", lang)
    if hw.vram_gb:
        gpu += f" · {hw.vram_gb:.1f} {t('GB', lang)}"
    console.print(f"{t('Graphics card', lang)}: {gpu}\n{t('RAM', lang)}: {hw.ram_gb:.1f} {t('GB', lang)}   "
                  f"{t('Free disk', lang)}: {hw.disk_free_gb:.1f} {t('GB', lang)}")
    ver = local.version()
    console.print(f"[green]✓ {t('Ollama {v} is running', lang, v=ver)}[/]" if ver
                  else f"[yellow]{t('Ollama is not running. Install it from {url}', lang, url=local.DOWNLOAD_PAGE)}[/]")
    have = {m.name for m in local.installed()} if ver else set()
    tb = Table(box=None, header_style=f"bold {AMBER}", title=t("Recommended for this computer", lang))
    for col in (t("Model", lang), "", t("GB", lang), ""):
        tb.add_column(col)
    for m in adv.models:
        tb.add_row(m.name, t({"chat": "For chatting", "think": "For harder questions", "vision": "For photos"}[m.role], lang),
                   f"{m.size_gb:.1f}", "[green]✓[/]" if m.name in have else f"[dim]lanterna local pull {m.name}[/]")
    console.print(tb)
    console.print(f"[dim]{t('Mode', lang)}: {s.mode}  ·  lanterna local mode cloud|local|auto[/]")
    return 0


def update_cmd(s: Settings) -> int:
    from .app import Api
    lang = s.lang
    with console.status(t("Checking for updates…", lang), spinner="dots"):
        u = Api(scheduler=False).check_update()
    if not u.get("latest"):
        msg = t("Couldn't check for updates. Are you online?", lang)
        console.print(f"[yellow]{msg}[/]")
        return 1
    if not u.get("newer"):
        console.print(f"[green]✓[/] {t('You have the latest version', lang)} ({u['current']})")
        return 0
    console.print(f"[bold {AMBER}]{t('Lanterna {v} is out', lang, v=u['latest'])}[/]  [dim]{t('You have {v}.', lang, v=u['current'])}[/]")
    if u.get("notes"):
        head = t("What's new", lang)
        console.print()
        console.print(f"[bold]{head}[/]")
        for n in u["notes"]:
            console.print(f"  • {n}", markup=False, highlight=False)
    console.print()
    console.print(f"[bold]{t('How to update', lang)}[/]")
    for i, step in enumerate(u.get("steps") or [], 1):
        console.print(f"  {i}. {step}", markup=False, highlight=False)
        if step.endswith(":") and u.get("command"):           # the command goes right under "run:"
            console.print(f"\n       {u['command']}\n", style=f"bold {AMBER}", markup=False, highlight=False)
    if u.get("download"):
        console.print(f"\n[dim]{u['download']}[/]")
    return 0


def sync_cmd(s: Settings, action: str) -> int:
    """lanterna sync: status · in (sign in with Google) · now · out (sign out) · out --delete."""
    import time as _time
    from .app import Api
    lang, api = s.lang, Api(scheduler=False)
    st = api.sync_status()
    if action == "in":
        if st["phase"] == "off":
            console.print(t("Finish signing in in your browser…", lang))
            api.sync_sign_in()
            while api.sync_status()["phase"] == "waiting":
                _time.sleep(0.5)
            st = api.sync_status()
            if st["phase"] == "off":
                console.print(f"[yellow]{st['error'] or 'cancelled'}[/]", markup=True, highlight=False)
                return 1
        while st["phase"] == "password":
            console.print(t("Enter the sync password you chose on your other device.", lang) if st["cloud"] else
                          t("Choose a sync password (at least 8 characters). You will need it on your other devices.", lang),
                          highlight=False)
            st = api.sync_password(getpass.getpass(t("Sync password", lang) + ": "))
            if st["error"] in ("password", "short"):
                console.print(f"[yellow]{t('Wrong password.' if st['error'] == 'password' else 'At least 8 characters.', lang)}[/]")
            elif st["phase"] == "password":
                break
    elif action == "now":
        st = api.sync_now()
    elif action in ("out", "out-delete"):
        st = api.sync_sign_out(action == "out-delete")
    if st["phase"] == "off":
        console.print(t("Sign in with Google to see your chats on all your devices.", lang) + "  lanterna sync in", highlight=False)
    else:
        console.print(t("Signed in as {account}", lang, account=st["account"]) if st["account"] else t("Signed in with Google", lang),
                      highlight=False)
        if st["last"]:
            console.print(t("Last synced at {time}", lang, time=_time.strftime("%H:%M", _time.localtime(st["last"]))))
    if st["error"] and st["error"] not in ("password", "short"):
        msg = t("Couldn't sync: {error}", lang, error=st["error"])
        console.print(msg, style="yellow", markup=False, highlight=False)
        return 1
    return 0


def bug_cmd(s: Settings) -> int:
    """Asks what went wrong, shows the exact text, then opens a ready letter (or prints where to send it)."""
    from .app import Api
    lang = s.lang
    console.print(f"[bold {AMBER}]{t('Report a bug', lang)}[/]")
    console.print(t("Tell what went wrong. You see the whole text first, and you send it yourself.", lang), highlight=False)
    console.print(f"[dim]{t('What did you do, what happened, and what did you expect?', lang)} (Enter ×2)[/]")
    lines: list[str] = []
    while True:
        try:
            ln = input("> " if not lines else "  ")
        except (EOFError, KeyboardInterrupt):
            break
        if not ln.strip() and lines:
            break
        if ln.strip():
            lines.append(ln)
    api = Api(scheduler=False)
    r = api.bug_report("\n".join(lines), True)
    if not r["ok"]:
        console.print(t("Write a few words first.", lang))
        return 1
    console.print()
    console.print(f"[bold]{t('This is exactly what will be sent:', lang)}[/]")
    console.print(Panel(r["body"], expand=False), markup=False, highlight=False)
    if r["email"]:
        console.print(t("No mail app? Copy the text and send it to {email} from any mail.", lang, email=r["email"]), highlight=False)
        if Prompt.ask(t("Write e-mail", lang) + "?", choices=["y", "n"], default="y") == "y":
            api.open_mail(r["mailto"])
            console.print(t("Your mail app opens with the letter ready. Check it and press Send.", lang), highlight=False)
    else:
        console.print(t("Reports by e-mail are coming soon. For now open it on GitHub (free account) or copy the text.", lang), highlight=False)
    console.print(f"\n{t('Open on GitHub', lang)}:")
    console.print(r["issue"], markup=False, highlight=False, soft_wrap=True)
    if not r["email"] and Prompt.ask(t("Open on GitHub", lang) + "?", choices=["y", "n"], default="y") == "y":
        api.open_url(r["issue"])
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="lanterna", description="Lanterna — a friendly AI assistant by mikybuilds")
    ap.add_argument("--version", action="version", version=f"Lanterna {__version__}")
    ap.add_argument("--plain", action="store_true", help="simple line-by-line chat instead of the full-screen app")
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("setup")
    sub.add_parser("chat", help="simple line-by-line chat")
    sub.add_parser("about")
    sub.add_parser("update", help="is there a new version, and how to install it")
    sub.add_parser("bug", help="report a bug: see the text, then send it from your mail app or GitHub")
    sy = sub.add_parser("sync", help="sign in with Google and keep the same chats on all your devices")
    sy.add_argument("action", nargs="?", default="status", choices=["status", "in", "now", "out", "out-delete"])
    mp = sub.add_parser("models")
    mp.add_argument("--refresh", action="store_true")
    lp = sub.add_parser("local", help="local models: what fits this computer, download with progress, pick the mode")
    lp.add_argument("action", nargs="?", choices=["info", "pull", "mode"], default="info")
    lp.add_argument("value", nargs="?", help="model name (pull) or cloud|local|auto (mode)")
    dp = sub.add_parser("desktop", help="add Lanterna to the app menu (Linux: GNOME, KDE…)")
    dp.add_argument("--remove", action="store_true")
    k = sub.add_parser("key")
    k.add_argument("action", choices=["set", "list", "delete"])
    k.add_argument("provider", nargs="?", choices=list(PROVIDERS))
    a = ap.parse_args(argv)

    s = Settings.load()
    if a.cmd == "about":
        banner(s.lang)
        return 0
    if a.cmd == "update":
        return update_cmd(s)
    if a.cmd == "bug":
        return bug_cmd(s)
    if a.cmd == "sync":
        return sync_cmd(s, a.action)
    if a.cmd == "models":
        return show_models(s, a.refresh)
    if a.cmd == "local":
        return local_cmd(s, a.action, a.value)
    if a.cmd == "desktop":
        from . import desktop
        if not sys.platform.startswith("linux"):
            console.print(t("This command is for Linux. On Windows use the installer.", s.lang))
            return 1
        if a.remove:
            desktop.remove()
            console.print(t("Removed from the app menu.", s.lang))
            return 0
        desk, _ = desktop.install()
        console.print(f"[green]✓[/] {t('Lanterna is in your app menu now. Press Super and type Lanterna.', s.lang)}\n[dim]{desk}[/]")
        return 0
    if a.cmd == "key":
        if a.action == "list":
            for pid, p in PROVIDERS.items():
                if p.needs_key:
                    console.print(f"{p.name:16} {keys.mask(keys.get_key(pid))}")
            return 0
        if not a.provider:
            ap.error("choose a provider")
        if a.action == "delete":
            keys.delete_key(a.provider)
            console.print(t("Saved.", s.lang))
            return 0
        return 0 if ask_key(a.provider, s.lang) else 1
    if a.cmd != "chat" and not a.plain and _can_tui():
        from .tui import run
        return run(force_setup=a.cmd == "setup")
    if a.cmd == "setup" or not s.onboarded:
        s = setup(s)
    return run_chat(s)


def _can_tui() -> bool:
    """Full-screen app needs a real terminal; pipes and dumb terminals get the plain chat."""
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        return False
    try:
        import textual  # noqa: F401
    except ImportError:
        return False
    return True


if __name__ == "__main__":
    sys.exit(main())
