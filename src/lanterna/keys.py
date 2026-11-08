"""API keys live in the system's secure store (Windows Credential Manager, GNOME Keyring, macOS Keychain).

An environment variable (e.g. GROQ_API_KEY) wins over the stored key — handy for servers and CI.
Keys are never written to settings, logs or chat history.
"""
from __future__ import annotations

import os

import keyring
from keyring.errors import KeyringError

SERVICE = "Lanterna"


def env_name(provider: str) -> str:
    return f"{provider.upper()}_API_KEY"


def get_key(provider: str) -> str | None:
    env = os.getenv(env_name(provider)) or os.getenv(f"LANTERNA_{env_name(provider)}")
    if env:
        return env.strip()
    try:
        return keyring.get_password(SERVICE, provider)
    except KeyringError:
        return None


def stored_key(provider: str) -> str:
    """Only the key in the vault (an environment variable is not synced to other devices)."""
    try:
        return keyring.get_password(SERVICE, provider) or ""
    except KeyringError:
        return ""


def set_key(provider: str, key: str) -> None:
    keyring.set_password(SERVICE, provider, key.strip())


def delete_key(provider: str) -> None:
    try:
        keyring.delete_password(SERVICE, provider)
    except KeyringError:
        pass


# Windows keeps at most 2,560 bytes (1,280 characters) per entry; sign-in tokens can be longer, so a long value
# is kept in pieces: the first entry says how many ("~3~" + piece 1), the others are "<name>~2", "<name>~3".
_PIECE = 1000


def set_long(name: str, value: str) -> None:
    pieces = [value[i:i + _PIECE] for i in range(0, len(value), _PIECE)] or [""]
    old = _pieces(name)
    if len(pieces) == 1 and not value.startswith("~"):
        keyring.set_password(SERVICE, name, value)
    else:
        for i, p in enumerate(pieces[1:], 2):
            keyring.set_password(SERVICE, f"{name}~{i}", p)
        keyring.set_password(SERVICE, name, f"~{len(pieces)}~" + pieces[0])
    for i in range(len(pieces) + 1, old + 1):              # a shorter value: drop the pieces left over
        delete_key(f"{name}~{i}")


def _pieces(name: str) -> int:
    first = stored_key(name)
    if first.startswith("~") and first[1:first.find("~", 1)].isdigit():
        return int(first[1:first.find("~", 1)])
    return 1 if first else 0


def get_long(name: str) -> str:
    first = stored_key(name)
    n = _pieces(name)
    if n <= 1 and not first.startswith("~"):
        return first
    rest = [stored_key(f"{name}~{i}") for i in range(2, n + 1)]
    return first[first.find("~", 1) + 1:] + "".join(rest)


def delete_long(name: str) -> None:
    for i in range(2, _pieces(name) + 1):
        delete_key(f"{name}~{i}")
    delete_key(name)


def mask(key: str | None) -> str:
    """For display only: 'gsk_…9f2a'."""
    if not key:
        return "—"
    return key[:4] + "…" + key[-4:] if len(key) > 12 else "…"
