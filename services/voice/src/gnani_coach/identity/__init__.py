"""Identity — **Phase 06 owns this tree**.

The identity port turns a caller's credential into a user id, or into
nothing. A guest is a supported state: a guest call works, a guest simply
has no saved history and no retained audio.

The exported name is ``get_identity``. It is used as a FastAPI
dependency, so replacing the implementation is a one-line change in
``gnani_coach.main``:

.. code-block:: python

    from gnani_coach.identity import get_identity

    @router.get("/api/history")
    async def history(identity: IdentityPort = Depends(get_identity)): ...

What this package guarantees:

* an absent, malformed, expired, wrong-audience, wrong-issuer or unknown
  token yields ``None`` — a guest — and never raises;
* a token is never logged and never stored: the verification cache is
  keyed by a SHA-256 hash of it;
* without a Supabase URL and a key the implementation **fails closed** and
  returns the anonymous guest.

The implementation lives in :mod:`gnani_coach.identity.verifier`; the
reasoning and the sources are documented there.

Frozen contract: ``docs/contracts/seams.md``.
"""

from __future__ import annotations

import os

from gnani_coach.identity.verifier import (
    GuestIdentity,
    SupabaseIdentity,
    decode_claims,
    get_identity as _get_supabase_identity,
    get_identity_for,
    publishable_key_from_environment,
    reset_identity_cache,
    subject_from_user_id,
    token_fingerprint,
    user_id_from_subject,
)
from gnani_coach.ports.identity import IdentityPort

__all__ = [
    "GuestIdentity",
    "IdentityPort",
    "SupabaseIdentity",
    "decode_claims",
    "get_identity",
    "get_identity_for",
    "publishable_key_from_environment",
    "reset_identity_cache",
    "subject_from_user_id",
    "token_fingerprint",
    "user_id_from_subject",
]


def get_identity() -> IdentityPort:
    """The identity port for the current process.

    ``SPEAKING_COACH_STORAGE_BACKEND=sqlite`` selects the local
    email/password provider, which shares the embedded database with the
    stores. Any other value keeps today's behaviour: the Supabase
    verifier when it is configured, and the anonymous guest otherwise.

    The local provider **fails closed**: a database that cannot be opened
    returns the guest identity, never an exception on the call path.

    The local import is deliberately lazy: the persistence package
    imports this package at module load, so a top-level import here would
    close an import cycle.
    """
    backend = os.environ.get("SPEAKING_COACH_STORAGE_BACKEND", "").strip().lower()
    if backend == "sqlite":
        from gnani_coach.identity.local import local_identity_from_environment

        return local_identity_from_environment()
    return _get_supabase_identity()
