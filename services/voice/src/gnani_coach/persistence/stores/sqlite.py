"""The SQLite-backed implementations of the storage and identity stores.

This module is the whole backend of the small EC2 deployment: one embedded
database file and one recordings directory. It deliberately uses only the
Python standard library (``sqlite3``, ``hashlib``, ``secrets``, ``hmac``),
so it adds no dependency and no lockfile change.

Design rules
------------

* **One connection, one lock.** SQLite is happiest with a single writer.
  Every call is moved off the event loop with ``asyncio.to_thread`` and
  serialised by a ``threading.Lock``.
* **Fail closed.** If the database cannot be opened the accessors return
  ``None``; a caller then behaves like a guest. The call path never
  crashes because storage is missing.
* **Small memory.** ``cache_size=-2000`` (about 2 MB), ``mmap_size=0``,
  ``journal_mode=WAL``, ``busy_timeout=5000`` and ``synchronous=NORMAL``
  keep the resident footprint low on a 2 GB box.
* **Parameterised SQL only.** No query is built by string formatting.
* **Owner isolation.** Every read and delete filters by ``user_id``; a
  foreign id and a missing id are indistinguishable to the caller.
* **The metrics-only guard and the consent re-check** are the same as the
  in-memory reference implementation.

Sources
-------

* Python ``sqlite3`` documentation, including the threading and PRAGMA
  notes: https://docs.python.org/3/library/sqlite3.html (checked 2026-11-07)
* SQLite WAL and memory PRAGMAs:
  https://www.sqlite.org/pragma.html (checked 2026-11-07)
* OWASP password-storage guidance (cited in ``identity/local.py``):
  https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shutil
import sqlite3
import threading
import uuid
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from gnani_coach.persistence.consent import (
    CONSENT_VERSION,
    ConsentState,
    isoformat,
    utc_now,
)
from gnani_coach.persistence.errors import (
    ConsentRequiredError,
    ContentRejectedError,
    RecordingFencedError,
    RecordingTooLargeError,
    StorageQuotaExceededError,
    StorageUnavailableError,
)
from gnani_coach.persistence.metrics import assert_metrics_only
from gnani_coach.ports.recording_store import RecordingRef
from gnani_coach.ports.session_store import SessionSummary
from gnani_coach.ports.types import RecordingId, SessionId, UserId

logger = logging.getLogger(__name__)

#: The default directory the service owns.
DEFAULT_DATA_DIR = "/var/lib/gnani-coach"

#: The database file inside the data directory.
DB_FILENAME = "gnani-coach.sqlite3"

#: The recordings directory inside the data directory.
RECORDINGS_DIRNAME = "recordings"

#: The current schema version, stored in ``PRAGMA user_version``.
SCHEMA_VERSION = 1

#: How long a retained recording lives.
RETENTION_DAYS = 30

#: Per-file and per-user recording caps.
MAX_RECORDING_BYTES = 10 * 1024 * 1024
MAX_USER_RECORDING_BYTES = 200 * 1024 * 1024

#: The validated id shapes. A path is built only from an id that matches.
_USER_ID_PATTERN = re.compile(r"^usr_[a-z0-9]{6,40}$")
_RECORDING_ID_PATTERN = re.compile(r"^rec_[a-z0-9]{6,40}$")

#: The schema. It mirrors ``supabase/migrations`` but uses SQLite types.
_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS auth_tokens (
    token_hash TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    revoked_at TEXT NULL
);

CREATE INDEX IF NOT EXISTS auth_tokens_user ON auth_tokens(user_id);

CREATE TABLE IF NOT EXISTS consent (
    user_id TEXT PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
    consent_version TEXT NOT NULL,
    recording_retention_granted INTEGER NOT NULL DEFAULT 0,
    recording_retention_granted_at TEXT NULL,
    recording_retention_withdrawn_at TEXT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS consent_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    consent_version TEXT NOT NULL,
    recording_retention_granted INTEGER NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS session_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    session_id TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    practice_language_id TEXT NOT NULL,
    scenario_id TEXT NOT NULL,
    recording_id TEXT NULL,
    turn_count INTEGER NOT NULL DEFAULT 0 CHECK (turn_count >= 0),
    speaking_time_ms INTEGER NOT NULL DEFAULT 0 CHECK (speaking_time_ms >= 0),
    metrics_version TEXT NOT NULL DEFAULT '0.1',
    document TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (user_id, session_id)
);

CREATE INDEX IF NOT EXISTS session_metrics_user
    ON session_metrics(user_id, recorded_at DESC);

CREATE TABLE IF NOT EXISTS recordings (
    recording_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    session_id TEXT NOT NULL,
    owner_ref TEXT NOT NULL,
    created_at TEXT NOT NULL,
    duration_ms INTEGER NOT NULL CHECK (duration_ms >= 0),
    size_bytes INTEGER NOT NULL CHECK (size_bytes >= 0),
    content_type TEXT NOT NULL DEFAULT 'audio/wav',
    consent_version TEXT NOT NULL,
    consent_granted_at TEXT NULL,
    state TEXT NOT NULL DEFAULT 'retained'
        CHECK (state IN ('retained', 'deleted')),
    expires_at TEXT NOT NULL,
    deleted_at TEXT NULL,
    CHECK (
        (state = 'deleted' AND deleted_at IS NOT NULL)
        OR (state = 'retained' AND deleted_at IS NULL)
    )
);

CREATE INDEX IF NOT EXISTS recordings_user
    ON recordings(user_id, state);
CREATE INDEX IF NOT EXISTS recordings_session
    ON recordings(user_id, session_id, state);
"""


def _parse_timestamp(value: str) -> datetime | None:
    """Parse an RFC 3339 timestamp, returning ``None`` when unreadable."""
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=utc_now().tzinfo)
    return parsed


class SQLiteDatabase:
    """One SQLite file, one connection and one lock.

    The object is process-wide. It owns the schema, the user/token tables
    used by the local identity provider, and the recordings directory.
    """

    def __init__(self, data_dir: str | Path) -> None:
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        os.chmod(self.data_dir, 0o700)
        self.recordings_dir = self.data_dir / RECORDINGS_DIRNAME
        self.recordings_dir.mkdir(parents=True, exist_ok=True)
        os.chmod(self.recordings_dir, 0o700)

        self.path = self.data_dir / DB_FILENAME
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(
            str(self.path), check_same_thread=False, isolation_level=None
        )
        os.chmod(self.path, 0o600)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA busy_timeout=5000")
            self._conn.execute("PRAGMA cache_size=-2000")
            self._conn.execute("PRAGMA mmap_size=0")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._migrate_locked()

    # -- connection plumbing ---------------------------------------------

    def _migrate_locked(self) -> None:
        version = int(self._conn.execute("PRAGMA user_version").fetchone()[0])
        if version >= SCHEMA_VERSION:
            return
        self._conn.executescript(_SCHEMA)
        self._conn.execute(f"PRAGMA user_version={SCHEMA_VERSION}")

    def _call_locked(
        self, function: Callable[..., Any], args: tuple[Any, ...], kwargs: dict[str, Any]
    ) -> Any:
        with self._lock:
            return function(self._conn, *args, **kwargs)

    async def call(
        self, function: Callable[..., Any], *args: Any, **kwargs: Any
    ) -> Any:
        """Run one blocking database function off the event loop."""
        return await asyncio.to_thread(
            self._call_locked, function, args, kwargs
        )

    def close(self) -> None:
        """Close the connection. Used by tests."""
        with self._lock:
            self._conn.close()

    # -- local identity tables -------------------------------------------

    async def create_user(
        self, user_id: UserId, email: str, password_hash: str, created_at: str
    ) -> bool:
        """Insert one local account. ``False`` when the email is taken."""
        return await self.call(
            _create_user, user_id, email, password_hash, created_at
        )

    async def get_user_by_email(self, email: str) -> dict[str, Any] | None:
        return await self.call(_get_user_by_email, email)

    async def get_user(self, user_id: UserId) -> dict[str, Any] | None:
        return await self.call(_get_user, user_id)

    async def insert_token(
        self,
        token_hash: str,
        user_id: UserId,
        created_at: str,
        expires_at: str,
    ) -> None:
        await self.call(
            _insert_token, token_hash, user_id, created_at, expires_at
        )

    async def get_token(self, token_hash: str) -> dict[str, Any] | None:
        return await self.call(_get_token, token_hash)

    async def revoke_token(self, token_hash: str, revoked_at: str) -> bool:
        return await self.call(_revoke_token, token_hash, revoked_at)

    async def delete_user(self, user_id: UserId) -> bool:
        """Delete every row and every recording file of one account."""
        return await asyncio.to_thread(self._delete_user_locked, user_id)

    def _delete_user_locked(self, user_id: UserId) -> bool:
        if not _USER_ID_PATTERN.match(user_id):
            return False
        with self._lock:
            folder = self.recordings_dir / user_id
            if folder.is_dir() and folder.parent == self.recordings_dir:
                shutil.rmtree(folder, ignore_errors=True)
            cursor = self._conn.execute(
                "DELETE FROM users WHERE user_id = ?", (user_id,)
            )
            return cursor.rowcount > 0


def _create_user(
    conn: sqlite3.Connection,
    user_id: UserId,
    email: str,
    password_hash: str,
    created_at: str,
) -> bool:
    try:
        conn.execute(
            "INSERT INTO users (user_id, email, password_hash, created_at) "
            "VALUES (?, ?, ?, ?)",
            (user_id, email, password_hash, created_at),
        )
    except sqlite3.IntegrityError:
        return False
    return True


def _get_user_by_email(
    conn: sqlite3.Connection, email: str
) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT user_id, email, password_hash, created_at "
        "FROM users WHERE email = ? LIMIT 1",
        (email,),
    ).fetchone()
    return dict(row) if row is not None else None


def _get_user(conn: sqlite3.Connection, user_id: UserId) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT user_id, email, password_hash, created_at "
        "FROM users WHERE user_id = ? LIMIT 1",
        (user_id,),
    ).fetchone()
    return dict(row) if row is not None else None


def _insert_token(
    conn: sqlite3.Connection,
    token_hash: str,
    user_id: UserId,
    created_at: str,
    expires_at: str,
) -> None:
    conn.execute(
        "INSERT INTO auth_tokens "
        "(token_hash, user_id, created_at, expires_at, revoked_at) "
        "VALUES (?, ?, ?, ?, NULL)",
        (token_hash, user_id, created_at, expires_at),
    )


def _get_token(
    conn: sqlite3.Connection, token_hash: str
) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT token_hash, user_id, created_at, expires_at, revoked_at "
        "FROM auth_tokens WHERE token_hash = ? LIMIT 1",
        (token_hash,),
    ).fetchone()
    return dict(row) if row is not None else None


def _revoke_token(
    conn: sqlite3.Connection, token_hash: str, revoked_at: str
) -> bool:
    cursor = conn.execute(
        "UPDATE auth_tokens SET revoked_at = ? "
        "WHERE token_hash = ? AND revoked_at IS NULL",
        (revoked_at, token_hash),
    )
    return cursor.rowcount > 0


# ---------------------------------------------------------------------------
# consent
# ---------------------------------------------------------------------------


class SQLiteConsentStore:
    """The consent state, in the ``consent`` table."""

    def __init__(
        self, database: SQLiteDatabase, *, clock: Callable[[], datetime] = utc_now
    ) -> None:
        self._db = database
        self._clock = clock

    async def get_state(self, user_id: UserId) -> ConsentState:
        row = await self._db.call(_select_consent, user_id)
        if row is None:
            return ConsentState.not_granted()
        return ConsentState(
            consent_version=str(row.get("consent_version") or CONSENT_VERSION),
            recording_retention_granted=bool(row.get("recording_retention_granted")),
            recording_retention_granted_at=(
                str(row["recording_retention_granted_at"])
                if row.get("recording_retention_granted_at")
                else None
            ),
            updated_at=str(row.get("updated_at") or isoformat(self._clock())),
        )

    async def set_state(
        self, user_id: UserId, *, consent_version: str, granted: bool
    ) -> ConsentState:
        if not _USER_ID_PATTERN.match(user_id):
            raise StorageUnavailableError("the owner of a consent write is not known")
        moment = self._clock()
        timestamp = isoformat(moment)
        await self._db.call(
            _write_consent,
            user_id,
            consent_version,
            bool(granted),
            timestamp,
            None if granted else timestamp,
            timestamp,
        )
        return ConsentState(
            consent_version=consent_version,
            recording_retention_granted=granted,
            recording_retention_granted_at=timestamp if granted else None,
            updated_at=timestamp,
        )


def _select_consent(
    conn: sqlite3.Connection, user_id: UserId
) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT consent_version, recording_retention_granted, "
        "recording_retention_granted_at, updated_at "
        "FROM consent WHERE user_id = ? LIMIT 1",
        (user_id,),
    ).fetchone()
    return dict(row) if row is not None else None


def _write_consent(
    conn: sqlite3.Connection,
    user_id: UserId,
    consent_version: str,
    granted: bool,
    granted_at: str | None,
    withdrawn_at: str | None,
    updated_at: str,
) -> None:
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute(
            "INSERT INTO consent (user_id, consent_version, "
            "recording_retention_granted, recording_retention_granted_at, "
            "recording_retention_withdrawn_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET "
            "consent_version = excluded.consent_version, "
            "recording_retention_granted = excluded.recording_retention_granted, "
            "recording_retention_granted_at = excluded.recording_retention_granted_at, "
            "recording_retention_withdrawn_at = "
            "excluded.recording_retention_withdrawn_at, "
            "updated_at = excluded.updated_at",
            (
                user_id,
                consent_version,
                1 if granted else 0,
                granted_at,
                withdrawn_at,
                updated_at,
            ),
        )
        conn.execute(
            "INSERT INTO consent_events "
            "(user_id, consent_version, recording_retention_granted, created_at) "
            "VALUES (?, ?, ?, ?)",
            (user_id, consent_version, 1 if granted else 0, updated_at),
        )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise


# ---------------------------------------------------------------------------
# sessions
# ---------------------------------------------------------------------------


class SQLiteSessionStore:
    """The metrics-only session store, in the ``session_metrics`` table."""

    def __init__(
        self,
        database: SQLiteDatabase,
        *,
        owner_resolver: Callable[[], Any] | None = None,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._db = database
        self._owner_resolver = owner_resolver or _current_owner
        self._clock = clock

    async def save_metrics(self, record: dict) -> None:
        assert_metrics_only(record)
        owner = await self._owner_resolver()
        if owner is None:
            return
        await self.save_metrics_for(owner, record)

    async def save_metrics_for(self, user_id: UserId, record: dict) -> None:
        assert_metrics_only(record)
        session_id = record.get("sessionId")
        if not isinstance(session_id, str) or not session_id:
            raise ContentRejectedError("a durable record needs a session id")
        if not _USER_ID_PATTERN.match(user_id):
            raise StorageUnavailableError("the owner of a record is not known")
        totals = record.get("totals") if isinstance(record.get("totals"), dict) else {}
        recording_id = record.get("recordingId")
        document = json.dumps(record, separators=(",", ":"), sort_keys=True)
        await self._db.call(
            _write_session,
            user_id,
            session_id,
            str(record.get("recordedAt") or isoformat(self._clock())),
            str(record.get("practiceLanguageId") or ""),
            str(record.get("scenarioId") or ""),
            recording_id if isinstance(recording_id, str) else None,
            int(totals.get("turnCount", 0) or 0),
            int(totals.get("speakingTimeMs", 0) or 0),
            str(record.get("metricsVersion") or "0.1"),
            document,
            isoformat(self._clock()),
        )

    async def list_sessions(
        self, user_id: UserId, *, limit: int = 20
    ) -> list[SessionSummary]:
        if not _USER_ID_PATTERN.match(user_id):
            return []
        rows = await self._db.call(_list_sessions, user_id, max(0, int(limit)))
        return [_summary_from_row(row) for row in rows]

    async def get_session(self, user_id: UserId, session_id: SessionId) -> dict | None:
        if not _USER_ID_PATTERN.match(user_id):
            return None
        document = await self._db.call(_get_session_document, user_id, session_id)
        return document if isinstance(document, dict) else None


async def _current_owner() -> UserId | None:
    from gnani_coach.identity import get_identity

    identity = get_identity()
    return await identity.current_user()


def _write_session(
    conn: sqlite3.Connection,
    user_id: UserId,
    session_id: str,
    recorded_at: str,
    practice_language_id: str,
    scenario_id: str,
    recording_id: str | None,
    turn_count: int,
    speaking_time_ms: int,
    metrics_version: str,
    document: str,
    created_at: str,
) -> None:
    conn.execute(
        "INSERT INTO session_metrics "
        "(user_id, session_id, recorded_at, practice_language_id, scenario_id, "
        "recording_id, turn_count, speaking_time_ms, metrics_version, document, "
        "created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(user_id, session_id) DO UPDATE SET "
        "recorded_at = excluded.recorded_at, "
        "practice_language_id = excluded.practice_language_id, "
        "scenario_id = excluded.scenario_id, "
        "recording_id = excluded.recording_id, "
        "turn_count = excluded.turn_count, "
        "speaking_time_ms = excluded.speaking_time_ms, "
        "metrics_version = excluded.metrics_version, "
        "document = excluded.document",
        (
            user_id,
            session_id,
            recorded_at,
            practice_language_id,
            scenario_id,
            recording_id,
            turn_count,
            speaking_time_ms,
            metrics_version,
            document,
            created_at,
        ),
    )


def _list_sessions(
    conn: sqlite3.Connection, user_id: UserId, limit: int
) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT session_id, recorded_at, practice_language_id, scenario_id, "
        "recording_id, turn_count, speaking_time_ms "
        "FROM session_metrics WHERE user_id = ? "
        "ORDER BY recorded_at DESC LIMIT ?",
        (user_id, limit),
    ).fetchall()
    return [dict(row) for row in rows]


def _get_session_document(
    conn: sqlite3.Connection, user_id: UserId, session_id: str
) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT document FROM session_metrics "
        "WHERE user_id = ? AND session_id = ? LIMIT 1",
        (user_id, session_id),
    ).fetchone()
    if row is None:
        return None
    try:
        document = json.loads(str(row["document"]))
    except (TypeError, ValueError):
        return None
    return document if isinstance(document, dict) else None


def _summary_from_row(row: dict[str, Any]) -> SessionSummary:
    recorded_at = row.get("recorded_at")
    recording_id = row.get("recording_id")
    return SessionSummary(
        session_id=str(row.get("session_id") or ""),
        recorded_at=str(recorded_at) if recorded_at else "",
        practice_language_id=str(row.get("practice_language_id") or ""),
        scenario_id=str(row.get("scenario_id") or ""),
        recording_id=str(recording_id) if recording_id else None,
        turn_count=int(row.get("turn_count") or 0),
        speaking_time_ms=int(row.get("speaking_time_ms") or 0),
    )


# ---------------------------------------------------------------------------
# recordings
# ---------------------------------------------------------------------------


class SQLiteRecordingStore:
    """The opt-in recording store: a row in SQLite and a WAV file on disk.

    The fence is the ``state`` column: a deleted recording keeps its row,
    so a late job cannot recreate it after a restart or from another
    request.
    """

    def __init__(
        self,
        database: SQLiteDatabase,
        consent_store: SQLiteConsentStore,
        *,
        clock: Callable[[], datetime] = utc_now,
        retention_days: int = RETENTION_DAYS,
    ) -> None:
        self._db = database
        self._consent = consent_store
        self._clock = clock
        self._retention = timedelta(days=retention_days)
        self._root = database.recordings_dir

    @property
    def consent_store(self) -> SQLiteConsentStore:
        return self._consent

    async def save_recording(
        self,
        user_id: UserId,
        session_id: SessionId,
        audio: bytes,
        *,
        duration_ms: int,
        content_type: str = "audio/wav",
        recording_id: RecordingId | None = None,
    ) -> RecordingRef:
        state = await self._consent.get_state(user_id)
        if not state.recording_retention_granted:
            raise ConsentRequiredError(
                "recording retention is not granted for this account"
            )
        if not _USER_ID_PATTERN.match(user_id):
            raise StorageUnavailableError("the owner of a recording is not known")

        identifier = str(recording_id) if recording_id else f"rec_{uuid.uuid4().hex}"
        if not _RECORDING_ID_PATTERN.match(identifier):
            raise ContentRejectedError(
                "a recording id must be a controlled identifier"
            )

        payload = bytes(audio)
        if len(payload) > MAX_RECORDING_BYTES:
            raise RecordingTooLargeError("a recording is larger than the file cap")

        moment = self._clock()
        expires_at = moment + self._retention
        target = self._root / user_id / f"{identifier}.wav"
        reference = await self._db.call(
            self._save_locked,
            user_id,
            str(session_id),
            identifier,
            payload,
            int(duration_ms),
            content_type,
            state.consent_version,
            state.recording_retention_granted_at,
            isoformat(moment),
            isoformat(expires_at),
            isoformat(moment),
            target,
        )
        return reference

    def _save_locked(
        self,
        conn: sqlite3.Connection,
        user_id: UserId,
        session_id: str,
        identifier: str,
        payload: bytes,
        duration_ms: int,
        content_type: str,
        consent_version: str,
        consent_granted_at: str | None,
        created_at: str,
        expires_at: str,
        now: str,
        target: Path,
    ) -> RecordingRef:
        written = False
        conn.execute("BEGIN IMMEDIATE")
        try:
            self._sweep_expired(conn, now)
            self._assert_not_fenced(conn, user_id, session_id, identifier)
            used = conn.execute(
                "SELECT COALESCE(SUM(size_bytes), 0) FROM recordings "
                "WHERE user_id = ? AND state = 'retained'",
                (user_id,),
            ).fetchone()[0]
            if int(used) + len(payload) > MAX_USER_RECORDING_BYTES:
                raise StorageQuotaExceededError(
                    "this account has reached its recording quota"
                )

            conn.execute(
                "INSERT INTO recordings "
                "(recording_id, user_id, session_id, owner_ref, created_at, "
                "duration_ms, size_bytes, content_type, consent_version, "
                "consent_granted_at, state, expires_at, deleted_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'retained', ?, NULL)",
                (
                    identifier,
                    user_id,
                    session_id,
                    user_id,
                    created_at,
                    duration_ms,
                    len(payload),
                    content_type,
                    consent_version,
                    consent_granted_at,
                    expires_at,
                ),
            )
            self._write_file(target, payload)
            written = True
            conn.execute("COMMIT")
        except Exception:
            try:
                conn.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            if written:
                self._remove_file(target)
            raise

        return RecordingRef(
            recording_id=identifier,
            session_id=session_id,
            created_at=created_at,
            duration_ms=duration_ms,
            size_bytes=len(payload),
            content_type=content_type,
        )

    def _sweep_expired(self, conn: sqlite3.Connection, now: str) -> None:
        rows = conn.execute(
            "SELECT recording_id, user_id, expires_at FROM recordings "
            "WHERE state = 'retained' AND expires_at <= ?",
            (now,),
        ).fetchall()
        for row in rows:
            conn.execute(
                "UPDATE recordings SET state = 'deleted', deleted_at = ? "
                "WHERE recording_id = ? AND state = 'retained'",
                (row["expires_at"], row["recording_id"]),
            )
            self._remove_file(
                self._root / str(row["user_id"]) / f"{row['recording_id']}.wav"
            )

    def _assert_not_fenced(
        self,
        conn: sqlite3.Connection,
        user_id: UserId,
        session_id: str,
        identifier: str,
    ) -> None:
        existing = conn.execute(
            "SELECT user_id, state FROM recordings WHERE recording_id = ? LIMIT 1",
            (identifier,),
        ).fetchone()
        if existing is not None:
            if existing["state"] == "deleted":
                raise RecordingFencedError(
                    "the recording was deleted and may not be recreated"
                )
            raise RecordingFencedError("a recording with this id already exists")

        deleted = conn.execute(
            "SELECT 1 FROM recordings WHERE user_id = ? AND session_id = ? "
            "AND state = 'deleted' LIMIT 1",
            (user_id, session_id),
        ).fetchone()
        if deleted is not None:
            raise RecordingFencedError(
                "the recording of this session was deleted and may not be recreated"
            )

    async def get_recording(
        self, user_id: UserId, recording_id: RecordingId
    ) -> bytes | None:
        if not _USER_ID_PATTERN.match(user_id) or not _RECORDING_ID_PATTERN.match(
            str(recording_id)
        ):
            return None
        return await self._db.call(
            self._get_locked, user_id, str(recording_id), isoformat(self._clock())
        )

    def _get_locked(
        self, conn: sqlite3.Connection, user_id: UserId, recording_id: str, now: str
    ) -> bytes | None:
        row = conn.execute(
            "SELECT session_id, state, expires_at FROM recordings "
            "WHERE recording_id = ? AND user_id = ? LIMIT 1",
            (recording_id, user_id),
        ).fetchone()
        if row is None or row["state"] != "retained":
            return None
        expires_at = _parse_timestamp(str(row["expires_at"]))
        if expires_at is not None and expires_at <= self._clock():
            conn.execute(
                "UPDATE recordings SET state = 'deleted', deleted_at = ? "
                "WHERE recording_id = ? AND user_id = ? AND state = 'retained'",
                (row["expires_at"], recording_id, user_id),
            )
            self._remove_file(self._root / user_id / f"{recording_id}.wav")
            return None
        target = self._root / user_id / f"{recording_id}.wav"
        try:
            return target.read_bytes()
        except OSError:
            return None

    async def delete_recording(
        self, user_id: UserId, recording_id: RecordingId
    ) -> bool:
        if not _USER_ID_PATTERN.match(user_id) or not _RECORDING_ID_PATTERN.match(
            str(recording_id)
        ):
            return False
        deleted = await self._db.call(
            self._delete_locked,
            user_id,
            str(recording_id),
            isoformat(self._clock()),
        )
        return bool(deleted)

    def _delete_locked(
        self,
        conn: sqlite3.Connection,
        user_id: UserId,
        recording_id: str,
        deleted_at: str,
    ) -> bool:
        cursor = conn.execute(
            "UPDATE recordings SET state = 'deleted', deleted_at = ? "
            "WHERE recording_id = ? AND user_id = ? AND state = 'retained'",
            (deleted_at, recording_id, user_id),
        )
        if cursor.rowcount <= 0:
            return False
        self._remove_file(self._root / user_id / f"{recording_id}.wav")
        return True

    def _write_file(self, target: Path, payload: bytes) -> None:
        folder = target.parent
        folder.mkdir(parents=True, exist_ok=True)
        os.chmod(folder, 0o700)
        # ``x`` refuses an existing path, so a retry cannot overwrite a
        # file that belongs to another row.
        with open(target, "xb") as handle:
            os.chmod(target, 0o600)
            handle.write(payload)

    def _remove_file(self, target: Path) -> None:
        try:
            target.unlink()
        except FileNotFoundError:
            return
        except OSError:
            logger.warning("a recording file could not be removed")


# ---------------------------------------------------------------------------
# the process-wide database
# ---------------------------------------------------------------------------


_instances: dict[str, SQLiteDatabase] = {}
_instance_lock = threading.Lock()


def database_from_environment() -> SQLiteDatabase | None:
    """Open the configured database, or ``None`` when it cannot be opened.

    **Fail closed.** A missing or unreadable database turns storage off;
    the caller then behaves like a guest. The log line names no path and
    no content.
    """
    raw = os.environ.get("SPEAKING_COACH_DATA_DIR", "").strip()
    data_dir = raw or DEFAULT_DATA_DIR
    with _instance_lock:
        existing = _instances.get(data_dir)
        if existing is not None:
            return existing
        try:
            database = SQLiteDatabase(data_dir)
        except Exception:
            logger.warning(
                "sqlite storage could not be opened; continuing without storage"
            )
            return None
        _instances[data_dir] = database
        return database


def reset_sqlite() -> None:
    """Close and forget every database. Used by tests."""
    with _instance_lock:
        for database in _instances.values():
            try:
                database.close()
            except Exception:
                pass
        _instances.clear()


__all__ = [
    "DB_FILENAME",
    "DEFAULT_DATA_DIR",
    "MAX_RECORDING_BYTES",
    "MAX_USER_RECORDING_BYTES",
    "RETENTION_DAYS",
    "SCHEMA_VERSION",
    "SQLiteConsentStore",
    "SQLiteDatabase",
    "SQLiteRecordingStore",
    "SQLiteSessionStore",
    "database_from_environment",
    "reset_sqlite",
]
