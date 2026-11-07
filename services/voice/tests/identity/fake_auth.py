"""The fake Supabase Auth server.

**Phase 06 owns this file.** It carries obviously fake sentinels only:
there is no real credential, no real user and no real network anywhere
in this tree.
"""

from __future__ import annotations

import base64
import json
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

#: The fake project URL every fake token is issued by.
FAKE_SUPABASE_URL = "https://fake-project.supabase.co"

#: An obviously fake key. It is not a credential and never leaves this
#: tree.
FAKE_SERVICE_ROLE_KEY = "sb_fake_service_role_key_for_tests_only"

#: An obviously fake publishable key.
FAKE_PUBLISHABLE_KEY = "sb_fake_publishable_key_for_tests_only"


def _b64url(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def make_token(
    *,
    subject: str = "11111111-1111-4111-8111-111111111111",
    expires_at: int | None = None,
    audience: str = "authenticated",
    issuer: str = f"{FAKE_SUPABASE_URL}/auth/v1",
    signature: str = "ZmFrZS1zaWduYXR1cmU",
) -> str:
    """Build a token for the fake Auth server.

    The signature is fake on purpose: the point of the tests is that the
    verifier never trusts the payload, so a forged payload must not
    produce a user id.
    """
    header = _b64url({"alg": "HS256", "typ": "JWT"})
    payload = _b64url(
        {
            "sub": subject,
            "exp": expires_at if expires_at is not None else int(time.time()) + 3600,
            "aud": audience,
            "iss": issuer,
            "role": "authenticated",
        }
    )
    return f"{header}.{payload}.{signature}"


@dataclass
class FakeAuthServer:
    """A fake Supabase Auth server.

    Only the tokens it was told about are valid. Every call is recorded,
    so a test can assert that a token was *not* sent to the network.
    """

    valid_tokens: dict[str, str] = field(default_factory=dict)
    calls: list[httpx.Request] = field(default_factory=list)
    status_code: int = 200

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        token = request.headers.get("authorization", "")
        token = token[7:].strip() if token.lower().startswith("bearer ") else ""
        subject = self.valid_tokens.get(token)
        if subject is None:
            return httpx.Response(401, json={"error": "invalid_token"})
        if self.status_code != 200:
            return httpx.Response(self.status_code, json={"error": "nope"})
        return httpx.Response(200, json={"id": subject})

    @property
    def call_count(self) -> int:
        return len(self.calls)
