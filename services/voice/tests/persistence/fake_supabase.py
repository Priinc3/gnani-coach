"""Fakes for the Supabase HTTP API.

**Phase 06 owns this file.** The identity verifier and the Supabase
stores talk to Supabase over plain HTTPS, so the tests fake the HTTPS
and nothing else: the real client, the real request building and the
real error handling all run.

The fakes carry **obviously fake sentinels** only. There is no real key,
no real user and no real audio anywhere in this tree.
"""

from __future__ import annotations

import base64
import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qs, urlsplit

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


@dataclass
class FakeSupabase:
    """A fake Supabase project: the REST tables and the storage bucket.

    It is a **fake**, not a database: it understands the exact requests
    the stores make (the filters the owner scoping relies on, the
    upsert, the object put/get/delete) and nothing else.
    """

    tables: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    objects: dict[str, bytes] = field(default_factory=dict)
    requests: list[httpx.Request] = field(default_factory=list)
    #: Every row and every object, so a test can inspect what was stored.
    audit: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.tables.setdefault("session_metrics", [])
        self.tables.setdefault("recordings", [])
        self.tables.setdefault("consent", [])
        self.tables.setdefault("consent_events", [])

    # -- the request handler ---------------------------------------------

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        url = urlsplit(str(request.url))
        path = url.path
        params = {key: values[0] for key, values in parse_qs(url.query).items()}

        if path.startswith("/storage/v1/object/"):
            return self._storage(request, path)
        if path.startswith("/rest/v1/"):
            return self._rest(request, path, params)
        return httpx.Response(404, json={"error": "unknown_path"})

    def _storage(self, request: httpx.Request, path: str) -> httpx.Response:
        key = path[len("/storage/v1/object/") :]
        bucket, _, name = key.partition("/")
        if bucket != "recordings":
            return httpx.Response(404, json={"error": "no_such_bucket"})
        if request.method == "PUT":
            self.objects[name] = request.content
            self.audit.append({"kind": "upload", "name": name, "size": len(request.content)})
            return httpx.Response(200, json={"Key": name})
        if request.method == "GET":
            if name not in self.objects:
                return httpx.Response(404, json={"error": "not_found"})
            self.audit.append({"kind": "download", "name": name})
            return httpx.Response(200, content=self.objects[name])
        if request.method == "DELETE":
            self.objects.pop(name, None)
            self.audit.append({"kind": "delete", "name": name})
            return httpx.Response(200, json={})
        return httpx.Response(405, json={"error": "method_not_allowed"})

    def _rest(
        self, request: httpx.Request, path: str, params: dict[str, str]
    ) -> httpx.Response:
        table = path[len("/rest/v1/") :]
        rows = self.tables.setdefault(table, [])
        method = request.method

        if method == "GET":
            selected = [row for row in rows if self._matches(row, params)]
            order = params.get("order")
            if order:
                column, _, direction = order.partition(".")
                selected.sort(key=lambda row: str(row.get(column, "")), reverse=direction == "desc")
            limit = params.get("limit")
            if limit:
                selected = selected[: int(limit)]
            return httpx.Response(200, json=selected)

        if method == "POST":
            body = json.loads(request.content.decode("utf-8")) if request.content else {}
            if isinstance(body, list):
                rows.extend(body)
                return httpx.Response(201, json=body)
            conflict = params.get("on_conflict")
            if conflict:
                columns = [column.strip() for column in conflict.split(",")]
                existing = next(
                    (
                        row
                        for row in rows
                        if all(row.get(column) == body.get(column) for column in columns)
                    ),
                    None,
                )
                if existing is not None:
                    existing.update(body)
                    return httpx.Response(201, json=[existing])
            rows.append(body)
            self.audit.append({"kind": "insert", "table": table, "row": body})
            return httpx.Response(201, json=[body])

        if method == "PATCH":
            body = json.loads(request.content.decode("utf-8")) if request.content else {}
            selected = [row for row in rows if self._matches(row, params)]
            if not selected:
                return httpx.Response(200, json=[])
            for row in selected:
                row.update(body)
            self.audit.append({"kind": "update", "table": table, "row": body})
            return httpx.Response(200, json=selected)

        return httpx.Response(405, json={"error": "method_not_allowed"})

    @staticmethod
    def _matches(row: dict[str, Any], params: dict[str, str]) -> bool:
        """Whether a row matches the ``eq.`` filters of a request."""
        for key, value in params.items():
            if not key.endswith("_id") and key not in ("state", "user_id"):
                continue
            if not value.startswith("eq."):
                continue
            if str(row.get(key)) != value[3:]:
                return False
        return True


def new_recording_id() -> str:
    """A fresh fake recording id."""
    return f"rec_{uuid.uuid4().hex}"


def new_session_id() -> str:
    """A fresh fake session id."""
    return f"ses_{uuid.uuid4().hex[:12]}"
