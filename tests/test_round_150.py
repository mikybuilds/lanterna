"""Round 150 (1.1.11b2): «why doesn't it work» on Linux too.

The same as round 149, with Linux's own places: Steam's games run natively or through Proton (a Windows game keeps
its AppData in its Proton prefix), Heroic, Lutris, Flatpak and the installed apps; what the system noted (crashes kept
by systemd-coredump or apport, the kernel's lines about the graphics card and memory, systemd-oomd); and the system
itself: sound (PipeWire or PulseAudio), internet (NetworkManager), printers (CUPS) and updates (dnf, apt, rpm-ostree).
The fixes change only the user's own settings: the sound output and its volume, a restart of the user's sound service,
the desktop's proxy, the default printer and the user's own print jobs.
Every test runs on a pretend computer: a folder for / and a table of commands with their answers. Nothing on this
computer is run or changed, on Windows and on Linux alike.
"""
import ast
import json
import os
import re
import shutil
import sqlite3
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from lanterna import app, chat, fixit, fixlinux, history, i18n, sent, thinking, workspace
from lanterna.workspace import WAITING, Actions, WorkError
from test_round_144 import _api  # noqa: E402  (an Api of its own)
from test_round_149 import GAME, JS, SETTINGS, FakePrinters, _card, _manifest, _write  # noqa: E402

LX_HOME = "/home/" + "olena"                 # (split: the secrets scan looks for such paths)
USER_UNIT = "user" + "@1000.service"         # systemd's unit of the user's programs (the scan reads it as an e-mail)
GB, MB = fixit.GB, fixit.MB
J = "--since=-7d --no-pager -q -o short-iso -n 3000"
KERNEL, OOMD, PACKAGEKIT = f"journalctl -k -p 0..5 {J}", f"journalctl -u systemd-oomd {J}", \
    f"journalctl -u packagekit -p 0..3 {J}"
DUMPS = "coredumpctl --json=short --no-pager -q --since=-30d list"
MESA = "rpm -q --qf %{VERSION}\\n mesa-dri-drivers"
UNITS = "systemctl --user is-active pipewire.service pipewire-pulse.service wireplumber.service pulseaudio.service"
LSPCI = ('00:1f.3 "Audio device" "Intel Corporation" "Cannon Lake PCH cAVS" -r10 "Lenovo" "Device 3ffc"\n'
         '03:00.0 "VGA compatible controller" "Advanced Micro Devices, Inc. [AMD/ATI]" "Navi 21 [Radeon RX 6800/6800 '
         'XT / 6900 XT]" -rc1 "Sapphire Technology Limited" "Device e438"\n')
VDF = ('"InstallConfigStore"\n{\n\t"Software"\n\t{\n\t\t"Valve"\n\t\t{\n\t\t\t"Steam"\n\t\t\t{\n'
       '\t\t\t\t"CompatToolMapping"\n\t\t\t\t{\n'
       '\t\t\t\t\t"0"\n\t\t\t\t\t{\n\t\t\t\t\t\t"name"\t\t"proton_experimental"\n\t\t\t\t\t}\n'
       '\t\t\t\t\t"1643320"\n\t\t\t\t\t{\n\t\t\t\t\t\t"name"\t\t"proton_9"\n\t\t\t\t\t}\n'
       '\t\t\t\t}\n\t\t\t}\n\t\t}\n\t}\n}\n')
EPIC = "dc9d2e595d0e4650b35d659f90d41059"


class Cmds:
    """The pretend system's commands: a whole command line → (exit code, what it printed), or a function of its
    arguments. A command it doesn't know isn't installed (127)."""

    def __init__(self, table=None):
        self.table, self.runs = dict(table or {}), []

    def __call__(self, args, timeout=60, env=None):
        line = " ".join(args)
        self.runs.append(line)
        assert env is not None and env["LC_ALL"] == "C", line           # every command answers in English
        r = self.table.get(line, (127, ""))
        return r(list(args)) if callable(r) else r

    def ran(self, prefix):
        return [x for x in self.runs if x.startswith(prefix)]


def _lx(tmp_path: Path) -> SimpleNamespace:
    """A pretend Fedora laptop: Steam with S.T.A.L.K.E.R. 2 through Proton (its videos renamed aside, its log in its
    Proton prefix) and Hollow Knight (a Linux game), Heroic, Lutris, a Flatpak app, a Snap, the system's apps and an
    AMD graphics card."""
    root = tmp_path / "root"
    home = root / "home" / "olena"
    steam = home / ".local" / "share" / "Steam"
    game = _manifest(steam, "1643320", GAME, "S.T.A.L.K.E.R. 2")
    _write(game / "Stalker2.exe", "MZ")
    win64 = game / "Stalker2" / "Binaries" / "Win64"
    _write(win64 / "Stalker2-Win64-Shipping.exe", "MZ")
    _write(game / "Stalker2/Content/Movies_old/Intro.bk2", "v" * 2000)
    _write(game / "Stalker2/Content/Movies_old/Mission_01.bk2", "v" * 3000)
    pfx = steam / "steamapps" / "compatdata" / "1643320" / "pfx"
    local = pfx / "drive_c" / "users" / "steamuser" / "AppData" / "Local"
    _write(local / "Stalker2/Saved/Logs/Stalker2.log",
           "[2026.11.20-18.01.02:123][  0]LogInit: Build: ++Stalker2+release\n"
           "[2026.11.20-18.20.40:001][512]LogVulkanRHI: Error: VK_ERROR_DEVICE_LOST\n")
    _write(local / "Stalker2/Saved/Config/Windows/GameUserSettings.ini", SETTINGS)
    _write(steam / "config" / "config.vdf", VDF)
    hk = _manifest(steam, "367520", "Hollow Knight", "Hollow Knight")
    _write(hk / "hollow_knight.x86_64", "ELF")
    _write(hk / "hollow_knight_Data" / "app.info", "Team Cherry\nHollow Knight")
    unity = home / ".config" / "unity3d" / "Team Cherry" / "Hollow Knight"
    _write(unity / "Player.log", "Initialize engine version: 2020.2.2f1\nCrash!!!\n")
    _write(steam / "steamapps" / "shadercache" / "367520" / "fozpipelinesv6" / "a.foz", "s" * 300)
    _manifest(steam, "1493710", "Proton Experimental", "Proton - Experimental")      # Steam's own tools: not games
    _manifest(steam, "1628350", "Steam Linux Runtime 3.0 (sniper)", "SteamLinuxRuntime_sniper")
    _write(home / ".cache" / "mesa_shader_cache_db" / "part0" / "mesa_cache.db", "m" * 700)
    # Heroic: an Epic game (its Wine prefix in the game's settings) and a GOG one
    heroic = home / ".config" / "heroic"
    aw, aw_pfx = home / "Games" / "Heroic" / "AlanWake2", home / "Games" / "Heroic" / "Prefixes" / "default" / "Alan Wake 2"
    _write(aw / "AlanWake2.exe", "MZ")
    _write(heroic / "legendaryConfig/legendary/installed.json", json.dumps(
        {EPIC: {"app_name": EPIC, "title": "Alan Wake 2", "install_path": str(aw), "version": "1.2.8", "is_dlc": False}}))
    _write(heroic / "GamesConfig" / f"{EPIC}.json",
           json.dumps({EPIC: {"winePrefix": "~/Games/Heroic/Prefixes/default/Alan Wake 2"}}))
    ug = home / "Games" / "Heroic" / "Unreal Gold"
    _write(ug / "System" / "Unreal.exe", "MZ")
    _write(heroic / "gog_store/installed.json", json.dumps(
        {"installed": [{"appName": "1207658964", "install_path": str(ug), "version": "226f", "platform": "windows"}]}))
    # Lutris: a Windows game in its own Wine prefix (its directory is the whole prefix)
    lpfx = home / "Games" / "diablo-ii"
    _write(lpfx / "drive_c/Program Files/Diablo II/Game.exe", "MZ")
    _write(home / ".config/lutris/games/diablo-ii-1700000000.yml",
           f"game:\n  exe: drive_c/Program Files/Diablo II/Game.exe\n  prefix: {lpfx}\nwine:\n  version: wine-ge-8-26\n")
    db = home / ".local" / "share" / "lutris" / "pga.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE games (id INTEGER PRIMARY KEY, name TEXT, slug TEXT, runner TEXT, directory TEXT, "
                "configpath TEXT, installed INTEGER)")
    con.executemany("INSERT INTO games (name, slug, runner, directory, configpath, installed) VALUES (?, ?, ?, ?, ?, ?)",
                    [("Diablo II", "diablo-ii", "wine", str(lpfx), "diablo-ii-1700000000", 1),
                     ("Not Here Any More", "gone", "linux", "", "", 0)])
    con.commit()
    con.close()
    # a Flatpak app (its own folders in ~/.var/app), the system's apps, one in /opt and a Snap
    fp = root / "var" / "lib" / "flatpak"
    (fp / "app" / "org.gimp.GIMP").mkdir(parents=True)
    (fp / "app" / "org.gimp.GIMP.Locale").mkdir(parents=True)
    _write(fp / "exports/share/applications/org.gimp.GIMP.desktop",
           "[Desktop Entry]\nName=GNU Image Manipulation Program\nName[uk]=Програма GIMP\n"
           "Exec=/usr/bin/flatpak run org.gimp.GIMP @@u %U @@\nType=Application\n")
    var = home / ".var" / "app" / "org.gimp.GIMP"
    _write(var / "config/GIMP/2.10/gimprc", '(theme "Dark")\n')
    _write(var / "cache/gimp/2.10/thumb.png", "t" * 1200)
    apps = root / "usr" / "share" / "applications"
    _write(apps / "org.gnome.TextEditor.desktop", "[Desktop Entry]\nName=Text Editor\nExec=gnome-text-editor %U\n"
                                                  "Type=Application\n")
    _write(root / "usr" / "bin" / "gnome-text-editor", "ELF")
    _write(apps / "bitwig-studio.desktop", "[Desktop Entry]\nName=Bitwig Studio\nExec=/opt/bitwig-studio/bitwig-studio\n")
    _write(root / "opt" / "bitwig-studio" / "bitwig-studio", "ELF")
    _write(apps / "hidden-helper.desktop", "[Desktop Entry]\nName=Hidden Helper\nExec=/usr/bin/helper\nNoDisplay=true\n")
    _write(home / ".local/share/applications/Hollow Knight.desktop",
           "[Desktop Entry]\nName=Hollow Knight\nExec=steam steam://rungameid/367520\nType=Application\n")
    _write(root / "var/lib/snapd/desktop/applications/vlc_vlc.desktop",
           "[Desktop Entry]\nName=VLC media player\nExec=env BAMF_DESKTOP_FILE_HINT=/var/lib/snapd/desktop/applications/"
           "vlc_vlc.desktop /snap/bin/vlc --started-from-file %U\nType=Application\n")
    # the graphics card, the disks and the sound card
    drm = root / "sys" / "class" / "drm"
    _write(drm / "card0" / "device" / "uevent", "DRIVER=amdgpu\nPCI_CLASS=30000\nPCI_ID=1002:73BF\n"
                                                "PCI_SLOT_NAME=0000:03:00.0\n")
    (drm / "card0-DP-1").mkdir()
    _write(root / "proc" / "self" / "mounts", "/dev/nvme0n1p3 / btrfs rw,relatime 0 0\n/dev/nvme0n1p2 /boot ext4 rw 0 0\n")
    _write(root / "proc" / "asound" / "cards", " 0 [PCH            ]: HDA-Intel - HDA Intel PCH\n"
                                               "                      HDA Intel PCH at 0x6001108000 irq 147\n")
    procs = [("systemd", ""), ("gnome-shell", "/usr/bin/gnome-shell"), ("steam", str(steam / "ubuntu12_32" / "steam")),
             ("Discord", "/usr/share/discord/Discord")]
    cmds = Cmds({"lspci -mm": (0, LSPCI), MESA: (0, "24.2.7\n"), KERNEL: (0, ""), OOMD: (0, ""),
                 DUMPS: (1, "No coredumps found.\n")})
    return SimpleNamespace(tmp=tmp_path, root=root, home=home, steam=steam, game=game, win64=win64, pfx=pfx,
                           local=local, hk=hk, unity=unity, aw=aw, aw_pfx=aw_pfx, ug=ug, lpfx=lpfx, var=var,
                           procs=procs, cmds=cmds, online=True)


def _lfx(w, actions=None, env=None, printers=None):
    log = SimpleNamespace(urls=[], trashed=[])
    fx = fixit.Fixer(actions if actions is not None else Actions(), runner=w.cmds, platform_="linux", env=env or {},
                     home=w.home, user="olena", pc="fedora", steam_base=lambda: w.steam,
                     open_url=lambda u: log.urls.append(u) or True, trash=lambda paths: log.trashed.append(list(paths)),
                     printers=printers, refresh_net=lambda: None, drives=lambda: [], data_dir=w.tmp / "lanterna-data",
                     procs=lambda: list(w.procs), root=w.root, probe=lambda host, port: w.online,
                     uname=lambda: "6.11.4-301.fc41.x86_64")
    return fx, log


def _disk(monkeypatch, free=200 * GB, boot=None):
    """The free space of every disk (the test computer's own doesn't matter); boot: of /boot."""
    def usage(p):
        f = boot if boot is not None and str(p).replace("\\", "/").rstrip("/").endswith("/boot") else free
        return SimpleNamespace(total=1000 * GB, used=1000 * GB - f, free=f)
    monkeypatch.setattr(shutil, "disk_usage", usage)


# ---------------------------------------------------------------- 1. the programs
def test_the_programs_of_a_linux_computer(tmp_path):
    w = _lx(tmp_path)
    fx, _log = _lfx(w)
    progs = fx.programs()
    got = {p.name: p for p in progs}
    assert len(progs) == len(got) == 9 and {n: p.label() for n, p in got.items()} == {
        GAME: "Steam game 1643320", "Hollow Knight": "Steam game 367520", "Alan Wake 2": "Epic Games in Heroic",
        "Unreal Gold": "GOG in Heroic", "Diablo II": "Lutris", "GNU Image Manipulation Program": "Flatpak app org.gimp.GIMP",
        "Text Editor": "program", "Bitwig Studio": "program", "VLC media player": "Snap app vlc"}
    # Proton, Steam's runtime, a hidden helper, a launcher's shortcut and a game no longer installed are not programs
    assert got[GAME].prefix == str(w.pfx) and got["Hollow Knight"].prefix == ""
    assert got["Alan Wake 2"].prefix == str(w.aw_pfx) and got["Alan Wake 2"].version == "1.2.8"
    assert Path(got["Diablo II"].folder) == w.lpfx / "drive_c" / "Program Files" / "Diablo II"   # not the whole prefix
    assert got["Diablo II"].prefix == str(w.lpfx)
    assert got["Bitwig Studio"].folder == str(w.root / "opt" / "bitwig-studio") and got["Text Editor"].folder == ""
    assert fx.program("gimp").appid == "org.gimp.GIMP" and fx.program("сталкер 2").name == GAME


# ---------------------------------------------------------------- 2. fix_check: a game, what the system noted
def test_a_windows_game_through_proton(tmp_path, monkeypatch):
    w = _lx(tmp_path)
    _disk(monkeypatch)
    fx, _log = _lfx(w)
    out = fx.check("stalker 2", "black screen in a mission", limit=9000)
    flat = out.replace("\\", "/")
    assert out.startswith(f"Program: {GAME} — Steam game 1643320, build 16612345\n")
    assert "Installed in (place install): ~/.local/share/Steam/steamapps/common/S.T.A.L.K.E.R. 2\n" in flat
    assert "It isn't running now." in out
    assert ("! Stalker2/Content/Movies_old (folder, 4.9 KB: 2 videos (.bk2)): its videos are hidden from the program "
            "by renaming the folder (there is no 'Movies').") in out
    assert ("Runs through Proton 9 (chosen for this game in Steam). Another version: Steam → the game → Properties → "
            "Compatibility.") in out
    assert ("- For more details: Steam → the game → Properties → Launch options: PROTON_LOG=1 %command% — then Proton "
            "writes ~/steam-1643320.log, and fix_check reads it.") in out
    assert "The system noted (crashes: last 30 days; the graphics card and memory: last 7 days):\n- No crashes of it." \
        in out
    # its AppData is in its Proton prefix: its log is found there
    assert "Newest log: local/Saved/Logs/Stalker2.log" in out and "- LogVulkanRHI: Error: VK_ERROR_DEVICE_LOST" in out
    assert "- local: ~/.local/share/Steam/steamapps/compatdata/1643320/pfx/drive_c/users/steamuser/AppData/Local/" \
           "Stalker2\n" in flat
    assert "Graphics: AMD Radeon RX 6800/6800 XT / 6900 XT, the amdgpu driver (Mesa) 24.2.7" in out
    assert "Running now (these can hook into games: overlays, recorders, audio tools): Discord" in out
    assert "- shader caches (fix_cache): mesa_cache" in out and "Free on its disk: " in out
    assert "Steam isn't running now" not in out and "Visual C++" not in out and "Windows noted" not in out
    assert str(w.home) not in out and "olena" not in out                  # the home folder is "~", the name goes
    assert {x.split()[0] for x in w.cmds.runs} == {"journalctl", "coredumpctl", "lspci", "rpm"}     # it only reads


def test_a_linux_game_its_crashes_and_memory(tmp_path, monkeypatch):
    w = _lx(tmp_path)
    _disk(monkeypatch)
    t = 1795600000
    exe = str(w.hk / "hollow_knight.x86_64")
    w.cmds.table[DUMPS] = (0, json.dumps([
        {"time": t * 1_000_000, "pid": 4242, "uid": 1000, "gid": 1000, "sig": 11, "corefile": "present", "exe": exe,
         "size": 52_000_000},
        {"time": (t - 600) * 1_000_000, "pid": 4100, "uid": 1000, "gid": 1000, "sig": 11, "corefile": "present",
         "exe": exe, "size": 51_000_000},
        {"time": t * 1_000_000, "pid": 999, "uid": 1000, "gid": 1000, "sig": 6, "corefile": "missing",
         "exe": "/usr/bin/gnome-text-editor", "size": 0}]))
    w.cmds.table[KERNEL] = (0, "2026-11-20T21:04:11+02:00 fedora kernel: amdgpu 0000:03:00.0: amdgpu: ring gfx_0.0.0 "
                               "timeout, signaled seq=48227, emitted seq=48229\n"
                               "2026-11-20T21:04:12+02:00 fedora kernel: amdgpu 0000:03:00.0: amdgpu: GPU reset begin!\n"
                               "2026-11-21T19:02:33+02:00 fedora kernel: Out of memory: Killed process 5151 "
                               "(hollow_knight.x) total-vm:9882736kB, anon-rss:7100000kB\n")
    w.cmds.table[OOMD] = (0, f"2026-11-21T19:05:00+02:00 fedora systemd-oomd[987]: Killed /user.slice/user-1000.slice/"
                             f"{USER_UNIT}/app.slice/app-gnome-steam-4242.scope due to memory pressure for "
                             f"/user.slice/user-1000.slice/{USER_UNIT} being 81.23% > 50.00% for > 20s\n"
                             "2026-11-21T19:05:00+02:00 fedora systemd-oomd[987]: Considering 3 cgroups for killing.\n")
    fx, _log = _lfx(w)
    out = fx.check("hollow knight", limit=9000)
    last = time.strftime("%Y-%m-%d %H:%M", time.localtime(t))
    assert "A Linux version of the game (no Proton)." in out and "PROTON_LOG" not in out
    assert (f"hollow_knight.x86_64 crashed 2× (last {last}): SIGSEGV — it touched memory it shouldn't (often a mod, an "
            "overlay, the graphics driver or damaged files)") in out
    assert "gnome-text-editor" not in out                                  # another program's crash stays out
    # the kernel writes its name cut to 15 letters: hollow_knight.x
    assert ("! Linux ran out of memory and stopped it (1×, last 2026-11-21 19:02): close other programs while it runs; "
            "more memory or a bigger swap helps.") in out
    assert "! systemd-oomd closed Steam with the game when memory ran low (1×, last 2026-11-21 19:05)" in out
    assert ("! The graphics card hung or was reset in the last 7 days (1×, last 2026-11-20 21:04): amdgpu 0000:03:00.0: "
            "amdgpu: GPU reset begin. Usually the driver") in out
    assert "- Linux ran out of memory 1× this week (it stopped: hollow_knight.x)." in out
    assert "Newest log: config/Player.log" in out and "- Crash!!!" in out          # Unity's log in ~/.config/unity3d
    assert "- config: ~/.config/unity3d/Team Cherry/Hollow Knight\n" in out.replace("\\", "/")
    assert "- shader caches (fix_cache): steam_shaders, mesa_cache" in out


def test_older_systems_and_ubuntus_crash_reports(tmp_path):
    w = _lx(tmp_path)
    fx, _log = _lfx(w)
    game = LX_HOME + "/.local/share/Steam/steamapps/common/Hollow Knight/hollow_knight.x86_64"
    w.cmds.table[DUMPS] = (1, "coredumpctl: unrecognized option '--json=short'\n")           # systemd before 248
    w.cmds.table["coredumpctl --no-pager --no-legend --since=-30d list"] = (
        0, f"Fri 2026-11-20 21:04:11 EET  4242  1000  1000 SIGSEGV present  {game}  52.0M\n"
           "Fri 2026-11-20 21:10:00 EET  4300  1000  1000 6 none  /usr/bin/foo  -\n")
    assert fixlinux.coredumps(fx) == [{"exe": game, "sig": "SIGSEGV", "t": "2026-11-20 21:04"},
                                      {"exe": "/usr/bin/foo", "sig": "SIGABRT", "t": "2026-11-20 21:10"}]
    del w.cmds.table[DUMPS]                                                   # Ubuntu: no coredumpctl, apport's files
    _write(w.root / "var/crash/_usr_games_foo.1000.crash", "ProblemType: Crash\nExecutablePath: /usr/games/foo\n"
                                                          "Signal: 11\n")
    _write(w.root / "var/crash/_usr_bin_bar.1000.crash", "ProblemType: Crash\nExecutablePath: /usr/bin/bar\n")
    got = sorted(fixlinux.coredumps(fx), key=lambda d: d["exe"])
    assert [(d["exe"], d["sig"]) for d in got] == [("/usr/bin/bar", ""), ("/usr/games/foo", "SIGSEGV")]


def test_a_game_on_a_windows_disk_and_two_graphics_cards(tmp_path, monkeypatch):
    w = _lx(tmp_path)
    _disk(monkeypatch)
    disk = tmp_path / "Games Disk"
    lib = disk / "SteamLibrary"
    _write(w.steam / "steamapps" / "libraryfolders.vdf",
           f'"libraryfolders"\n{{\n\t"0"\n\t{{\n\t\t"path"\t\t"{w.steam.as_posix()}"\n\t}}\n'
           f'\t"1"\n\t{{\n\t\t"path"\t\t"{lib.as_posix()}"\n\t}}\n}}\n')
    er = _manifest(lib, "1245620", "ELDEN RING", "ELDEN RING")
    _write(er / "Game" / "eldenring.exe", "MZ")
    _write(er / "Game" / "EasyAntiCheat" / "Settings.json", "{}")
    mount = disk.as_posix().replace(" ", "\\040")                             # /proc/self/mounts writes a space so
    _write(w.root / "proc/self/mounts", f"/dev/nvme0n1p3 / btrfs rw 0 0\n/dev/sdb1 {mount} ntfs3 rw,uid=1000 0 0\n")
    drm = w.root / "sys/class/drm"
    _write(drm / "card0/device/uevent", "DRIVER=i915\nPCI_ID=8086:3E9B\nPCI_SLOT_NAME=0000:00:02.0\n")
    _write(drm / "card1/device/uevent", "DRIVER=nouveau\nPCI_ID=10DE:1F91\nPCI_SLOT_NAME=0000:01:00.0\n")
    w.cmds.table["lspci -mm"] = (0, '00:02.0 "VGA compatible controller" "Intel Corporation" "CoffeeLake-H GT2 [UHD '
                                    'Graphics 630]" -r02 "Lenovo" "Device 3ffc"\n'
                                    '01:00.0 "3D controller" "NVIDIA Corporation" "TU117M [GeForce GTX 1650 Mobile / '
                                    'Max-Q]" -ra1 "Lenovo" "Device 3ffc"\n')
    fx, _log = _lfx(w)
    out = fx.check("elden ring", limit=9000)
    assert "Runs through Proton Experimental (Steam's default). Another version:" in out    # Steam's choice for all
    assert ("It has Easy Anti-Cheat: online play works on Linux only when the game's makers allow it (ProtonDB or "
            "areweanticheatyet.com say).") in out
    assert ("! It is on a disk with NTFS (a Windows file system): games through Proton often don't start, crash or lose "
            "saves there. Steam can move it to a Linux disk: Properties → Installed Files → Move install folder.") in out
    assert "Graphics: Intel UHD Graphics 630, the i915 driver (Mesa) 24.2.7" in out
    assert ("! NVIDIA GeForce GTX 1650 Mobile / Max-Q: it runs on the open nouveau driver, so games run very slowly or "
            "not at all. NVIDIA's own driver fixes it (Fedora: from RPM Fusion; Ubuntu: Software & Updates → "
            "Additional Drivers). Installing it needs the computer's password, so the user does it.") in out
    assert "- Two graphics cards: a game may run on the weaker built-in one." in out
    assert "- For more details: Steam → the game → Properties → Launch options: PROTON_LOG=1" in out   # no prefix yet
    # another program: the slow driver of the second card is seldom its problem, so it is no strong clue
    out = fx.check("gimp", limit=9000)
    assert ("- NVIDIA GeForce GTX 1650 Mobile / Max-Q: it runs on the open nouveau driver; that matters for games and "
            "3D, less for other programs.") in out
    assert "! NVIDIA" not in out and "Two graphics cards" not in out
    assert "A Flatpak app (org.gimp.GIMP): its installed files are Flatpak's own (fix_verify says how to repair them)." \
        in out
    out = fx.check("text editor", limit=9000)
    assert re.search(r"\nA program from the system's packages \(.+gnome-text-editor\): its installed files aren't "
                     r"changed \(fix_verify says how to install it again\)\.\n", out)


def test_programs_started_through_dbus_or_a_shell(tmp_path):
    root, home = tmp_path / "root", tmp_path / "root" / "home" / "olena"
    _write(root / "usr/share/dbus-1/services/org.gnome.Maps.service",
           "[D-BUS Service]\nName=org.gnome.Maps\nExec=/usr/share/gnome-maps/org.gnome.Maps --gapplication-service\n")
    assert fixlinux.exec_path("gapplication launch org.gnome.Maps %U", root, home) == \
        str(root / "usr/share/gnome-maps/org.gnome.Maps")                 # not /usr/bin/gapplication
    assert fixlinux.exec_path("gapplication launch org.gnome.Weather", root, home) == ""        # no service file
    assert fixlinux.exec_path('sh -c "cd /opt/x && ./run"', root, home) == ""


def test_protons_log_is_read_and_never_changed(tmp_path, monkeypatch):
    w = _lx(tmp_path)
    _disk(monkeypatch)
    log = _write(w.home / "steam-1643320.log",
                 "======================\nProton: 1730000000 proton-9.0-4\nSteamGameId: 1643320\n"
                 'err:module:import_dll Library VCRUNTIME140_1.dll (which is needed by L"C:\\\\windows\\\\system32\\\\'
                 'msvcp140.dll") not found\n')
    future = time.time() + 60
    os.utime(log, (future, future))                                        # newer than the game's own log
    fx, _log = _lfx(w)
    out = fx.check("stalker 2", limit=9000)
    assert "Newest log: proton_log (steam-1643320.log)" in out and "PROTON_LOG=1" not in out
    assert "Older logs: local/Saved/Logs/Stalker2.log" in out
    assert "- proton_log: ~/steam-1643320.log\n" in out.replace("\\", "/")
    text = fx.read("stalker 2", "proton_log", "steam-1643320.log", find="not found")
    assert text.startswith("proton_log/steam-1643320.log (") and "VCRUNTIME140_1.dll" in text
    assert fx.read("stalker 2", "proton_log", "").startswith("proton_log/steam-1643320.log (")
    with pytest.raises(WorkError, match="The place 'proton_log' is one file: give path 'steam-1643320.log'."):
        fx.read("stalker 2", "proton_log", "other.txt")
    with pytest.raises(WorkError, match="Proton's log is only read"):
        fx.propose_rename("stalker 2", "proton_log", "steam-1643320.log", "old.log")
    with pytest.raises(WorkError, match="Proton's log is only read"):
        fx.propose_setting("stalker 2", "proton_log", "steam-1643320.log", "x", "1")


def test_paths_come_back_the_way_they_were_shown(tmp_path):
    w = _lx(tmp_path)
    fx, _log = _lfx(w)
    shown = "~/.config/unity3d/Team Cherry/Hollow Knight/Player.log"         # as fix_check showed it
    assert "Crash!!!" in fx.read("hollow knight", "config", shown)
    assert "Crash!!!" in fx.read("hollow knight", "config", "Player.log")
    with pytest.raises(WorkError, match="outside the place 'config'"):
        fx.read("hollow knight", "config", "~/.config/heroic/gog_store/installed.json")


# ---------------------------------------------------------------- 3. what runs now
def test_what_runs_now_is_read_from_proc(tmp_path):
    proc = tmp_path / "proc"

    def pid(n, comm, args, cgroup="0::/user.slice/user-1000.slice/session-2.scope\n"):
        _write(proc / str(n) / "comm", comm + "\n")
        _write(proc / str(n) / "cmdline", b"".join(a.encode() + b"\0" for a in args))
        _write(proc / str(n) / "cgroup", cgroup)
    common = LX_HOME + "/.local/share/Steam/steamapps/common"
    game = common + "/S.T.A.L.K.E.R. 2"
    pid(1, "systemd", ["/usr/lib/systemd/systemd", "--switched-root"])
    pid(200, "Stalker2-Win64-", ["Z:" + game.replace("/", "\\") + "\\Stalker2\\Binaries\\Win64\\Stalker2-Win64-Shipping.exe",
                                 "-dx12"])                                  # Wine shows the Windows path: Z: is /
    pid(201, "explorer.exe", ["C:\\windows\\explorer.exe", "/desktop"])
    pid(300, "reaper", [LX_HOME + "/.local/share/Steam/ubuntu12_32/reaper", "SteamLaunch", "AppId=1643320", "--",
                        common + "/SteamLinuxRuntime_sniper/_v2-entry-point", "--verb=waitforexitandrun", "--",
                        common + "/Proton 9.0 (Beta)/proton", "waitforexitandrun", game + "/Stalker2.exe"])
    pid(400, "gimp-2.10", ["/app/bin/gimp-2.10"],
        f"0::/user.slice/user-1000.slice/{USER_UNIT}/app.slice/app-flatpak-org.gimp.GIMP-12345.scope\n")
    (proc / "self").mkdir()
    (proc / "500").mkdir()                                                 # ended while it was read
    assert sorted(fixlinux.processes(proc)) == sorted([
        ("systemd", ""), ("Stalker2-Win64-", ""),
        ("Stalker2-Win64-Shipping.exe", game + "/Stalker2/Binaries/Win64/Stalker2-Win64-Shipping.exe"),
        ("explorer.exe", ""), ("explorer.exe", ""),
        ("reaper", ""), ("steam game", "steam-app:1643320"), ("Stalker2.exe", game + "/Stalker2.exe"),
        ("gimp-2.10", ""), ("org.gimp.GIMP", "flatpak:org.gimp.GIMP")])


@pytest.mark.skipif(sys.platform == "win32", reason="/proc/<pid>/exe is a link")
def test_a_programs_path_comes_from_its_link(tmp_path):
    _write(tmp_path / "7" / "comm", "foo\n")
    os.symlink("/usr/bin/foo (deleted)", tmp_path / "7" / "exe")           # updated while it runs
    assert fixlinux.processes(tmp_path) == [("foo", "/usr/bin/foo")]


def test_a_game_steam_started_is_running(tmp_path):
    w = _lx(tmp_path)
    fx, _log = _lfx(w)
    game, gimp = fx.program("stalker 2"), fx.program("gimp")
    assert fx.running(game) == [] and fx.running(gimp) == []
    w.procs += [("reaper", ""), ("steam game", "steam-app:1643320")]
    assert fx.running(game) == [GAME]                                     # Steam started it: its AppId says so
    w.procs[-1:] = [("Stalker2-Win64-Shipping.exe", str(w.win64 / "Stalker2-Win64-Shipping.exe"))]
    assert fx.running(game) == ["Stalker2-Win64-Shipping.exe"]             # where Wine runs it from
    with pytest.raises(WorkError, match=re.escape(f"{GAME} is running now")):
        fx.propose_rename("stalker 2", "install", "Stalker2/Content/Movies_old", "Movies")
    w.procs[:] = [("gimp-2.10", ""), ("org.gimp.GIMP", "flatpak:org.gimp.GIMP")]
    assert fx.running(gimp) == ["GNU Image Manipulation Program"] and fx.running(game) == []


# ---------------------------------------------------------------- 4. sound
HDMI, ANALOG, MIC, BUDS = ("alsa_output.pci-0000_00_1f.3.hdmi-stereo", "alsa_output.pci-0000_00_1f.3.analog-stereo",
                           "alsa_input.pci-0000_00_1f.3.analog-stereo", "bluez_output.AC_80_0A_12_34_56.1")
PA_INFO = ("Server String: /run/user/1000/pulse/native\nLibrary Protocol Version: 35\nServer Protocol Version: 35\n"
           "Is Local: yes\nClient Index: 77\nTile Size: 65472\nUser Name: olena\nHost Name: fedora\n"
           "Server Name: PulseAudio (on PipeWire 1.2.6)\nServer Version: 15.0.0\n"
           "Default Sample Specification: float32le 2ch 48000Hz\nDefault Channel Map: front-left,front-right\n"
           f"Default Sink: {HDMI}\nDefault Source: {MIC}\nCookie: 2b4a:9f3c\n")


def _dev(n, state, name, desc, mute, vol, ports=(), active="", kind="Sink"):
    """One device the way 'pactl list sinks' (or sources) prints it."""
    return (f"{kind} #{n}\n\tState: {state}\n\tName: {name}\n\tDescription: {desc}\n\tDriver: PipeWire\n"
            "\tSample Specification: s32le 2ch 48000Hz\n\tChannel Map: front-left,front-right\n"
            f"\tOwner Module: 4294967295\n\tMute: {mute}\n"
            f"\tVolume: front-left: {vol * 655} / {vol}% / -1.00 dB,   front-right: {vol * 655} / {vol}% / -1.00 dB\n"
            "\t        balance 0.00\n\tBase Volume: 65536 / 100% / 0.00 dB\n"
            f'\tProperties:\n\t\talsa.card = "0"\n\t\tdevice.description = "{desc}"\n'
            "\tPorts:\n" + "".join(f"\t\t{p}: {d}\n" for p, d in ports) + f"\tActive Port: {active}\n\tFormats:\n\t\tpcm\n")


def _sound(w):
    """PipeWire with the laptop's speakers (muted and almost silent), HDMI as the output and Bluetooth earbuds; the
    speakers and the microphone have the same name, as they often do."""
    sinks = "\n".join([
        _dev(52, "SUSPENDED", HDMI, "Built-in Audio Digital Stereo (HDMI)", "no", 100,
             [("hdmi-output-0", "HDMI / DisplayPort (type: HDMI, priority: 5900, available)")], "hdmi-output-0"),
        _dev(53, "RUNNING", ANALOG, "Built-in Audio Analog Stereo", "yes", 5,
             [("analog-output-speaker", "Speakers (type: Speaker, priority: 10000, availability unknown)"),
              ("analog-output-headphones", "Headphones (type: Headphones, priority: 9900, not available)")],
             "analog-output-speaker"),
        _dev(60, "IDLE", BUDS, "Olena's Buds", "no", 70, [("headset-output", "Headset (type: Headset, available)")],
             "headset-output")])
    sources = "\n".join([
        _dev(54, "SUSPENDED", HDMI + ".monitor", "Monitor of Built-in Audio Digital Stereo (HDMI)", "no", 100,
             kind="Source"),
        _dev(55, "SUSPENDED", MIC, "Built-in Audio Analog Stereo", "yes", 60,
             [("analog-input-internal-mic", "Internal Microphone (type: Mic, priority: 8900, availability unknown)")],
             "analog-input-internal-mic", kind="Source")])
    w.cmds.table.update({"pactl info": (0, PA_INFO), "pactl list sinks": (0, sinks), "pactl list sources": (0, sources),
                         UNITS: (3, "active\nactive\nactive\ninactive\n")})
    for line in ([f"pactl set-default-sink {x}" for x in (HDMI, ANALOG, BUDS)] +
                 [f"pactl set-sink-mute {ANALOG} {x}" for x in "01"] + [f"pactl set-source-mute {MIC} {x}" for x in "01"] +
                 [f"pactl set-sink-volume {ANALOG} {x}" for x in ("50%", "5%")] +
                 ["systemctl --user restart pipewire.service pipewire-pulse.service wireplumber.service"]):
        w.cmds.table[line] = (0, "")


def test_the_sound_check(tmp_path):
    w = _lx(tmp_path)
    _sound(w)
    fx, _log = _lfx(w)
    out = fx.check("no sound")
    assert out.startswith(
        "Sound:\n- The sound goes to 'Built-in Audio Digital Stereo (HDMI)' (a monitor or TV over HDMI or DisplayPort). "
        "If it has no speakers: fix_system sound_output with one of: Built-in Audio Analog Stereo; <user>'s Buds.\n"
        "- The microphone 'Built-in Audio Analog Stereo' is muted (if the microphone is the problem: fix_system mic_on "
        "turns it on).\n")
    lines = out.split("\n")
    for line in ("- Sound service: PipeWire (pipewire active, pipewire-pulse active, wireplumber active)",
                 "- Sound cards: HDA Intel PCH", "- Output: Built-in Audio Digital Stereo (HDMI) (default) — suspended, "
                 "volume 100%", "- Output: Built-in Audio Analog Stereo — running, volume 5%, muted",
                 "- Output: <user>'s Buds — idle, volume 70%", "- Input: Built-in Audio Analog Stereo (default), muted"):
        assert line in lines, line
    assert "Monitor of" not in out and "Olena" not in out and "sound_restart" not in out
    assert {x.split()[0] for x in w.cmds.runs} == {"pactl", "systemctl"} and not w.cmds.ran("pactl set")


def test_the_sound_goes_elsewhere_and_comes_back(tmp_path):
    w = _lx(tmp_path)
    _sound(w)
    fx, _log = _lfx(w)
    assert fx.propose_system("sound_output", "hdmi") == "'Built-in Audio Digital Stereo (HDMI)' is the sound output " \
                                                        "already."
    assert fx.propose_system("sound_output", "analog") == WAITING
    card = _card(fx)
    assert card.kind == "fix_sound" and card.details == {"name": "Built-in Audio Analog Stereo",
                                                         "was": "Built-in Audio Digital Stereo (HDMI)"}
    assert not w.cmds.ran("pactl set")                                    # nothing changes before Confirm
    done = fx.actions.confirm(card.id)
    assert done.state == "done" and done.result == "the sound goes to Built-in Audio Analog Stereo"
    assert w.cmds.runs[-1] == f"pactl set-default-sink {ANALOG}" and done.undo == {"type": "sound", "default": HDMI}
    assert fx.undo_sound(done.undo) and w.cmds.runs[-1] == f"pactl set-default-sink {HDMI}"
    assert fx.propose_system("sound_output", "<user>'s Buds") == WAITING   # the name the way the check showed it
    assert _card(fx).details["name"] == "<user>'s Buds"
    assert fx.actions.confirm(_card(fx).id).state == "done" and w.cmds.runs[-1] == f"pactl set-default-sink {BUDS}"
    with pytest.raises(WorkError, match="No output is called that. There are: Built-in Audio Digital Stereo"):
        fx.propose_system("sound_output", "usb headset")
    with pytest.raises(WorkError, match="action: sound_output, sound_on, mic_on, sound_restart"):
        fx.propose_system("reboot")


def test_a_muted_output_and_a_muted_microphone(tmp_path):
    w = _lx(tmp_path)
    _sound(w)
    fx, _log = _lfx(w)
    assert fx.propose_system("sound_on", "") == "'Built-in Audio Digital Stereo (HDMI)' is on already (100%)."
    assert fx.propose_system("sound_on", "analog") == WAITING              # the outputs only, not the microphone
    speakers = _card(fx)
    assert speakers.details == {"name": "Built-in Audio Analog Stereo", "muted": True, "volume": 5, "to": 50,
                                "mic": False}
    assert fx.propose_system("mic_on", "") == WAITING                      # the default microphone: a card of its own
    mic = _card(fx)
    assert mic.details == {"name": "Built-in Audio Analog Stereo", "muted": True, "volume": 60, "to": None, "mic": True}
    with pytest.raises(WorkError, match="This card already waits"):
        fx.propose_system("sound_on", "Built-in Audio Analog Stereo")
    done = fx.actions.confirm(speakers.id)
    assert done.result == "Built-in Audio Analog Stereo is on at 50%"
    assert w.cmds.runs[-2:] == [f"pactl set-sink-mute {ANALOG} 0", f"pactl set-sink-volume {ANALOG} 50%"]
    assert done.undo == {"type": "sound", "device": ANALOG, "kind": "sink", "mute": True, "volume": 5}
    assert fx.undo_sound(done.undo)
    assert w.cmds.runs[-2:] == [f"pactl set-sink-volume {ANALOG} 5%", f"pactl set-sink-mute {ANALOG} 1"]
    done = fx.actions.confirm(mic.id)
    assert done.result == "Built-in Audio Analog Stereo is on" and w.cmds.runs[-1] == f"pactl set-source-mute {MIC} 0"
    assert done.undo == {"type": "sound", "device": MIC, "kind": "source", "mute": True, "volume": None}
    # two devices of one model: their system names tell them apart
    twins = [{"name": "usb-1", "description": "USB Headset"}, {"name": "usb-2", "description": "USB Headset"}]
    with pytest.raises(WorkError, match=re.escape("Several match: USB Headset (usb-1); USB Headset (usb-2). Give the "
                                                  "name in brackets.")):
        fixlinux._pick_device("usb headset", twins, "output")
    assert fixlinux._pick_device("usb-2", twins, "output") is twins[1]


def test_the_sound_service_starts_again(tmp_path):
    w = _lx(tmp_path)
    _sound(w)
    fx, _log = _lfx(w)
    assert fx.propose_system("sound_restart") == WAITING
    card = _card(fx)
    assert card.kind == "fix_sound_restart" and card.details == {"name": "PipeWire"} and not w.cmds.ran("systemctl --user r")
    done = fx.actions.confirm(card.id)
    assert done.result == "the sound service started again" and done.undo is None
    assert w.cmds.runs[-1] == "systemctl --user restart pipewire.service pipewire-pulse.service wireplumber.service"
    assert "fix_sound_restart" not in workspace.AUTO_KINDS                 # it stops a call's sound for a moment
    assert {"fix_sound", "fix_unmute"} <= workspace.AUTO_KINDS and "sound" in history.UNDO_TYPES


def test_when_the_sound_service_is_down(tmp_path):
    w = _lx(tmp_path)
    w.cmds.table.update({"pactl info": (1, "Connection failure: Connection refused\n"),
                         UNITS: (3, "failed\nactive\ninactive\ninactive\n")})
    _write(w.root / "proc/asound/cards", "--- no soundcards ---\n")
    fx, _log = _lfx(w)
    out = fx.check("звук")
    assert ("! The sound service isn't running (pipewire, wireplumber): there is no sound without it. fix_system "
            "sound_restart starts it again.") in out
    assert "! The sound service doesn't answer: fix_system sound_restart starts it again." in out
    assert "! Linux sees no sound card: its driver or firmware is missing." in out
    with pytest.raises(WorkError, match="The sound service doesn't answer: fix_system sound_restart first."):
        fx.propose_system("sound_output", "analog")
    w.cmds.table.update({"pactl info": (0, "Server Name: PulseAudio (on PipeWire 1.2.6)\nDefault Sink: auto_null\n"),
                         "pactl list sinks": (0, _dev(1, "IDLE", "auto_null", "Dummy Output", "no", 100)),
                         "pactl list sources": (0, ""), UNITS: (0, "active\nactive\nactive\ninactive\n")})
    out = fx.check("звук")
    assert "! There is no sound output, only a dummy one:" in out and "- Output:" not in out


# ---------------------------------------------------------------- 5. internet
NM_GENERAL = "nmcli -t -f STATE,CONNECTIVITY,WIFI-HW,WIFI,NETWORKING general"
NM_DEVICES = "nmcli -t -f DEVICE,TYPE,STATE,CONNECTION device"
GS = "gsettings get org.gnome.system.proxy"


def _net(w, proxy="'manual'"):
    """Wi-Fi with a weak signal, a VPN, site names that don't work and a proxy left on in GNOME."""
    w.cmds.table.update({
        NM_GENERAL: (0, "connected:full:enabled:enabled:enabled\n"),
        NM_DEVICES: (0, "wlp2s0:wifi:connected:Home\\: 5G\nlo:loopback:connected (externally):lo\n"
                        "p2p-dev-wlp2s0:wifi-p2p:disconnected:\nenp3s0:ethernet:unavailable:\n"),
        "nmcli -t -f IN-USE,SIGNAL device wifi list --rescan no": (0, "*:31\n :80\n"),
        "nmcli -t -f NAME,TYPE connection show --active": (0, "Home\\: 5G:802-11-wireless\nwork-vpn:vpn\nlo:loopback\n"),
        "ip -j -4 addr show": (0, json.dumps([{"ifname": "lo", "addr_info": [{"local": "127.0.0.1"}]},
                                              {"ifname": "wlp2s0", "addr_info": [{"local": "192.168.1.23"}]}])),
        "ip -j -4 route show default": (0, json.dumps([{"dst": "default", "gateway": "192.168.1.1", "dev": "wlp2s0"}])),
        "ping -c 1 -W 2 192.168.1.1": (0, ""),
        "getent ahostsv4 one.one.one.one": (2, ""), "getent ahostsv4 www.msftconnecttest.com": (2, ""),
        f"{GS} mode": (0, proxy + "\n"),
        f"{GS}.http host": (0, "'proxy.example.org'\n"), f"{GS}.http port": (0, "3128\n"),
        f"{GS}.https host": (0, "'proxy.example.org'\n"), f"{GS}.https port": (0, "3128\n"),
        f"{GS}.socks host": (0, "''\n"), f"{GS}.socks port": (0, "0\n"),
        "gsettings set org.gnome.system.proxy mode 'none'": (0, ""),
        "gsettings set org.gnome.system.proxy mode 'manual'": (0, "")})


def test_the_internet_check_and_the_proxy(tmp_path):
    w = _lx(tmp_path)
    _net(w)
    fx, _log = _lfx(w)
    lines = fx.check("internet").split("\n")
    assert lines[0] == "Internet:"
    for line in ("! The Wi-Fi signal is weak (31%): closer to the router, or a cable.",
                 "! A VPN is on: work-vpn. It can block the internet: try with it off.",
                 "! A proxy is on: proxy.example.org:3128. If the user didn't set it on purpose (some programs leave "
                 "one), fix_system proxy_off turns it off.",
                 "- wlp2s0 (wifi): connected", "- enp3s0 (ethernet): unavailable", "- Wi-Fi signal: 31% — weak",
                 "- Addresses: 192.168.1.23; router: 192.168.1.1", "- The router answers: yes",
                 "- Names of sites (DNS): do not work", "- The internet by a direct address: works",
                 "- Proxy: proxy.example.org:3128"):
        assert line in lines, line
    assert ("! The internet works, but site names don't (DNS). The user can set the DNS server 1.1.1.1 in Settings → "
            "Network → the connection → IPv4. Clearing the DNS cache needs the computer's password, so the user runs "
            "'sudo resolvectl flush-caches' in Terminal.") in lines
    assert not any("p2p" in x or "loopback" in x for x in lines)
    assert not w.cmds.ran("gsettings set")                                # it only looked
    assert fx.propose_system("proxy_off") == WAITING
    card = _card(fx)
    assert card.kind == "fix_proxy" and card.details == {"server": "proxy.example.org:3128", "linux": True}
    done = fx.actions.confirm(card.id)
    assert done.state == "done" and w.cmds.runs[-1] == "gsettings set org.gnome.system.proxy mode 'none'"
    assert done.undo == {"type": "proxy", "linux": "gnome", "old": "manual"}
    assert fx.undo_proxy(done.undo) and w.cmds.runs[-1] == "gsettings set org.gnome.system.proxy mode 'manual'"
    w.cmds.table[f"{GS} mode"] = (0, "'none'\n")
    assert fx.propose_system("proxy_off") == "No proxy is on: nothing to turn off."


@pytest.mark.parametrize("general, says", [
    ("disconnected:none:enabled:disabled:enabled", "! Wi-Fi is turned off: the user turns it on in the system menu"),
    ("disconnected:none:disabled:enabled:enabled", "! Wi-Fi is turned off by a key or a switch on the computer"),
    ("asleep:none:enabled:enabled:disabled", "! Networking is turned off:"),
    ("disconnected:none:enabled:enabled:enabled", "! The computer isn't connected to any network:")])
def test_when_the_computer_isnt_connected(tmp_path, general, says):
    w = _lx(tmp_path)
    _net(w, proxy="'none'")
    w.online = False
    w.cmds.table.update({NM_GENERAL: (0, general + "\n"), NM_DEVICES: (0, "wlp2s0:wifi:disconnected:\n"),
                         "ip -j -4 addr show": (0, "[]"), "ip -j -4 route show default": (0, "[]")})
    fx, _log = _lfx(w)
    out = fx.check("internet")
    assert says in out and "- Addresses: none; router: none" in out and "- Proxy: off" in out


def test_a_proxy_lanterna_cant_turn_off_and_kdes_proxy(tmp_path):
    w = _lx(tmp_path)
    _net(w, proxy="'none'")
    fx, _log = _lfx(w, env={"HTTPS_PROXY": "http://10.0.0.5:8080"})
    assert ("! A proxy is set in the environment: HTTPS_PROXY=http://10.0.0.5:8080. The user removes it from the file "
            "that sets it (~/.bashrc, ~/.profile or /etc/environment), then signs out and in.") in fx.check("internet")
    with pytest.raises(WorkError, match="This proxy is set in the environment"):
        fx.propose_system("proxy_off")
    del w.cmds.table[f"{GS} mode"]                                         # KDE: no GNOME settings here
    _write(w.home / ".config" / "kioslaverc", "[Proxy Settings]\nProxyType=1\nhttpProxy=http://127.0.0.1 8080\n\n"
                                              "[Other]\nx=1\n")
    kio = "kwriteconfig6 --file kioslaverc --group Proxy Settings --key ProxyType"
    w.cmds.table.update({f"{kio} 0": (0, ""), f"{kio} 1": (0, "")})
    fx, _log = _lfx(w, env={"XDG_CURRENT_DESKTOP": "KDE"})
    assert fx.propose_system("proxy_off") == WAITING
    assert _card(fx).details == {"server": "http://127.0.0.1 8080", "linux": True}
    done = fx.actions.confirm(_card(fx).id)
    assert w.cmds.runs[-1] == f"{kio} 0" and done.undo == {"type": "proxy", "linux": "kde", "old": "1"}
    assert fx.undo_proxy(done.undo) and w.cmds.runs[-1] == f"{kio} 1"


# ---------------------------------------------------------------- 6. printers
LPSTAT_P = ("printer Canon_TS5050 disabled since Sat 21 Nov 2026 09:12:44 AM EET -\n\tPaused\n\tForm mounted:\n"
            "\tContent types: any\n\tPrinter types: unknown\n\tDescription: Canon TS5050 series\n"
            "\tAlerts: offline-report\n\tLocation: \n\tConnection: direct\n"
            "printer HP_LaserJet_M110w is idle.  enabled since Fri 20 Nov 2026 10:00:00 AM EET\n\tForm mounted:\n"
            "\tDescription: HP LaserJet M110w\n\tAlerts: none\n\tLocation: Office\n"
            "printer PDF is idle.  enabled since Fri 20 Nov 2026 10:00:00 AM EET\n"
            "\tDescription: Generic CUPS-PDF Printer\n\tAlerts: none\n")
JOBS = ("Canon_TS5050-7          olena          1024   Sat 21 Nov 2026 09:00:01 AM EET\n"
        "HP_LaserJet_M110w-12    olena         10240   Sat 21 Nov 2026 09:05:00 AM EET\n"
        "HP_LaserJet_M110w-13    anna           2048   Sat 21 Nov 2026 09:06:00 AM EET\n")


def _cups(w, default="PDF"):
    """CUPS with a paused, offline Canon, an HP and the PDF printer; lpoptions -d makes the user's own default."""
    st = SimpleNamespace(default=default)

    def lpd(_args):
        return 0, f"system default destination: {st.default}\n" if st.default else "no system default destination\n"

    def lpo(args):
        st.default = args[-1]
        _write(w.home / ".cups" / "lpoptions", f"Default {args[-1]}\n")
        return 0, ""
    w.cmds.table.update({"lpstat -r": (0, "scheduler is running\n"), "lpstat -l -p": (0, LPSTAT_P), "lpstat -d": lpd,
                         "lpstat -e": (0, "Canon_TS5050\nHP_LaserJet_M110w\nPDF\n"), "lpstat -o": (0, JOBS),
                         "lpstat -o HP_LaserJet_M110w": (0, JOBS.split("\n", 1)[1]), "lpstat -o PDF": (0, ""),
                         "cancel HP_LaserJet_M110w-12": (0, "")})
    for name in ("Canon_TS5050", "HP_LaserJet_M110w", "PDF"):
        w.cmds.table[f"lpoptions -d {name}"] = lpo
    return st


def test_the_printer_check(tmp_path):
    w = _lx(tmp_path)
    _cups(w)
    fx, _log = _lfx(w)
    assert fx.check("printer").split("\n") == [
        "Printers:",
        "! Canon_TS5050 is paused: in Settings → Printers, open it and resume it (it may ask for the computer's "
        "password).",
        "! Canon_TS5050 is offline: check that it is on and connected (cable or the same Wi-Fi).",
        "! 3 print jobs wait in the queue: stuck jobs block the next ones; fix_system print_queue clears them.",
        "! The default printer is 'PDF' (not a real printer): fix_system default_printer makes the right one the "
        "default.",
        "- Canon_TS5050: paused, offline, 1 job waiting", "- HP_LaserJet_M110w: ready, 2 jobs waiting",
        "- PDF (default): ready"]
    w.cmds.table["lpstat -r"] = (1, "scheduler is not running\n")
    assert ("! The printing service (CUPS) isn't running: nothing prints without it. Starting it needs the computer's "
            "password, so the user runs 'sudo systemctl enable --now cups' in Terminal (or restarts the computer).") \
        in fx.check("printer").split("\n")
    w.cmds.table.pop("lpstat -r")                                          # no CUPS at all
    assert fx.check("printer") == ("Printers:\n! Printing isn't set up on this computer: CUPS, the printing service, "
                                   "isn't installed (the package 'cups'). Installing it needs the computer's password.")


def test_the_default_printer_and_the_users_own_print_jobs(tmp_path):
    w = _lx(tmp_path)
    st = _cups(w)
    fx, _log = _lfx(w)
    assert fx.propose_system("default_printer", "laserjet") == WAITING
    card = _card(fx)
    assert card.kind == "fix_printer" and card.details == {"name": "HP_LaserJet_M110w", "was": "PDF", "linux": True}
    done = fx.actions.confirm(card.id)
    assert done.state == "done" and st.default == "HP_LaserJet_M110w" and w.cmds.runs[-1] == "lpoptions -d HP_LaserJet_M110w"
    assert done.undo == {"type": "printer", "name": "PDF", "linux": True}
    assert fx.undo_printer(done.undo) and st.default == "PDF"
    assert fx.propose_system("default_printer", "pdf") == "'PDF' is the default printer already."
    st.default = ""                                  # no default before: Undo takes away the user's own choice only
    assert fx.propose_system("default_printer", "laserjet") == WAITING
    done = fx.actions.confirm(_card(fx).id)
    lpoptions = w.home / ".cups" / "lpoptions"
    assert done.undo == {"type": "printer", "name": "", "linux": True}
    assert lpoptions.read_text(encoding="utf-8") == "Default HP_LaserJet_M110w\n"
    assert fx.undo_printer(done.undo) and lpoptions.read_text(encoding="utf-8") == "Dest HP_LaserJet_M110w\n"
    assert fx.propose_system("print_queue", "pdf") == "No print jobs wait for PDF: nothing to clear."
    assert fx.propose_system("print_queue", "laserjet") == WAITING
    card = _card(fx)
    assert card.kind == "fix_queue" and card.details == {"name": "HP_LaserJet_M110w", "linux": True}
    done = fx.actions.confirm(card.id)
    assert done.result == "removed 1 print job of HP_LaserJet_M110w; 1 of other users stayed"
    assert w.cmds.runs[-1] == "cancel HP_LaserJet_M110w-12"                 # the user's own job, not anna's
    with pytest.raises(WorkError, match="No printer is called that. Printers: Canon_TS5050; HP_LaserJet_M110w; PDF"):
        fx.propose_system("default_printer", "epson")


# ---------------------------------------------------------------- 7. updates
def test_updates_on_fedora(tmp_path, monkeypatch):
    _disk(monkeypatch, free=3 * GB, boot=100 * MB)
    w = _lx(tmp_path)
    r = w.root
    _write(r / "etc/os-release", 'NAME="Fedora Linux"\nVERSION="41 (Workstation Edition)"\nID=fedora\nVERSION_ID=41\n'
                                 'PRETTY_NAME="Fedora Linux 41 (Workstation Edition)"\n')
    for k in ("6.10.12-200.fc41.x86_64", "6.11.4-301.fc41.x86_64", "6.12.9-200.fc41.x86_64"):
        (r / "lib" / "modules" / k).mkdir(parents=True)
    _write(r / "var/log/dnf5.log", '2026-11-21T08:00:12+0000 [4020] INFO --- DNF5 launched with arguments: "dnf5 '
                                   'upgrade" ---\n2026-11-21T08:00:30+0000 [4020] ERROR Librepo error: Curl error (6): '
                                   "Could not resolve hostname for https://mirrors.fedoraproject.org/metalink?repo="
                                   "updates-released-f41&arch=x86_64 [Could not resolve host: mirrors.fedoraproject.org]\n")
    offline = r / "usr/lib/sysimage/libdnf5/offline/offline-transaction-state.toml"      # GNOME Software with dnf5
    _write(offline, '[offline-transaction-state]\nmodule_platform_id = ""\npoweroff_after = false\nverb = ""\n'
                    'system_releasever = "41"\ntarget_releasever = "41"\ncachedir = "/var/cache/dnf5daemon-server"\n'
                    'status = "download-complete"\ncmd_line = "dnf5daemon-server"\nstate_version = 1\n')
    w.cmds.table[PACKAGEKIT] = (0, "2026-11-21T08:11:00+02:00 fedora PackageKit[1500]: error: GPG check FAILED\n")
    w.procs.append(("dnf5", "/usr/bin/dnf5"))
    fx, _log = _lfx(w)
    lines = fx.check("updates").split("\n")
    for line in ("! Updates are downloaded and wait for a restart: they install while the computer restarts (Software "
                 "→ Updates → Restart & Update).",
                 "! An update is running now (dnf5): wait until it finishes; a second one can't start meanwhile.",
                 f"! Only {fixit._size(3 * GB)} is free on the system disk: updates need several GB. Free up space first "
                 "(pc_disk).",
                 f"! Only {fixit._size(100 * MB)} is free on /boot: new kernels won't fit. Removing old kernels frees it "
                 "(Fedora: 'sudo dnf remove --oldinstallonly').",
                 "! Failed: a repository's signing key is missing or has expired — PackageKit: error: GPG check FAILED",
                 "- System: Fedora Linux 41 (Workstation Edition)",
                 "- A newer Linux kernel is installed (6.12.9-200.fc41.x86_64): it starts after a restart (now: "
                 "6.11.4-301.fc41.x86_64)."):
        assert line in lines, line
    assert any(x.startswith("! Failed: there was no internet (or site names didn't work) during the update — dnf5.log: "
                            "2026-11-21T08:00:30+0000 [4020] ERROR Librepo error: Curl error (6)") for x in lines)
    assert any("'sudo dnf upgrade --refresh' in Terminal" in x for x in lines)
    assert {x.split()[0] for x in w.cmds.runs} == {"journalctl"}             # the logs are files: only read
    _write(offline, 'verb = "system-upgrade"\nsystem_releasever = "41"\ntarget_releasever = "42"\n'
                    'status = "download-complete"\n')                       # the next Fedora, downloaded
    out = fx.check("updates")
    assert ("! An upgrade to Fedora Linux 42 is downloaded and waits for a restart: it installs while the computer "
            "restarts (Software → Restart & Upgrade).") in out and "! Updates are downloaded" not in out
    _write(offline, 'status = "install-initiated"\nsystem_releasever = "42"\ntarget_releasever = "42"\n')
    assert "downloaded and wait" not in fx.check("updates")


def test_updates_on_ubuntu_and_silverblue(tmp_path, monkeypatch):
    _disk(monkeypatch)
    u = _lx(tmp_path / "ubuntu")
    _write(u.root / "etc/os-release", 'NAME="Ubuntu"\nID=ubuntu\nID_LIKE=debian\nPRETTY_NAME="Ubuntu 24.04.1 LTS"\n')
    _write(u.root / "run/reboot-required", "*** System restart required ***\n")
    _write(u.root / "var/lib/PackageKit/prepared-update", "")             # GNOME Software with PackageKit
    _write(u.root / "var/log/apt/term.log", "Log started: 2026-11-21  09:00:01\nE: dpkg was interrupted, you must "
                                            "manually run 'sudo dpkg --configure -a' to correct the problem.\n")
    out = _lfx(u)[0].check("updates")
    assert "! The system waits for a restart to finish updates: restart the computer first." in out
    assert "! Updates are downloaded and wait for a restart: they install while the computer restarts" in out
    assert ("! Failed: an earlier update was interrupted: 'sudo dpkg --configure -a' finishes it — term.log: E: dpkg "
            "was interrupted") in out
    assert "'sudo apt update && sudo apt full-upgrade' in Terminal" in out and "- System: Ubuntu 24.04.1 LTS" in out
    s = _lx(tmp_path / "silverblue")
    _write(s.root / "etc/os-release", 'NAME="Fedora Linux"\nID=fedora\nVARIANT_ID=silverblue\n'
                                      'PRETTY_NAME="Fedora Linux 41.20241120.0 (Silverblue)"\n')
    _write(s.root / "run/ostree-booted", "")
    s.cmds.table["rpm-ostree status --json"] = (0, json.dumps({"deployments": [{"staged": True, "booted": False},
                                                                               {"booted": True}]}))
    out = _lfx(s)[0].check("updates")
    assert "! A system update is ready and waits for a restart." in out and "'rpm-ostree upgrade' in Terminal" in out
    assert "No failed updates" not in out and "Explain what is above in plain words" in out
    other = _lx(tmp_path / "unknown")                                     # a system Lanterna doesn't know, all well
    assert _lfx(other)[0].check("updates").split("\n") == [
        "Updates:", "- No failed updates and nothing blocking them.", f"- Free on the system disk: {fixit._size(200 * GB)}",
        f"- Free on /boot: {fixit._size(200 * GB)}",
        "(Lanterna: installing updates needs the computer's password, so the user runs them: Software → Updates (KDE: "
        "Discover), or the system's own update command in Terminal; Flatpak apps: 'flatpak update'. If an update still "
        "fails, running it in Terminal shows the exact error.)"]


# ---------------------------------------------------------------- 8. privacy, caches, other programs
def test_what_goes_on_is_cleaned_on_linux(tmp_path):
    fx = fixit.Fixer(Actions(), runner=Cmds(), platform_="linux", env={}, home=Path(LX_HOME), user="olena",
                     pc="kitchen-pc", printers=FakePrinters([], ""), procs=lambda: [], drives=lambda: [],
                     root=tmp_path, data_dir=tmp_path / "data")
    win = "Z:" + LX_HOME.replace("/", "\\")                               # the home folder as Wine shows it
    out = fx.clean(f"{LX_HOME}/.config/game/log.txt; {LX_HOME}-old/x; {win}\\Documents\\save; on kitchen-pc; Olena; "
                   "olena@example.com")
    assert out == "~/.config/game/log.txt; /home/<user>-old/x; Z:~\\Documents\\save; on <pc>; <user>; <email>"
    assert fx.unmask("<user>'s Buds on <pc>") == "olena's Buds on kitchen-pc"
    fx.pc = "fedora"                                    # a computer named after its system: "Fedora Linux 41" stays
    assert fx.clean("Fedora Linux 41 on fedora") == "Fedora Linux 41 on fedora"


def test_lanternas_own_words_get_through_the_secret_filter(tmp_path):
    """clean() hides the word after «password:» (a log may hold one): a hint written that way would show the user's
    command as ••••. Every text of the fixes goes through clean() unchanged."""
    fx = fixit.Fixer(Actions(), runner=Cmds(), platform_="linux", env={}, home=Path(LX_HOME), user="olena",
                     pc="kitchen-pc", printers=FakePrinters([], ""), procs=lambda: [], drives=lambda: [],
                     root=tmp_path, data_dir=tmp_path / "data")
    texts = 0
    for mod in (fixit, fixlinux):
        for node in ast.walk(ast.parse(Path(mod.__file__).read_text(encoding="utf-8"))):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and " " in node.value.strip() and \
                    not re.search(r"\$[\w({]", node.value):                        # (not Windows' PowerShell code)
                texts += 1
                assert fx.clean(node.value) == node.value, node.value
    assert texts > 400


def test_a_flatpak_apps_cache_and_the_mesa_cache_go_to_the_trash(tmp_path):
    w = _lx(tmp_path)
    fx, log = _lfx(w)
    assert fx.places(fx.program("gimp")) == {"config": w.var / "config", "cache": w.var / "cache",
                                             "mesa_cache": w.home / ".cache" / "mesa_shader_cache_db"}
    assert fx.propose_cache("gimp", "cache") == WAITING                    # its own cache folder, as a whole
    card = _card(fx)
    size = fixit._size(1200)
    assert card.details == {"name": "GNU Image Manipulation Program", "place": "cache", "path": "cache", "size": size,
                            "count": 1, "driver": False, "why": "", "linux": True}
    done = fx.actions.confirm(card.id)
    assert done.result == f"cleared cache ({size} into the Trash)" and log.trashed == [[(w.var / "cache").resolve()]]
    assert app.card_text("fix_cache", card.details, "en").split("\n") == [
        f"Its cache folder · {size}", "It goes to the Trash, and a new one is made (the first start may take a little "
                                      "longer)."]
    with pytest.raises(WorkError, match="fix_cache is for cache folders only: a place like mesa_cache / nvidia_cache "
                                        "/ steam_shaders or its cache"):
        fx.propose_cache("gimp", "config", "GIMP")
    assert fx.propose_cache("", "mesa_cache") == WAITING                   # the driver's cache: no program
    assert _card(fx).details == {"name": "", "place": "mesa_cache", "path": "the Mesa driver's shader cache",
                                 "size": fixit._size(700), "count": 1, "driver": True, "why": "", "linux": True}


def test_how_other_games_and_apps_are_repaired(tmp_path):
    w = _lx(tmp_path)
    fx, log = _lfx(w)
    assert fx.propose_verify("stalker 2").startswith(WAITING)              # Steam's check: the same as on Windows
    assert fx.actions.confirm(_card(fx).id).state == "done" and log.urls == ["steam://validate/1643320"]
    assert fx.propose_verify("alan wake").startswith("Not a Steam game: the user checks it in Heroic")
    assert fx.propose_verify("diablo").startswith("Lutris can't check a game's files")
    assert "'flatpak repair --user'" in fx.propose_verify("gimp") and "org.gimp.GIMP" in fx.propose_verify("gimp")
    assert "'sudo snap revert vlc'" in fx.propose_verify("vlc")
    assert fx.propose_verify("text editor").startswith("Not a Steam game. A program from the system's packages")
    assert fx.propose_verify("text editor").endswith("It needs the computer's password, so tell the user.")


def test_the_fix_tools_on_linux(tmp_path):
    w = _lx(tmp_path)
    fx, _log = _lfx(w)
    found = fixit.fix_tools(fx)
    assert [t.name for t in found] == ["fix_check", "fix_list", "fix_read", "fix_rename", "fix_setting", "fix_aside",
                                       "fix_cache", "fix_verify", "fix_system"]
    assert "Steam with Proton, Heroic, Lutris, Flatpak" in found[0].description
    assert "proton_log" in found[1].parameters["properties"]["place"]["description"]
    system = found[-1]
    assert system.parameters["properties"]["action"]["enum"] == ["sound_output", "sound_on", "mic_on", "sound_restart",
                                                                 "proxy_off", "default_printer", "print_queue"]
    assert chat.acting_pc("fix_system") and "fix_system" in chat.FIX_GUIDE
    assert thinking.tool_step("fix_system", '{"action": "sound_on"}', "uk") == i18n.t("Preparing a fix in the system",
                                                                                     "uk")


# ---------------------------------------------------------------- 9. in the app: cards, titles, Undo, languages
def test_the_app_undoes_a_sound_change(tmp_path, monkeypatch):
    api = _api(tmp_path, monkeypatch)
    w = _lx(tmp_path)
    _sound(w)
    api.fixer, _log = _lfx(w, api.actions)
    offered = {t.name: t for t in api._pc_tools()}
    assert {"fix_check", "fix_system"} <= set(offered) and "fix_windows" not in offered
    assert offered["fix_system"].group == "fix"
    api.fixer.propose_system("sound_output", "analog")
    res = api.action_confirm(_card(api.fixer).id)
    assert res["state"] == "done" and res["text"] == i18n.t("The sound goes to {name}", "uk",
                                                            name="Built-in Audio Analog Stereo")
    entry = api.history_list()[0]
    assert entry["kind"] == "fix_sound" and entry["can_undo"]
    assert api.history_undo(entry["id"]) == {"ok": True, "text": i18n.t("Changed back.", "uk")}
    assert w.cmds.runs[-1] == f"pactl set-default-sink {HDMI}"
    api.fixer.propose_system("mic_on")
    res = api.action_confirm(_card(api.fixer).id)
    assert res["text"] == i18n.t("Turned on the microphone {name}", "uk", name="Built-in Audio Analog Stereo")
    w.cmds.table[f"pactl set-source-mute {MIC} 1"] = (1, "Failure: No such entity\n")      # the microphone is gone
    entry = api.history_list()[0]
    assert api.history_undo(entry["id"]) == {"ok": False,
                                             "text": i18n.t("The old sound device isn't there any more.", "uk")}


def test_the_linux_cards_say_what_changes():
    sound = {"name": "Built-in Audio Analog Stereo", "was": "Built-in Audio Digital Stereo (HDMI)"}
    assert app.card_text("fix_sound", sound, "en").split("\n") == [
        "Now: Built-in Audio Digital Stereo (HDMI)",
        "Programs play their sound there from now on. Undo puts the old output back."]
    unmute = {"name": "Built-in Audio Analog Stereo", "muted": True, "volume": 5, "to": 50, "mic": False}
    assert app.card_text("fix_unmute", unmute, "en").split("\n") == ["Now: 5% 🔇 → 50%",
                                                                     "Undo puts the volume back as it was."]
    printer = {"name": "HP_LaserJet_M110w", "was": "PDF", "linux": True}
    assert app.card_text("fix_printer", printer, "en").split("\n") == [
        "Now: PDF", "It becomes your default printer. Undo puts the old one back."]
    assert app.card_text("fix_printer", {**printer, "linux": False}, "en").endswith("Windows stops choosing the "
                                                                                    "default printer by itself. Undo "
                                                                                    "puts the old one back.")
    assert app.card_text("fix_sound_restart", {"name": "PipeWire"}, "en") == app.FIX_TEXT["fix_sound_restart"]
    mic = {**unmute, "mic": True}
    for kind, d in (("fix_sound", sound), ("fix_unmute", unmute), ("fix_unmute", mic), ("fix_sound_restart", {})):
        for done in (False, True):
            en, uk = (app.action_title(kind, d, "", lang, done=done) for lang in ("en", "uk"))
            assert en != uk and "{" not in uk, (kind, done, uk)
    assert app.action_title("fix_unmute", mic, "", "en") == "Turn on the microphone Built-in Audio Analog Stereo"
    assert app.action_title("fix_unmute", unmute, "", "en", done=True) == "Turned on the sound of Built-in Audio " \
                                                                          "Analog Stereo"


def test_every_linux_string_is_translated():
    new = ["Its settings folder", "Its data folder", "Its cache folder", "The Mesa driver's shader cache",
           app.FIX_TEXT["fix_cache_linux"], app.FIX_TEXT["fix_printer_linux"], app.FIX_TEXT["fix_sound"],
           app.FIX_TEXT["fix_unmute"], app.FIX_TEXT["fix_sound_restart"],
           "Send the sound to {name}", "The sound goes to {name}", "Turn on the sound of {name}",
           "Turned on the sound of {name}", "Turn on the microphone {name}", "Turned on the microphone {name}",
           "Restart the sound service", "Restarted the sound service",
           "The system didn't take the old proxy back.", "The system didn't accept the old default printer.",
           "The old sound device isn't there any more.", sent.FIX_PROGRAM_LINUX, sent.FIX_SYSTEM,
           thinking.TOOL_TEXT["fix_system"][0]]
    for s in new:
        assert s in i18n._T and i18n._T[s]["uk"] != s and i18n._T[s]["it"] != s, s
        for lang in i18n.FILE_LANGS:
            assert i18n.catalog(lang).get(s, s) != s, (lang, s)
    items = sent.build("M", False, 0, False, 0, [], 0, [("fix_check", '{"what": "Hollow Knight"}'),
                                                        ("fix_check", '{"what": "no sound"}')], win=False)
    lines = sent.view(sent.dumps(items), "uk")
    assert i18n.t(sent.FIX_PROGRAM_LINUX, "uk", what="Hollow Knight") in lines
    assert i18n.t(sent.FIX_SYSTEM, "uk", what="no sound") in lines and not any("Windows" in x for x in lines)


def test_the_window_shows_the_linux_cards():
    for kind, key in (("fix_sound", "Send the sound to {name}"), ("fix_unmute", "Turn on the sound of {name}"),
                      ("fix_sound_restart", "Restart the sound service")):
        assert f"{kind}: {json.dumps(key)}" in JS, kind
    assert 'if (c.kind === "fix_unmute" && d.mic) return "Turn on the microphone {name}";' in JS
    assert 'const key = d.linux && FIX_TEXT[k + "_linux"] ? k + "_linux" : k;' in JS
    assert '((k === "fix_printer" || k === "fix_sound") && d.was)' in JS and 'k === "fix_unmute" && d.volume != null' \
        in JS
