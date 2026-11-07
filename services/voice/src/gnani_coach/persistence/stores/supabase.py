"""The Supabase-backed implementations of the storage ports.

The backend is PostgREST (the tables) and the Storage API (the audio).
Both are plain HTTPS, so both are reached with ``httpx`` and no new
runtime dependency.

Two facts shape this module:

* **The service role key bypasses row-level security.** The policies in
  ``supabase/migrations`` protect the *direct-from-the-browser* path; the
  Python service enforces ownership itself, in every query, with an
  explicit ``user_id`` filter. The two are complementary, not redundant.
* **An object key is a capability.** The key of a recording is
  ``<user id>/<recording id>``, it is derived rather than stored, and it
  never leaves this module: no response, no error message and no log line
  carries it.

The bucket is **private**. No public URL is ever created, stored or
returned; a recording is served by the owner-scoped route, which reads
the bytes and hands them to the owner.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import httpx

from gnani_coach.identity.verifier import subject_from_user_id
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
    StorageUnavailableError,
)
from gnani_coach.persistence.metrics import assert_metrics_only
from gnani_coach.ports.recording_store import RecordingRef
from gnani_coach.ports.session_store import SessionSummary
from gnani_coach.ports.types import RecordingId, SessionId, UserId

logger = logging.getLogger(__name__)

#: The bucket that holds the recordings. It is private.
RECORDINGS_BUCKET = "recordings"

#: How long a retained recording lives: 30 days.
RETENTION_DAYS = 30

#: The default timeout of one backend call, in seconds.
DEFAULT_TIMEOUT_SECONDS = 15.0

OwnerResolver = Callable[[], Awaitable[UserId | None]]


async def current_owner() -> UserId | None:
    """The user id verified in the current request context, or ``None``."""
    from gnani_coach.identity import get_identity

    identity = get_identity()
    return await identity.current_user()


class SupabaseRest:
    """A thin HTTPS client for the PostgREST and Storage APIs.

    The service role key is held in memory, is sent only in the
    ``apikey`` and ``Authorization`` headers, and is never logged.
    """

    def __init__(
        self,
        base_url: str,
        service_role_key: str,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._key = service_role_key
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            transport=transport,
            timeout=timeout_seconds,
            headers={"Accept": "application/json"},
        )

    def _headers(self, **extra: str) -> dict[str, str]:
        headers = {
            "apikey": self._key,
            "Authorization": f"Bearer {self._key}",
        }
        headers.update(extra)
        return headers

    async def rest(
        self,
        method: str,
        table: str,
        *,
        json_body: Any = None,
        params: dict[str, str] | None = None,
        prefer: str | None = None,
    ) -> httpx.Response:
        """One call against the PostgREST API."""
        headers = self._headers()
        if json_body is not None:
            headers["Content-Type"] = "application/json"
        if prefer:
            headers["Prefer"] = prefer
        url = f"{self._base_url}/rest/v1/{table}"
        try:
            response = await self._client.request(
                method, url, json=json_body, params=params, headers=headers
            )
        except Exception as exc:
            logger.warning("the storage backend could not be reached")
            raise StorageUnavailableError("the storage backend could not be reached") from exc
        return response

    async def rows(
        self,
        method: str,
        table: str,
        *,
        json_body: Any = None,
        params: dict[str, str] | None = None,
        prefer: str | None = None,
    ) -> list[dict]:
        """One call against the PostgREST API, decoded as rows."""
        response = await self.rest(
            method, table, json_body=json_body, params=params, prefer=prefer
        )
        if response.status_code >= 400:
            logger.warning(
                "the storage backend refused a request with status %s", response.status_code
            )
            raise StorageUnavailableError("the storage backend refused the request")
        if not response.content:
            return []
        try:
            payload = response.json()
        except Exception as exc:
            raise StorageUnavailableError("the storage backend sent an unreadable answer") from exc
        if isinstance(payload, list):
            return [row for row in payload if isinstance(row, dict)]
        if isinstance(payload, dict):
            return [payload]
        return []

    async def upload(
        self, key: str, audio: bytes, *, content_type: str = "audio/wav"
    ) -> None:
        """Put one object into the private bucket."""
        headers = self._headers(**{"Content-Type": content_type, "x-upsert": "false"})
        url = f"{self._base_url}/storage/v1/object/{RECORDINGS_BUCKET}/{key}"
        try:
            response = await self._client.put(url, content=audio, headers=headers)
        except Exception as exc:
            logger.warning("the storage backend could not be reached")
            raise StorageUnavailableError("the storage backend could not be reached") from exc
        if response.status_code >= 400:
            logger.warning(
                "the storage backend refused an upload with status %s",
                response.status_code,
            )
            raise StorageUnavailableError("the storage backend refused the upload")

    async def download(self, key: str) -> bytes | None:
        """Read one object out of the private bucket."""
        headers = self._headers()
        url = f"{self._base_url}/storage/v1/object/{RECORDINGS_BUCKET}/{key}"
        try:
            response = await self._client.get(url, headers=headers)
        except Exception as exc:
            logger.warning("the storage backend could not be reached")
            raise StorageUnavailableError("the storage backend could not be reached") from exc
        if response.status_code == 404:
            return None
        if response.status_code >= 400:
            logger.warning(
                "the storage backend refused a read with status %s",
                response.status_code,
            )
            raise StorageUnavailableError("the storage backend refused the read")
        return response.content

    async def remove(self, key: str) -> None:
        """Delete one object out of the private bucket. Best effort."""
        headers = self._headers()
        url = f"{self._base_url}/storage/v1/object/{RECORDINGS_BUCKET}/{key}"
        try:
            response = await self._client.delete(url, headers=headers)
        except Exception as exc:
            logger.warning("the storage backend could not be reached")
            raise StorageUnavailableError("the storage backend could not be reached") from exc
        if response.status_code >= 400 and response.status_code != 404:
            logger.warning(
                "the storage backend refused a delete with status %s",
                response.status_code,
            )
            raise StorageUnavailableError("the storage backend refused the delete")

    async def aclose(self) -> None:
        """Close the HTTP client this wrapper owns."""
        if self._owns_client:
            await self._client.aclose()


def _object_key(user_id: UserId, recording_id: str) -> str | None:
    """The private object key of one recording.

    ``<user id>/<recording id>``. The key is derived, never stored, and
    never returned. ``None`` when the owner is not one of ours.
    """
    subject = subject_from_user_id(user_id)
    if subject is None:
        return None
    return f"{subject}/{recording_id}"


@dataclass
class SupabaseConsentStore:
    """The consent state, in the ``consent`` table.

    The current state lives in ``consent``; every write is also appended
    to ``consent_events``, so the version and the time of every consent
    write are on the record.
    """

    rest: SupabaseRest
    _clock: Callable[[], datetime] = utc_now

    async def get_state(self, user_id: UserId) -> ConsentState:
        subject = subject_from_user_id(user_id)
        if subject is None:
            return ConsentState.not_granted()
        rows = await self.rest.rows(
            "GET",
            "consent",
            params={
                "select": (
                    "consent_version,recording_retention_granted,"
                    "recording_retention_granted_at,updated_at"
                ),
                "user_id": f"eq.{subject}",
                "limit": "1",
            },
        )
        if not rows:
            return ConsentState.not_granted()
        row = rows[0]
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
        subject = subject_from_user_id(user_id)
        if subject is None:
            raise StorageUnavailableError("the owner of a consent write is not known")
        moment = self._clock()
        timestamp = isoformat(moment)
        body = {
            "user_id": subject,
            "consent_version": consent_version,
            "recording_retention_granted": granted,
            "recording_retention_granted_at": timestamp if granted else None,
            "recording_retention_withdrawn_at": None if granted else timestamp,
            "updated_at": timestamp,
        }
        await self.rest.rows(
            "POST",
            "consent",
            json_body=body,
            params={"on_conflict": "user_id"},
            prefer="resolution=merge-duplicates,return=minimal",
        )
        await self.rest.rows(
            "POST",
            "consent_events",
            json_body={
                "user_id": subject,
                "consent_version": consent_version,
                "recording_retention_granted": granted,
                "created_at": timestamp,
            },
            prefer="return=minimal",
        )
        return ConsentState(
            consent_version=consent_version,
            recording_retention_granted=granted,
            recording_retention_granted_at=timestamp if granted else None,
            updated_at=timestamp,
        )


@dataclass
class SupabaseSessionStore:
    """The metrics-only session store, in the ``session_metrics`` table."""

    rest: SupabaseRest
    owner_resolver: OwnerResolver = current_owner
    _clock: Callable[[], datetime] = utc_now

    async def save_metrics(self, record: dict) -> None:
        """Persist one durable-metrics record for the current owner.

        A **guest writes nothing**. A document that carries content is
        refused loudly.
        """
        assert_metrics_only(record)
        owner = await self.owner_resolver()
        if owner is None:
            return
        await self.save_metrics_for(owner, record)

    async def save_metrics_for(self, user_id: UserId, record: dict) -> None:
        """Persist one durable-metrics record for an explicit owner."""
        assert_metrics_only(record)
        subject = subject_from_user_id(user_id)
        if subject is None:
            raise StorageUnavailableError("the owner of a record is not known")
        session_id = record.get("sessionId")
        if not isinstance(session_id, str) or not session_id:
            raise ContentRejectedError("a durable record needs a session id")
        totals = record.get("totals") if isinstance(record.get("totals"), dict) else {}
        recording_id = record.get("recordingId")
        body = {
            "user_id": subject,
            "session_id": session_id,
            "recorded_at": str(record.get("recordedAt") or isoformat(self._clock())),
            "practice_language_id": str(record.get("practiceLanguageId") or ""),
            "scenario_id": str(record.get("scenarioId") or ""),
            "recording_id": recording_id if isinstance(recording_id, str) else None,
            "turn_count": int(totals.get("turnCount", 0) or 0),
            "speaking_time_ms": int(totals.get("speakingTimeMs", 0) or 0),
            "metrics_version": str(record.get("metricsVersion") or "0.1"),
            "document": record,
        }
        await self.rest.rows(
            "POST",
            "session_metrics",
            json_body=body,
            params={"on_conflict": "user_id,session_id"},
            prefer="resolution=merge-duplicates,return=minimal",
        )

    async def list_sessions(
        self, user_id: UserId, *, limit: int = 20
    ) -> list[SessionSummary]:
        """List the caller's sessions, newest first."""
        subject = subject_from_user_id(user_id)
        if subject is None:
            return []
        rows = await self.rest.rows(
            "GET",
            "session_metrics",
            params={
                "select": (
                    "session_id,recorded_at,practice_language_id,scenario_id,"
                    "recording_id,turn_count,speaking_time_ms"
                ),
                "user_id": f"eq.{subject}",
                "order": "recorded_at.desc",
                "limit": str(max(0, limit)),
            },
        )
        return [_summary_from_row(row) for row in rows]

    async def get_session(self, user_id: UserId, session_id: SessionId) -> dict | None:
        """Return one record, or ``None`` when it is not the caller's."""
        subject = subject_from_user_id(user_id)
        if subject is None:
            return None
        rows = await self.rest.rows(
            "GET",
            "session_metrics",
            params={
                "select": "document",
                "user_id": f"eq.{subject}",
                "session_id": f"eq.{session_id}",
                "limit": "1",
            },
        )
        if not rows:
            return None
        document = rows[0].get("document")
        return document if isinstance(document, dict) else None


@dataclass
class SupabaseRecordingStore:
    """The opt-in recording store, in the ``recordings`` table and the
    private ``recordings`` bucket.

    The fence lives in two places: the ``state`` column of the row (so it
    survives a restart and another process) and an in-process set (so a
    late job is refused without a round trip).
    """

    rest: SupabaseRest
    consent_store: SupabaseConsentStore
    _clock: Callable[[], datetime] = utc_now
    _retention: timedelta = timedelta(days=RETENTION_DAYS)
    _fenced_sessions: set[tuple[UserId, str]] = None  # type: ignore[assignment]
    _fenced_recordings: set[tuple[UserId, str]] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self._fenced_sessions is None:
            self._fenced_sessions = set()
        if self._fenced_recordings is None:
            self._fenced_recordings = set()

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
        """Retain one recording for an owner who has opted in."""
        state = await self.consent_store.get_state(user_id)
        if not state.recording_retention_granted:
            raise ConsentRequiredError(
                "recording retention is not granted for this account"
            )

        subject = subject_from_user_id(user_id)
        if subject is None:
            raise StorageUnavailableError("the owner of a recording is not known")

        identifier = str(recording_id) if recording_id else f"rec_{uuid.uuid4().hex}"
        await self._assert_not_fenced(user_id, subject, str(session_id), identifier)

        moment = self._clock()
        expires_at = moment + self._retention
        key = _object_key(user_id, identifier)
        if key is None:
            raise StorageUnavailableError("the owner of a recording is not known")

        await self.rest.upload(key, bytes(audio), content_type=content_type)
        try:
            await self.rest.rows(
                "POST",
                "recordings",
                json_body={
                    "recording_id": identifier,
                    "user_id": subject,
                    "session_id": str(session_id),
                    "owner_ref": user_id,
                    "created_at": isoformat(moment),
                    "duration_ms": int(duration_ms),
                    "size_bytes": len(audio),
                    "content_type": content_type,
                    "format": {
                        "container": "wav",
                        "codec": "pcm_s16le",
                        "sampleRateHz": 16000,
                        "channels": 1,
                    },
                    "consent_version": state.consent_version,
                    "consent_granted_at": state.recording_retention_granted_at,
                    "state": "retained",
                    "expires_at": isoformat(expires_at),
                    "deleted_at": None,
                },
                prefer="return=minimal",
            )
        except Exception:
            # The object is uploaded but the row is not there: undo the
            # upload, so an audio file never exists without a record of
            # its consent.
            await self.rest.remove(key)
            raise

        return RecordingRef(
            recording_id=identifier,
            session_id=str(session_id),
            created_at=isoformat(moment),
            duration_ms=int(duration_ms),
            size_bytes=len(audio),
            content_type=content_type,
        )

    async def get_recording(self, user_id: UserId, recording_id: RecordingId) -> bytes | None:
        """Read a recording, or ``None`` when it is not the caller's."""
        subject = subject_from_user_id(user_id)
        if subject is None:
            return None
        rows = await self.rest.rows(
            "GET",
            "recordings",
            params={
                "select": "recording_id,user_id,state,expires_at",
                "user_id": f"eq.{subject}",
                "recording_id": f"eq.{recording_id}",
                "limit": "1",
            },
        )
        if not rows:
            return None
        row = rows[0]
        if row.get("state") != "retained":
            return None
        expires_at = row.get("expires_at")
        if isinstance(expires_at, str) and expires_at:
            if _parse_timestamp(expires_at) <= self._clock():
                return None
        key = _object_key(user_id, str(recording_id))
        if key is None:
            return None
        return await self.rest.download(key)

    async def delete_recording(self, user_id: UserId, recording_id: RecordingId) -> bool:
        """Delete a recording. ``True`` when something was deleted."""
        subject = subject_from_user_id(user_id)
        if subject is None:
            return False
        rows = await self.rest.rows(
            "PATCH",
            "recordings",
            json_body={"state": "deleted", "deleted_at": isoformat(self._clock())},
            params={
                "user_id": f"eq.{subject}",
                "recording_id": f"eq.{recording_id}",
                "state": "eq.retained",
            },
            prefer="return=representation",
        )
        if not rows:
            return False
        self._fenced_sessions.add((user_id, str(_session_of(rows[0]))))
        self._fenced_recordings.add((user_id, str(recording_id)))
        key = _object_key(user_id, str(recording_id))
        if key is not None:
            await self.rest.remove(key)
        return True

    async def _assert_not_fenced(
        self, user_id: UserId, subject: str, session_id: str, recording_id: str
    ) -> None:
        """Refuse a write that would recreate something that was deleted."""
        if (user_id, session_id) in self._fenced_sessions:
            raise RecordingFencedError(
                "the recording of this session was deleted and may not be recreated"
            )
        if (user_id, recording_id) in self._fenced_recordings:
            raise RecordingFencedError(
                "the recording was deleted and may not be recreated"
            )
        rows = await self.rest.rows(
            "GET",
            "recordings",
            params={
                "select": "recording_id,session_id,state",
                "user_id": f"eq.{subject}",
                "recording_id": f"eq.{recording_id}",
                "limit": "5",
            },
        )
        for row in rows:
            if row.get("state") == "deleted":
                raise RecordingFencedError(
                    "the recording was deleted and may not be recreated"
                )
            if row.get("recording_id") == recording_id:
                raise RecordingFencedError("a recording with this id already exists")

        deleted_rows = await self.rest.rows(
            "GET",
            "recordings",
            params={
                "select": "recording_id,session_id,state",
                "user_id": f"eq.{subject}",
                "session_id": f"eq.{session_id}",
                "state": "eq.deleted",
                "limit": "5",
            },
        )
        if deleted_rows:
            raise RecordingFencedError(
                "the recording of this session was deleted and may not be recreated"
            )


def _session_of(row: dict) -> str:
    """The session id of a recording row."""
    value = row.get("session_id")
    return str(value) if value is not None else ""


def _parse_timestamp(value: str) -> datetime:
    """Parse an RFC 3339 timestamp, tolerating the two shapes Postgres uses."""
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return datetime.min.replace(tzinfo=utc_now().tzinfo)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=utc_now().tzinfo)
    return parsed


def _summary_from_row(row: dict) -> SessionSummary:
    """Build one history row out of a database row."""
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


__all__ = [
    "RECORDINGS_BUCKET",
    "RETENTION_DAYS",
    "SupabaseConsentStore",
    "SupabaseRecordingStore",
    "SupabaseRest",
    "SupabaseSessionStore",
]
