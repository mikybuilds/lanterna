"""Round 130 (1.1.6b5), from a test on Fedora: programs, honest replies, the lines under a reply, Connectors.

- Programs on Linux: the search looks in Flatpak and the system's packages, drops Flatpak's loose matches (htop used
  to offer "Beat And Match To Pass"), says where each result comes from; a Flatpak installs from the remote that has it, in that
  remote's installation (Fedora's Flathub is system-wide: "--user flathub" failed); nothing is installed "again".
  Seen on the laptop: dnf5 writes a tab after a package's name; Fedora's VLC is org.videolan.vlc and Flathub's is
  org.videolan.VLC, so with either one installed VLC is installed.
- A reply that only looked things up but says "installing…, I'll let you know" gets the warning too.
- The tool lines under a reply say what was looked for, in the user's language.
- A reply after a reply is a second opinion only when it was one; no theme card that changes nothing; Undo isn't
  called like Cancel; "3 моделі", not "3 моделей".
- Connectors: no unreadable wordmark logos; "Added" is a word, the tick after a name means "made by the service".
"""
import json
import re
from pathlib import Path

import pytest

from lanterna import apps, chat, i18n, keys, pcsys, sent, thinking
from lanterna.discovery import Candidate
from lanterna.providers import ToolCall, ToolCalls
from lanterna.router import Router
from lanterna.store import Store
from lanterna.tools import READ_ONLY_TOOLS, Tool, Toolbox
from lanterna.workspace import Actions, WorkError

UI = Path(apps.__file__).parent / "ui"

# ---------------------------------------------------------------- a Fedora: Flathub and Fedora's remote, both system-wide
REMOTES = "flathub\tFlathub\tsystem,filtered\nfedora\tFedora Flatpaks\tsystem,oci\n"
FP_SEARCH = {                # as on the laptop: the search shows Fedora's VLC, "org.videolan.vlc"
    "htop": "Beat And Match To Pass\tio.github.beat\t1.0\tflathub\tSomething else entirely\n",
    "vlc": ("Pause Click plugin for VLC\torg.videolan.VLC.Plugin.pause_click\t1.0\tflathub\tPause on click\n"
            "VLC\torg.videolan.vlc\t3.0.21\tfedora\tVLC media player\n"),
}
REMOTE_APPS = {"flathub": ("com.spotify.Client", "io.github.beat", "org.videolan.VLC"), "fedora": ("org.videolan.vlc",)}
DNF_SEARCH = {               # dnf5 into a pipe, as on the laptop: a tab after the name
    "htop": ("Updating and loading repositories:\nRepositories loaded.\nMatched fields: name (exact)\n"
             " htop.x86_64\tInteractive process viewer\nMatched fields: summary\n"
             " btop.x86_64\tModern and colorful command line resource monitor that shows usage and stats\n"),
}
VLC_INFO = "\nVLC - VLC media player\n\n          ID: org.videolan.VLC\n     Version: 3.0.21\n     License: GPL-2.0+\n"
HTOP_INFO = "Name            : htop\nVersion         : 3.4.1\nSummary         : Interactive process viewer\nLicense : GPL-2.0\n"


class Fedora:
    def __init__(self, flatpaks: str = ""):
        self.calls, self.rpm_has, self.flatpaks = [], set(), flatpaks

    def __call__(self, args, timeout=0):
        self.calls.append(args)
        if args[:2] == ["flatpak", "remotes"]:
            return 0, REMOTES
        if args[:2] == ["flatpak", "search"]:
            return 0, FP_SEARCH.get(args[-1], "No matches found\n")
        if args[:2] == ["flatpak", "remote-info"]:
            ok = args[2] == "--system" and args[4] in REMOTE_APPS.get(args[3], ())
            return (0, VLC_INFO.replace("org.videolan.VLC", args[4])) if ok else (1, f"error: Can't find ref {args[4]}")
        if args[:2] == ["flatpak", "list"]:
            return 0, self.flatpaks
        if args[:2] == ["dnf", "search"]:
            return 0, DNF_SEARCH.get(args[-1], "No matches found.\n")
        if args[:2] == ["dnf", "info"]:
            return (0, HTOP_INFO) if args[2] == "htop" else (1, "No matching packages to list")
        if args[:2] == ["rpm", "-q"]:
            return (0, f"{args[2]}-1.0") if args[2] in self.rpm_has else (1, f"package {args[2]} is not installed")
        if args[0] == "pkexec" or args[:2] in (["flatpak", "install"], ["flatpak", "uninstall"]):
            return 0, "done"
        return 1, "unexpected"


def linux(run, acts=None):
    return apps.Apps(acts or Actions(), runner=run, platform="linux",
                     which=lambda n: n if n in ("flatpak", "dnf") else None)


def test_the_search_looks_everywhere_and_drops_loose_matches():
    a = linux(Fedora())
    out = a.search("htop")
    assert "htop — id htop, source dnf (system packages): Interactive process viewer" in out
    assert "Beat And Match" not in out and "btop" not in out and "(2 loose matches" in out
    out = a.search("vlc")                     # the program itself first, then what only has its name in it
    assert out.index("VLC — id org.videolan.vlc, source flatpak (fedora), version 3.0.21") < out.index("Pause Click")
    nothing = a.search("zzzz")
    assert nothing.startswith("Nothing found for 'zzzz' (flatpak, dnf)") and "don't install a different program" in nothing
    assert "dnf" in linux(Fedora()).search("htop", "dnf") and "flatpak" not in linux(Fedora()).search("htop", "dnf")


def test_dnf_rows_in_every_format():
    for line in (" htop.x86_64\tInteractive process viewer", " htop.x86_64: Interactive process viewer",
                 "htop.x86_64 : Interactive process viewer", "htop.x86_64    Interactive process viewer"):
        r = apps.DNF_ROW.match(line)
        assert r and r.group(1) == "htop" and r.group(3) == "Interactive process viewer", line
    assert apps.DNF_ROW.match("python3.12.x86_64\tVersion 3.12 of Python").group(1) == "python3.12"
    for line in ("Matched fields: name (exact)", "Repositories loaded.", "Updating and loading repositories:"):
        assert not apps.DNF_ROW.match(line), line


def test_match_score():
    assert apps.match_score("htop", "htop", "htop") == 0
    assert apps.match_score("vlc", "VLC", "org.videolan.VLC") == 0
    assert apps.match_score("vlc", "Pause Click plugin for VLC", "org.videolan.VLC.Plugin.pause_click") == 1
    assert apps.match_score("video editor", "Kdenlive", "org.kde.kdenlive", "Video editor by KDE") == 2
    assert apps.match_score("htop", "Beat And Match To Pass", "io.github.beat", "Something else entirely") == 3


def test_a_flatpak_installs_from_the_remote_and_installation_that_have_it():
    acts, cards = Actions(), []
    acts.bind(cards, 1)
    run = Fedora(flatpaks="com.spotify.Client\tsystem\n")
    a = linux(run, acts)
    said = a.propose("install", "org.videolan.vlc")          # the search's id; no source: such an id is a Flatpak app
    d = cards[-1]["details"]
    assert d["command"] == "flatpak install --system -y --noninteractive fedora org.videolan.vlc"
    assert d["admin"] and d["publisher"] == "Fedora Flatpaks" and "password" in said
    assert ["flatpak", "remote-info", "--system", "flathub", "org.videolan.vlc"] in run.calls    # Flathub was tried first
    done = acts.confirm(cards[-1]["id"])
    assert done.state == "done" and run.calls[-1][:3] == ["flatpak", "install", "--system"]
    assert done.undo == {"type": "app", "op": "uninstall", "id": "org.videolan.vlc", "source": "flatpak"}
    a.propose("install", "org.videolan.VLC")                  # Flathub's own VLC comes from Flathub
    assert cards[-1]["details"]["command"].endswith(" flathub org.videolan.VLC")
    assert cards[-1]["details"]["publisher"] == "Flathub"
    a.propose("uninstall", "com.spotify.Client")
    assert cards[-1]["details"]["command"] == "flatpak uninstall --system -y --noninteractive com.spotify.Client"
    with pytest.raises(WorkError, match="not installed with Flatpak"):
        a.propose("uninstall", "org.gnome.Nope")
    again = linux(Fedora(flatpaks="org.videolan.VLC\tsystem\n"), acts)
    for pid in ("org.videolan.VLC", "org.videolan.vlc"):     # Flathub's VLC is there, so not Fedora's as well
        with pytest.raises(WorkError, match="already installed"):       # its removal would land in Undo
            again.propose("install", pid)


def test_a_plain_name_is_a_system_package_and_is_never_installed_again():
    acts, cards = Actions(), []
    acts.bind(cards, 1)
    run = Fedora()
    a = linux(run, acts)
    a.propose("install", "htop")
    assert cards[-1]["details"]["command"] == "pkexec dnf install -y htop" and cards[-1]["details"]["admin"]
    done = acts.confirm(cards[-1]["id"])
    assert done.state == "done" and done.undo == {"type": "app", "op": "uninstall", "id": "htop", "source": "dnf"}
    run.rpm_has.add("htop")
    n = len(cards)
    with pytest.raises(WorkError, match="already installed"):
        a.propose("install", "htop")
    assert len(cards) == n


WINGET_LIST = """Name    Id         Version Source
------------------------------------
7-Zip   7zip.7zip  26.05   winget
"""


def test_windows_doesnt_reinstall_either():
    def run(args, timeout=0):
        if args[:2] == ["winget", "show"]:
            return 0, "Found 7-Zip [7zip.7zip]\nVersion: 26.05\nPublisher: Igor Pavlov\n"
        if args[:2] == ["winget", "list"]:
            return 0, WINGET_LIST
        return 1, "unexpected"
    a = apps.Apps(Actions(), runner=run, platform="win32", which=lambda n: "C:/winget.exe" if n == "winget" else None)
    with pytest.raises(WorkError, match="already installed"):
        a.propose("install", "7zip.7zip")


# ---------------------------------------------------------------- honest replies
def test_lookups_alone_dont_cover_a_claimed_install():
    assert {"app_search", "pc_info", "web_search"} <= READ_ONLY_TOOLS and "app_install" not in READ_ONLY_TOOLS
    assert chat.false_claim("Встановлюю zsh, вже майже готово! Маякну.", ["app_search"]) == chat.ONLY_LOOKED
    assert chat.false_claim("Встановлюю zsh, вже майже готово!", ["app_search", "app_install"]) == ""
    assert chat.false_claim("Перевіряю, чи є zsh… Є, ось команда.", ["app_search"]) == ""     # it did look
    assert chat.false_claim("Перевіряю систему…", []) == chat.NOTHING_RAN
    assert chat.false_claim("Ось команда: sudo dnf install zsh", ["app_search", "pc_info"]) == ""
    assert chat.false_claim("I'm installing it now, almost done.", ["web_search"]) == chat.ONLY_LOOKED


class Fake:
    def __init__(self, replies):
        self.replies = replies

    def stream_chat(self, model, messages, tools=None, tool_choice="auto"):
        yield from self.replies.pop(0)

    def close(self):
        pass


class NoStore:
    def facts(self):
        return []


def test_a_search_then_installing_talk_gets_the_warning():
    call = ToolCalls([ToolCall("c1", "app_search", '{"query": "zsh"}')])
    fake = Fake([[call], ["Знайшла zsh. Встановлюю його зараз, маякну, як буде готово!"]])
    found = Tool("app_search", "find", {"type": "object", "properties": {}},
                 lambda query="": "zsh — id zsh, source dnf", "🔎")
    box = Toolbox(NoStore(), extra=lambda: [found])
    s = chat.Conversation(router=Router([Candidate("gemini", "able", 90)], client_for=lambda pid: fake),
                          lang="uk", toolbox=box)
    out = "".join(p for p in s.ask("встанови zsh") if isinstance(p, str))
    assert "⚠️" in out and "лише шукала" in out and s.history[-1]["content"].endswith("не змінено.")


# ---------------------------------------------------------------- the lines under a reply
def test_tool_lines_say_what_in_the_users_language():
    assert thinking.tool_step("app_search", '{"query": "htop"}', "uk") == "Шукаю програму: htop"
    en_why = '{"query": "zsh", "intent": "to see if zsh is available"}'
    assert thinking.tool_step("app_search", en_why, "uk") == "Шукаю програму: zsh"           # English "why" left out
    uk_why = '{"query": "zsh", "intent": "щоб знайти zsh"}'
    assert thinking.tool_step("app_search", uk_why, "uk") == "Шукаю програму: zsh — щоб знайти zsh"
    assert thinking.tool_step("app_search", uk_why, "uk", why=False) == "Шукаю програму: zsh"
    assert thinking.tool_step("app_search", en_why, "en").endswith("— to see if zsh is available")
    assert thinking.tool_step("pc_info", "{}", "uk") == "Дивлюсь характеристики комп'ютера"
    from lanterna.tui import tool_text
    assert tool_text("🔎 Шукаю програму: htop", "uk") == "🔎 Шукаю програму: htop"        # already the step
    assert tool_text("🔎 web_search", "uk") == "🔎 Шукаю в інтернеті"                      # older chips still work
    js = (UI / "app.js").read_text(encoding="utf-8")
    assert 'const [emo, ...rest] = String(s).split(" ")' in js


# ---------------------------------------------------------------- second opinion, theme, words
def test_only_a_real_second_opinion_gets_its_title(tmp_path, monkeypatch):
    from lanterna.app import Api
    monkeypatch.setattr(keys, "get_key", lambda n: None)
    monkeypatch.setenv("LANTERNA_HOME", str(tmp_path))
    api = Api(store=Store(tmp_path / "t.db"), scheduler=False)
    tid = api.new_thread()["id"]
    api.store.add(tid, "user", "постав темну тему")
    api.store.add(tid, "assistant", "Підготувала картку.", "m1", sent.dumps(sent.build("m1", False, 0, False, 0, [], 0, [])))
    api.store.add(tid, "assistant", "✅ Тему змінено")                    # the note after Confirm: not a second opinion
    api.store.add(tid, "assistant", "Інша думка", "m2",
                  sent.dumps(sent.build("m2", False, 0, False, 0, [], 0, [], second=True)))
    assert [bool(m.get("second")) for m in api.messages(tid)] == [False, False, False, True]
    js = (UI / "app.js").read_text(encoding="utf-8")
    assert "addBot(m.content, m.model, m.sent, m.second)" in js and "an answer right after an answer" not in js


class Reg:
    def __init__(self, apps_, system):
        self.v = {"AppsUseLightTheme": apps_, "SystemUsesLightTheme": system}

    def get(self, hive, path, name):
        return self.v.get(name)

    def set(self, hive, path, name, value, kind):
        self.v[name] = value


def test_no_theme_card_when_it_is_already_so():
    acts, cards = Actions(), []
    acts.bind(cards, 1)
    s = pcsys.System(acts, runner=lambda args, timeout=0: (0, "'prefer-dark'\n"), platform_="linux",
                     which=lambda n: "/usr/bin/" + n)
    assert "already dark" in s.propose_theme("dark") and not cards
    s.propose_theme("light")
    assert cards[-1]["details"] == {"theme": "light", "was": "dark"}
    win = pcsys.System(acts, platform_="win32", reg=Reg(0, 0), which=lambda n: None)
    assert "already dark" in win.propose_theme("dark")
    n = len(cards)
    pcsys.System(acts, platform_="win32", reg=Reg(0, 1), which=lambda n: None).propose_theme("dark")
    assert len(cards) == n + 1                                            # the taskbar part was still light


def test_undo_is_not_called_like_cancel_and_models_count_right():
    for lang in ("uk", "it", "fr", "de", "es", "pl"):
        assert i18n.t("Undo", lang) != i18n.t("Cancel", lang), lang
    assert i18n.t("Undo", "uk") == "Повернути як було"
    for text in ("The old values are kept: Undo puts them back.", "on its own; Undo is in What Lanterna did"):
        assert "Скасувати" not in i18n.t(text, "uk") and "Повернути як було" in i18n.t(text, "uk")
    assert i18n.t("(tried {n} models)", "uk", n=3) == "(спробував моделей: 3)"
    js = (UI / "app.js").read_text(encoding="utf-8")
    assert '"Undo": { uk: "Повернути як було", it: "Ripristina" }' in js
    assert '"(tried {n} models)": { uk: "(спробував моделей: {n})"' in js


# ---------------------------------------------------------------- Connectors
def test_connectors_logos_and_badges():
    js = (UI / "logos.js").read_text(encoding="utf-8")
    logos = json.loads(re.search(r"const LOGOS = (\{.*\});", js).group(1))
    assert not {"cal", "egnyte", "wix", "kaggle", "zapier"} & set(logos) and len(logos) >= 45
    app = (UI / "app.js").read_text(encoding="utf-8")
    assert '&nbsp;<span class="cn-ok"' in app                  # the tick stays on the name's last line
    assert app.count('class="cn-badge on"') == 2 and "cn-added" not in app
    assert 'id="cn-back"' in app and 'v.querySelector(".dialog").scrollTop = 0' in app
    css = (UI / "style.css").read_text(encoding="utf-8")
    assert ".cn-badge.on" in css and re.search(r"\.dialog\.connectors \{[^}]*height:", css)
