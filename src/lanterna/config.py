"""User settings: a small JSON file in the per-user config folder. Keys never go here (see keys.py)."""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

from platformdirs import user_config_dir, user_data_dir

APP = "Lanterna"


def config_dir() -> Path:
    p = Path(os.getenv("LANTERNA_HOME") or user_config_dir(APP, appauthor=False))
    p.mkdir(parents=True, exist_ok=True)
    return p


def data_dir() -> Path:
    p = Path(os.getenv("LANTERNA_HOME") or user_data_dir(APP, appauthor=False))
    p.mkdir(parents=True, exist_ok=True)
    return p


@dataclass
class Settings:
    lang: str = "en"                       # interface language: en | uk | it
    name: str = ""                         # how the assistant calls the user
    mode: str = "cloud"                    # cloud | local | auto
    provider: str = ""                     # first provider chosen at setup (groq | gemini | …)
    models: dict = field(default_factory=dict)   # preferred model per provider
    onboarded: bool = False

    @classmethod
    def load(cls) -> "Settings":
        f = config_dir() / "settings.json"
        try:
            raw = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cls()
        known = {k: v for k, v in raw.items() if k in cls.__dataclass_fields__}
        return cls(**known)

    def save(self) -> None:
        f = config_dir() / "settings.json"
        tmp = f.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(f)
