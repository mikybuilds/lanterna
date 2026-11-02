"""Answers with the best available free model and moves to the next one when a limit is hit."""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Iterator

from . import keys
from .discovery import Candidate
from .providers import PROVIDERS, Client, ProviderError

# How long to skip a model (or a whole provider) after each kind of failure, in seconds.
COOLDOWN = {"rate": 60, "network": 30, "other": 60, "bad_request": 24 * 3600, "auth": 3600}


@dataclass
class Switched:
    """Yielded by Router.stream when it moves to another model (the UI shows a small note)."""
    to: Candidate
    reason: str


class AllFailed(ProviderError):
    pass


class Router:
    def __init__(self, candidates: list[Candidate], client_for: Callable[[str], Client] | None = None,
                 clock: Callable[[], float] = time.monotonic):
        self.candidates = list(candidates)
        self._clients: dict[str, Client] = {}
        self._client_for = client_for or self._default_client
        self._until: dict[tuple[str, str], float] = {}     # (provider, model or "*") -> skip until
        self._clock = clock
        self.current: Candidate | None = self.candidates[0] if self.candidates else None

    @staticmethod
    def _default_client(pid: str) -> Client:
        return Client(PROVIDERS[pid], keys.get_key(pid))

    def client(self, pid: str) -> Client:
        if pid not in self._clients:
            self._clients[pid] = self._client_for(pid)
        return self._clients[pid]

    def _cooling(self, c: Candidate) -> bool:
        now = self._clock()
        return self._until.get((c.provider, c.model), 0) > now or self._until.get((c.provider, "*"), 0) > now

    def _cool(self, c: Candidate, e: ProviderError) -> None:
        secs = e.retry_after if e.kind == "rate" and e.retry_after else COOLDOWN.get(e.kind, 60)
        whole_provider = e.kind in ("auth", "network")
        self._until[(c.provider, "*" if whole_provider else c.model)] = self._clock() + secs

    def available(self) -> list[Candidate]:
        return [c for c in self.candidates if not self._cooling(c)]

    def stream(self, messages: list[dict], need_vision: bool = False) -> Iterator[str | Switched]:
        last: ProviderError | None = None
        first = self.current
        for c in self.available():
            if need_vision and not c.vision:
                continue
            if c is not first:
                yield Switched(c, last.kind if last else "")
            self.current = c
            started = False
            try:
                client = self.client(c.provider)
                for piece in client.stream_chat(c.model, messages):
                    started = True
                    yield piece
                return
            except ProviderError as e:
                if started:                                 # the answer was half-way: don't mix two models
                    raise
                self._cool(c, e)
                last, first = e, None
        raise AllFailed(last.kind if last else "rate", str(last) if last else "No free model is available right now")

    def close(self) -> None:
        for c in self._clients.values():
            c.close()
