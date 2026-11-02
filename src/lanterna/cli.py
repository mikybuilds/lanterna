"""Terminal interface (stage 0): first-run setup and a streaming chat.

  lanterna                 chat (runs setup the first time)
  lanterna setup           run setup again
  lanterna key set groq    store a key in the system vault
  lanterna key list        show which keys are stored (masked)
  lanterna about
"""
from __future__ import annotations

import argparse
import getpass
import sys

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt

from . import AUTHOR, HOMEPAGE, __version__, keys
from .chat import Conversation
from .config import Settings
from .i18n import LANGS, t
from .providers import PROVIDERS, Client, ProviderError

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


def run_chat(s: Settings) -> int:
    lang = s.lang
    p = PROVIDERS[s.provider or "groq"]
    key = keys.get_key(p.id)
    if p.needs_key and not key:
        console.print(f"[red]{t('No key for {p}. Run: lanterna key set {id}', lang, p=p.name, id=p.id)}[/]")
        return 1
    client = Client(p, key)
    try:
        model = s.models.get(p.id) or client.pick_model()
    except ProviderError as e:
        console.print(f"[red]{t('Error: {err}', lang, err=e)}[/]")
        return 1
    conv = Conversation(client, model, s.name)
    banner(lang)
    console.print(f"[dim]{p.name} · {model}\n{t('Type a message. /exit to quit, /new for a new chat.', lang)}[/]\n")
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
                console.print(piece, end="", markup=False, highlight=False)
            console.print("\n")
        except ProviderError as e:
            msg = (t("Limit reached on {p}. Try again in a bit (automatic switching comes in the next version).", lang, p=p.name)
                   if e.kind == "rate" else t("Network problem: {err}", lang, err=e) if e.kind == "network" else t("Error: {err}", lang, err=e))
            console.print(f"\n[red]{msg}[/]\n")
        except KeyboardInterrupt:
            console.print()
    console.print(f"[dim]{t('Bye!', lang)}[/]")
    client.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="lanterna", description="Lanterna — a friendly AI assistant by mikybuilds")
    ap.add_argument("--version", action="version", version=f"Lanterna {__version__}")
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("setup")
    sub.add_parser("about")
    k = sub.add_parser("key")
    k.add_argument("action", choices=["set", "list", "delete"])
    k.add_argument("provider", nargs="?", choices=list(PROVIDERS))
    a = ap.parse_args(argv)

    s = Settings.load()
    if a.cmd == "about":
        banner(s.lang)
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
    if a.cmd == "setup" or not s.onboarded:
        s = setup(s)
    return run_chat(s)


if __name__ == "__main__":
    sys.exit(main())
