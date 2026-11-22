"""Why doesn't it work? Lanterna looks for itself, the way a helper at the computer would, and fixes it from a
fixed list.

The user says what is wrong in their own words ("the game goes black in a mission", "there is no sound"). Lanterna
finds the program (Steam, Epic, GOG, Xbox or the list of installed programs), looks through its install folder for
what is out of place (a folder renamed by a "skip the intro videos" trick, a mod or an injector next to the game),
reads its newest log and crash reports in its own folders, and what Windows noted itself (crashes and the file
they happened in, the graphics driver, programs that hook into games). Windows itself too: sound, internet, the
printer and updates. On Linux the same, from fixlinux.py: Steam (with Proton), Heroic, Lutris, Flatpak and the
installed apps; sound, internet, printers and updates of the system.

Looking is immediate and changes nothing. A fix comes only from this list, each one on a card (or done at once
when the user let Lanterna act on its own in the chat), and each can be undone where that is possible:
- rename a file or folder of the program back, or turn one off by renaming it;
- change one setting in one of its settings files (the old file is kept);
- move mods or injector files aside into a folder next to them;
- clear a cache folder (into the Recycle Bin or the Trash: the program makes a new one);
- Steam's own check of a game's files;
- Windows: clear the DNS cache, turn off a proxy left on, choose the default printer, clear stuck print jobs;
- Linux: choose the sound output, turn the sound on, restart the user's own sound service, turn off the desktop's
  proxy, choose the default printer, clear the user's own stuck print jobs.
No other commands are ever run, and a program has to be closed before its files change.

Never read or changed: system folders, browsers, password managers, wallets, mail, messengers and remote-access
programs, files and folders that may hold passwords, keys or sign-ins; saved games are never changed. What goes to
the model is cut short, with the user's name, the computer's name and anything secret taken out.
"""
from __future__ import annotations

import codecs
import ctypes
import datetime as dt
import difflib
import html
import json
import os
import platform
import re
import shutil
import socket
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import quiet, sensitive
from .pcsys import run
from .workspace import WAITING, WorkError

MB, GB = 1024 ** 2, 1024 ** 3
DAY = 86400
TURNED_OFF = "_turned_off_by_Lanterna"        # mods moved aside go here, next to where they were
SCAN_ENTRIES, SCAN_SECONDS, SCAN_DEPTH = 40_000, 4.0, 5
LOG_TAIL = 512 * 1024                          # bytes read from the end of a log
READ_MAX = 2 * MB                              # a bigger file is read from its end only
PROGRAMS_TTL = 600                             # seconds the list of installed programs is kept
SCAN_TTL = 30                                  # …and the look through one install folder
LIST_MAX = 80
UNINSTALL = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"
INET = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
WINDOWS_NT = r"Software\Microsoft\Windows NT\CurrentVersion\Windows"
SHELL_FOLDERS = r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"
SAVED_GAMES_ID = "{4C5C32FF-BB9D-43B0-B5B4-2D72E54EAAA4}"

# Windows itself: area → words the model (or the user) may use for it
AREAS = {
    "sound": ("sound", "audio", "speaker", "speakers", "headphones", "headset", "microphone", "звук", "звуку", "аудіо",
              "колонки", "навушники", "мікрофон", "suono", "audio", "ton", "sonido", "son", "dźwięk", "dzwiek"),
    "internet": ("internet", "network", "wifi", "wi fi", "ethernet", "connection", "інтернет", "інтернету", "мережа",
                 "мережі", "вайфай", "rete", "netzwerk", "red", "réseau", "reseau", "sieć", "siec", "internetu"),
    "printer": ("printer", "printers", "printing", "print", "принтер", "принтера", "друк", "stampante", "drucker",
                "impresora", "imprimante", "drukarka", "drukarki"),
    "updates": ("updates", "update", "windows update", "оновлення", "оновлень", "aggiornamenti", "aktualisierungen",
                "actualizaciones", "mises à jour", "aktualizacje"),
}

# never read: folders and files that may hold passwords, cookies, keys or sign-ins
SECRET_DIRS = {"local storage", "session storage", "indexeddb", "leveldb", "cookies", "network", "login data",
               "databases", "service worker", "blob_storage", "webstorage", "partitions", "user data", "tdata",
               "credentials", "protect", "vault", "crypto", ".ssh", ".gnupg", "keys", "keystore", "wallets",
               "userdata", "secrets", "tokens", "accounts", "profiles",
               "keyrings", ".pki", "nssdb", ".password-store", "kwalletd", "gnome-keyring", "goa-1.0"}   # Linux
_SECRET_NAME = re.compile(r"passw|secret|token|cookie|credential|oauth|\bauth|session|wallet|api_?key|private|"
                          r"licen[cs]e|account|login|keychain|mnemonic|\bseed\b|vault|sitemanager|recentservers|"
                          r"loginusers|^config\.vdf$|^localconfig\.vdf$|^ssfn|\.(pem|pfx|p12|key|ppk|kdbx|ovpn|"
                          r"keystore|jks|asc|gpg|sqlite|db|keyring|kwl)$|^id_(rsa|dsa|ecdsa|ed25519)", re.I)
TEXT_EXT = {".log", ".txt", ".ini", ".cfg", ".conf", ".config", ".json", ".xml", ".yaml", ".yml", ".toml",
            ".properties", ".lua", ".csv", ".md", ".vdf", ".acf", ".runtime-xml", ".err", ".out"}
SETTINGS_EXT = {".ini", ".cfg", ".conf", ".json", ".properties", ".txt"}
SAVE_DIRS = {"savegames", "savegame", "saves", "save", "savedata", "saved games", "savedgames", "profiles"}
RUNNABLE = {".exe", ".dll", ".com", ".bat", ".cmd", ".ps1", ".psm1", ".vbs", ".vbe", ".js", ".jse", ".wsf", ".wsh",
            ".hta", ".lnk", ".scr", ".msi", ".msp", ".pif", ".reg", ".cpl", ".jar", ".url", ".sys", ".asi", ".ocx",
            ".drv", ".scf", ".inf", ".appx", ".msix"}
# browsers, password managers, wallets, mail, messengers, remote access, launchers with sign-ins: their data is
# never read (Lanterna still says what Windows noted about them)
PRIVATE = re.compile(r"chrome|chromium|firefox|mozilla|microsoft edge|msedge|\bopera\b|brave|vivaldi|yandex|"
                     r"tor browser|waterfox|librewolf|thorium|floorp|1password|bitwarden|keepass|lastpass|dashlane|"
                     r"enpass|nordpass|proton ?(pass|mail|vpn|drive)|roboform|keeper (password|security|desktop)|"
                     r"exodus|electrum|ledger live|metamask|trezor|atomic wallet|bitcoin|ethereum|monero|litecoin|"
                     r"wasabi wallet|sparrow wallet|coinbase|binance|telegram|\bsignal\b|whatsapp|viber|skype|"
                     r"discord|\bslack\b|\bteams\b|\bzoom\b|thunderbird|betterbird|outlook|mailbird|em client|"
                     r"filezilla|winscp|putty|mobaxterm|rclone|openvpn|wireguard|anydesk|teamviewer|rustdesk|"
                     r"\bparsec\b|nordvpn|expressvpn|surfshark|mullvad|windscribe|cyberghost|tunnelbear|veracrypt|"
                     r"gpg4win|kleopatra|authy|authenticator|yubico|\bbank|^steam$|epic games launcher|gog galaxy|"
                     r"^ea app$|^ea$|ubisoft connect|battle\.net|rockstar games launcher|riot client|^origin$|"
                     r"amazon games|itch\.io|lanterna|"
                     # Linux: its browsers, mail, messengers, passwords, remote access and launchers with sign-ins
                     r"epiphany|gnome web|^web$|falkon|konqueror|midori|qutebrowser|zen browser|evolution|geary|"
                     r"kmail|kontact|claws mail|^element$|fractal|nheko|pidgin|hexchat|gajim|kotatogram|ayugram|"
                     r"seahorse|passwords and keys|kwallet|gnome secrets|^secrets$|remmina|krdc|gnome connections|"
                     r"^connections$|nomachine|x2go|heroic|^lutris$|^bottles$|minigalaxy|^itch$", re.I)
# first-level folders in AppData and Documents that are never a program's data place
DENY_DIRS = {"microsoft", "google", "mozilla", "packages", "temp", "tmp", "programs", "bravesoftware",
             "operasoftware", "vivaldi", "yandex", "comms", "connecteddevicesplatform", "virtualstore", "crashdumps",
             "d3dscache", "nvidia", "nvidiacorporation", "amd", "intel", "lanterna", "pip", "npmcache",
             "squirreltemp", "elevateddiagnostics", "publishers", "steam", "epicgameslauncher", "gogcom",
             "discord", "telegramdesktop", "signal", "whatsapp", "slack", "teams", "zoom", "thunderbird",
             "1password", "bitwarden", "keepass", "keepassxc", "exodus", "electrum", "ledgerlive", "atomic",
             "nordvpn", "protonvpn", "anydesk", "teamviewer", "rustdesk", "filezilla", "winscp", "github",
             "githubdesktop", "code", "cursor", "jetbrains", "docker", "ssh", "gnupg", "mylanternaprojects",
             "lanternaprojects", "onedrive", "dropbox", "googledrive", "icloud", "icloudrive", "diagnostics",
             "peerdistrepub", "placeholdertilelogofolder", "iconcache", "history", "inetcache", "inetcookies",
             "fontcache", "explorer", "windows", "windowsapps", "programs", "applicationdata", "appdata",
             "unrealengine", "unrealenginelauncher", "epicgames", "unity", "unitytechnologies", "nuget", "npm",
             "yarn", "cargo", "go", "python", "conda", "anaconda", "jupyter", "gradle", "maven", "android",
             # Linux: ~/.config, ~/.local/share and ~/.cache of the desktop itself, the launchers and the drivers
             "lutris", "heroic", "bottles", "flatpak", "trash", "keyrings", "applications", "gnomeshell", "dconf",
             "pulse", "systemd", "autostart", "gtk30", "gtk40", "fontconfig", "fonts", "icons", "thumbnails",
             "mesashadercache", "mesashadercachedb", "nautilus", "ibus", "evolution", "goa10", "menus", "kde",
             "plasma", "akonadi", "baloo", "kwalletd", "tracker", "tracker3", "gvfsmetadata", "gstreamer10",
             "wireplumber", "pipewire", "xorg", "wine", "protonfixes", "umu", "mangohud", "vkbasalt", "gamescope",
             "glcache", "containers", "keepassxc", "remmina", "evolutiondataserver"}
GENERIC_KEYS = {"game", "games", "the", "launcher", "client", "app", "apps", "program", "programs", "steam", "epic",
                "microsoft", "windows", "nvidia", "google", "binaries", "win64", "engine", "content", "data",
                "common", "unity", "unreal", "setup", "update", "updater", "crashreportclient", "unitycrashhandler",
                "unitycrashhandler64", "bin", "x64", "x86", "start", "play", "main", "edition", "remastered",
                "definitive", "deluxe", "ultimate", "complete", "goty", "online", "demo", "beta", "test", "tools",
                "documents", "mygames", "saved", "savedgames", "user", "users", "local", "roaming", "temp",
                "installer", "installers", "uninstall", "uninstaller", "helper", "service", "services", "updater",
                "browser", "webhelper", "overlay", "server", "platform", "runtime", "runtimes", "redist", "launch",
                "crashhandler", "crashpad", "crashreporter", "logs", "cache", "config", "settings", "plugins",
                "packages", "assets", "default", "shared", "system", "driver", "drivers", "support", "studio"}
GENERIC_USERS = {"user", "admin", "administrator", "owner", "player", "gamer", "test", "pc", "home", "guest", "default",
                 # Linux computers are often named after the system: masking it would hide "Fedora Linux 41"
                 "localhost", "localhost-live", "fedora", "ubuntu", "debian", "linux", "archlinux", "manjaro", "mint",
                 "linuxmint", "pop-os", "nobara", "bazzite", "steamdeck", "kali", "raspberrypi", "opensuse", "endeavour"}
SKIP_SCAN = {"_commonredist", "redist", "redistributables", "directx", "vcredist", "__installer", "installers",
             "thirdparty", ".git", "node_modules", "__pycache__", "shadercache", "derivedddatacache"}
SKIP_EXE = {"unrealcefsubprocess", "steamwebhelper", "qtwebengineprocess", "uplaywebcore", "cefsubprocess",
            "unitycrashhandler64", "unitycrashhandler32", "crashreportclient", "crashreporter", "crashpad_handler",
            "unins000", "unins001", "uninstall", "uninst", "vc_redist.x64", "vc_redist.x86", "vcredist_x64",
            "vcredist_x86", "dxsetup", "dxwebsetup", "ue4prereqsetup_x64", "ueprereqsetup_x64", "easyanticheat_setup",
            "easyanticheat_eos_setup", "beservice", "beservice_x64", "dotnetfx", "oalinst", "physx", "touchup",
            "cefprocess", "cefsharp.browsersubprocess", "quicksfv", "notification_helper", "crashhandler",
            "steamerrorreporter", "steamerrorreporter64", "epicwebhelper"}
# files mods and overlays use to hook into a game; games don't ship them in their own folder as a rule
INJECTORS = {"dxgi.dll", "d3d9.dll", "d3d10.dll", "d3d11.dll", "d3d12.dll", "dinput8.dll", "version.dll", "winmm.dll",
             "winhttp.dll", "dsound.dll", "opengl32.dll", "wininet.dll", "nvngx.dll", "dlssg_to_fsr3_amd_is_better.dll",
             "ue4ss.dll", "specialk64.dll", "specialk32.dll", "scripthookv.dll", "scripthookvdotnet.asi", "xlive.dll",
             "ddraw.dll"}           # not xinput1_3.dll: games and Steam ship that one themselves
MOD_FILES = {"reshade.ini": "ReShade (a graphics mod)", "reshade.log": "ReShade (a graphics mod)",
             "reshade64.log": "ReShade (a graphics mod)", "enblocal.ini": "ENB (a graphics mod)",
             "enbseries.ini": "ENB (a graphics mod)", "dxvk.conf": "DXVK (it replaces the game's DirectX)",
             "optiscaler.ini": "OptiScaler (an upscaling and frame generation mod)",
             "specialk.ini": "Special K (a mod)", "ue4ss-settings.ini": "UE4SS (a mod loader)",
             "doorstop_config.ini": "Doorstop (a mod loader, e.g. BepInEx)",
             "dlssg_to_fsr3.ini": "a frame generation mod (DLSS to FSR3)", "nvngx.ini": "an upscaling mod's settings",
             "d3d11.ini": "a mod's settings", "dxgi.ini": "a mod's settings", "openiv.asi": "OpenIV's mod loader",
             "modloader.log": "a mod loader"}
MOD_DIRS = {"reshade-shaders", "enbseries", "bepinex", "melonloader", "ue4ss", "~mods", "logicmods", "mods",
            "modloader", "specialk", "optiscaler", "nativemods"}
GENERIC_EXE = {"launcher", "game", "start", "setup", "updater", "update", "patcher", "config", "settings", "server",
               "client", "main", "app", "run", "play", "bootstrap", "bootstrapper", "helper", "service", "agent",
               "installer", "uninstaller", "crashreporter", "reporter", "editor", "tool", "tools", "x64", "win64"}
LOG_SKIP = {"screenshots", "screenshot", "videos", "movies", "captures", "photos", "replays", "recordings", "mods",
            "shadercache", "pipelinecaches", "webcache", "gpucache", "code cache"}
VIDEO_EXT = {".bk2", ".bik", ".usm", ".webm", ".mp4", ".wmv", ".avi", ".mkv", ".mov", ".ogv", ".bink"}
_OFF = re.compile(r"^(?P<base>.+?)(?:[ ._-](?:old|bak|backup|orig|original|disabled|disable|off|unused|copy|копія|копия)"
                  r"\d*|\s-\s(?:copy|копія|копия)(?:\s\(\d+\))?|~)$", re.I)
CACHE_PLACES = ("steam_shaders", "nvidia_cache", "amd_cache", "d3d_cache", "intel_cache", "mesa_cache")
CACHE_NAMES = {"steam_shaders": "Steam's shader cache of the game", "nvidia_cache": "the NVIDIA driver's shader cache",
               "amd_cache": "the AMD driver's shader cache", "d3d_cache": "the DirectX shader cache",
               "intel_cache": "the Intel driver's shader cache", "mesa_cache": "the Mesa driver's shader cache"}
ANTICHEAT = {"easyanticheat": "Easy Anti-Cheat", "battleye": "BattlEye"}
GAME_SOURCES = ("steam", "epic", "gog", "xbox", "heroic-epic", "heroic-gog", "lutris")
# parts of a Flatpak id that name no program (com.spotify.Client, org.kde.kdenlive, io.github.<person>.App)
APPID_WORDS = {"github", "gitlab", "kde", "gnome", "desktop", "client", "browser", "studio", "app", "launcher",
               "player", "editor"}

# ---------------------------------------------------------------- what Windows' notes mean
EXC_CODES = {
    "c0000005": "access violation: it touched memory it shouldn't (often a mod, an overlay, a driver or damaged files)",
    "c0000409": "it stopped itself on a fatal error (often an overlay, damaged files or a driver)",
    "c0000135": "a DLL it needs is missing (a runtime such as Visual C++ or DirectX)",
    "c000007b": "a DLL of the wrong kind (32/64-bit) or a damaged runtime",
    "c0000142": "a DLL failed to start (a runtime, or an antivirus blocking it)",
    "c00000fd": "stack overflow",
    "c000001d": "an instruction this processor doesn't have (the program needs a newer processor)",
    "c0000417": "an invalid parameter (the C++ runtime stopped it)",
    "c0000374": "heap corruption: its memory got damaged (mods, overlays, drivers or RAM)",
    "c0000602": "it stopped itself at once (fail fast)",
    "c0000006": "a file couldn't be read from the disk",
    "e0434352": "a .NET error",
    "80000003": "its own check failed (a breakpoint)",
    "40000015": "it stopped itself (abort)",
}
MODULES = [
    (r"^nv(wgf2um|warp|d3dum|oglv|cuda|api|lddmkm|ldumd|gpucomp|tt|xdapix)", "the NVIDIA graphics driver"),
    (r"^(atidxx|amdxx|atiumd|amdxc|aticfx|atio6axx|amdvlk|amdihk|amfrt)", "the AMD graphics driver"),
    (r"^(igd|igc|igxel|igdumd|intelocl|igdgmm|igvk)", "the Intel graphics driver"),
    (r"^rtsshooks", "RivaTuner (MSI Afterburner's overlay)"),
    (r"^discordhook", "Discord's overlay"),
    (r"^gameoverlayrenderer", "Steam's overlay"),
    (r"^graphics-hook", "OBS game capture"),
    (r"^(eosovh|eossdk)", "Epic's online services and overlay"),
    (r"^nahimic", "Nahimic audio (a known cause of game crashes)"),
    (r"^reshade", "ReShade"),
    (r"^(vcruntime|msvcp|ucrtbase|concrt)", "the Visual C++ runtime (often only where the error surfaced)"),
    (r"^kernelbase", "Windows' error handling: the program raised an error itself (missing or damaged files, a failed "
                     "check)"),
    (r"^ntdll", "Windows' core: memory got damaged (mods, overlays, drivers or RAM)"),
    (r"^(d3d12|d3d12core|d3d11|dxgi|d3d9|dxcore)", "DirectX (usually the graphics driver)"),
    (r"^(xinput1_3|x3daudio|xaudio2_[0-7]|d3dx9|d3dx10|d3dx11|d3dcompiler_4[0-3])",
     "an old part of DirectX (the DirectX End-User Runtime may be missing)"),
    (r"^steam_api", "Steam's library in the game folder (replaced or damaged: Steam's check puts it back)"),
    (r"^(clr|coreclr|mscorlib|system\.private\.corelib)", "the .NET runtime"),
    (r"^(unityplayer|mono-2\.0)", "the Unity engine of the program"),
    (r"^(easyanticheat|eac|beclient|battleye)", "the anti-cheat"),
    (r"^(amsi|mpengine|mpoav)", "the antivirus"),
]
OVERLAYS = {"rtss": "RivaTuner (MSI Afterburner's overlay)", "msiafterburner": "MSI Afterburner",
            "discord": "Discord (its overlay hooks into games)", "obs64": "OBS", "obs32": "OBS",
            "nvidia overlay": "the NVIDIA overlay", "nvsphelper64": "NVIDIA ShadowPlay", "gamebar": "Xbox Game Bar",
            "overwolf": "Overwolf", "medal": "Medal", "nahimicsvc64": "Nahimic audio (known to crash games)",
            "nahimicsvc32": "Nahimic audio (known to crash games)", "steelseriesgg": "SteelSeries GG",
            "razercortex": "Razer Cortex", "wallpaper64": "Wallpaper Engine", "wallpaper32": "Wallpaper Engine",
            "fpsmonitor": "FPS Monitor", "signalrgb": "SignalRGB"}
STEAM_STATE = {2: "needs an update", 32: "files are missing", 128: "files are damaged", 256: "an update is running",
               512: "an update is paused", 1024: "an update has started", 131072: "its files are being checked",
               1048576: "it is downloading"}
CM_CODES = {1: "isn't set up right", 3: "its driver is damaged (or memory is low)", 10: "can't start (its driver)",
            18: "needs its driver installed again", 19: "its settings in the registry are damaged",
            21: "Windows is removing it", 22: "is turned off (disabled)", 24: "isn't there or doesn't work",
            28: "has no driver", 31: "doesn't work right (its driver)", 43: "was stopped by Windows: it reported problems",
            45: "isn't connected"}
WU_CODES = {
    "0x80070070": "not enough disk space",
    "0x800f0922": "it couldn't finish (often too little room in a small system partition, or a VPN or no connection "
                  "to Microsoft)",
    "0x80070643": "the install failed (with this KB often the recovery partition is too small)",
    "0x8024402c": "the update servers can't be reached (a proxy or the connection)",
    "0x8024401c": "the update servers didn't answer in time",
    "0x800f081f": "files Windows needs for it are missing (DISM repairs it)",
    "0x80073712": "Windows' store of system files is damaged (DISM repairs it)",
    "0x800f0831": "an earlier update is missing or damaged (DISM repairs it)",
    "0x80070002": "a file wasn't found (the downloaded update is damaged)",
    "0x80070005": "access was denied",
    "0x8007000d": "the update data is damaged",
    "0x80240034": "the download failed",
    "0x80244022": "the update server is busy (try later)",
    "0x80070422": "the Windows Update service is turned off",
    "0x80248007": "Windows Update's own data is missing (the troubleshooter repairs it)",
    "0x800705b4": "it took too long",
    "0xc1900101": "a driver stopped the upgrade (often the graphics or storage driver)",
    "0xc1900208": "a program that doesn't work with the new version blocks the upgrade",
}
PRINTER_STATUS = {1: "other", 2: "unknown", 3: "ready", 4: "printing", 5: "warming up", 6: "stopped printing",
                  7: "offline"}
PRINTER_ERROR = {3: "little paper", 4: "no paper", 5: "little toner or ink", 6: "no toner or ink", 7: "a door is open",
                 8: "paper is jammed", 9: "offline", 10: "it needs service", 11: "the output tray is full"}
VIRTUAL_PRINTERS = re.compile(r"microsoft print to pdf|xps document writer|onenote|\bfax\b|send to|pdf24|"
                              r"adobe pdf|cutepdf|pdfcreator|foxit|cups-?pdf|^pdf$|print to file", re.I)
VPN = re.compile(r"vpn|wireguard|tap-windows|openvpn|wintun|nordlynx|proton|anyconnect|fortinet|hamachi|zerotier|"
                 r"tailscale|radmin", re.I)

# ---------------------------------------------------------------- fixed PowerShell scripts (they only read)
_PS_HEAD = "[Console]::OutputEncoding=[Text.Encoding]::UTF8; $ErrorActionPreference='SilentlyContinue'; $o=@{}; "
PS_PROGRAM = _PS_HEAD + (
    "$o.gpu=@(Get-CimInstance Win32_VideoController | ForEach-Object { @{n=[string]$_.Name; v=[string]$_.DriverVersion; "
    "d=$(if($_.DriverDate){$_.DriverDate.ToString('yyyy-MM-dd')}else{''})} }); "
    "$o.ev=@(Get-WinEvent -FilterHashtable @{LogName='Application'; ProviderName='Application Error','Application Hang',"
    "'.NET Runtime'; Id=1000,1002,1026; StartTime=(Get-Date).AddDays(-30)} -MaxEvents 400 | ForEach-Object { @{id=$_.Id; "
    "t=$_.TimeCreated.ToString('yyyy-MM-dd HH:mm'); p=@($_.Properties | Select-Object -First 12 | ForEach-Object { "
    "[string]$_.Value })} }); "
    "$o | ConvertTo-Json -Depth 5 -Compress")
PS_SOUND = _PS_HEAD + (
    "$o.svc=@(Get-Service Audiosrv,AudioEndpointBuilder | ForEach-Object { @{n=$_.Name; s=[string]$_.Status; "
    "t=[string]$_.StartType} }); "
    "$o.dev=@(Get-CimInstance Win32_SoundDevice | ForEach-Object { @{n=[string]$_.Name; s=[string]$_.Status; "
    "e=[int]$_.ConfigManagerErrorCode} }); "
    "$o.ep=@(Get-PnpDevice -Class AudioEndpoint | ForEach-Object { @{n=[string]$_.FriendlyName; s=[string]$_.Status} }); "
    "$o | ConvertTo-Json -Depth 4 -Compress")
PS_INTERNET = _PS_HEAD + (
    "$o.ad=@(Get-NetAdapter | ForEach-Object { @{n=[string]$_.Name; d=[string]$_.InterfaceDescription; "
    "s=[string]$_.Status; sp=[string]$_.LinkSpeed; v=[bool]$_.Virtual} }); "
    "$o.ip=@(Get-NetIPConfiguration | ForEach-Object { @{a=[string]$_.InterfaceAlias; ip=@($_.IPv4Address | "
    "ForEach-Object { [string]$_.IPAddress }); gw=@($_.IPv4DefaultGateway | ForEach-Object { [string]$_.NextHop }); "
    "dns=@($_.DNSServer | Where-Object { $_.AddressFamily -eq 2 } | ForEach-Object { $_.ServerAddresses })} }); "
    "$gw=@($o.ip | ForEach-Object { $_.gw } | Where-Object { $_ }); "
    "if ($gw.Count) { $o.gwok=[bool](Test-Connection -ComputerName $gw[0] -Count 1 -Quiet) }; "
    "$o.dnsok=[bool](Resolve-DnsName www.msftconnecttest.com -DnsOnly -QuickTimeout); "
    "$c=New-Object Net.Sockets.TcpClient; try { $o.tcp=[bool]$c.ConnectAsync('1.1.1.1',443).Wait(3000) } catch "
    "{ $o.tcp=$false }; $c.Close(); "
    "$o.wlan=[string](netsh wlan show interfaces | Out-String); "
    "$o | ConvertTo-Json -Depth 4 -Compress")
PS_PRINTER = _PS_HEAD + (
    "$o.pr=@(Get-CimInstance Win32_Printer | ForEach-Object { @{n=[string]$_.Name; d=[bool]$_.Default; "
    "off=[bool]$_.WorkOffline; st=[int]$_.PrinterStatus; er=[int]$_.DetectedErrorState; net=[bool]$_.Network} }); "
    "$o.jobs=@(Get-CimInstance Win32_PrintJob | ForEach-Object { @{p=[string](($_.Name -split ',')[0]); "
    "s=[string]$_.JobStatus; st=[string]$_.Status; t=$(if($_.TimeSubmitted){$_.TimeSubmitted.ToString('yyyy-MM-dd HH:mm')}"
    "else{''})} }); "
    "$o.sp=@(Get-Service Spooler | ForEach-Object { @{s=[string]$_.Status; t=[string]$_.StartType} }); "
    "$o | ConvertTo-Json -Depth 4 -Compress")
PS_UPDATES = _PS_HEAD + (
    "$o.svc=@(Get-Service wuauserv,bits,UsoSvc,TrustedInstaller,cryptsvc | ForEach-Object { @{n=$_.Name; "
    "s=[string]$_.Status; t=[string]$_.StartType} }); "
    "$o.reboot=[bool](Test-Path 'HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\WindowsUpdate\\Auto Update\\RebootRequired'); "
    "try { $s=New-Object -ComObject Microsoft.Update.Session; $h=$s.CreateUpdateSearcher(); $n=$h.GetTotalHistoryCount(); "
    "if ($n -gt 0) { $o.hist=@($h.QueryHistory(0,[Math]::Min(150,$n)) | ForEach-Object { @{t=[string]$_.Title; "
    "r=[int]$_.ResultCode; h=('0x{0:X8}' -f $_.HResult); d=$_.Date.ToString('yyyy-MM-dd')} }) } } catch "
    "{ $o.err=[string]$_.Exception.Message }; "
    "$o | ConvertTo-Json -Depth 4 -Compress")
# the printer's name comes in an environment variable, never inside the script
PS_CLEAR_QUEUE = ("$ErrorActionPreference='Stop'; Get-PrintJob -PrinterName $env:LANTERNA_PRINTER | Remove-PrintJob; "
                  "'ok'")


# ---------------------------------------------------------------- small helpers
_TR = str.maketrans({"а": "a", "б": "b", "в": "v", "г": "h", "ґ": "g", "д": "d", "е": "e", "є": "ie", "ж": "zh",
                     "з": "z", "и": "y", "і": "i", "ї": "i", "й": "i", "к": "k", "л": "l", "м": "m", "н": "n",
                     "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "х": "kh", "ц": "ts",
                     "ч": "ch", "ш": "sh", "щ": "shch", "ь": "", "ю": "iu", "я": "ia", "ё": "e", "ы": "y", "э": "e",
                     "ъ": ""})


def norm(s: str) -> str:
    """A name to compare: 'S.T.A.L.K.E.R. 2: Heart of Chornobyl™' → 'stalker 2 heart of chornobyl'."""
    s = str(s or "").lower().replace("™", "").replace("®", "").replace("©", "")
    s = re.sub(r"(?<=\w)[.'’](?=\w)", "", s)
    return " ".join(re.sub(r"[\W_]+", " ", s).split())


def compact(s: str) -> str:
    return norm(s).translate(_TR).replace(" ", "")


def _latin(s: str) -> str:
    return norm(s).translate(_TR)


def secret_dir(name: str) -> bool:
    return name.strip().lower() in SECRET_DIRS


def secret_name(name: str) -> bool:
    return bool(_SECRET_NAME.search(name))


def _size(n: float) -> str:
    from .pcfiles import size_text
    return size_text(n)


def _day(ts: float) -> str:
    return dt.datetime.fromtimestamp(ts).strftime("%Y-%m-%d") if ts else ""


def _when(ts: float) -> str:
    return dt.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M") if ts else ""


def _cut(s: str, n: int = 200) -> str:
    s = " ".join(str(s).split())
    return s if len(s) <= n else s[:n - 1].rstrip() + "…"


def _bom(raw: bytes) -> tuple[str, bytes]:
    """The encoding of a text file and its byte-order mark (kept when the file is written again)."""
    if raw.startswith(codecs.BOM_UTF8):
        return "utf-8", codecs.BOM_UTF8
    if raw.startswith(codecs.BOM_UTF16_LE):
        return "utf-16-le", codecs.BOM_UTF16_LE
    if raw.startswith(codecs.BOM_UTF16_BE):
        return "utf-16-be", codecs.BOM_UTF16_BE
    odd = raw[1:400:2]
    if len(raw) >= 4 and odd and odd.count(0) > len(odd) * 0.6:
        return "utf-16-le", b""
    try:
        codecs.getincrementaldecoder("utf-8")().decode(raw, final=False)     # a cut letter at the end is fine
        return "utf-8", b""
    except UnicodeDecodeError:
        return "latin-1", b""                          # every byte comes back the same when written again


def read_text(p: Path, tail: int = 0) -> tuple[str, bool]:
    """A text file as text (any of the encodings games use); tail: only the last bytes. → (text, cut)."""
    size = p.stat().st_size
    with open(p, "rb") as f:
        enc, bom = _bom(f.read(min(size, 400)))
        if (tail and size > tail) or size > READ_MAX:
            off = size - (tail or READ_MAX)
            off -= off % 2 if enc.startswith("utf-16") else 0
            f.seek(off)
            text = f.read().decode(enc, "replace")
            return text.replace("\r\n", "\n").split("\n", 1)[-1], True
        f.seek(len(bom))
        return f.read().decode(enc, "replace").replace("\r\n", "\n"), False


def _expand(path: str, env: Callable[[str], str]) -> str:
    return re.sub(r"%([^%]+)%", lambda m: env(m.group(1)) or m.group(0), str(path or ""))


def _same(a: Path, b: Path) -> bool:
    try:
        return os.path.samefile(a, b)
    except OSError:
        return False


def _tree(root: Path, limit: int = 60_000, seconds: float = 4.0) -> tuple[int, int, dict[str, int]]:
    """Size, file count and the kinds of files in a folder (stops early on a huge one)."""
    total = n = 0
    kinds: dict[str, int] = {}
    t0 = time.monotonic()
    for dirpath, _dirs, names in os.walk(root):
        for name in names:
            n += 1
            ext = os.path.splitext(name)[1].lower()
            kinds[ext] = kinds.get(ext, 0) + 1
            try:
                total += os.lstat(os.path.join(dirpath, name)).st_size
            except OSError:
                pass
        if n > limit or time.monotonic() - t0 > seconds:
            break
    return total, n, kinds


def _kinds_text(kinds: dict[str, int]) -> str:
    if not kinds:
        return ""
    top = sorted(kinds.items(), key=lambda kv: -kv[1])[:2]
    out = []
    for ext, k in top:
        what = "videos" if ext in VIDEO_EXT else f"{ext or 'no-extension'} files"
        out.append(f"{k} {what}" + (f" ({ext})" if ext in VIDEO_EXT else ""))
    return ", ".join(out)


def module_meaning(module: str, path: str = "", folder: str = "") -> str:
    low = module.lower()
    if folder and path and os.path.normcase(path).startswith(os.path.normcase(folder)):
        if low in INJECTORS or low.endswith(".asi"):
            return "a mod or injector file in the program's own folder"
    for rx, meaning in MODULES:
        if re.match(rx, low):
            return meaning
    if folder and path and os.path.normcase(path).startswith(os.path.normcase(folder)):
        return "a file of the program itself"
    return ""


def nvidia_version(v: str) -> str:
    """Windows' driver version 32.0.15.6636 → NVIDIA's 566.36."""
    digits = re.sub(r"\D", "", v or "")
    return f"{digits[-5:-2]}.{digits[-2:]}" if len(digits) >= 5 else v


# ---------------------------------------------------------------- what is found
@dataclass
class Program:
    name: str
    source: str                         # steam | epic | gog | xbox | app; Linux: heroic-epic | heroic-gog | lutris |
    folder: str = ""                    # flatpak | snap. Where it is installed ("" = not known)
    appid: str = ""                     # Steam's app id, Epic's app name, GOG's id, a Flatpak id, a Snap name
    version: str = ""
    publisher: str = ""
    exe: str = ""                       # the main program file, when the source says
    note: str = ""                      # e.g. "the install isn't finished" (Epic)
    prefix: str = ""                    # Linux: the Proton or Wine prefix a Windows game runs in

    @property
    def private(self) -> bool:
        return bool(PRIVATE.search(self.name) or PRIVATE.search(self.publisher or ""))

    def label(self) -> str:
        return {"steam": f"Steam game {self.appid}", "epic": "Epic Games", "gog": "GOG", "xbox": "Xbox app",
                "heroic-epic": "Epic Games in Heroic", "heroic-gog": "GOG in Heroic", "lutris": "Lutris",
                "flatpak": f"Flatpak app {self.appid}", "snap": f"Snap app {self.appid}"}.get(self.source, "program")


@dataclass
class Scan:
    root: Path
    exes: list[str] = field(default_factory=list)          # paths relative to the root
    renamed: list[dict] = field(default_factory=list)      # {"rel", "dir", "base", "mod"}
    mods: list[dict] = field(default_factory=list)         # {"rel", "dir", "what"}
    changed: list[tuple[str, float, bool]] = field(default_factory=list)
    logs: list[Path] = field(default_factory=list)
    unity: tuple[str, str] = ("", "")                       # company and product (Unity's app.info)
    aside: list[str] = field(default_factory=list)          # what Lanterna moved aside before
    anticheat: set[str] = field(default_factory=set)        # Easy Anti-Cheat, BattlEye (Linux: they decide online play)
    count: int = 0
    cut: bool = False
    at: float = field(default_factory=time.time)

    def flagged(self) -> set[str]:
        return {m["rel"].lower() for m in self.mods} | {r["rel"].lower() for r in self.renamed} | \
            {c[0].lower() for c in self.changed}


def mod_kind(name: str, exe_folder: bool = True) -> str:
    """What a file or folder of a program is, if it is one mods and overlays use ("" = nothing special)."""
    low = name.lower()
    if low in MOD_DIRS:
        return "a mods folder" if low in ("mods", "~mods", "logicmods", "nativemods", "modloader") else \
            f"{name}: a mod loader or shader pack"
    if low.endswith(".asi") and not low.startswith("mss"):          # mss*.asi: the Miles sound codecs
        return "an .asi mod (loaded by an ASI loader)"
    if low in MOD_FILES:
        return MOD_FILES[low]
    if exe_folder and low in INJECTORS:
        return "a file mods and overlays use to hook into a game (ReShade, ENB, frame generation…)"
    return ""


# ---------------------------------------------------------------- Windows' default printer
class WinPrinters:
    """The printers of this user (winspool). Only the default printer is ever changed."""

    def _spool(self):
        return ctypes.WinDLL("winspool.drv")

    def names(self) -> list[str]:
        from ctypes import wintypes

        class INFO4(ctypes.Structure):
            _fields_ = [("pPrinterName", wintypes.LPWSTR), ("pServerName", wintypes.LPWSTR),
                        ("Attributes", wintypes.DWORD)]
        try:
            sp = self._spool()
        except OSError:
            return []
        flags, needed, count = 2 | 4, wintypes.DWORD(0), wintypes.DWORD(0)      # local + connections
        sp.EnumPrintersW(flags, None, 4, None, 0, ctypes.byref(needed), ctypes.byref(count))
        if not needed.value:
            return []
        buf = (ctypes.c_byte * needed.value)()
        if not sp.EnumPrintersW(flags, None, 4, buf, needed.value, ctypes.byref(needed), ctypes.byref(count)):
            return []
        arr = ctypes.cast(buf, ctypes.POINTER(INFO4))
        return [arr[i].pPrinterName for i in range(count.value) if arr[i].pPrinterName]

    def default(self) -> str:
        from ctypes import wintypes
        try:
            sp = self._spool()
        except OSError:
            return ""
        n = wintypes.DWORD(0)
        sp.GetDefaultPrinterW(None, ctypes.byref(n))
        if not n.value:
            return ""
        b = ctypes.create_unicode_buffer(n.value)
        return b.value if sp.GetDefaultPrinterW(b, ctypes.byref(n)) else ""

    def set_default(self, name: str) -> bool:
        try:
            return bool(self._spool().SetDefaultPrinterW(str(name)))
        except OSError:
            return False


def _has_content(p: Path) -> bool:
    """A mods folder with something in it (games often ship an empty one, or one with only a readme)."""
    try:
        with os.scandir(p) as it:
            for i, e in enumerate(it):
                if i > 40 or not re.match(r"(?i)^(read ?me|placeholder|\.keep|\.gitkeep|info|how ?to)|.*\.(txt|md|url|"
                                          r"html?|pdf)$", e.name):
                    return True
    except OSError:
        pass
    return False


class _ENTRY(ctypes.Structure):
    _fields_ = [("dwSize", ctypes.c_uint32), ("cntUsage", ctypes.c_uint32), ("th32ProcessID", ctypes.c_uint32),
                ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", ctypes.c_uint32),
                ("cntThreads", ctypes.c_uint32), ("th32ParentProcessID", ctypes.c_uint32),
                ("pcPriClassBase", ctypes.c_long), ("dwFlags", ctypes.c_uint32), ("szExeFile", ctypes.c_wchar * 260)]


def _processes() -> list[tuple[str, str]]:
    """(name, full path) of the programs running now; the path is '' where Windows doesn't show it."""
    if sys.platform.startswith("linux"):
        from .fixlinux import processes
        return processes()
    if sys.platform != "win32":
        return []
    from ctypes import wintypes
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    k.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    k.Process32FirstW.argtypes = k.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(_ENTRY)]
    k.OpenProcess.restype = wintypes.HANDLE
    k.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    k.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                             ctypes.POINTER(wintypes.DWORD)]
    k.CloseHandle.argtypes = [wintypes.HANDLE]
    snap = k.CreateToolhelp32Snapshot(0x2, 0)                  # TH32CS_SNAPPROCESS
    if not snap or snap == ctypes.c_void_p(-1).value:
        return []
    out = []
    try:
        e = _ENTRY()
        e.dwSize = ctypes.sizeof(_ENTRY)
        ok = k.Process32FirstW(snap, ctypes.byref(e))
        while ok:
            path = ""
            h = k.OpenProcess(0x1000, False, e.th32ProcessID)  # PROCESS_QUERY_LIMITED_INFORMATION
            if h:
                buf, n = ctypes.create_unicode_buffer(1024), wintypes.DWORD(1024)
                if k.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n)):
                    path = buf.value
                k.CloseHandle(h)
            out.append((e.szExeFile, path))
            ok = k.Process32NextW(snap, ctypes.byref(e))
    finally:
        k.CloseHandle(snap)
    return out


def tcp_probe(host: str, port: int, timeout: float = 3.0) -> bool:
    """Whether a direct connection to an address works (the internet without site names)."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _refresh_wininet() -> None:
    """Tells Windows the proxy settings changed, so browsers and programs pick them up now."""
    if sys.platform != "win32":
        return
    try:
        w = ctypes.WinDLL("wininet")
        w.InternetSetOptionW(None, 39, None, 0)        # INTERNET_OPTION_SETTINGS_CHANGED
        w.InternetSetOptionW(None, 37, None, 0)        # INTERNET_OPTION_REFRESH
    except (OSError, AttributeError):
        pass


def _short_path(p: Path) -> str:
    """The 8.3 form of a folder (C:\\Users\\ABCD~1): logs write it too."""
    if sys.platform != "win32":
        return ""
    try:
        buf = ctypes.create_unicode_buffer(600)
        n = ctypes.windll.kernel32.GetShortPathNameW(str(p), buf, 600)
        return buf.value if 0 < n < 600 else ""
    except (OSError, AttributeError):
        return ""


def _drives() -> list[str]:
    from .pcsys import disks
    try:
        return [d for d, _total, _free in disks()]
    except OSError:
        return []


_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_STEAMID = re.compile(r"\b7656119\d{10}\b")
_IPV4 = re.compile(r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b")
_MAC = re.compile(r"\b(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}\b")
_URL_SECRET = re.compile(r"(?i)([?&](?:access_)?(?:token|key|sig|signature|auth|session|code|ticket|password|pass|pwd|"
                         r"secret)=)[^&\s\"'<>]+")
_CONF_SECRET = re.compile(r"(?i)([\"']?\b(?:password|passwd|pwd|pass|secret|token|api[_-]?key|apikey|auth[_-]?key|"
                          r"access[_-]?key|private[_-]?key|client[_-]?secret|refresh[_-]?token|session[_-]?id|"
                          r"cookie)\b[\"']?\s*[:=]\s*[\"']?)([^\"'\s,;}<]{4,})")
_XML_SECRET = re.compile(r"(?i)(<(pass|password|pwd|secret|token|key|apikey|accesstoken)\b[^>]*>)([^<]{3,})(</)")
_BEARER = re.compile(r"(?i)(\bbearer\s+)[A-Za-z0-9._~+/=-]{12,}")
_VERSIONISH = re.compile(r"(?i)(?:ver(?:sion)?|build|v|driver)\W{0,3}$")


def _private_ip(ip: str) -> bool:
    a, b = (int(x) for x in ip.split(".")[:2])
    return a in (0, 10, 127) or (a == 192 and b == 168) or (a == 172 and 16 <= b <= 31) or (a == 169 and b == 254) or \
        a >= 224 or (a == 100 and 64 <= b <= 127)


# the public DNS servers everyone uses: they say nothing about the user (and a hint may name one)
PUBLIC_DNS = {"1.1.1.1", "1.0.0.1", "8.8.8.8", "8.8.4.4", "9.9.9.9", "149.112.112.112", "208.67.222.222",
              "208.67.220.220"}


# ---------------------------------------------------------------- the helper itself
class Fixer:
    def __init__(self, actions, runner: Callable[..., tuple[int, str]] = run, platform_: str = sys.platform, reg=None,
                 env: dict | None = None, home: Path | None = None, user: str | None = None, pc: str | None = None,
                 steam_base: Callable[[], Path | None] | None = None, open_url: Callable[[str], bool] = quiet.open_url,
                 trash: Callable[[list[Path]], None] | None = None, printers=None,
                 refresh_net: Callable[[], None] = _refresh_wininet, drives: Callable[[], list[str]] = _drives,
                 now: Callable[[], float] = time.time, data_dir: Path | None = None,
                 procs: Callable[[], list[tuple[str, str]]] = _processes, root: Path | None = None,
                 probe: Callable[[str, int], bool] = tcp_probe, uname: Callable[[], str] = platform.release):
        from .pcsys import WinReg
        self.actions, self.run, self.platform, self.procs = actions, runner, platform_, procs
        self.win, self.linux = platform_ == "win32", platform_.startswith("linux")
        self.reg = reg if reg is not None else (WinReg() if self.win else None)
        self._envd = {str(k).upper(): str(v) for k, v in (os.environ if env is None else env).items()}
        self.home = Path(home or Path.home())
        self.root = Path(root) if root is not None else Path("/")    # Linux: where / is (a folder in the tests)
        self.user = (self._env("USERNAME") or self._env("USER") or self._env("LOGNAME")) if user is None else user
        if pc is None:
            pc = self._env("COMPUTERNAME") or (socket.gethostname() if env is None and not self.win else "")
        self.pc = pc
        self._steam_base = steam_base
        self.open_url, self.refresh_net, self.drives, self.now = open_url, refresh_net, drives, now
        self.probe, self.uname = probe, uname
        self._trash = trash
        if printers is None and not self.win:
            from .fixlinux import CupsPrinters
            printers = CupsPrinters(runner, self.home)
        self.printers = printers if printers is not None else WinPrinters()
        self._data = data_dir
        self._progs: list[Program] = []
        self._progs_at = 0.0
        self.runtimes: list[str] = []                 # display names of the Visual C++ runtimes installed
        self._listed = False                          # the list of installed programs could be read
        self._scans: dict[str, Scan] = {}
        self._lock = threading.Lock()
        self._homes = [x for x in {str(self.home), _short_path(self.home) if home is None else ""} if x]

    # ---------------------------------------------------------------- where things are
    def _env(self, name: str) -> str:
        return self._envd.get(name.upper(), "")

    def _dir(self, var: str, fallback: str) -> Path:
        v = self._env(var)
        return Path(v) if v else self.home / fallback

    def local(self) -> Path:
        return self._dir("LOCALAPPDATA", "AppData/Local")

    def roaming(self) -> Path:
        return self._dir("APPDATA", "AppData/Roaming")

    def _shell_folder(self, name: str, fallback: str) -> Path:
        v = self.reg.get("HKEY_CURRENT_USER", SHELL_FOLDERS, name) if self.reg is not None else None
        return Path(_expand(str(v), self._env)) if v else self.home / fallback

    def documents(self) -> Path:
        return self._shell_folder("Personal", "Documents")

    def saved_games(self) -> Path:
        return self._shell_folder(SAVED_GAMES_ID, "Saved Games")

    def steam_base(self) -> Path | None:
        if self._steam_base is not None:
            return self._steam_base()
        from . import diskmap
        return diskmap.steam_base(self.platform == "win32")

    def data_dir(self) -> Path:
        if self._data is None:
            from .config import data_dir
            self._data = data_dir()
        return self._data

    # ---------------------------------------------------------------- privacy
    def clean(self, text: str) -> str:
        """Text for the model: the home folder, the user's and the computer's names, e-mails, IDs and anything
        secret taken out."""
        text = str(text or "")
        sep = r"[\\/]+"
        for h in sorted(self._homes, key=len, reverse=True):
            raw = [x for x in re.split(r"[\\/]+", h) if x]
            parts = [re.escape(x) for x in raw]
            if parts and self.win:
                text = re.sub(sep.join(parts) + r"(?![\w-])", "%USERPROFILE%", text, flags=re.I)
            elif parts:                                  # /home/<user>/.config → ~/.config (Z:\home\<user> too)
                lead = "" if re.fullmatch(r"[A-Za-z]:", raw[0]) else sep
                text = re.sub(lead + sep.join(parts) + r"(?![\w-])", "~", text)
        text = _EMAIL.sub("<email>", text)               # before the names: olena@… goes whole, not as <user>@…
        for name, mask in ((self.user, "<user>"), (self.pc, "<pc>")):
            if name and len(name) >= 3 and name.lower() not in GENERIC_USERS:
                text = re.sub(rf"(?i)(?<![\w]){re.escape(name)}(?![\w])", mask, text)
        text = _STEAMID.sub("<steam id>", text)
        text = _IPV4.sub(lambda m: m.group(0) if _private_ip(m.group(0)) or m.group(0) in PUBLIC_DNS or
                         _VERSIONISH.search(text[max(0, m.start() - 12):m.start()]) else "<ip>", text)
        text = _MAC.sub("<mac>", text)
        text = _URL_SECRET.sub(r"\1••••", text)
        text = _CONF_SECRET.sub(r"\1••••", text)
        text = _XML_SECRET.sub(r"\1••••\4", text)
        text = _BEARER.sub(r"\1••••", text)
        finds = sensitive.find(text)
        return sensitive.mask(text, finds) if finds else text

    def unmask(self, text: str) -> str:
        """A path or a name the model has the way clean() showed it (<user>, <pc>), as it is on this computer."""
        text = str(text or "")
        for name, mask in ((self.user, "<user>"), (self.pc, "<pc>")):
            if name:
                text = text.replace(mask, name)
        return text

    # ---------------------------------------------------------------- the installed programs
    def programs(self) -> list[Program]:
        with self._lock:
            if self._progs and self.now() - self._progs_at < PROGRAMS_TTL:
                return self._progs
        found: list[Program] = []
        seen: set[str] = set()
        if self.win:
            sources = [self._steam, self._epic, self._gog, self._xbox, self._installed]
        else:
            from . import fixlinux
            sources = [self._steam] + fixlinux.programs(self)
        for source in sources:
            try:
                items = source()
            except Exception:                              # noqa: BLE001  one broken source doesn't hide the rest
                items = []
            for p in items:
                key = os.path.normcase(os.path.normpath(p.folder)) if p.folder else "name:" + compact(p.name)
                if key in seen or not p.name.strip():
                    continue
                seen.add(key)
                found.append(p)
        with self._lock:
            self._progs, self._progs_at = found, self.now()
        return found

    def _steam(self) -> list[Program]:
        from . import diskmap
        base = self.steam_base()
        if not base:
            return []
        if not self.win:
            from .fixlinux import steam_prefix
        return [Program(g.name, "steam", g.folder, appid=g.appid,
                        prefix="" if self.win else steam_prefix(g.folder, g.appid))
                for g in diskmap.steam_games(base, self.win)
                if g.appid != "228980" and not re.match(r"steamworks|proton\b|steam linux runtime", g.name, re.I)]

    def _epic(self) -> list[Program]:
        d = Path(self._env("PROGRAMDATA") or r"C:\ProgramData") / "Epic" / "EpicGamesLauncher" / "Data" / "Manifests"
        out = []
        for f in sorted(d.glob("*.item")) if d.is_dir() else []:
            try:
                m = json.loads(f.read_text(encoding="utf-8", errors="replace"))
            except (OSError, ValueError):
                continue
            if not isinstance(m, dict) or not m.get("DisplayName"):
                continue
            out.append(Program(str(m["DisplayName"]), "epic", str(m.get("InstallLocation") or ""),
                               appid=str(m.get("AppName") or ""), version=str(m.get("AppVersionString") or ""),
                               exe=str(m.get("LaunchExecutable") or ""),
                               note="its install isn't finished" if m.get("bIsIncompleteInstall") else ""))
        return out

    def _gog(self) -> list[Program]:
        if self.reg is None or not hasattr(self.reg, "subkeys"):
            return []
        base = r"SOFTWARE\WOW6432Node\GOG.com\Games"
        out = []
        for sub in self.reg.subkeys("HKEY_LOCAL_MACHINE", base):
            v = self.reg.values("HKEY_LOCAL_MACHINE", base + "\\" + sub)
            name = str(v.get("gameName") or v.get("GAMENAME") or "").strip()
            if name:
                out.append(Program(name, "gog", str(v.get("path") or v.get("PATH") or ""), appid=sub,
                                   version=str(v.get("ver") or v.get("version") or ""),
                                   exe=str(v.get("exeFile") or v.get("exe") or "")))
        return out

    def _xbox(self) -> list[Program]:
        out = []
        for d in self.drives():
            base = Path(d) / "XboxGames"
            try:
                kids = [x for x in base.iterdir() if x.is_dir()] if base.is_dir() else []
            except OSError:
                continue
            for x in kids:
                if x.name.lower() == "gamesave":
                    continue
                folder = x / "Content" if (x / "Content").is_dir() else x
                out.append(Program(x.name, "xbox", str(folder)))
        return out

    def _installed(self) -> list[Program]:
        if self.reg is None or not hasattr(self.reg, "subkeys"):
            return []
        out, runtimes = [], []
        win = os.path.normcase(self._env("WINDIR") or r"C:\Windows")
        for hive, base in (("HKEY_LOCAL_MACHINE", UNINSTALL),
                           ("HKEY_LOCAL_MACHINE", r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
                           ("HKEY_CURRENT_USER", UNINSTALL)):
            for sub in self.reg.subkeys(hive, base):
                if re.match(r"steam app \d+$", sub, re.I):           # Steam's games come from Steam itself
                    continue
                v = self.reg.values(hive, base + "\\" + sub)
                name = str(v.get("DisplayName") or "").strip()
                if not name or "steam://uninstall" in str(v.get("UninstallString") or "").lower():
                    continue
                if re.search(r"visual c\+\+", name, re.I):
                    runtimes.append(name)
                if (v.get("SystemComponent") == 1 or v.get("ParentKeyName")
                        or str(v.get("ReleaseType") or "") in ("Update", "Hotfix", "Security Update", "Update Rollup")
                        or re.search(r"\(KB\d+\)|^(update|security update|hotfix) for", name, re.I)):
                    continue
                folder = str(v.get("InstallLocation") or "").strip().strip('"')
                if not folder:
                    for raw in (v.get("DisplayIcon"), v.get("UninstallString")):
                        m = re.match(r'\s*"?([A-Za-z]:\\[^",]+?\.(?:exe|ico|dll))"?', str(raw or ""))
                        if m and not os.path.normcase(m.group(1)).startswith(win) and not re.search(
                                r"package cache|installshield installation information|\\installer\\", m.group(1), re.I):
                            folder = str(Path(m.group(1)).parent)
                            break
                if folder and self._bad_root(Path(folder)):
                    folder = ""
                icon = re.match(r'\s*"?([A-Za-z]:\\[^",]+?\.exe)"?', str(v.get("DisplayIcon") or ""))
                out.append(Program(name, "app", folder, version=str(v.get("DisplayVersion") or ""),
                                   publisher=str(v.get("Publisher") or ""), exe=icon.group(1) if icon else ""))
        self.runtimes, self._listed = runtimes, bool(out)
        return out

    def _bad_root(self, p: Path) -> bool:
        """A folder too big or too important to be one program's folder (a disk, Windows, Program Files…)."""
        if not self.win:
            from .fixlinux import bad_root
            return bad_root(self, p)
        try:
            p = p.resolve()
        except OSError:
            return True
        if p.parent == p:
            return True
        tops = [self._env(v) for v in ("WINDIR", "PROGRAMFILES", "PROGRAMFILES(X86)", "PROGRAMDATA", "APPDATA",
                                       "LOCALAPPDATA", "USERPROFILE")] + [str(self.home)]
        for t in filter(None, tops):
            try:
                if os.path.normcase(str(p)) == os.path.normcase(str(Path(t).resolve())):
                    return True
            except OSError:
                continue
        win = self._env("WINDIR")
        try:
            if win and p.is_relative_to(Path(win).resolve()):
                return True
            if p.is_relative_to(self.data_dir().resolve()):
                return True
        except (OSError, ValueError):
            pass
        return False

    # ---------------------------------------------------------------- one program by name
    def _score(self, q: str, p: Program) -> float:
        names = [norm(p.name)] + ([norm(Path(p.folder).name)] if p.folder else [])
        if p.source in ("flatpak", "snap") and p.appid:        # org.gimp.GIMP is "gimp" too; a Snap by its own name
            parts = p.appid.split(".")
            names += [norm(x) for x in (parts[1:] if len(parts) > 1 else parts)
                      if len(x) >= 3 and x.lower() not in APPID_WORDS]
        ql, qc = _latin(q), _latin(q).replace(" ", "")
        best = 0.0
        for n in names:
            nl = _latin(n)
            nc = nl.replace(" ", "")
            if not nc:
                continue
            if ql == nl or qc == nc:
                return 1.0
            words, qw = nl.split(), ql.split()
            if qw and all(any(w.startswith(x) for w in words) for x in qw):
                best = max(best, 0.9 if words[0].startswith(qw[0]) else 0.8)
            elif len(qc) >= 4 and qc in nc:
                best = max(best, 0.7)
            else:
                r = difflib.SequenceMatcher(None, qc, nc[:len(qc) + 2]).ratio()
                if r >= 0.8:
                    best = max(best, 0.6 * r)
        return best

    def find(self, name: str) -> list[Program]:
        """The programs that match a name, best first."""
        q = norm(name)
        if not q:
            return []
        scored = sorted(((self._score(q, p), i, p) for i, p in enumerate(self.programs())), key=lambda x: (-x[0], x[1]))
        hits = [(s, p) for s, _i, p in scored if s >= 0.48]
        if not hits:
            return []
        top = hits[0][0]
        same = [p for s, p in hits if s >= top - 0.001]
        # a game and its own tools (editor, server, soundtrack): the shortest name is the game
        return sorted(same, key=lambda p: (p.source not in GAME_SOURCES, len(p.name)))

    def program(self, name: str) -> Program:
        hits = self.find(name)
        if not hits:
            raise WorkError(self._not_found(name))
        if len(hits) > 1 and len({norm(p.name) for p in hits}) > 1:
            exact = [p for p in hits if norm(p.name) == norm(name)]
            if len(exact) == 1:
                return exact[0]
            short = min(hits, key=lambda p: len(norm(p.name)))          # Valheim / Valheim Dedicated Server
            if all(norm(p.name).startswith(norm(short.name)) for p in hits):
                return short
            raise WorkError("Several programs match: " + "; ".join(f"{p.name} ({p.label()})" for p in hits[:8]) +
                            ". Call again with the exact name.")
        return hits[0]

    def _not_found(self, name: str) -> str:
        progs = self.programs()
        if not progs:
            return "Lanterna couldn't read the list of installed programs here."
        q = _latin(name).replace(" ", "")
        close = sorted(progs, key=lambda p: -difflib.SequenceMatcher(None, q, compact(p.name)).ratio())[:6]
        games = [p.name for p in progs if p.source in GAME_SOURCES][:25]
        return (f"No installed program is called '{name}'. Closest names: {'; '.join(p.name for p in close)}."
                + (f" Games here: {'; '.join(games)}." if games else "") +
                " Call again with the name as installed (in Latin letters, as the game or program calls itself).")

    # ---------------------------------------------------------------- its folders
    def scan(self, p: Program) -> Scan | None:
        if p.private or not p.folder or not Path(p.folder).is_dir() or self._bad_root(Path(p.folder)):
            return None                                   # a browser or a launcher has no mods to look for
        key = os.path.normcase(p.folder)
        with self._lock:
            s = self._scans.get(key)
            if s and self.now() - s.at < SCAN_TTL:
                return s
        s = self._scan(Path(p.folder), self._steam_info(p).get("updated", 0) if p.source == "steam" else 0)
        s.at = self.now()
        with self._lock:
            self._scans[key] = s
        return s

    def forget(self, p: Program) -> None:
        """After a change: the next look reads the folder again."""
        with self._lock:
            self._scans.pop(os.path.normcase(p.folder or ""), None)

    def _scan(self, root: Path, updated: float = 0) -> Scan:
        s = Scan(root)
        t0 = time.monotonic()
        todo: deque[tuple[Path, int]] = deque([(root, 0)])
        while todo and not s.cut:
            d, depth = todo.popleft()
            try:
                entries = list(os.scandir(d))
            except OSError:
                continue
            names = {e.name.lower() for e in entries}
            exe_folder = any(n.endswith(".exe") for n in names)
            in_mods = any(x.lower() in MOD_DIRS for x in d.relative_to(root).parts)
            paks = {n[:6] for n in names if n.endswith(".pak") and not n.endswith("_p.pak")}
            for e in entries:
                s.count += 1
                if s.count > SCAN_ENTRIES or time.monotonic() - t0 > SCAN_SECONDS:
                    s.cut = True
                    break
                try:
                    st = e.stat(follow_symlinks=False)
                    is_dir = e.is_dir(follow_symlinks=False)
                except OSError:
                    continue
                if getattr(st, "st_file_attributes", 0) & 0x400:       # a link to somewhere else: not followed
                    continue
                low = e.name.lower()
                rel = Path(e.path).relative_to(root).as_posix()
                if is_dir and low in ANTICHEAT:
                    s.anticheat.add(ANTICHEAT[low])
                elif not is_dir and low.startswith(("easyanticheat", "beclient", "beservice")):
                    s.anticheat.add(ANTICHEAT["easyanticheat" if low.startswith("easy") else "battleye"])
                if is_dir and low == TURNED_OFF.lower():
                    s.aside.append(rel)
                    continue
                m = _OFF.match(e.name)
                base = m.group("base") if m else ""
                # a file counts only with its whole name kept (dxgi.dll.bak): 'dbghelp.bak' may be the game's own;
                # deep in the game's data '005-Old' is just a name
                if m and base.lower() not in names and not in_mods and (is_dir or Path(base).suffix) and \
                        rel.count("/") <= 3:
                    s.renamed.append({"rel": rel, "dir": is_dir, "base": base, "mod": bool(mod_kind(base, exe_folder)),
                                      "own": not is_dir and Path(base).suffix.lower() in RUNNABLE})
                kind = mod_kind(e.name, exe_folder)
                if low.endswith("_p.pak") and not is_dir and low[:6] not in paks:
                    kind = "a mod pack (a .pak with _P loads over the game's own files)"   # official patches share
                if kind and not in_mods and (not is_dir or _has_content(Path(e.path))):   # the game's pak names
                    s.mods.append({"rel": rel, "dir": is_dir, "what": kind})
                if not is_dir:
                    if (low.endswith(".exe") and Path(low).stem not in SKIP_EXE) or low.endswith((".x86_64", ".x86")) \
                            or (not self.win and not Path(low).suffix and st.st_mode & 0o111 and st.st_size > 100_000):
                        s.exes.append(rel)                       # Linux games: game.x86_64, or a big runnable file
                    elif low.endswith(".log"):
                        s.logs.append(Path(e.path))
                if updated and st.st_mtime > updated + 3600 and not _churn(rel, is_dir):
                    s.changed.append((rel, st.st_mtime, is_dir))
                if is_dir:
                    if low.endswith("_data") and (Path(e.path) / "app.info").is_file() and not s.unity[1]:
                        try:
                            info = (Path(e.path) / "app.info").read_text(encoding="utf-8", errors="replace").splitlines()
                            s.unity = (info[0].strip(), info[1].strip()) if len(info) >= 2 else s.unity
                        except OSError:
                            pass
                    if depth < SCAN_DEPTH and low not in SKIP_SCAN and not secret_dir(low):
                        todo.append((Path(e.path), depth + 1))
        s.changed.sort(key=lambda c: -c[1])
        return s

    def _keys(self, p: Program, scan: Scan | None) -> set[str]:
        """Names its own folders in AppData and Documents may have."""
        words = _latin(p.name).split()
        keys = {"".join(words), "".join(words[:2]), "".join(words[:3]),
                compact(re.split(r"[:–—]| - ", p.name)[0])}
        if len(words) >= 3:
            keys.add("".join(w[0] for w in words))                        # Grand Theft Auto V → gtav
        if words and len(words[0]) >= 5:
            keys.add(words[0])
        if p.folder:
            keys.add(compact(Path(p.folder).name))
        if p.exe:
            keys.add(compact(Path(p.exe.replace("\\", "/")).stem))
        if scan and p.source != "app":            # Unreal names its folder after the project: <Project>/Binaries/…
            for rel in scan.exes[:40]:            # (plain exe names are too common: diagnostics, helper…)
                parts = rel.split("/")
                if 4 <= len(parts) <= 5 and parts[-3].lower() == "binaries":
                    keys.add(compact(parts[-4]))
        if scan and scan.unity[1]:
            keys.add(compact(scan.unity[1]))
        return {k for k in keys if len(k) >= 4 and k not in GENERIC_KEYS and k not in DENY_DIRS}

    def _match(self, base: Path, keys: set[str], nested: bool) -> list[Path]:
        out: list[Path] = []
        try:
            kids = [e for e in os.scandir(base) if e.is_dir(follow_symlinks=False)]
        except OSError:
            return out
        for e in kids:
            c = compact(e.name)
            if c in DENY_DIRS or secret_dir(e.name) or PRIVATE.search(e.name):
                continue
            if c in keys:
                out.append(Path(e.path))
            elif nested:
                try:
                    sub = [x for x in os.scandir(e.path) if x.is_dir(follow_symlinks=False)][:80]
                except OSError:
                    continue
                out += [Path(x.path) for x in sub if compact(x.name) in keys and not secret_dir(x.name)]
            if len(out) >= 4:
                break
        return out

    def _bases(self, p: Program) -> list[tuple[str, Path, str]]:
        """Where its own folders may be: (label, folder, how): 'nested' = a folder named like it there, or one level
        deeper; 'flat' = a folder named like it; 'self' = that folder itself (Linux: a Flatpak app's own)."""
        if not self.win:
            from .fixlinux import bases
            return bases(self, p)
        out = [("local", self.local(), "nested"), ("roaming", self.roaming(), "nested"),
               ("locallow", self.home / "AppData" / "LocalLow", "nested")]
        if p.source != "app":                             # Documents holds the user's own files: games only
            docs = self.documents()
            out += [("mygames", docs / "My Games", "flat"), ("documents", docs, "flat"),
                    ("saved", self.saved_games(), "nested")]
        return out

    def places(self, p: Program | None, scan: Scan | None = None) -> dict[str, Path]:
        """Where its files are: install, its data folders (local, roaming, locallow, mygames, documents, saved;
        Linux: config, data, cache, and those of its Proton prefix) and the shader caches."""
        out: dict[str, Path] = {}
        if p is not None:
            if p.folder and Path(p.folder).is_dir() and not self._bad_root(Path(p.folder)):
                out["install"] = Path(p.folder)
            if not p.private:
                scan = scan or self.scan(p)
                keys = self._keys(p, scan)
                for label, base, how in self._bases(p):
                    found = ([base] if base.is_dir() else []) if how == "self" else \
                        self._match(base, keys, how == "nested")
                    for d in found:
                        if any(_same(d, x) for x in out.values()) or self._inside_data(d):
                            continue
                        n = sum(1 for k in out if k.rstrip("0123456789") == label)
                        out[label if not n else f"{label}{n + 1}"] = d
                if self.linux:
                    from .fixlinux import proton_log
                    log = proton_log(self, p)
                    if log is not None:
                        out["proton_log"] = log                 # one file: what Proton wrote while the game ran
            if p.source == "steam" and p.appid and p.folder:
                sc = Path(p.folder).parent.parent / "shadercache" / p.appid
                if sc.is_dir():
                    out["steam_shaders"] = sc
        if self.win:
            local = self.local()
            for label, d in (("nvidia_cache", local / "NVIDIA" / "DXCache"), ("amd_cache", local / "AMD" / "DxCache"),
                             ("d3d_cache", local / "D3DSCache"), ("intel_cache", local / "Intel" / "ShaderCache")):
                if d.is_dir():
                    out[label] = d
        elif self.linux:
            from .fixlinux import driver_caches
            out.update(driver_caches(self))
        return out

    def _inside_data(self, d: Path) -> bool:
        try:
            r = d.resolve()
            return r == self.data_dir().resolve() or r.is_relative_to(self.data_dir().resolve())
        except (OSError, ValueError):
            return False

    def _path(self, p: Program | None, place: str, rel: str = "") -> tuple[Path, Path]:
        """(the place's folder, the file or folder in it). Nothing outside the place, nothing secret."""
        places = self.places(p)
        place = str(place or "").strip().lower()
        if place not in places:
            who = p.name if p else "This computer"
            raise WorkError(f"{who} has no place '{place}'. Places: {', '.join(places) or 'none'} (see fix_check).")
        root = places[place].resolve()
        rel = self.unmask(str(rel or "").strip().strip('"').replace("\\", "/"))   # the way clean() showed it
        if root.is_file():                                          # a place that is one file (Proton's log)
            if rel.strip("/") not in ("", ".", place, root.name) and Path(rel).name != root.name:
                raise WorkError(f"The place '{place}' is one file: give path '{root.name}'.")
            return root.parent, root
        target = None
        if rel and (re.match(r"^[A-Za-z]:/", rel) or rel.startswith("%")):
            target = Path(_expand(rel, lambda v: str(self.home) if v.upper() == "USERPROFILE" else self._env(v)))
            if not target.is_absolute():
                raise WorkError("Give a path inside the place, as fix_check or fix_list showed it.")
            target = target.resolve()
        elif rel and not self.win and (rel == "~" or rel.startswith(("~/", "/"))):
            t = (self.home / rel[2:] if rel.startswith("~/") else self.home if rel == "~" else Path(rel)).resolve()
            if rel.startswith("~") or t == root or t.is_relative_to(root):
                target = t                     # '/Content/Movies' that isn't a whole path: inside the place after all
        if target is None:
            parts = [x for x in rel.split("/") if x not in ("", ".")]
            if ".." in parts:
                raise WorkError("Give a path inside the place, without '..'.")
            if parts and parts[0].lower() == place and not (root / parts[0]).exists():
                parts = parts[1:]                                   # "install/Content/Movies"
            target = root.joinpath(*parts).resolve() if parts else root
        if target != root and not target.is_relative_to(root):
            raise WorkError(f"That path is outside the place '{place}'.")
        if any(secret_dir(x) or (secret_name(x) and i < len(target.relative_to(root).parts) - 1)
               for i, x in enumerate(target.relative_to(root).parts)):
            raise WorkError("Lanterna doesn't look into folders that may hold passwords, cookies, keys or sign-ins.")
        return root, target

    @staticmethod
    def _rel(root: Path, target: Path) -> str:
        return target.relative_to(root).as_posix() or "."

    # ---------------------------------------------------------------- Steam's own notes
    def _steam_info(self, p: Program) -> dict:
        if p.source != "steam" or not p.folder:
            return {}
        from . import diskmap
        apps = Path(p.folder).parent.parent
        kv: dict[str, str] = {}
        try:
            for k, v in diskmap._vdf((apps / f"appmanifest_{p.appid}.acf").read_text(encoding="utf-8", errors="replace")):
                kv.setdefault(k, v)
        except OSError:
            return {}

        def num(k: str) -> int:
            try:
                return int(kv.get(k) or 0)
            except ValueError:
                return 0
        return {"state": num("stateflags"), "updated": num("lastupdated"), "build": kv.get("buildid", ""),
                "result": num("updateresult"), "todo": num("bytestodownload") - num("bytesdownloaded"),
                "size": num("sizeondisk")}

    def launch_options(self, appid: str) -> str:
        base = self.steam_base()
        if not base or not appid:
            return ""
        files = sorted((base / "userdata").glob("*/config/localconfig.vdf"), key=lambda f: -f.stat().st_mtime) \
            if (base / "userdata").is_dir() else []
        for f in files[:3]:
            try:
                tree = vdf_tree(f.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                continue
            node = tree
            for k in ("userlocalconfigstore", "software", "valve", "steam", "apps", appid):
                node = node.get(k, {}) if isinstance(node, dict) else {}
            if isinstance(node, dict) and str(node.get("launchoptions", "")).strip():
                return str(node["launchoptions"]).strip()
        return ""

    # ---------------------------------------------------------------- logs and crash reports
    def _logs(self, places: dict[str, Path], scan: Scan | None) -> tuple[list[Path], list[Path]]:
        """(its logs, newest first; its crash reports)."""
        logs = list(scan.logs) if scan else []
        crashes: list[Path] = []
        for name, root in places.items():
            if name == "install" or name in CACHE_PLACES or name.rstrip("0123456789") == "cache":
                continue
            if root.is_file():                                   # Proton's log
                logs.append(root)
                continue
            todo: deque[tuple[Path, int]] = deque([(root, 0)])
            seen = 0
            while todo and seen < 6000:
                d, depth = todo.popleft()
                try:
                    entries = list(os.scandir(d))
                except OSError:
                    continue
                for e in entries:
                    seen += 1
                    low = e.name.lower()
                    try:
                        if e.is_dir(follow_symlinks=False):
                            if depth < 4 and not secret_dir(low) and low not in SAVE_DIRS and low not in LOG_SKIP \
                                    and "cache" not in low:
                                todo.append((Path(e.path), depth + 1))
                            continue
                    except OSError:
                        continue
                    if secret_name(e.name):
                        continue
                    if low.endswith(".log") or (low.endswith(".txt") and "log" in low):
                        logs.append(Path(e.path))
                    elif low == "crashcontext.runtime-xml":
                        crashes.append(Path(e.path))

        def mtime(f: Path) -> float:
            try:
                return f.stat().st_mtime
            except OSError:
                return 0.0
        logs = sorted({str(x): x for x in logs if not secret_name(x.name)}.values(), key=mtime, reverse=True)
        crashes.sort(key=mtime, reverse=True)
        return logs, crashes

    def digest(self, f: Path) -> dict:
        """The newest part of a log: its problem lines (each once, with how many times) and its last lines."""
        try:
            text, _cut_ = read_text(f, LOG_TAIL)
            st = f.stat()
        except OSError:
            return {}
        lines = [x for x in text.split("\n") if x.strip()]
        groups: dict[str, list] = {}
        for i, line in enumerate(lines):
            if CALM.search(line):
                continue
            sev = 3 if SEVERE.search(line) else 1 if PROBLEM.search(line) else 0
            if not sev:
                continue
            body = STAMP.sub("", line).strip()
            key = re.sub(r"\s+", " ", re.sub(r"0x[0-9a-f]+|\d+", "#", body.lower()))[:140]
            g = groups.setdefault(key, [sev, 0, i, body])
            g[1] += 1
            g[2] = i
        problems = sorted(groups.values(), key=lambda g: (-g[0], -g[1], -g[2]))[:12]
        last = [_cut(STAMP.sub("", x).strip(), 180) for x in lines[-12:]]
        return {"path": f, "size": st.st_size, "mtime": st.st_mtime,
                "problems": [(g[0], g[1], _cut(g[3], 220)) for g in problems], "last": [x for x in last if x]}

    @staticmethod
    def crash_report(f: Path) -> str:
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
            when = _when(f.stat().st_mtime)
        except OSError:
            return ""

        def tag(name: str) -> str:
            m = re.search(rf"<{name}>(.*?)</{name}>", text, re.S)
            return html.unescape(m.group(1)).strip() if m else ""
        stack = [x.strip() for x in tag("CallStack").splitlines() if x.strip()][:3]
        parts = [p for p in (tag("CrashType"), tag("ErrorMessage")) if p]
        return f"{when}: " + _cut(" — ".join(parts) or "a crash", 260) + (f" | {' / '.join(_cut(x, 90) for x in stack)}"
                                                                         if stack else "")

    # ---------------------------------------------------------------- what Windows noted
    def _ps(self, script: str, timeout: float = 60) -> dict:
        code, out = self.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], timeout=timeout)
        i, j = out.find("{"), out.rfind("}")
        if i < 0 or j < i:
            return {}
        try:
            data = json.loads(out[i:j + 1])
        except ValueError:
            return {}
        return data if isinstance(data, dict) else {}

    def windows_facts(self) -> dict:
        return self._ps(PS_PROGRAM, timeout=60)

    def crash_lines(self, facts: dict, p: Program, exes: set[str]) -> list[str]:
        folder = os.path.normcase(os.path.normpath(p.folder)) + os.sep if p.folder else ""
        exe = os.path.normcase(p.exe) if p.exe else ""
        named = {x for x in exes if x not in GENERIC_EXE}         # 'launcher' may be any program's

        def ours(app: str, path: str) -> bool:
            if path and (folder or exe):
                low = os.path.normcase(path)
                return bool((folder and low.startswith(folder)) or low == exe)
            return Path(app).stem.lower() in named

        groups: dict[tuple, list] = {}
        for ev in facts.get("ev") or []:
            if not isinstance(ev, dict):
                continue
            props = [str(x) for x in (ev.get("p") or [])]
            eid = ev.get("id")
            if eid == 1026:
                msg = props[0] if props else ""
                app = (re.search(r"Application:\s*(\S+)", msg) or [None, ""])[1]
                if not ours(app, ""):
                    continue
                exc = (re.search(r"Exception Info:\s*([^\r\n]+)", msg) or [None, ""])[1]
                key = (".net", _cut(exc, 120))
            else:
                if not props:
                    continue
                app, path = props[0], props[10] if eid == 1000 and len(props) > 10 else ""
                if not ours(app, path):
                    continue
                if eid == 1002:
                    key = ("hang", app)
                else:
                    module = props[3] if len(props) > 3 else ""
                    code = (props[6] if len(props) > 6 else "").strip().lower().removeprefix("0x")
                    if re.fullmatch(r"-\d+|\d{9,10}", code):    # a number (-1073741819 = c0000005); Windows 10+
                        code = f"{int(code) & 0xFFFFFFFF:08x}"     # writes hex digits ("80000003" stays as it is)
                    key = ("crash", app, module, code, props[11] if len(props) > 11 else "")
            g = groups.setdefault(key, [0, ""])
            g[0] += 1
            g[1] = max(g[1], str(ev.get("t") or ""))
        out = []
        for key, (n, last) in sorted(groups.items(), key=lambda kv: (kv[1][0], kv[1][1]), reverse=True):
            times = f"{n}×, last {last}"
            if key[0] == "hang":
                out.append(f"{key[1]} stopped responding ({times})")
            elif key[0] == ".net":
                out.append(f".NET error {key[1] or ''} ({times})")
            else:
                _k, app, module, code, mpath = key
                what = module_meaning(module, mpath, p.folder)
                out.append(f"{app} crashed in {module or '?'}" + (f" ({what})" if what else "") +
                           (f", code {code}" + (f" ({EXC_CODES[code]})" if code in EXC_CODES else "") if code else "") +
                           f" ({times})")
        return out[:8]

    def gpu_lines(self, facts: dict) -> list[str]:
        out = []
        for g in facts.get("gpu") or []:
            if not isinstance(g, dict):
                continue
            name, ver, date = str(g.get("n") or ""), str(g.get("v") or ""), str(g.get("d") or "")
            if re.search(r"remote display|parsec|virtual|indirect display|spacedesk|meta virtual", name, re.I):
                continue
            if re.search(r"basic display|basic render", name, re.I):
                out.append(f"! {name}: no graphics driver is installed (games run very badly or not at all). The "
                           "user installs the driver from the maker of the graphics card (NVIDIA, AMD or Intel).")
                continue
            shown = f"{nvidia_version(ver)} ({ver})" if "nvidia" in name.lower() else ver
            line = f"Graphics: {name}, driver {shown}" + (f" from {date}" if date else "")
            try:
                age = (dt.datetime.fromtimestamp(self.now()) - dt.datetime.strptime(date, "%Y-%m-%d")).days
            except ValueError:
                age = 0
            if age > 365:
                line += f" — over {age // 365} year{'s' if age >= 730 else ''} old: new games often need a newer driver"
            out.append(line)
        return out

    @staticmethod
    def overlay_lines(names: set[str], table: dict[str, str] | None = None) -> list[str]:
        found = sorted({label for name, label in (OVERLAYS if table is None else table).items() if name in names})
        return [f"Running now (these can hook into games: overlays, recorders, audio tools): {', '.join(found)}"] \
            if found else []

    def exe_stems(self, p: Program, scan: Scan | None) -> set[str]:
        stems = {Path(rel).stem.lower() for rel in (scan.exes if scan else [])[:60]}
        if p.exe:
            stems.add(Path(p.exe.replace("\\", "/")).stem.lower())
        return {s for s in stems if s and s not in SKIP_EXE}

    def running(self, p: Program | None, procs: list[tuple[str, str]] | None = None) -> list[str]:
        """Its programs running now: by where they run from (by name only where Windows hides the path)."""
        if p is None:
            return []
        sep = os.sep if self.win else "/"

        def key(x: str) -> str:
            return os.path.normcase(os.path.normpath(x)).replace(os.sep, sep)
        folder = key(p.folder) + sep if p.folder else ""
        exes = {key(p.exe)} | ({key(os.path.realpath(p.exe))} if not self.win else set()) if p.exe else set()
        named = {x for x in self.exe_stems(p, self.scan(p) if p.folder else None) if x not in GENERIC_EXE}
        # a game inside Steam's folder is the game's, not Steam's: the deepest folder wins
        deeper = [f for f in (key(x.folder) + sep for x in self.programs() if x.folder)
                  if folder and f.startswith(folder) and f != folder]
        # Linux: Steam starts a game with 'SteamLaunch AppId=…', a Flatpak app runs in its own scope
        marks = {f"steam-app:{p.appid}" if p.source == "steam" and p.appid else "",
                 f"flatpak:{p.appid}" if p.source == "flatpak" and p.appid else ""} - {""}
        hits = set()
        try:
            procs = self.procs() if procs is None else procs
        except OSError:
            procs = []
        for name, path in procs:
            if path.startswith(("steam-app:", "flatpak:")):
                if path in marks:
                    hits.add(p.name)
                continue
            low = key(path) if path else ""
            if low and ((folder and low.startswith(folder) and not any(low.startswith(f) for f in deeper))
                        or low in exes):
                hits.add(Path(path).name)
            elif not low and Path(name).stem.lower() in named:
                hits.add(name)
        return sorted(hits)

    # ---------------------------------------------------------------- fix_check
    def check(self, what: str, problem: str = "", limit: int = 3800) -> str:
        if not (self.win or self.linux):
            return "Lanterna checks programs and the system on Windows and Linux only."
        if not norm(what):
            raise WorkError("Say what doesn't work: the program's name, or sound / internet / printer / updates.")
        area = area_of(what)
        if area:
            return self.check_area(area, limit)
        try:
            p = self.program(what)
        except WorkError:
            area = area_of(what, strict=False)
            if area:
                return self.check_area(area, limit)
            raise
        return self.check_program(p, problem, limit)

    def check_program(self, p: Program, problem: str = "", limit: int = 3800) -> str:
        box: dict = {}
        lx = None
        if not self.win:
            from . import fixlinux as lx
        th = threading.Thread(target=lambda: box.update(self.windows_facts() if lx is None else lx.facts(self)),
                              daemon=True)
        th.start()
        info = self._steam_info(p)
        scan = self.scan(p)
        places = self.places(p, scan)
        logs, crashes = self._logs(places, scan) if not p.private else ([], [])
        try:
            procs = self.procs()
        except OSError:
            procs = []
        names = {Path(n).stem.lower() for n, _path in procs}
        running = self.running(p, procs)
        th.join(70)
        facts = dict(box)
        exes = self.exe_stems(p, scan)

        head = [f"Program: {p.name} — {p.label()}" + (f", version {p.version}" if p.version else "") +
                (f", build {info['build']}" if info.get("build") else "") +
                (f", updated {_day(info['updated'])}" if info.get("updated") else "")]
        if p.folder:
            head.append(f"Installed in (place install): {p.folder}" if "install" in places else
                        f"Its folder {p.folder} isn't there (or can't be looked at).")
        else:
            head.append("Its install folder isn't known." if lx is None else lx.install_line(self, p))
        head.append(f"It is running now ({', '.join(running)}): close it before changing its files." if running
                    else "It isn't running now.")
        if p.note:
            head.append(f"! {p.note}")
        if p.private:
            head.append("Its data is private (a browser, a password manager, a wallet, mail, a messenger or a launcher "
                        f"with sign-ins): Lanterna doesn't read it, only what {'Windows' if self.win else 'the system'} "
                        "noted.")

        found: list[str] = []
        if scan:
            for r in scan.renamed[:6]:
                kind = "folder" if r["dir"] else "file"
                if r["mod"]:
                    found.append(f"- {r['rel']} ({kind}): a mod or injector turned off by renaming (fine as it is).")
                    continue
                if r["own"]:
                    found.append(f"! {r['rel']}: the program's own file '{r['base']}' is missing, only this renamed copy "
                                 "is there. " + ("Steam's check (fix_verify) puts the original back." if
                                                 p.source == "steam" else "Repairing or reinstalling puts it back."))
                    continue
                if not r["dir"]:
                    found.append(f"! {r['rel']}: there is no '{r['base']}' next to it (renamed, or only a backup is "
                                 "left), so the program won't find it.")
                    continue
                size, n, kinds = _tree(scan.root / r["rel"], 20_000, 1.5)
                videos = sum(k for ext, k in kinds.items() if ext in VIDEO_EXT)
                what = f"folder, {_size(size)}" + (f": {_kinds_text(kinds)}" if kinds else "")
                if n and videos >= n / 2:
                    found.append(f"! {r['rel']} ({what}): its videos are hidden from the program by renaming the "
                                 f"folder (there is no '{r['base']}'). It is the usual trick to skip intro videos, but "
                                 "it also hides story videos: a black screen or a stuck scene where one should play. "
                                 f"Renaming it back to '{r['base']}' undoes it.")
                elif r["base"].startswith(("_", "~", ".")) or size < MB:
                    found.append(f"- {r['rel']} ({what}): kept aside, often a mod's or an installer's backup.")
                else:
                    found.append(f"! {r['rel']} ({what}): renamed or put aside — there is no '{r['base']}' next to "
                                 "it, so the program won't find it.")
            for m in scan.mods[:8]:
                gog = p.source == "gog" and m["what"].startswith("a file mods")
                found.append(f"! {m['rel']}{'/' if m['dir'] else ''}: {m['what']}" +
                             (" (GOG sometimes ships one as its own fix for an old game)" if gog else "") + ".")
            for a in scan.aside[:2]:
                found.append(f"- {a}/: files Lanterna turned off earlier (Undo is in What Lanterna did).")
            if scan.cut:
                found.append("- The folder is very big: Lanterna looked at its first part only.")
            if not found:
                found.append("- Nothing out of place in its folder (no renamed folders, mods or injector files).")

        steam: list[str] = []
        if info:
            state = info.get("state", 0)
            if state and state != 4:
                bits = [txt for bit, txt in STEAM_STATE.items() if state & bit]
                steam.append(f"! Steam says: {', '.join(bits) or f'state {state}'}.")
            if info.get("result"):
                steam.append(f"! Steam's last update of it failed (code {info['result']}).")
            if info.get("todo", 0) > 0:
                steam.append(f"! Steam still has {_size(info['todo'])} of it to download.")
            opts = self.launch_options(p.appid)
            if opts:
                steam.append(f"Steam launch options: {opts}")
            if names and "steam" not in names:
                steam.append("Steam isn't running now (its games need it).")
        if p.folder and Path(p.folder).is_dir():
            try:
                u = shutil.disk_usage(p.folder)
                low = u.free < 5 * GB or u.free / max(u.total, 1) < 0.03
                steam.append(f"{'! ' if low else ''}Free on its disk: {_size(u.free)}" +
                             (" — almost full (games need room for saves, caches and updates)" if low else ""))
            except OSError:
                pass
        if self._listed and not any(re.search(r"(2015|2017|2019|2022|v14)\b.*\(x64\)|x64.*(2015|2017|2019|2022)", r, re.I)
                                    for r in self.runtimes):
            steam.append("! The Visual C++ 2015-2022 runtime (x64) isn't installed: programs often won't start without "
                         "it (app_install Microsoft.VCRedist.2015+.x64).")

        if lx is None:
            crash = self.crash_lines(facts, p, exes) if facts else []
            system = self.gpu_lines(facts) + self.overlay_lines(names)
            prog: list[str] = []
            noted, calm = "Windows noted in the last 30 days:", "- No crashes or hangs of it."
        else:
            crash = lx.crash_lines(self, facts, p, exes, scan) if facts else []
            system = lx.gpu_lines(self, facts, game=p.source in GAME_SOURCES or bool(p.prefix)) + \
                self.overlay_lines(names, lx.OVERLAYS)
            prog = lx.program_lines(self, p, scan)
            noted = "The system noted (crashes: last 30 days; the graphics card and memory: last 7 days):"
            calm = "- No crashes of it."
        reports = [x for x in (self.crash_report(f) for f in crashes[:2]) if x]
        log_head, log_problems, log_last = [], [], []
        if logs:
            d = self.digest(logs[0])
            if d:
                where = self._where(places, d["path"])
                log_head = [f"Newest log: {where} ({_size(d['size'])}, changed {_when(d['mtime'])})"]
                log_problems = [f"- {'[' + str(n) + '×] ' if n > 1 else ''}{txt}" for _sev, n, txt in d["problems"]] or \
                    ["- No error lines in its newest part."]
                log_last = [f"  {x}" for x in d["last"]]
            others = []
            for f in logs[1:4]:
                try:
                    others.append(f"{self._where(places, f)} ({_when(f.stat().st_mtime)})")
                except OSError:
                    continue
            if others:
                log_head.append("Older logs: " + "; ".join(others))
        elif not p.private:
            log_head = ["No log of it was found in its folders."]

        place_lines = [f"- {k}: {v}" for k, v in places.items() if k not in CACHE_PLACES]
        caches = [k for k in places if k in CACHE_PLACES]
        if caches:
            place_lines.append(f"- shader caches (fix_cache): {', '.join(caches)}")
        changed = [f"- {rel}{'/' if is_dir else ''} ({_when(ts)})" for rel, ts, is_dir in (scan.changed if scan else [])[:8]]

        sections = [
            (0, "", head),
            (0, "Found in its folder:", found) if scan else (9, "", []),
            (1, "", prog),
            (1, noted, crash or [calm]) if facts else (9, "", []),
            (1, "", log_head),
            (1, "Error lines in the newest log:" if log_head and logs else "", log_problems),
            (2, "Crash reports of it:", reports),
            (2, "", steam + system),
            (3, f"Changed after Steam's last update ({_day(info.get('updated', 0))}):", changed),
            (4, "The newest log ends with:", log_last),
            (2, "Places (for fix_list / fix_read and the fixes):", place_lines),
            (0, "", ["(Lanterna: the strongest clues have '!'. Check the likeliest one on the web with the program's "
                     "name, then explain it and fix it with one fix_* card; if nothing stands out, look closer with "
                     "fix_list / fix_read or search the exact error.)"]),
        ]
        return self.clean(_fit(sections, limit))

    def _where(self, places: dict[str, Path], f: Path) -> str:
        for k, root in places.items():
            try:
                if root.is_file():
                    if _same(f, root):
                        return f"{k} ({root.name})"
                    continue
                if f.resolve().is_relative_to(root.resolve()):
                    return f"{k}/{f.resolve().relative_to(root.resolve()).as_posix()}"
            except (OSError, ValueError):
                continue
        return str(f)

    # ---------------------------------------------------------------- Windows itself
    def check_area(self, area: str, limit: int = 3800) -> str:
        if not self.win:
            from .fixlinux import AREAS as linux
            return self.clean(_fit(linux[area](self), limit))
        make = {"sound": self._sound, "internet": self._internet, "printer": self._printer, "updates": self._updates}
        return self.clean(_fit(make[area](), limit))

    def _sound(self) -> list:
        d = self._ps(PS_SOUND, 45)
        if not d:
            return [(0, "", ["Couldn't read the sound settings of Windows."])]
        lines, found = [], []
        for s in d.get("svc") or []:
            ok = str(s.get("s")) == "Running"
            lines.append(f"- Service {s.get('n')}: {s.get('s')} ({s.get('t')})")
            if not ok:
                found.append(f"! The service {s.get('n')} isn't running: Windows has no sound without it. Starting it "
                             "needs administrator rights: the user restarts the computer, or opens Services → "
                             f"{'Windows Audio' if s.get('n') == 'Audiosrv' else 'Windows Audio Endpoint Builder'} → Start.")
        devs = []
        for x in d.get("dev") or []:
            code = int(x.get("e") or 0)
            devs.append(f"- Sound card: {x.get('n')} — " + ("works" if not code else f"{CM_CODES.get(code, 'a problem')} "
                                                                                   f"(code {code})"))
            if code:
                found.append(f"! {x.get('n')} {CM_CODES.get(code, 'has a problem')} (code {code}). "
                             + ("Turn it on in Device Manager." if code == 22 else
                                "Its driver is the usual fix: from the maker of the computer or the sound card."))
        eps = d.get("ep") or []
        on = [str(x.get("n")) for x in eps if str(x.get("s")) == "OK"]
        bad = [f"{x.get('n')} ({x.get('s')})" for x in eps if str(x.get("s")) in ("Error", "Degraded")]
        off = [str(x.get("n")) for x in eps if str(x.get("s")) not in ("OK", "Error", "Degraded")]
        out_lines = [f"- Working outputs and inputs: {'; '.join(on) or 'none'}"]
        if off:
            out_lines.append(f"- Not connected now: {'; '.join(off[:8])}")
        if bad:
            found.append(f"! With an error: {'; '.join(bad)}.")
        if not on:
            found.append("! No sound output works: plug the speakers or headphones in (or turn them on), or check the "
                         "driver.")
        hint = ["(Lanterna: if everything here works, the sound likely goes to another output or is turned down in "
                "one program: open the sound settings with pc_settings_page sound for the user to pick the output "
                "and check the volume mixer.)"]
        return [(0, "Sound in Windows:", found or ["- No problem found in the sound devices and services."]),
                (1, "", lines + devs), (1, "", out_lines), (0, "", hint)]

    def _internet(self) -> list:
        d = self._ps(PS_INTERNET, 60)
        if not d:
            return [(0, "", ["Couldn't read the network settings of Windows."])]
        found, lines = [], []
        ads = [a for a in d.get("ad") or [] if isinstance(a, dict)]
        up = [a for a in ads if str(a.get("s")) == "Up"]
        for a in ads:
            if str(a.get("s")) == "Not Present":
                continue
            line = f"- {a.get('n')} ({_cut(a.get('d') or '', 60)}): {a.get('s')}" + (f", {a.get('sp')}" if
                                                                                    str(a.get('s')) == "Up" else "")
            lines.append(line)
        signal = re.findall(r"^\s*\S[^:\r\n]*:\s*(\d{1,3})\s?%\s*$", str(d.get("wlan") or ""), re.M)
        if signal:
            lines.append(f"- Wi-Fi signal: {signal[0]}%" + (" — weak" if int(signal[0]) < 40 else ""))
            if int(signal[0]) < 40:
                found.append(f"! The Wi-Fi signal is weak ({signal[0]}%): closer to the router, or a cable.")
        vpn = [str(a.get("d") or a.get("n")) for a in up if VPN.search(f"{a.get('n')} {a.get('d')}")]
        ips = [i for i in d.get("ip") or [] if isinstance(i, dict)]
        addrs = [ip for i in ips for ip in (i.get("ip") or [])]
        gws = [g for i in ips for g in (i.get("gw") or []) if g]
        lines.append(f"- Addresses: {', '.join(addrs) or 'none'}; router: {', '.join(gws) or 'none'}")
        if not up:
            found.append("! No network adapter is connected: Wi-Fi off, airplane mode on, or the cable is out.")
        elif addrs and all(a.startswith("169.254.") for a in addrs):
            found.append("! The computer got no address from the router (169.254…): restart the router and the "
                         "computer; on Wi-Fi forget the network and connect again.")
        gw_ok, dns_ok, tcp_ok = d.get("gwok"), bool(d.get("dnsok")), bool(d.get("tcp"))
        if gws:
            lines.append(f"- The router answers: {'yes' if gw_ok else 'no'}")
        lines.append(f"- Names of sites (DNS): {'work' if dns_ok else 'do not work'}")
        lines.append(f"- The internet by a direct address: {'works' if tcp_ok else 'does not work'}")
        if up and not dns_ok and tcp_ok:
            found.append("! The internet works, but site names don't (DNS): fix_windows dns clears the DNS cache; "
                         "if that doesn't help, the router's DNS is the problem (the user can set 1.1.1.1 in the "
                         "adapter's settings).")
        elif up and not tcp_ok and gw_ok:
            found.append("! The router answers but the internet doesn't: the router or the provider. Restart the "
                         "router; if it stays, call the provider.")
        elif up and gws and gw_ok is False and not tcp_ok:
            found.append("! Even the router doesn't answer: check the cable or Wi-Fi, and restart the router.")
        if vpn and not (dns_ok and tcp_ok):
            found.append(f"! A VPN is on: {'; '.join(vpn)}. It can block the internet: try with it off.")
        elif vpn:
            lines.append(f"- A VPN is on: {'; '.join(vpn)} (it can slow some sites or games down)")
        proxy = self._proxy()
        if proxy["on"]:
            found.append(f"! A proxy is on: {proxy['shown']}. If the user didn't set it on purpose (some programs and "
                         "viruses leave one), fix_windows proxy_off turns it off.")
        lines.append(f"- Proxy: {proxy['shown'] if proxy['on'] else 'off'}")
        hint = ["(Lanterna: if everything works here, the problem is one site or program (or its firewall rule).)"]
        return [(0, "Internet:", found or ["- Everything answers: the internet works on this computer."]),
                (1, "", lines), (0, "", hint)]

    def _proxy(self) -> dict:
        if self.reg is None:
            return {"on": False, "shown": "", "enable": None, "pac": ""}
        enable = self.reg.get("HKEY_CURRENT_USER", INET, "ProxyEnable")
        server = str(self.reg.get("HKEY_CURRENT_USER", INET, "ProxyServer") or "")
        pac = str(self.reg.get("HKEY_CURRENT_USER", INET, "AutoConfigURL") or "")
        on = enable == 1 or bool(pac)
        shown = "; ".join(x for x in ((server if enable == 1 else ""), (f"script {pac}" if pac else "")) if x)
        return {"on": on, "shown": self.clean(shown), "enable": enable, "pac": pac}

    def _printer(self) -> list:
        d = self._ps(PS_PRINTER, 45)
        if not d:
            return [(0, "", ["Couldn't read the printers of Windows."])]
        found, lines = [], []
        prs = [x for x in d.get("pr") or [] if isinstance(x, dict)]
        jobs = [x for x in d.get("jobs") or [] if isinstance(x, dict)]
        real = [x for x in prs if not VIRTUAL_PRINTERS.search(str(x.get("n")))]
        for x in prs:
            st, er = int(x.get("st") or 0), int(x.get("er") or 0)
            state = "offline (set to work offline)" if x.get("off") else PRINTER_STATUS.get(st, "")
            if er in PRINTER_ERROR and er != 9:
                state += f", {PRINTER_ERROR[er]}"
            n_jobs = sum(1 for j in jobs if str(j.get("p")) == str(x.get("n")))
            lines.append(f"- {x.get('n')}{' (default)' if x.get('d') else ''}: {state or 'unknown'}"
                         + (f", {n_jobs} job{'s' if n_jobs != 1 else ''} waiting" if n_jobs else ""))
            if x in real and (x.get("off") or st == 7 or er == 9):
                found.append(f"! {x.get('n')} is offline: check that it is on and connected (cable or the same Wi-Fi). "
                             "If it is on: Settings → Bluetooth & devices → Printers → it → Open print queue → Printer → "
                             "untick 'Use Printer Offline'.")
            elif x in real and er in PRINTER_ERROR and er != 9:
                found.append(f"! {x.get('n')}: {PRINTER_ERROR[er]}.")
        stuck = [j for j in jobs if re.search(r"error|paused|blocked|offline|deleting", f"{j.get('s')} {j.get('st')}", re.I)]
        if stuck or len(jobs) >= 3:
            oldest = min((str(j.get("t") or "") for j in jobs), default="")
            found.append(f"! {len(jobs)} print jobs wait in the queue" + (f" (the oldest from {oldest})" if oldest else "")
                         + ": stuck jobs block the next ones; fix_windows print_queue clears them.")
        if not real:
            found.append("! No real printer is set up in Windows: add it in Settings → Bluetooth & devices → Printers "
                         "(pc_settings_page printers).")
        default = next((x for x in prs if x.get("d")), None)
        if real and default is not None and default not in real:
            found.append(f"! The default printer is '{default.get('n')}' (not a real printer): fix_windows "
                         "default_printer makes the right one the default.")
        sp = (d.get("sp") or [{}])[0] if isinstance(d.get("sp"), list) and d.get("sp") else {}
        if sp and str(sp.get("s")) != "Running":
            found.append("! The print service (Spooler) isn't running: nothing prints without it. Starting it needs "
                         "administrator rights: restart the computer, or Services → Print Spooler → Start.")
        legacy = self.reg.get("HKEY_CURRENT_USER", WINDOWS_NT, "LegacyDefaultPrinterMode") if self.reg is not None else 1
        if legacy != 1:
            lines.append("- Windows chooses the default printer by itself (the last one used).")
        return [(0, "Printers:", found or ["- No problem found with the printers."]), (1, "", lines)]

    def _updates(self) -> list:
        d = self._ps(PS_UPDATES, 90)
        if not d:
            return [(0, "", ["Couldn't read Windows Update."])]
        found, lines = [], []
        for s in d.get("svc") or []:
            if str(s.get("t")) == "Disabled" and s.get("n") in ("wuauserv", "bits", "UsoSvc"):
                found.append(f"! The service {s.get('n')} is turned off: Windows can't update. Turning it on needs "
                             "administrator rights (Services → it → Startup type: Manual).")
        if d.get("reboot"):
            found.append("! Windows waits for a restart to finish updates: restart the computer first.")
        drive = (self._env("SYSTEMDRIVE") or "C:") + "\\"
        try:
            free = shutil.disk_usage(drive).free
            lines.append(f"- Free on {drive}: {_size(free)}")
            if free < 10 * GB:
                found.append(f"! Only {_size(free)} is free on {drive}: updates need 10-20 GB. Free up space first "
                             "(pc_disk).")
        except OSError:
            pass
        # Defender's definitions come several times a day (KB2267602): they would hide everything else
        hist = [h for h in d.get("hist") or [] if isinstance(h, dict) and
                not re.search(r"2267602|4052623|2461484", str(h.get("t") or ""))]
        failed: dict[str, list] = {}
        for h in hist:
            if int(h.get("r") or 0) in (4, 5):
                g = failed.setdefault(str(h.get("t")), [0, str(h.get("h") or "").lower(), str(h.get("d") or "")])
                g[0] += 1
        for title, (n, code, day) in list(failed.items())[:6]:
            meaning = WU_CODES.get(code, "")
            found.append(f"! Failed{f' {n}×' if n > 1 else ''}: {_cut(title, 110)} — {code}" +
                         (f" ({meaning})" if meaning else "") + f", last {day}")
        ok = sorted({str(h.get("t")): h for h in reversed(hist) if int(h.get("r") or 0) == 2}.values(),
                    key=lambda h: str(h.get("d") or ""), reverse=True)[:5]
        lines += [f"- {h.get('d')}: {_cut(h.get('t'), 110)} — installed" for h in ok]
        if d.get("err"):
            lines.append(f"- Couldn't read the update history: {_cut(d['err'], 120)}")
        hint = ["(Lanterna: the Windows Update troubleshooter is in Settings → System → Troubleshoot → Other "
                "troubleshooters (pc_settings_page troubleshoot). Repairs that need administrator rights are for the "
                "user to run in Terminal (Admin): DISM /Online /Cleanup-Image /RestoreHealth, then sfc /scannow.)"]
        return [(0, "Windows Update:", found or ["- No failed updates and nothing blocking them."]), (1, "", lines),
                (0, "", hint)]

    # ---------------------------------------------------------------- fix_list / fix_read
    def list_dir(self, program: str, place: str, folder: str = "", limit: int = 3800) -> str:
        p = self._who(program, place)
        root, d = self._path(p, place, folder)
        if not d.is_dir():
            raise WorkError(f"'{folder}' is not a folder in {place}.")
        try:
            entries = sorted(os.scandir(d), key=lambda e: (not e.is_dir(), e.name.lower()))
        except OSError as e:
            raise WorkError(f"Can't look in it: {e.strerror or e}") from None
        names = {e.name.lower() for e in entries}
        exe_folder = any(n.endswith(".exe") for n in names)
        lines, hidden = [], 0
        for e in entries:
            try:
                is_dir = e.is_dir(follow_symlinks=False)
                st = e.stat(follow_symlinks=False)
            except OSError:
                continue
            if secret_dir(e.name) if is_dir else secret_name(e.name):
                hidden += 1
                continue
            if len(lines) >= LIST_MAX:
                continue
            m = _OFF.match(e.name)
            note = ""
            if m and m.group("base").lower() not in names and (is_dir or Path(m.group("base")).suffix):
                note = f"  ← there is no '{m.group('base')}' here (renamed or kept aside)"
            elif mod_kind(e.name, exe_folder):
                note = f"  ← {mod_kind(e.name, exe_folder)}"
            lines.append((f"📁 {e.name}/  ({_when(st.st_mtime)})" if is_dir else
                          f"📄 {e.name}  ({_size(st.st_size)}, {_when(st.st_mtime)})") + note)
        while lines and sum(len(x) + 1 for x in lines) > limit - 300:
            lines.pop()
        more = len(entries) - hidden - len(lines)
        head = f"{place}/{self._rel(root, d)} ({len(entries) - hidden} items):"
        tail = (f"\n… and {more} more" if more > 0 else "") + (f"\n({hidden} private items not shown)" if hidden else "")
        return self.clean(head + "\n" + ("\n".join(lines) or "(empty)") + tail)

    def read(self, program: str, place: str, path: str, find: str = "", limit: int = 3800) -> str:
        p = self._who(program, place)
        root, f = self._path(p, place, path)
        if not f.is_file():
            raise WorkError(f"There is no file '{path}' in {place}.")
        if secret_name(f.name):
            raise WorkError("Lanterna doesn't read files that may hold passwords, keys or sign-ins.")
        if f.suffix.lower() not in TEXT_EXT:
            raise WorkError(f"Lanterna reads only text files (logs and settings); '{f.name}' isn't one.")
        st = f.stat()
        is_log = f.suffix.lower() in (".log", ".err", ".out") or "log" in f.stem.lower()
        text, cut = read_text(f, LOG_TAIL if is_log else 0)
        text = self.clean(text)
        head = f"{place}/{self._rel(root, f)} ({_size(st.st_size)}, changed {_when(st.st_mtime)})"
        room = max(800, limit - len(head) - 80)
        if find:
            lines = text.split("\n")
            q = str(find).lower()
            hits = [i for i, x in enumerate(lines) if q in x.lower()]
            if not hits:
                return f"{head}: no line has '{find}'" + (" in its newest part." if cut else ".")
            out, last = [], -2
            for i in hits:
                for k in range(max(0, i - 1), min(len(lines), i + 2)):
                    if k > last:
                        if k > last + 1 and out:
                            out.append("…")
                        out.append(_cut(lines[k], 300))
                        last = k
                if sum(len(x) + 1 for x in out) > room:
                    out.append(f"… ({len(hits)} lines have it)")
                    break
            return f"{head}, lines with '{find}':\n" + "\n".join(out)
        if len(text) > room:
            text = ("…\n" + text[-room:].split("\n", 1)[-1]) if is_log else (text[:room].rsplit("\n", 1)[0] + "\n…")
            cut = True
        return f"{head}{' — its newest part' if cut and is_log else ' — its start' if cut else ''}:\n{text}"

    def _who(self, program: str, place: str) -> Program | None:
        """The program a call is about (none is needed for the graphics driver's caches)."""
        if not str(program or "").strip():
            if str(place or "").strip().lower() in CACHE_PLACES[1:]:
                return None
            raise WorkError("Say which program (its name as fix_check showed it).")
        return self.program(program)

    # ---------------------------------------------------------------- the fixes (cards)
    def _changeable(self, place: str, root: Path, target: Path) -> None:
        if place == "proton_log":
            raise WorkError("Proton's log is only read: Proton writes it again when the game starts.")
        parts = [x.lower() for x in target.relative_to(root).parts]
        if place.rstrip("0123456789") == "saved" or any(x in SAVE_DIRS for x in parts):
            raise WorkError("Lanterna never changes saved games.")
        if target == root:
            raise WorkError("Not the whole place: give a file or folder inside it.")
        if any(secret_dir(x) for x in parts) or secret_name(target.name):
            raise WorkError("Lanterna doesn't touch files that may hold passwords, keys or sign-ins.")

    def _closed(self, p: Program | None, confirm: bool = False) -> None:
        """confirm: the check when the user presses Confirm (the card shows it to the user, not the model)."""
        if p is None:
            return
        now = self.running(p)
        if now and confirm:
            raise WorkError(f"{p.name} is running now ({', '.join(now)}): nothing was changed. Close it, then ask again.")
        if now:
            raise WorkError(f"{p.name} is running now ({', '.join(now)}). Ask the user to close it first (its files are "
                            "in use, and it may write its settings back when it closes), then call this again.")

    def _no_twin(self, kind: str, **same) -> None:
        """One card per change: the model sometimes asks twice."""
        for a in list(self.actions.items.values()):
            a = self.actions.get(a.id) or a
            if a.kind == kind and a.state in ("pending", "running") and \
                    all(a.details.get(k) == v for k, v in same.items()):
                raise WorkError("This card already waits for the user's Confirm: don't make another.")

    def propose_rename(self, program: str, place: str, path: str, new_name: str, why: str = "") -> str:
        p = self.program(program)
        place = str(place or "").strip().lower()
        root, src = self._path(p, place, path)
        self._changeable(place, root, src)
        if not src.exists():
            raise WorkError(f"There is no '{path}' in {place}.")
        new = str(new_name or "").strip()
        if not new or new in (".", "..") or re.search(r'[\\/:*?"<>|\x00-\x1f]', new) or new.endswith((" ", ".")) \
                or len(new) > 120:
            raise WorkError("new_name is only the new name, in the same folder: e.g. 'Movies'.")
        dst = src.with_name(new)
        if dst.exists() and not _same(src, dst):
            raise WorkError(f"'{new}' already exists next to it: nothing was changed.")
        if new == src.name:
            return f"It is already called '{new}'."
        old_ext, new_ext = Path(src.name).suffix.lower(), Path(new).suffix.lower()
        if new_ext in RUNNABLE and new_ext != old_ext:
            raise WorkError(f"Lanterna doesn't make {new_ext} files by renaming: that could start a program. If the "
                            "program needs its own file back, Steam's check (fix_verify) or reinstalling puts the "
                            "original back.")
        if secret_name(new):
            raise WorkError("Pick another name.")
        self._closed(p)
        rel, is_dir = self._rel(root, src), src.is_dir()
        self._no_twin("fix_rename", name=p.name, path=rel)

        def go() -> str:
            if not src.exists():
                raise WorkError(f"'{rel}' isn't there any more.")
            if dst.exists() and not _same(src, dst):
                raise WorkError(f"'{new}' is there now: nothing was changed.")
            self._closed(p, confirm=True)
            os.rename(src, dst)
            self.forget(p)
            self.actions.note_undo({"type": "moves", "moves": [(str(src), str(dst))], "rename": True})
            return f"renamed {place}/{rel} → {new} ({p.name})"
        self.actions.propose("fix_rename", {"name": p.name, "place": place, "path": rel, "to": new, "is_dir": is_dir,
                                            "why": self.clean(why)[:300]}, go)
        return WAITING

    def propose_setting(self, program: str, place: str, path: str, key: str, value, section: str = "",
                        why: str = "") -> str:
        p = self.program(program)
        place = str(place or "").strip().lower()
        root, f = self._path(p, place, path)
        self._changeable(place, root, f)
        if not f.is_file():
            raise WorkError(f"There is no file '{path}' in {place}.")
        if f.suffix.lower() not in SETTINGS_EXT:
            raise WorkError("Lanterna changes settings only in text settings files (.ini, .cfg, .conf, .json, "
                            ".properties, .txt).")
        if f.stat().st_size > READ_MAX:
            raise WorkError("This file is too big to be a settings file.")
        key, section = str(key or "").strip(), str(section or "").strip().strip("[]").strip()
        value = ("true" if value else "false") if isinstance(value, bool) else str(value if value is not None else "")
        if not key or len(key) > 120 or len(value) > 300 or len(section) > 160 or \
                any(c in x for x in (key, value, section) for c in "\r\n"):
            raise WorkError("key, value and section are one short line each.")
        raw = f.read_bytes()
        enc, bom = _bom(raw)
        text = raw[len(bom):].decode(enc)
        if f.suffix.lower() == ".json":
            new_text, old = json_set(text, key, value)
        else:
            new_text, old = ini_set(text, key, value, section)
        if old is not None and old.strip().strip('"') == value.strip().strip('"'):
            return f"Nothing to change: {key} is already {value}."
        try:
            data = (bom + new_text.encode(enc))
        except UnicodeEncodeError:
            raise WorkError("That value has letters this file can't hold.") from None
        self._closed(p)
        rel = self._rel(root, f)
        self._no_twin("fix_setting", name=p.name, path=rel, key=key)

        def go() -> str:
            from .workspace import _backup
            if f.read_bytes() != raw:
                raise WorkError("The file changed since it was read: nothing was changed. Ask again.")
            self._closed(p, confirm=True)
            backup = _backup(f)
            try:
                f.write_bytes(data)
            except PermissionError:
                raise WorkError(("Windows didn't let Lanterna write it (the file is read-only, or a program holds it)."
                                 if self.win else "The system didn't let Lanterna write it (the file is read-only).") +
                                " Nothing was changed.") from None
            self.forget(p)
            self.actions.note_undo({"type": "restore_backup", "path": str(f), "backup": backup})
            return f"{place}/{rel}: {key} = {value} (the old file is kept)"
        self.actions.propose("fix_setting", {"name": p.name, "place": place, "path": rel, "key": key,
                                             "section": section, "from": "" if old is None else self.clean(old)[:200],
                                             "to": self.clean(value), "added": old is None,
                                             "why": self.clean(why)[:300]}, go)
        return WAITING

    def propose_aside(self, program: str, place: str, paths, why: str = "") -> str:
        p = self.program(program)
        place = str(place or "").strip().lower()
        if isinstance(paths, str):
            paths = [x for x in re.split(r"[\n;]+", paths) if x.strip()]
        if not isinstance(paths, list) or not paths:
            raise WorkError("paths: the mod files or folders to turn off, as fix_check / fix_list show them.")
        scan = self.scan(p) if place == "install" else None
        flagged = scan.flagged() if scan else set()
        items: list[tuple[Path, Path]] = []
        root = None
        for rel in [str(x) for x in paths][:30]:
            root, src = self._path(p, place, rel)
            self._changeable(place, root, src)
            if not src.exists():
                raise WorkError(f"There is no '{rel}' in {place}.")
            parts = src.relative_to(root).parts
            if any(x.lower() == TURNED_OFF.lower() for x in parts):
                raise WorkError(f"'{rel}' is turned off already.")
            exe_folder = any(x.suffix.lower() == ".exe" for x in src.parent.iterdir()) if src.parent.is_dir() else False
            addon = (mod_kind(src.name, exe_folder) or any(x.lower() in MOD_DIRS for x in parts[:-1]) or
                     src.relative_to(root).as_posix().lower() in flagged or bool(_OFF.match(src.name)))
            if not addon:
                raise WorkError(f"'{rel}' doesn't look like a mod or an added file, so Lanterna doesn't move it. If it "
                                "really should go, the user can move it themselves.")
            dst = root / TURNED_OFF / src.relative_to(root)
            n = 2
            while dst.exists():
                dst = dst.with_name(f"{src.stem} ({n}){src.suffix}" if src.is_file() else f"{src.name} ({n})")
                n += 1
            items.append((src, dst))
        self._closed(p)
        rels = [self._rel(root, s) for s, _d in items]
        self._no_twin("fix_aside", name=p.name, files=rels)

        def go() -> str:
            self._closed(p, confirm=True)
            moves, failed = [], []
            for s, d in items:
                if not s.exists():
                    continue
                try:
                    d.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(s), str(d))
                    moves.append((str(s), str(d)))
                except OSError as e:
                    failed.append(f"{s.name} ({e.strerror or e})")
            if not moves:
                raise WorkError("Nothing was moved" + (f": {'; '.join(failed)}" if failed else " (they are gone)."))
            self.forget(p)
            self.actions.note_undo({"type": "moves", "moves": moves})
            return f"moved {len(moves)} into {TURNED_OFF} ({p.name})" + (
                f"; couldn't move {'; '.join(failed)}" if failed else "")
        self.actions.propose("fix_aside", {"name": p.name, "place": place, "files": rels, "count": len(rels),
                                           "to": TURNED_OFF, "why": self.clean(why)[:300]}, go)
        return WAITING

    def propose_cache(self, program: str, place: str, path: str = "", why: str = "") -> str:
        place = str(place or "").strip().lower()
        p = self._who(program, place)
        root, d = self._path(p, place, path)
        own = place.rstrip("0123456789") == "cache"           # Linux: its folder in ~/.cache is a cache as a whole
        if place not in CACHE_PLACES:
            parts = [x.lower() for x in d.relative_to(root).parts]
            if not own and (d == root or not any("cache" in x for x in parts)):
                raise WorkError("fix_cache is for cache folders only: a place like " +
                                ("nvidia_cache / d3d_cache / steam_shaders" if self.win else
                                 "mesa_cache / nvidia_cache / steam_shaders or its cache") +
                                ", or a folder with 'cache' in its name.")
            if d != root:
                self._changeable(place, root, d)
        if not d.is_dir():
            raise WorkError(f"There is no folder '{path}' in {place}.")
        size, count, _kinds = _tree(d)
        if not count:
            return "It is already empty."
        self._closed(p)
        label = CACHE_NAMES.get(place, "") if d == root else f"{place}/{self._rel(root, d)}"
        self._no_twin("fix_cache", path=label or place)
        bin_ = "the Recycle Bin" if self.win else "the Trash"

        def go() -> str:
            self._closed(p, confirm=True)
            trash = self._trash
            if trash is None:
                from .pcfiles import to_trash as trash
            trash([d])
            if p is not None:
                self.forget(p)
            self.actions.note_undo({"type": "trash", "paths": [str(d)]})
            return f"cleared {label or place} ({_size(size)} into {bin_})"
        details = {"name": p.name if p else "", "place": place, "path": label or place, "size": _size(size),
                   "count": count, "driver": p is None, "why": self.clean(why)[:300]}
        if not self.win:
            details["linux"] = True                       # the card says the Trash, not the Recycle Bin
        self.actions.propose("fix_cache", details, go)
        return WAITING

    def propose_verify(self, program: str) -> str:
        p = self.program(program)
        if p.source == "steam" and p.appid.isdigit():
            self._no_twin("fix_verify", appid=p.appid)

            def go() -> str:
                if not self.open_url(f"steam://validate/{p.appid}"):
                    raise WorkError("Steam didn't open.")
                return f"Steam is checking the files of {p.name}"
            self.actions.propose("fix_verify", {"name": p.name, "appid": p.appid}, go)
            return WAITING + " After Confirm, Steam checks the files itself and downloads what is missing or changed."
        if p.source == "epic":
            return ("Not a Steam game: the user checks it in the Epic Games Launcher: Library → the three dots on the "
                    "game → Manage → Verify. Tell them these steps.")
        if p.source == "gog":
            return ("Not a Steam game: the user checks it in GOG Galaxy: the game → the settings icon next to Play → "
                    "Manage installation → Verify / Repair. Tell them these steps.")
        if p.source.startswith("heroic"):
            return ("Not a Steam game: the user checks it in Heroic: the game → its menu (⋮) → Verify and Repair. Tell "
                    "them these steps.")
        if p.source == "lutris":
            return ("Lutris can't check a game's files: the user installs it again in Lutris (for a GOG or Epic game, "
                    "Heroic can verify it). Tell the user.")
        if p.source == "flatpak":
            return (f"Not a Steam game. A Flatpak app is checked and repaired with 'flatpak repair --user' (or 'sudo "
                    f"flatpak repair' when it is installed for all users) in Terminal, or by installing {p.appid} again "
                    "in Software. Tell the user.")
        if p.source == "snap":
            return (f"Not a Steam game. If it broke after an update, 'sudo snap revert {p.appid}' in Terminal goes back "
                    "to the version before; otherwise install it again in Software. Tell the user.")
        if not self.win:
            return ("Not a Steam game. A program from the system's packages is repaired by installing it again: in "
                    "Software, or in Terminal (Fedora: 'sudo dnf reinstall <package>'; Ubuntu: 'sudo apt install "
                    "--reinstall <package>'). It needs the computer's password, so tell the user.")
        return ("Not a Steam game. To repair a program: Settings → Apps → Installed apps → it → … → Modify or Repair "
                "(when it offers that), or install it again (app_install / app_upgrade). Tell the user.")

    def propose_windows(self, action: str, printer: str = "") -> str:
        a = str(action or "").strip().lower().replace("-", "_").replace(" ", "_")
        printer = self.unmask(printer)                            # "<user>'s printer", as clean() showed it
        if a in ("dns", "flush_dns", "flushdns"):
            self._no_twin("fix_dns")

            def go() -> str:
                code, out = self.run(["ipconfig", "/flushdns"], timeout=30)
                if code:
                    raise WorkError(_cut(out, 200) or "ipconfig failed")
                return "the DNS cache is cleared"
            self.actions.propose("fix_dns", {}, go)
            return WAITING
        if a in ("proxy_off", "proxy", "no_proxy"):
            px = self._proxy()
            if not px["on"]:
                return "No proxy is on: nothing to turn off."
            self._no_twin("fix_proxy")
            old_enable, old_pac = px["enable"], px["pac"]

            def go() -> str:
                if old_enable == 1:
                    self.reg.set("HKEY_CURRENT_USER", INET, "ProxyEnable", 0, "REG_DWORD")
                if old_pac:
                    self.reg.delete("HKEY_CURRENT_USER", INET, "AutoConfigURL")
                self.refresh_net()
                self.actions.note_undo({"type": "proxy", "enable": old_enable, "pac": old_pac})
                return "the proxy is off"
            self.actions.propose("fix_proxy", {"server": px["shown"]}, go)
            return WAITING
        if a in ("default_printer", "printer", "default"):
            names = self.printers.names()
            want = _pick_name(printer, names)
            was = self.printers.default()
            if want == was:
                return f"'{want}' is the default printer already."
            self._no_twin("fix_printer")
            legacy = self.reg.get("HKEY_CURRENT_USER", WINDOWS_NT, "LegacyDefaultPrinterMode")

            def go() -> str:
                self.reg.set("HKEY_CURRENT_USER", WINDOWS_NT, "LegacyDefaultPrinterMode", 1, "REG_DWORD")
                if not self.printers.set_default(want):
                    raise WorkError("Windows didn't accept it as the default printer.")
                self.actions.note_undo({"type": "printer", "name": was, "legacy": legacy})
                return f"{want} is the default printer"
            self.actions.propose("fix_printer", {"name": self.clean(want), "was": self.clean(was)}, go)
            return WAITING
        if a in ("print_queue", "queue", "clear_queue", "jobs"):
            names = self.printers.names()
            want = _pick_name(printer, names)
            self._no_twin("fix_queue", name=self.clean(want))

            def go() -> str:
                code, out = self.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", PS_CLEAR_QUEUE],
                                     timeout=60, env={**os.environ, "LANTERNA_PRINTER": want})
                if code or "ok" not in out:
                    raise WorkError("Windows didn't clear it: " + (_cut(out, 160) or "no answer") + ". Jobs of other "
                                    "users need administrator rights: the user opens the printer's queue in Settings.")
                return f"the print queue of {want} is cleared"
            self.actions.propose("fix_queue", {"name": self.clean(want)}, go)
            return WAITING
        raise WorkError("action: dns, proxy_off, default_printer or print_queue.")

    def propose_system(self, action: str, name: str = "") -> str:
        """Linux: the fixes in the system (fixlinux.propose)."""
        if self.win:
            return self.propose_windows(action, name)
        from .fixlinux import propose
        return propose(self, action, name)

    # ---------------------------------------------------------------- Undo of the fixes in the system
    def undo_sound(self, u: dict) -> bool:
        from .fixlinux import undo_sound
        return undo_sound(self, u)

    def undo_proxy(self, u: dict) -> bool:
        if u.get("linux"):
            from .fixlinux import undo_proxy
            return undo_proxy(self, u)
        if u.get("enable") == 1:
            self.reg.set("HKEY_CURRENT_USER", INET, "ProxyEnable", 1, "REG_DWORD")
        if u.get("pac"):
            self.reg.set("HKEY_CURRENT_USER", INET, "AutoConfigURL", str(u["pac"]), "REG_SZ")
        self.refresh_net()
        return True

    def undo_printer(self, u: dict) -> bool:
        if u.get("linux"):
            from .fixlinux import undo_printer
            return undo_printer(self, u)
        if u.get("legacy") is None:
            self.reg.delete("HKEY_CURRENT_USER", WINDOWS_NT, "LegacyDefaultPrinterMode")
        else:
            self.reg.set("HKEY_CURRENT_USER", WINDOWS_NT, "LegacyDefaultPrinterMode", int(u["legacy"]), "REG_DWORD")
        return self.printers.set_default(u["name"]) if u.get("name") else True


# ---------------------------------------------------------------- logs: which lines matter
SEVERE = re.compile(r"\bfatal\b|\bcrash(?:ed|es|ing)?\b|\bexception\b|access violation|device (?:removed|hung|lost|reset)|"
                    r"dxgi_error|out of (?:video )?memory|gpu (?:crash|hang)|assert(?:ion)? fail|\bunhandled\b|"
                    r"stack overflow|segmentation fault|\bpanic\b", re.I)
PROBLEM = re.compile(r"\berror\b|\berr\b|\bfail(?:ed|ure|s)?\b|\bmissing\b|\bunable to\b|\bcannot\b|\bcan'?t\b|"
                     r"\bcould ?n[o']?t\b|\bnot found\b|\binvalid\b|\bdenied\b|\btimed? ?out\b|\bcorrupt", re.I)
# lines that only sound bad: counters at zero, success, and programs setting up their own crash reporting
CALM = re.compile(r"\b0 errors?\b|\berrors?\s*[:=]\s*0\b|\bno errors?\b|\bwithout errors?\b|\berror ?code\s*[:=]\s*0\b|"
                  r"\bsucce(?:ss|eded|ssful(?:ly)?)\b|\bexception(?:s)? ?handler|crash ?report(?:ing|er|s)?\b|"
                  r"crash ?handler|crash ?guid|unprocessedcrashes|crashcontext|abort handler|"
                  r"\b(?:mounting|loading|loaded|mounted)\b.*\bplugin\b", re.I)
STAMP = re.compile(r"^\s*(?:\[[^\]]{0,40}\]\s*){1,3}|^\s*\d{4}[-./]\d\d[-./]\d\d[ T_-]\d\d[:.]\d\d[:.]\d\d(?:[.,:]\d+)?"
                   r"\s*(?:[+-]\d\d:?\d\d|Z)?\s*")


FILLER = {"no", "not", "isn", "doesn", "don", "t", "is", "are", "the", "my", "a", "on", "in", "of", "with", "windows",
          "pc", "computer", "laptop", "works", "working", "work", "broken", "problem", "problems", "issue", "issues",
          "settings", "device", "devices", "slow", "немає", "нема", "не", "працює", "працюють", "проблема", "проблеми",
          "з", "із", "в", "у", "на", "комп", "компі", "компютер", "ноутбук", "ноуті", "налаштування", "пропав",
          "пропала", "пропало", "зник", "зникло", "погано", "non", "funziona", "il", "la", "kein", "keine", "geht",
          "nicht", "funktioniert", "sin", "funciona", "pas", "de", "ne", "marche", "nie", "działa", "dziala", "brak"}


def area_of(q: str, strict: bool = True) -> str:
    """'no sound' → sound; 'принтер' → printer; '' when it is not about Windows itself. strict: only the area's
    words (and words like 'no', 'not working'); else any longer word of one area is enough."""
    words = norm(q).split()
    if not words or len(words) > 6:
        return ""
    text = f" {' '.join(words)} "
    for area, syns in AREAS.items():
        for s in (x for x in syns if " " in x):
            text = text.replace(f" {s} ", f" @{area} ")
    found, rest = set(), []
    for w in text.split():
        if w.startswith("@"):
            found.add(w[1:])
            continue
        hit = next((area for area, syns in AREAS.items()
                    if (w in syns and (strict or len(w) >= 4)) or
                    (len(w) >= 6 and any(len(s) >= 5 and w.startswith(s) for s in syns))), "")
        if hit:
            found.add(hit)
        elif w not in FILLER:
            rest.append(w)
    if len(found) != 1 or (strict and rest):
        return ""
    return found.pop()


def _pick_name(want: str, names: list[str]) -> str:
    q = str(want or "").strip().lower()
    if not names:
        raise WorkError("No printers are set up on this computer.")
    if not q:
        raise WorkError("Say which printer: " + "; ".join(names))
    exact = [n for n in names if n.lower() == q]
    hits = exact or [n for n in names if q in n.lower()]
    if len(hits) != 1:
        raise WorkError(("Several printers match: " if hits else "No printer is called that. Printers: ") +
                        "; ".join(hits or names))
    return hits[0]


def _churn(rel: str, is_dir: bool) -> bool:
    """Files a program changes itself while it runs (logs, caches, its settings): not a sign of anything."""
    low = rel.lower()
    parts = low.split("/")
    if any(x in ("saved", "logs", "log", "cache", "shadercache", "crashes", "crashdumps", "screenshots", "temp", "tmp",
                 "userdata", "_turned_off_by_lanterna", "thumbnails", "thumbs", "config_backups", "backups")
           or "cache" in x for x in parts):
        return True
    if not is_dir and "log" in parts[-1] and parts[-1].endswith(".txt"):
        return True
    return not is_dir and os.path.splitext(low)[1] in (".log", ".tmp", ".dmp", ".bak", ".old", ".etl", ".lock",
                                                       ".dat", ".sav", ".crash")


def _fit(sections: list[tuple[int, str, list[str]]], limit: int) -> str:
    """Sections (importance, title, lines) as one text that fits the limit: the least important lines go first."""
    secs = [[imp, title, [x for x in lines if x]] for imp, title, lines in sections if lines and any(lines)]

    def text() -> str:
        return "\n".join("\n".join(([s[1]] if s[1] else []) + s[2]) for s in secs if s[2])
    out = text()
    while len(out) > limit:
        cand = [s for s in secs if s[0] > 0 and s[2]]
        if not cand:
            break
        s = max(cand, key=lambda s: (s[0], len(s[2])))
        s[2].pop()
        out = text()
    return out[:limit]


# ---------------------------------------------------------------- settings files
def ini_set(text: str, key: str, value: str, section: str = "") -> tuple[str, str | None]:
    """key=value in an INI-like file, its spacing and line endings kept. → (new text, old value or None = added)."""
    lines = text.splitlines(keepends=True)
    nl = "\r\n" if "\r\n" in text else "\n"
    cur, hits, last_of = "", [], {}
    for i, line in enumerate(lines):
        s = line.strip()
        m = re.match(r"^\[(.+)\]$", s)
        if m:
            cur = m.group(1).strip()
            last_of[cur.lower()] = i
            continue
        if s:
            last_of[cur.lower()] = i
        if not s or s.startswith((";", "#", "//")) or "=" not in s:
            continue
        if s.split("=", 1)[0].strip().lower() == key.lower():
            hits.append((i, cur))
    if section:
        hits = [h for h in hits if h[1].lower() == section.lower()]
    elif len({h[1].lower() for h in hits}) > 1:
        raise WorkError(f"'{key}' is in several sections ({', '.join(sorted({h[1] for h in hits}))}): say which one.")
    if hits:
        old = None
        for i, _sec in hits:
            line = lines[i]
            body = line.rstrip("\r\n")
            end = line[len(body):]
            k, v = body.split("=", 1)
            pad = v[:len(v) - len(v.lstrip())]
            old = v.strip() if old is None else old
            lines[i] = f"{k}={pad}{value}{end}"
        return "".join(lines), old
    if not section:
        raise WorkError(f"There is no '{key}' in this file. To add it, give the [section] it belongs to.")
    if section.lower() in last_of:
        at = last_of[section.lower()]
        if not lines[at].endswith(("\n", "\r")):
            lines[at] += nl
        lines.insert(at + 1, f"{key}={value}{nl}")
        return "".join(lines), None
    body = "".join(lines)
    if body and not body.endswith(("\n", "\r")):
        body += nl
    return body + ("" if not body or body.endswith(nl * 2) else nl) + f"[{section}]{nl}{key}={value}{nl}", None


def _json_value(value: str):
    try:
        v = json.loads(value)
        if not isinstance(v, (dict, list)):
            return v
    except ValueError:
        pass
    return value


def json_set(text: str, key: str, value: str) -> tuple[str, str | None]:
    """A value in a JSON file by its dotted key ('graphics.vsync'); only where the key or its parent exists."""
    try:
        data = json.loads(text)
    except ValueError:
        raise WorkError("This file isn't plain JSON (it may have comments): Lanterna doesn't change it.") from None
    parts = [x for x in key.split(".") if x]
    node = data
    for x in parts[:-1]:
        if isinstance(node, dict) and x in node:
            node = node[x]
        elif isinstance(node, list) and x.isdigit() and int(x) < len(node):
            node = node[int(x)]
        else:
            raise WorkError(f"There is no '{x}' in this file.")
    last = parts[-1] if parts else ""
    if isinstance(node, list) and last.isdigit() and int(last) < len(node):
        old, node[int(last)] = json.dumps(node[int(last)], ensure_ascii=False), _json_value(value)
    elif isinstance(node, dict) and last:
        old = json.dumps(node[last], ensure_ascii=False) if last in node else None
        if old is not None and isinstance(node[last], (dict, list)):
            raise WorkError(f"'{key}' holds a group of settings: give one of the settings inside it.")
        node[last] = _json_value(value)
    else:
        raise WorkError(f"There is no '{key}' in this file.")
    m = re.search(r"\n([ \t]+)\S", text)
    indent = (m.group(1) if m.group(1).startswith("\t") else len(m.group(1))) if m else None
    out = json.dumps(data, ensure_ascii=False, indent=indent, separators=None if indent is not None else (",", ":"))
    if "\r\n" in text:
        out = out.replace("\n", "\r\n")
    if text.endswith(("\n", "\r\n")):
        out += "\r\n" if "\r\n" in text else "\n"
    return out, (old.strip('"') if old is not None else None)


_TOKEN = re.compile(r'"((?:[^"\\]|\\.)*)"|([{}])')


def vdf_tree(text: str) -> dict:
    """Steam's nested key-value files as dicts (keys in lower case)."""
    stack: list[dict] = [{}]
    key = None
    for m in _TOKEN.finditer(text):
        s, brace = m.group(1), m.group(2)
        if brace == "{":
            d: dict = {}
            stack[-1][(key or "").lower()] = d
            stack.append(d)
            key = None
        elif brace == "}":
            if len(stack) > 1:
                stack.pop()
            key = None
        elif key is None:
            key = s
        else:
            stack[-1][key.lower()] = s.replace("\\\\", "\\")
            key = None
    return stack[0]


# ---------------------------------------------------------------- tools
def fix_tools(fx: Fixer, limit: Callable[[], int] = lambda: 3800) -> list:
    if not (fx.win or fx.linux):
        return []
    from .tools import Tool, _obj
    win = fx.win
    s = {"type": "string"}
    prog = {"type": "string", "description": "the program's name as fix_check showed it"}
    place = {"type": "string", "description": "a place from fix_check: " + (
        "install, local, roaming, locallow, mygames, documents, saved, or a cache" if win else
        "install, config, data, cache, local, roaming, locallow, mygames, documents, saved, proton_log, or a cache")}
    path = {"type": "string", "description": "a path inside the place, as fix_check / fix_list show it"}
    why = {"type": "string", "description": "why, in a few words in the user's language (shown on the card)"}
    card = "The user confirms it on a card, so don't ask in text first."
    check = ("Find out why a game, a program or part of Windows doesn't work. Call it FIRST, before asking the user "
             "anything, when something won't start, crashes, freezes, goes black, shows an error, or there is no sound "
             "/ internet / printing / updates. It finds the program (Steam, Epic, GOG, Xbox, installed), looks through "
             "its folder for what is out of place (renamed folders, mods), reads its newest log and crash reports, and "
             "what Windows noted (crashes, the graphics driver, overlays). Only looks." if win else
             "Find out why a game, a program or part of the system doesn't work. Call it FIRST, before asking the user "
             "anything, when something won't start, crashes, freezes, goes black, shows an error, or there is no sound "
             "/ internet / printing / updates. It finds the program (Steam with Proton, Heroic, Lutris, Flatpak, "
             "installed apps), looks through its folder for what is out of place (renamed folders, mods), reads its "
             "newest log (Proton's too) and crash reports, and what the system noted (crashes, the graphics driver, "
             "running out of memory, overlays). Only looks.")
    tools = [
        Tool("fix_check", check,
             _obj({"what": {"type": "string", "description": "the program's name as installed, e.g. 'S.T.A.L.K.E.R. "
                                                             "2'; or sound, internet, printer, updates"},
                   "problem": {"type": "string", "description": "what is wrong, in a few words"}}, ["what"]),
             lambda what, problem="": fx.check(what, problem, limit=limit()), "🩺"),
        Tool("fix_list", "List a folder of a program from its fix_check places. Only looks.",
             _obj({"program": prog, "place": place, "folder": {"type": "string", "description": "a folder inside the "
                                                                                                "place; empty = its top"}},
                  ["program", "place"]),
             lambda program, place, folder="": fx.list_dir(program, place, folder, limit=limit()), "📂"),
        Tool("fix_read", "Read a text file of a program (a log, a settings file) from its fix_check places; find = only "
             "the lines with this text. Only looks.",
             _obj({"program": prog, "place": place, "path": path, "find": s}, ["program", "place", "path"]),
             lambda program, place, path, find="": fx.read(program, place, path, find, limit=limit()), "📄"),
        Tool("fix_rename", "Rename a file or folder of a program in its own folder: put back a name that was changed "
             "(e.g. Movies_old → Movies), or turn a file off by renaming it. The program must be closed. Undo puts "
             "the old name back. " + card,
             _obj({"program": prog, "place": place, "path": path, "new_name": {"type": "string", "description": "only "
                   "the new name, e.g. 'Movies'"}, "why": why}, ["program", "place", "path", "new_name"]),
             lambda program, place, path, new_name, why="": fx.propose_rename(program, place, path, new_name, why), "✏️"),
        Tool("fix_setting", "Change one setting in a program's settings file (.ini, .cfg, .json…): key = value, in "
             "[section] for an INI file with sections (Unreal: e.g. /Script/Engine.GameUserSettings). The old file is "
             "kept for Undo. The program must be closed. " + card,
             _obj({"program": prog, "place": place, "path": path, "key": s, "value": s,
                   "section": {"type": "string", "description": "the INI section, without brackets"}, "why": why},
                  ["program", "place", "path", "key", "value"]),
             lambda program, place, path, key, value, section="", why="": fx.propose_setting(
                 program, place, path, key, value, section, why), "⚙️"),
        Tool("fix_aside", "Turn off mods or injector files of a program (dxgi.dll, ReShade, .asi, ~mods…) by moving "
             "them into a folder next to them; Undo puts them back. The program must be closed. " + card,
             _obj({"program": prog, "place": place, "paths": {"type": "array", "items": s}, "why": why},
                  ["program", "place", "paths"]),
             lambda program, place, paths, why="": fx.propose_aside(program, place, paths, why), "📦"),
        Tool("fix_cache", ("Clear a cache: a place nvidia_cache / amd_cache / d3d_cache (program may be empty) or "
                           "steam_shaders, or a program's folder with 'cache' in its name. Into the Recycle Bin; it is "
                           "made again. " if win else
                           "Clear a cache: a place mesa_cache / nvidia_cache (program may be empty), steam_shaders, a "
                           "program's place cache, or a folder with 'cache' in its name. Into the Trash; it is made "
                           "again. ") + card,
             _obj({"program": prog, "place": place, "path": path, "why": why}, ["place"]),
             lambda place, program="", path="", why="": fx.propose_cache(program, place, path, why), "🧹"),
        Tool("fix_verify", "Steam's own check of a game's files: it downloads again what is missing or changed "
             "(renamed folders, replaced files). " + ("For Epic and GOG it says how the user does it. " if win else
                                                       "For other games and apps it says how the user does it. ") + card,
             _obj({"program": prog}, ["program"]), lambda program: fx.propose_verify(program), "🔍"),
    ]
    if win:
        tools.append(Tool(
            "fix_windows", "A fix in Windows: dns (clear the DNS cache), proxy_off (turn off a proxy that was left on), "
            "default_printer (make a printer the default), print_queue (remove stuck print jobs of a printer). " + card,
            _obj({"action": {"type": "string", "enum": ["dns", "proxy_off", "default_printer", "print_queue"]},
                  "printer": {"type": "string", "description": "the printer's name (for the printer actions)"}},
                 ["action"]),
            lambda action, printer="": fx.propose_windows(action, printer), "🛠"))
    else:
        tools.append(Tool(
            "fix_system", "A fix in the system: sound_output (send the sound to another output), sound_on (turn on a "
            "muted or very quiet output; name empty = the default one), mic_on (the same for a microphone), "
            "sound_restart (start the user's sound service again), proxy_off (turn off the desktop's proxy), "
            "default_printer (make a printer the default), print_queue (remove the user's stuck print jobs of a "
            "printer). " + card,
            _obj({"action": {"type": "string", "enum": ["sound_output", "sound_on", "mic_on", "sound_restart",
                                                        "proxy_off", "default_printer", "print_queue"]},
                  "name": {"type": "string", "description": "the output, the microphone or the printer, as fix_check "
                                                            "showed it"}},
                 ["action"]),
            lambda action, name="": fx.propose_system(action, name), "🛠"))
    return tools
