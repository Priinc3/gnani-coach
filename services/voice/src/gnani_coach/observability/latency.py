"""The end-of-turn to first-coach-audio latency registry.

One number is measured per completed turn:

    end of the learner's turn  ->  first coach audio byte sent

It is measured on the service's monotonic clock, so it includes the
reasoning call and the synthesiser's first chunk and excludes the
learner's own speech and the network. It is a **service-side** number,
not the learner's perceived latency.

The registry keeps the last :data:`WINDOW` numbers only. ``snapshot()``
returns ``{"turns": n, "p50Ms": x, "p95Ms": x}`` with nearest-rank
percentiles; an empty window answers ``0`` for both percentiles rather
than guessing. Nothing here stores or returns content.

The values are per process. A multi-worker deployment reports one
worker's window; ``docs/operations/RUNBOOK.md`` states the caveat.
"""

from __future__ import annotations

import threading
from collections import deque

#: How many recent turns the percentiles cover.
WINDOW = 200


class LatencyRegistry:
    """A bounded, thread-safe store of per-turn latency numbers."""

    def __init__(self, window: int = WINDOW) -> None:
        self._values: deque[float] = deque(maxlen=max(1, int(window)))
        self._lock = threading.Lock()

    def record(self, milliseconds: float) -> int:
        """Record one measured turn and return the rounded value."""
        value = max(0, int(round(float(milliseconds))))
        with self._lock:
            self._values.append(float(value))
        return value

    def snapshot(self) -> dict[str, int | float]:
        """The content-free percentile view of the window."""
        with self._lock:
            values = sorted(self._values)
        if not values:
            return {"turns": 0, "p50Ms": 0, "p95Ms": 0}
        return {
            "turns": len(values),
            "p50Ms": _nearest_rank(values, 50),
            "p95Ms": _nearest_rank(values, 95),
        }

    def reset(self) -> None:
        """Forget every value. For tests only."""
        with self._lock:
            self._values.clear()


def _nearest_rank(values: list[float], percentile: int) -> int:
    """The nearest-rank percentile of a sorted, non-empty list."""
    rank = max(1, int(round(percentile / 100.0 * len(values) + 0.4999)))
    rank = min(rank, len(values))
    return int(round(values[rank - 1]))


#: The process-wide registry.
registry = LatencyRegistry()

__all__ = ["WINDOW", "LatencyRegistry", "registry"]
