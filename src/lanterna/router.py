"""Answers with the best available free model and moves to the next one when a limit is hit."""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Iterator

from . import keys
from .discovery import Candidate
from .providers import PROVIDERS, Client, ProviderError, ToolCalls

# How long to skip a model (or a whole provider) after each kind of failure, in seconds.
MAX_WAIT = 12            # seconds worth waiting for a rate limit instead of failing
COOLDOWN = {"rate": 60, "network": 30, "timeout": 15 * 60, "dropped": 30, "other": 60, "bad_request": 24 * 3600,
            "auth": 3600}


@dataclass
class Switched:
    """Yielded by Router.stream when it moves to another model (the UI shows a small note)."""
    to: Candidate
    reason: str


class AllFailed(ProviderError):
    pass


class Router:
    def __init__(self, candidates: list[Candidate], client_for: Callable[[str], Client] | None = None,
                 clock: Callable[[], float] = time.monotonic, sleep: Callable[[float], None] = time.sleep):
        self.candidates = list(candidates)
        self._clients: dict[str, Client] = {}
        self._client_for = client_for or self._default_client
        self._until: dict[tuple[str, str], float] = {}     # (provider, model or "*") -> skip until
        self.no_tools = {(c.provider, c.model) for c in candidates if not c.tools}   # models that can't use tools
        self._clock = clock
        self._sleep = sleep
        self._short_wait: float | None = None
        self.current: Candidate | None = self.candidates[0] if self.candidates else None

    @staticmethod
    def _default_client(pid: str) -> Client:
        p = PROVIDERS[pid]
        if p.local:                                          # loading a model into memory can take a while
            return Client(p, None, timeout=300)
        return Client(p, keys.get_key(pid))

    def client(self, pid: str) -> Client:
        if pid not in self._clients:
            self._clients[pid] = self._client_for(pid)
        return self._clients[pid]

    def _cooling(self, c: Candidate) -> bool:
        now = self._clock()
        if self._until.get((c.provider, c.model), 0) > now or self._until.get((c.provider, "*"), 0) > now:
            return True
        from .limits import TRACKER                      # a daily limit seen earlier, maybe before a restart
        return TRACKER.rest_until(c.provider, c.model) > time.time()

    def _cool(self, c: Candidate, e: ProviderError) -> None:
        secs = e.retry_after if e.kind == "rate" and e.retry_after else COOLDOWN.get(e.kind, 60)
        whole_provider = e.kind in ("auth", "network")
        self._until[(c.provider, "*" if whole_provider else c.model)] = self._clock() + secs

    def resting(self) -> dict[str, float]:
        """"provider/model" -> seconds until it is tried again (after a limit or an error)."""
        now, out = self._clock(), {}
        for c in self.candidates:
            left = max(self._until.get((c.provider, c.model), 0), self._until.get((c.provider, "*"), 0)) - now
            if left > 0:
                out[f"{c.provider}/{c.model}"] = left
        return out

    def available(self) -> list[Candidate]:
        return [c for c in self.candidates if not self._cooling(c)]

    def has_cloud(self) -> bool:
        return any(not PROVIDERS[c.provider].local for c in self.candidates)

    def stream(self, messages: list[dict], need_vision: bool = False,
               tools: list[dict] | None = None, tool_choice: str = "auto",
               prefer_cloud: bool = False) -> Iterator["str | Switched | ToolCalls"]:
        """Best model first; on a limit, the next one. If every model is briefly rate-limited
        (the service says "try again in a few seconds"), wait once and try again.
        prefer_cloud: try online models before local ones (auto mode, hard question)."""
        self._short_wait = None
        self._prefer_cloud = prefer_cloud
        try:
            yield from self._stream_once(messages, need_vision, tools, tool_choice)
            return
        except AllFailed as e:
            wait = self._short_wait
            if e.kind != "rate" or wait is None or wait > MAX_WAIT:
                raise
        self._sleep(wait + 0.5)
        now = self._clock()
        for k, until in list(self._until.items()):
            if until - now <= COOLDOWN["rate"] + 1:          # forget the short rate cooldowns, keep the rest
                del self._until[k]
        yield from self._stream_once(messages, need_vision, tools, tool_choice)

    def _stream_once(self, messages: list[dict], need_vision: bool, tools: list[dict] | None,
                     tool_choice: str) -> Iterator["str | Switched | ToolCalls"]:
        if need_vision and not any(c.vision for c in self.candidates):
            raise ProviderError("vision", "No model that understands photos")
        last: ProviderError | None = None
        order = self.available()
        if getattr(self, "_prefer_cloud", False):
            order.sort(key=lambda c: PROVIDERS[c.provider].local)      # stable: cloud models keep their ranking
        if need_vision:
            order.sort(key=lambda c: not c.photo)                       # the local photo model first
        # a model already known to be resting (limit reached earlier) is skipped quietly, without a "switched" note
        first = self.current if self.current in order else next((c for c in order if c.vision or not need_vision), None)
        for c in order:
            if need_vision and not c.vision:
                continue
            if c is not first:
                yield Switched(c, last.kind if last else "")
            self.current = c
            started = False
            use_tools = tools if tools and (c.provider, c.model) not in self.no_tools else None
            try:
                client = self.client(c.provider)
                attempts = [(use_tools, tool_choice)] if use_tools else [(None, "auto")]
                if use_tools and tool_choice != "auto":
                    attempts.append((use_tools, "auto"))          # some services refuse "required"
                if use_tools:
                    attempts.append((None, "auto"))               # and some models refuse tools at all
                for i, (tl, choice) in enumerate(attempts):
                    try:
                        for piece in client.stream_chat(c.model, messages, tools=tl, tool_choice=choice):
                            started = True
                            yield piece
                        break
                    except ProviderError as e:
                        if started or e.kind != "bad_request" or i == len(attempts) - 1:
                            raise
                        if attempts[i + 1][0] is None:
                            self.no_tools.add((c.provider, c.model))
                return
            except ProviderError as e:
                if started:                                 # the answer was half-way: don't mix two models
                    raise
                if e.kind == "bad_request" and any(m.get("role") == "tool" for m in messages):
                    # refused in the middle of a tool round (often history another model left): not the model's fault
                    self._cool(c, ProviderError("other", str(e), e.status))
                else:
                    self._cool(c, e)
                if e.kind == "rate" and e.retry_after is not None:
                    self._short_wait = e.retry_after if self._short_wait is None else min(self._short_wait, e.retry_after)
                last, first = e, None
        raise AllFailed(last.kind if last else "rate", str(last) if last else "No free model is available right now")

    def supports_tools(self) -> bool:
        c = self.current
        return bool(c) and (c.provider, c.model) not in self.no_tools

    def close(self) -> None:
        for c in self._clients.values():
            c.close()
