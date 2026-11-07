"""Coarse, per-process resource guards.

Two guards live here and nowhere else:

* :class:`RateLimiter` — a fixed-window counter for one key (the caller's
  address). It is used by the HTTP middleware and, separately, by the
  WebSocket handshake. A refused request is answered with the frozen
  ``rate_limited`` error shape; a refused handshake is closed with 1008
  before it is accepted.

The counter is deliberately in-process. A deployment with several worker
processes multiplies the effective budget by the worker count; that is
stated in ``docs/operations/RUNBOOK.md`` and in the REPORT rather than
hidden. A distributed limiter needs shared state (Redis or the edge) and
is outside this phase's dependency budget.

Sources for the rule: the OWASP WebSocket Security Cheat Sheet asks for
rate limiting and connection caps
(<https://cheatsheetseries.owasp.org/cheatsheets/WebSocket_Security_Cheat_Sheet.html>,
checked 2026-10-23), and the OWASP ASVS v5 requirements 2.4.1/2.4.2 ask
for anti-automation and resource limits
(<https://owasp.org/www-project-application-security-verification-standard/>,
checked 2026-10-23). The window is a guard, not a security boundary.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from collections.abc import Callable


class RateLimiter:
    """A fixed-window counter, one bucket per key.

    ``per_minute`` is the number of admitted operations in a 60-second
    window. The clock is injectable so the tests do not sleep.
    """

    def __init__(
        self,
        per_minute: int,
        *,
        window_seconds: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._limit = max(1, int(per_minute))
        self._window = float(window_seconds)
        self._clock = clock
        self._buckets: dict[str, tuple[float, int]] = defaultdict(lambda: (0.0, 0))
        self._lock = threading.Lock()

    @property
    def limit(self) -> int:
        return self._limit

    def allow(self, key: str) -> bool:
        """Admit one operation for ``key``, or refuse it."""
        now = self._clock()
        with self._lock:
            started_at, count = self._buckets[key]
            if now - started_at >= self._window:
                self._buckets[key] = (now, 1)
                return True
            if count >= self._limit:
                return False
            self._buckets[key] = (started_at, count + 1)
            return True

    def reset(self) -> None:
        """Forget every bucket. For tests only."""
        with self._lock:
            self._buckets.clear()


#: The process-wide HTTP limiter. ``main`` configures it at startup.
http_limiter = RateLimiter(120)

#: The process-wide WebSocket-handshake limiter. ``router`` configures it
#: at startup from the same settings object.
handshake_limiter = RateLimiter(120)


def configure(settings: object) -> None:
    """Apply the settings to both process-wide limiters."""
    http_limit = int(getattr(settings, "http_requests_per_minute", 120))
    ws_limit = int(getattr(settings, "ws_handshakes_per_minute", 120))
    global http_limiter, handshake_limiter
    http_limiter = RateLimiter(http_limit)
    handshake_limiter = RateLimiter(ws_limit)


__all__ = [
    "RateLimiter",
    "configure",
    "handshake_limiter",
    "http_limiter",
]
