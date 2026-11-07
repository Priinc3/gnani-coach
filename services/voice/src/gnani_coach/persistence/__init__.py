"""Private history and recording storage — **Phase 06 owns this tree**.

This package holds the private side of the product:

* the **history** route: the caller's own session summaries;
* the **consent** route: recording retention is opt-in, and a withdrawal
  stops future retention without silently deleting what was retained;
* the **recording** routes: owner-only audio, with an expiry, a deletion
  that is a state rather than an erasure, and a fence against a late
  write.

The three accessors are the seam Phase 05 uses:

* :func:`get_session_store` — the metrics-only session store;
* :func:`get_recording_store` — the opt-in recording store;
* :func:`get_consent_store` — the consent state the two share.

Each returns ``None`` when storage is not configured, so a caller never
has to guess whether the storage is empty or missing. Phase 05 imports
them lazily, inside a ``try``/``except ImportError`` that treats a
missing name as ``None``.

Two promises this package keeps:

* **metrics-only is content-free.** A durable record holds numbers and
  controlled identifiers. A document that carries content is refused
  before the write, in the store itself.
* **a recording is private.** The bucket is private, the key is derived
  and never returned, and a recording that is not the caller's is
  answered exactly like a recording that does not exist.

Frozen contract: ``docs/contracts/seams.md``.
"""

from gnani_coach.persistence.router import router
from gnani_coach.persistence.stores import (
    get_consent_store,
    get_recording_store,
    get_session_store,
)

__all__ = [
    "get_consent_store",
    "get_recording_store",
    "get_session_store",
    "router",
]
