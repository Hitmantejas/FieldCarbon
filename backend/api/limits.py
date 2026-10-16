"""Limits on the ask endpoint: every question costs ~19k Gemini tokens, so a public URL needs a ceiling.

Kept in memory per Cloud Run instance (a restart resets them); the real daily ceiling is the daily cap times the
number of instances, so deploy the service with a small --max-instances.
FIELDCARBON_ASK_PER_MINUTE: questions one caller may ask in any 60 seconds (default 5).
FIELDCARBON_ASK_PER_DAY: questions the instance answers per UTC day, all callers together (default 200).
FIELDCARBON_GEN_PER_MINUTE / FIELDCARBON_GEN_PER_DAY: the same for texts Gemini writes outside the chat (client statement,
diagnosis, briefing, delivery-note upload); defaults 6 and 300. One limiter shared by those endpoints.
"""
from __future__ import annotations

import os
import threading
import time
from collections import deque
from datetime import datetime, timezone

WINDOW_S = 60.0


def _positive_int(name: str, default: int) -> int:
    raw = os.environ.get(name, str(default))
    try:
        value = int(raw)
    except ValueError:
        value = 0
    if value < 1:
        raise ValueError(f"{name} must be a whole number of at least 1, got {raw!r}")
    return value


class Refused(Exception):
    def __init__(self, message: str, retry_after_s: int):
        super().__init__(message)
        self.message = message
        self.retry_after_s = retry_after_s


# (daily limit reached, per-minute limit reached with {n}): what a refused caller reads.
ASK_MESSAGES = ("The analyst has answered its daily limit of questions. Try again tomorrow.",
                "You can ask {n} questions a minute. Please wait a moment and try again.")


class AskLimiter:
    def __init__(self, per_minute: int, per_day: int, clock=time.time, messages: tuple[str, str] = ASK_MESSAGES):
        self.per_minute, self.per_day, self.clock, self.messages = per_minute, per_day, clock, messages
        self._lock = threading.Lock()
        self._recent: dict[str, deque[float]] = {}
        self._day: str | None = None
        self._today = 0

    @classmethod
    def from_env(cls, clock=time.time, minute_var: str = "FIELDCARBON_ASK_PER_MINUTE", day_var: str = "FIELDCARBON_ASK_PER_DAY",
                 defaults: tuple[int, int] = (5, 200), messages: tuple[str, str] = ASK_MESSAGES) -> AskLimiter:
        """The analyst's limits by default; the Gemini-written texts pass their own variable names (backend/api/fleet.py)."""
        return cls(_positive_int(minute_var, defaults[0]), _positive_int(day_var, defaults[1]), clock, messages)

    def admit(self, caller: str) -> None:
        """Count one question from this caller, or raise Refused if a limit is reached."""
        with self._lock:
            now = self.clock()
            moment = datetime.fromtimestamp(now, timezone.utc)
            day = moment.strftime("%Y-%m-%d")
            if day != self._day:
                self._day, self._today, self._recent = day, 0, {}
            if self._today >= self.per_day:
                midnight = moment.replace(hour=0, minute=0, second=0, microsecond=0).timestamp() + 86400
                raise Refused(self.messages[0], max(1, int(midnight - now) + 1))
            recent = self._recent.setdefault(caller, deque())
            while recent and recent[0] <= now - WINDOW_S:
                recent.popleft()
            if len(recent) >= self.per_minute:
                raise Refused(self.messages[1].format(n=self.per_minute), max(1, int(recent[0] + WINDOW_S - now) + 1))
            recent.append(now)
            self._today += 1


def caller_of(forwarded_for: str | None, host: str | None) -> str:
    """Cloud Run appends the address it saw to X-Forwarded-For, so the last entry is the one a caller cannot forge."""
    if forwarded_for:
        last = forwarded_for.split(",")[-1].strip()
        if last:
            return last
    return host or "unknown"
