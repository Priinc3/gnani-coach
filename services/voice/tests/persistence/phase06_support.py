"""The shared names of the Phase 06 persistence tests.

**Phase 06 owns this file.** It is a plain module (not a ``conftest``)
because a test module that does ``from conftest import ...`` picks up
*whichever* ``conftest`` was imported first, and this repository has
several of them. A uniquely named module has no such ambiguity.

Nothing here reaches the network: the Supabase HTTP API is faked, the
tokens are obviously fake sentinels and the user ids are opaque.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi.testclient import TestClient

from gnani_coach.persistence.stores.memory import (
    InMemoryConsentStore,
    InMemoryRecordingStore,
    InMemorySessionStore,
)

#: The bearer tokens of the two accounts. They are sentinels.
TOKEN_A = "fake-bearer-token-for-user-a"
TOKEN_B = "fake-bearer-token-for-user-b"

#: The opaque user ids of the two accounts.
USER_A = f"usr_{'a' * 32}"
USER_B = f"usr_{'b' * 32}"

#: The subject (the Auth-server user id) behind each account.
SUBJECT_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
SUBJECT_B = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"


class FakeIdentity:
    """An identity that knows two fake tokens."""

    def __init__(self, tokens: dict[str, str]) -> None:
        self.tokens = tokens

    async def verify_token(self, token: str | None) -> str | None:
        return self.tokens.get(token or "")

    async def current_user(self) -> str | None:
        return None


@dataclass
class Harness:
    """Everything a persistence test needs."""

    client: TestClient
    consent: InMemoryConsentStore
    sessions: InMemorySessionStore
    recordings: InMemoryRecordingStore

    def auth(self, token: str) -> dict[str, str]:
        """The Authorization header of one account."""
        return {"Authorization": f"Bearer {token}"}
