"""Content-free observability helpers (Phase 07).

The only thing here is the latency registry behind ``/health/latency``.
It stores numbers: a turn's end-of-turn to first-coach-audio gap, in
milliseconds. It never stores a transcript, a reply, a user id or a
session id, and every log line built from it carries numbers only.
"""

from gnani_coach.observability.latency import registry as latency

__all__ = ["latency"]
