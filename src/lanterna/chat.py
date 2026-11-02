"""One conversation: history + system prompt + the model that answers."""
from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import Iterator

from . import soul
from .providers import Client

MAX_HISTORY = 30          # messages kept in context (older ones are dropped)


def system_prompt(name: str = "", now: datetime.datetime | None = None, extra: str = "") -> str:
    now = now or datetime.datetime.now()
    parts = [
        soul.persona(name),
        f"\nNow: {now:%A, %d %B %Y, %H:%M} (user's local time).",
        "Formatting: plain text or light Markdown. Use code blocks only for code.",
    ]
    if extra:
        parts.append(extra)
    return "\n".join(parts)


@dataclass
class Conversation:
    client: Client
    model: str
    user_name: str = ""
    history: list[dict] = field(default_factory=list)
    last_reply: str = ""

    def _messages(self, text: str) -> list[dict]:
        hint = soul.mood_hint(text)
        sys = system_prompt(self.user_name, extra=hint)
        return [{"role": "system", "content": sys}, *self.history[-MAX_HISTORY:], {"role": "user", "content": text}]

    def ask(self, text: str) -> Iterator[str]:
        """Streams the raw reply; when finished, the cleaned reply is stored in history and self.last_reply."""
        pieces: list[str] = []
        for p in self.client.stream_chat(self.model, self._messages(text)):
            pieces.append(p)
            yield p
        reply = soul.humanize("".join(pieces).strip(), self.last_reply)
        self.history += [{"role": "user", "content": text}, {"role": "assistant", "content": reply}]
        self.last_reply = reply
