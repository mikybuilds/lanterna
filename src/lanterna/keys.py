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


def set_key(provider: str, key: str) -> None:
    keyring.set_password(SERVICE, provider, key.strip())


def delete_key(provider: str) -> None:
    try:
        keyring.delete_password(SERVICE, provider)
    except KeyringError:
        pass


def mask(key: str | None) -> str:
    """For display only: 'gsk_…9f2a'."""
    if not key:
        return "—"
    return key[:4] + "…" + key[-4:] if len(key) > 12 else "…"
