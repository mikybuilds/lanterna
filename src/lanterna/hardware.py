"""What this computer can run locally: graphics card memory, RAM and free disk, plus model advice.

Everything is read locally (nvidia-smi, system files, Windows API). Nothing is sent anywhere.
"""
from __future__ import annotations

import ctypes
import os
import re
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


@dataclass
class Hardware:
    gpu: str = ""                 # graphics card name ("" = none found)
    vram_gb: float = 0.0          # video memory; 0 = unknown or none
    vram_exact: bool = False      # True when read from nvidia-smi / sysfs, False when guessed
    ram_gb: float = 0.0
    disk_free_gb: float = 0.0
    os: str = sys.platform

    def to_dict(self) -> dict:
        return asdict(self)


def _run(cmd: list[str]) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=8, creationflags=_NO_WINDOW).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def _nvidia() -> tuple[str, float] | None:
    if not shutil.which("nvidia-smi"):
        return None
    out = _run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"]).strip()
    best = None
    for line in out.splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) == 2 and parts[1].replace(".", "", 1).isdigit():
            gb = round(float(parts[1]) / 1024, 1)
            if not best or gb > best[1]:
                best = (parts[0], gb)
    return best


def _amd_linux() -> tuple[str, float] | None:
    best = None
    for f in Path("/sys/class/drm").glob("card*/device/mem_info_vram_total"):
        try:
            gb = round(int(f.read_text().strip()) / 1024 ** 3, 1)
        except (OSError, ValueError):
            continue
        if not best or gb > best[1]:
            best = ("AMD Radeon", gb)
    return best


def _windows_gpu() -> tuple[str, float] | None:
    """Name from WMI; memory there is capped at 4 GB, so it is only a rough guess."""
    out = _run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                "Get-CimInstance Win32_VideoController | ForEach-Object { $_.Name + '|' + $_.AdapterRAM }"])
    best = None
    for line in out.splitlines():
        name, _, ram = line.strip().partition("|")
        if not name or re.search(r"basic display|remote|virtual", name, re.I):
            continue
        gb = round(int(ram) / 1024 ** 3, 1) if ram.strip().isdigit() else 0.0
        if not best or gb > best[1]:
            best = (name, gb)
    return best


def _linux_gpu_name() -> str:
    out = _run(["lspci"]) if shutil.which("lspci") else ""
    m = re.search(r"(?:VGA|3D)[^:]*:\s*(.+)", out)
    return m.group(1).strip() if m else ""


def _ram_gb() -> float:
    if sys.platform == "win32":
        class MEM(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
        m = MEM()
        m.dwLength = ctypes.sizeof(MEM)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)):
            return round(m.ullTotalPhys / 1024 ** 3, 1)
        return 0.0
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal:"):
                return round(int(line.split()[1]) / 1024 ** 2, 1)
    except OSError:
        pass
    try:
        return round(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 1024 ** 3, 1)
    except (ValueError, OSError, AttributeError):
        return 0.0


def detect() -> Hardware:
    hw = Hardware(ram_gb=_ram_gb())
    try:
        hw.disk_free_gb = round(shutil.disk_usage(Path.home()).free / 1024 ** 3, 1)
    except OSError:
        pass
    found = _nvidia()
    if found:
        hw.gpu, hw.vram_gb, hw.vram_exact = found[0], found[1], True
        return hw
    if sys.platform.startswith("linux"):
        amd = _amd_linux()
        if amd:
            hw.gpu, hw.vram_gb, hw.vram_exact = _linux_gpu_name() or amd[0], amd[1], True
        else:
            hw.gpu = _linux_gpu_name()
    elif sys.platform == "win32":
        win = _windows_gpu()
        if win:
            hw.gpu, hw.vram_gb = win
    return hw


# ------------------------------------------------------------------------------------------- advice
@dataclass
class ModelInfo:
    name: str                     # Ollama model name
    role: str                     # chat | think | vision
    size_gb: float                # download size (checked in the Ollama registry on 02.11.2026)
    min_vram: float               # comfortable on a card with this much video memory


CATALOG: list[ModelInfo] = [
    # tiny: runs on most laptops, even without a graphics card (slowly)
    ModelInfo("qwen3:1.7b", "chat", 1.36, 0),
    ModelInfo("qwen3:4b", "think", 2.5, 3),
    ModelInfo("qwen3-vl:4b-instruct", "vision", 3.34, 4),
    ModelInfo("gemma4:e2b-it-qat", "chat", 4.34, 4),
    # 6-8 GB cards
    ModelInfo("gemma4:e4b-it-qat", "chat", 6.15, 6),
    ModelInfo("qwen3:8b", "think", 5.23, 6),
    ModelInfo("qwen3-vl:8b-instruct", "vision", 6.19, 6),
    # 12 GB and more
    ModelInfo("gemma4:12b", "chat", 8.02, 11),
    ModelInfo("qwen3:14b", "think", 9.28, 11),
    # 20 GB and more
    ModelInfo("gemma4:26b", "chat", 18.73, 20),
    ModelInfo("qwen3:30b-a3b", "think", 18.56, 20),
    ModelInfo("qwen3-vl:30b-a3b-instruct", "vision", 19.64, 20),
]
ROLE_ORDER = {"chat": 0, "think": 1, "vision": 2}


@dataclass
class Advice:
    tier: str                     # none | small | medium | large | huge
    mode: str                     # suggested mode: cloud | auto | local
    models: list[ModelInfo] = field(default_factory=list)   # one per role, best that fits

    def to_dict(self) -> dict:
        return {"tier": self.tier, "mode": self.mode, "models": [asdict(m) for m in self.models]}


def advise(hw: Hardware) -> Advice:
    """Biggest model per role that fits the graphics card (or RAM when there is no card)."""
    v = hw.vram_gb
    if v >= 20:
        tier, mode = "huge", "local"
    elif v >= 11:
        tier, mode = "large", "local"
    elif v >= 6:
        tier, mode = "medium", "auto"
    elif v >= 3 or hw.ram_gb >= 16:
        tier, mode = "small", "auto"
    else:
        tier, mode = "none", "cloud"
    budget = v if v >= 3 else (3 if hw.ram_gb >= 16 else 0)     # CPU-only: tiny models with plenty of RAM
    picks: dict[str, ModelInfo] = {}
    for m in CATALOG:
        if budget and m.min_vram <= budget and (m.role not in picks or m.min_vram >= picks[m.role].min_vram):
            picks[m.role] = m
    if tier == "none" and hw.ram_gb >= 8:
        picks = {"chat": CATALOG[0]}                               # one tiny model to try, slowly
    return Advice(tier, mode, sorted(picks.values(), key=lambda m: ROLE_ORDER[m.role]))
