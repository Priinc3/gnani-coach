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

from gnani_coach.identity.verifier import (
    GuestIdentity,
    SupabaseIdentity,
    decode_claims,
    get_identity,
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
