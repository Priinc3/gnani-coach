"""A local fake Supabase: Auth + PostgREST + Storage over HTTP.

Phase 07's assembled suite boots the **real** voice service and the
**real** Next.js app. The only stand-in is the managed backend: this
module speaks enough of the Supabase HTTP surface for the real identity
verifier and the real Supabase stores to run unmodified.

It is a test double, nothing more. It is not evidence that Supabase
works; it is evidence that *our* code works against the documented
request shapes. Port ``8018`` is used by ``launcher.py`` and the browser
suite.

Security note: the JWT secret below is a **test fixture** for an
in-process fake. It is not a credential, it never leaves the test
process, and no real Supabase project uses it.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit

#: The test-only signing secret. The browser suite signs with the same
#: value (``constants.ts``).
TEST_JWT_SECRET = "phase07-assembled-test-secret"
#: The fake project's issuer, exactly as Supabase publishes it.
TEST_ISSUER = "http://127.0.0.1:8018/auth/v1"


def _b64url_decode(text: str) -> bytes:
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + padding)


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def decode_token(token: str) -> dict[str, Any] | None:
    """Verify the fake JWT and return its payload, or ``None``."""
    try:
        header_b64, payload_b64, signature_b64 = token.split(".")
        header = json.loads(_b64url_decode(header_b64))
        payload = json.loads(_b64url_decode(payload_b64))
        if header.get("alg") != "HS256":
            return None
        expected = hmac.new(
            TEST_JWT_SECRET.encode("utf-8"),
            f"{header_b64}.{payload_b64}".encode("ascii"),
            hashlib.sha256,
        ).digest()
        if not hmac.compare_digest(expected, _b64url_decode(signature_b64)):
            return None
        import time

        if int(payload.get("exp", 0)) <= int(time.time()):
            return None
        if payload.get("aud") != "authenticated":
            return None
        if payload.get("iss") != TEST_ISSUER:
            return None
        if not isinstance(payload.get("sub"), str) or not payload["sub"]:
            return None
        return payload
    except Exception:  # noqa: BLE001 - any malformed token is unverified
        return None


@dataclass
class FakeDatabase:
    """The fake tables and object store, with failure switches."""

    sessions: dict[tuple[str, str], dict[str, Any]] = field(default_factory=dict)
    consents: dict[str, dict[str, Any]] = field(default_factory=dict)
    consent_events: list[dict[str, Any]] = field(default_factory=list)
    recordings: dict[tuple[str, str], dict[str, Any]] = field(default_factory=dict)
    objects: dict[str, bytes] = field(default_factory=dict)
    failures: set[str] = field(default_factory=set)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def reset(self) -> None:
        with self.lock:
            self.sessions.clear()
            self.consents.clear()
            self.consent_events.clear()
            self.recordings.clear()
            self.objects.clear()
            self.failures.clear()

    def dump(self) -> dict[str, Any]:
        with self.lock:
            return {
                "sessions": [dict(row) for row in self.sessions.values()],
                "consents": [dict(row) for row in self.consents.values()],
                "consentEvents": [dict(row) for row in self.consent_events],
                "recordings": [dict(row) for row in self.recordings.values()],
                "objectKeys": sorted(self.objects),
            }


def _value(raw: str) -> str:
    """Decode one PostgREST filter operand."""
    return unquote(raw)


def _matches(row: dict[str, Any], params: dict[str, list[str]]) -> bool:
    """Apply the ``eq.`` filters this fake supports."""
    for key, values in params.items():
        if key in {"select", "order", "limit", "on_conflict"}:
            continue
        for value in values:
            if not value.startswith("eq."):
                continue
            if str(row.get(key)) != _value(value[3:]):
                return False
    return True


class _Handler(BaseHTTPRequestHandler):
    """One request against the fake backend."""

    server_version = "FakeSupabase/1.0"
    db: FakeDatabase  # set on the server class

    # -- plumbing ------------------------------------------------------
    def log_message(self, format: str, *args: object) -> None:  # noqa: A003
        # The assembled suite keeps its own log; the HTTP access log would
        # echo paths (which carry ids) and add noise.
        return

    def _read_body(self) -> bytes:
        length = int(self.headers.get("content-length", "0") or "0")
        return self.rfile.read(length) if length else b""

    def _json_body(self) -> Any:
        raw = self._read_body()
        if not raw:
            return None
        return json.loads(raw.decode("utf-8"))

    def _send(self, status: int, body: Any = None, *, content_type: str = "application/json") -> None:
        if body is None:
            payload = b""
        elif isinstance(body, bytes):
            payload = body
        else:
            payload = json.dumps(body).encode("utf-8")
        self.send_response(status)
        if payload:
            self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        if payload:
            self.wfile.write(payload)

    def _error(self, status: int, message: str) -> None:
        self._send(status, {"message": message})

    # -- routing -------------------------------------------------------
    def do_GET(self) -> None:  # noqa: N802
        self._route("GET")

    def do_POST(self) -> None:  # noqa: N802
        self._route("POST")

    def do_PATCH(self) -> None:  # noqa: N802
        self._route("PATCH")

    def do_DELETE(self) -> None:  # noqa: N802
        self._route("DELETE")

    def do_PUT(self) -> None:  # noqa: N802
        self._route("PUT")

    def _route(self, method: str) -> None:
        parts = urlsplit(self.path)
        path = parts.path
        params = parse_qs(parts.query)
        db: FakeDatabase = self.server.db  # type: ignore[attr-defined]

        if path.startswith("/__control__/"):
            self._control(method, path, db)
            return

        if path == "/auth/v1/user":
            if "auth" in db.failures:
                self._error(503, "auth unavailable")
                return
            token = self._bearer()
            payload = decode_token(token) if token else None
            if payload is None:
                self._error(401, "invalid token")
                return
            self._send(200, {
                "id": payload["sub"],
                "aud": "authenticated",
                "role": "authenticated",
                "email": "assembled@example.test",
                "app_metadata": {},
                "user_metadata": {},
            })
            return

        if path == "/auth/v1/logout":
            self._send(204)
            return

        if path == "/auth/v1/token":
            # A refresh is not needed by the suite (the token is minted
            # with a far-future expiry); answer it honestly all the same.
            self._error(400, "no refresh in the fake")
            return

        if path.startswith("/storage/v1/object/recordings/"):
            self._storage(method, path, db)
            return

        if path.startswith("/rest/v1/"):
            self._rest(method, path, params, db)
            return

        self._error(404, "not found")

    def _bearer(self) -> str | None:
        header = self.headers.get("authorization", "")
        scheme, _, token = header.partition(" ")
        return token.strip() if scheme.lower() == "bearer" else None

    # -- PostgREST -----------------------------------------------------
    def _table(self, path: str) -> str:
        return path[len("/rest/v1/"):].strip("/")

    def _rest(self, method: str, path: str, params: dict[str, list[str]], db: FakeDatabase) -> None:
        if "rest" in db.failures:
            self._error(503, "database unavailable")
            return
        table = self._table(path)
        with db.lock:
            if method == "GET":
                rows = self._rows(table, db)
                rows = [row for row in rows if _matches(row, params)]
                rows = self._ordered(rows, params)
                limit = params.get("limit")
                if limit and limit[0].isdigit():
                    rows = rows[: int(limit[0])]
                selected = self._select(rows, params)
                self._send(200, selected)
                return

            if method == "POST":
                body = self._json_body()
                if not isinstance(body, dict):
                    self._error(400, "a JSON object is required")
                    return
                self._insert(table, body, params, db)
                self._send(201, None)
                return

            if method == "PATCH":
                body = self._json_body()
                if not isinstance(body, dict):
                    self._error(400, "a JSON object is required")
                    return
                updated: list[dict[str, Any]] = []
                for key, row in self._keyed(table, db):
                    if _matches(row, params):
                        row.update(body)
                        updated.append(dict(row))
                self._send(200, updated)
                return

        self._error(405, "method not allowed")

    def _rows(self, table: str, db: FakeDatabase) -> list[dict[str, Any]]:
        if table == "session_metrics":
            return [dict(row) for row in db.sessions.values()]
        if table == "consent":
            return [dict(row) for row in db.consents.values()]
        if table == "consent_events":
            return [dict(row) for row in db.consent_events]
        if table == "recordings":
            return [dict(row) for row in db.recordings.values()]
        return []

    def _keyed(self, table: str, db: FakeDatabase):
        if table == "session_metrics":
            return list(db.sessions.items())
        if table == "consent":
            return list(db.consents.items())
        if table == "recordings":
            return list(db.recordings.items())
        return []

    def _insert(self, table: str, body: dict[str, Any], params: dict[str, list[str]], db: FakeDatabase) -> None:
        if table == "session_metrics":
            key = (str(body.get("user_id")), str(body.get("session_id")))
            db.sessions[key] = dict(body)
            return
        if table == "consent":
            key = str(body.get("user_id"))
            db.consents[key] = dict(body)
            return
        if table == "consent_events":
            db.consent_events.append(dict(body))
            return
        if table == "recordings":
            key = (str(body.get("user_id")), str(body.get("recording_id")))
            db.recordings[key] = dict(body)
            return

    @staticmethod
    def _ordered(rows: list[dict[str, Any]], params: dict[str, list[str]]) -> list[dict[str, Any]]:
        order = params.get("order")
        if not order:
            return rows
        field, _, direction = order[0].partition(".")
        return sorted(
            rows,
            key=lambda row: str(row.get(field) or ""),
            reverse=direction.lower().startswith("desc"),
        )

    @staticmethod
    def _select(rows: list[dict[str, Any]], params: dict[str, list[str]]) -> list[dict[str, Any]]:
        select = params.get("select")
        if not select or select[0].strip() in {"*", ""}:
            return rows
        keys = [key.strip() for key in select[0].split(",") if key.strip()]
        return [{key: row.get(key) for key in keys} for row in rows]

    # -- Storage -------------------------------------------------------
    def _storage(self, method: str, path: str, db: FakeDatabase) -> None:
        if "storage" in db.failures:
            self._error(503, "storage unavailable")
            return
        key = unquote(path[len("/storage/v1/object/recordings/"):])
        with db.lock:
            if method == "PUT":
                body = self._read_body()
                db.objects[key] = body
                self._send(200, {"Key": key})
                return
            if method == "GET":
                data = db.objects.get(key)
                if data is None:
                    self._error(404, "object not found")
                    return
                self._send(200, data, content_type="audio/wav")
                return
            if method == "DELETE":
                db.objects.pop(key, None)
                self._send(200, {"message": "removed"})
                return
        self._error(405, "method not allowed")

    # -- control -------------------------------------------------------
    def _control(self, method: str, path: str, db: FakeDatabase) -> None:
        action = path[len("/__control__/"):]
        if action == "reset":
            db.reset()
            self._send(200, {"ok": True})
            return
        if action == "dump":
            self._send(200, db.dump())
            return
        if action == "fail":
            body = self._json_body()
            if not isinstance(body, dict):
                self._error(400, "a JSON object is required")
                return
            with db.lock:
                for name in ("rest", "storage", "auth"):
                    if body.get(name):
                        db.failures.add(name)
                    else:
                        db.failures.discard(name)
            self._send(200, {"failures": sorted(db.failures)})
            return
        self._error(404, "not found")


def start_fake_supabase(db: FakeDatabase, *, host: str = "127.0.0.1", port: int = 8018) -> ThreadingHTTPServer:
    """Start the fake backend in a background thread and return it."""
    server = ThreadingHTTPServer((host, port), _Handler)
    server.db = db  # type: ignore[attr-defined]
    thread = threading.Thread(target=server.serve_forever, name="fake-supabase", daemon=True)
    thread.start()
    return server
