"""The storage backends and the accessors that expose them.

Three accessors, one rule: **each returns ``None`` when storage is not
configured.** A caller that gets ``None`` knows that there is no storage
in this process, and does not have to guess whether the storage is empty
or missing.

The backend is chosen by ``SPEAKING_COACH_STORAGE_BACKEND``:

* ``sqlite`` — the embedded backend in :mod:`gnani_coach.persistence.stores.sqlite`;
* ``memory`` — the in-memory reference implementation;
* ``supabase`` — the PostgREST/Storage backend;
* unset — today's behaviour, i.e. Supabase when it is configured and no
  storage otherwise.

The instances are process-wide, so the fence of the recording store and
the single SQLite connection are shared by every request instead of being
rebuilt per request.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from gnani_coach.persistence.consent import ConsentStore
from gnani_coach.persistence.stores.memory import (
    InMemoryConsentStore,
    InMemoryRecordingStore,
    InMemorySessionStore,
)
from gnani_coach.persistence.stores.sqlite import (
    SQLiteConsentStore,
    SQLiteDatabase,
    SQLiteRecordingStore,
    SQLiteSessionStore,
    database_from_environment,
)
from gnani_coach.persistence.stores.supabase import (
    SupabaseConsentStore,
    SupabaseRecordingStore,
    SupabaseRest,
    SupabaseSessionStore,
)
from gnani_coach.ports.recording_store import RecordingStorePort
from gnani_coach.ports.session_store import SessionStorePort
from gnani_coach.settings import load_settings

logger = logging.getLogger(__name__)

__all__ = [
    "ConsentStore",
    "InMemoryConsentStore",
    "InMemoryRecordingStore",
    "InMemorySessionStore",
    "RecordingStorePort",
    "SQLiteConsentStore",
    "SQLiteDatabase",
    "SQLiteRecordingStore",
    "SQLiteSessionStore",
    "SessionStorePort",
    "SupabaseConsentStore",
    "SupabaseRecordingStore",
    "SupabaseRest",
    "SupabaseSessionStore",
    "get_consent_store",
    "get_recording_store",
    "get_session_store",
    "reset_stores",
]


#: The process-wide instances.
_instances: dict[str, Any] = {}


def storage_backend() -> str:
    """The selected backend. An unknown value falls back to today's rule."""
    raw = os.environ.get("SPEAKING_COACH_STORAGE_BACKEND", "").strip().lower()
    if raw in {"sqlite", "supabase", "memory"}:
        return raw
    if raw:
        logger.warning(
            "an unknown storage backend was configured; using the default"
        )
    return "supabase"


def _configuration() -> tuple[str | None, str | None]:
    """The Supabase URL and the service-role key, or ``(None, None)``.

    The service-role key never leaves this module and is never logged: it
    is the one credential the Python stores use, and it stays in the
    Python environment.
    """
    settings = load_settings()
    url = (settings.supabase.url or "").strip() or None
    key = settings.supabase.service_role_key
    secret = key.get_secret_value().strip() if key else ""
    return url, secret or None


def _rest() -> SupabaseRest | None:
    """The shared HTTP client for the backend, or ``None``."""
    url, key = _configuration()
    if not url or not key:
        return None
    rest = _instances.get("rest")
    if rest is None:
        rest = SupabaseRest(url, key)
        _instances["rest"] = rest
    return rest


def _sqlite_database() -> SQLiteDatabase | None:
    database = _instances.get("sqlite")
    if database is None:
        database = database_from_environment()
        if database is not None:
            _instances["sqlite"] = database
    return database


def _memory_consent() -> InMemoryConsentStore:
    store = _instances.get("memory_consent")
    if store is None:
        store = InMemoryConsentStore()
        _instances["memory_consent"] = store
    return store


def get_session_store() -> SessionStorePort | None:
    """The metrics-only session store, or ``None`` when storage is off."""
    backend = storage_backend()
    if backend == "memory":
        store = _instances.get("memory_session")
        if store is None:
            store = InMemorySessionStore()
            _instances["memory_session"] = store
        return store
    if backend == "sqlite":
        database = _sqlite_database()
        if database is None:
            return None
        store = _instances.get("sqlite_session")
        if store is None:
            store = SQLiteSessionStore(database)
            _instances["sqlite_session"] = store
        return store

    rest = _rest()
    if rest is None:
        return None
    store = _instances.get("session")
    if store is None:
        store = SupabaseSessionStore(rest=rest)
        _instances["session"] = store
    return store


def get_recording_store() -> RecordingStorePort | None:
    """The opt-in recording store, or ``None`` when storage is off."""
    backend = storage_backend()
    if backend == "memory":
        store = _instances.get("memory_recording")
        if store is None:
            store = InMemoryRecordingStore(_memory_consent())
            _instances["memory_recording"] = store
        return store
    if backend == "sqlite":
        database = _sqlite_database()
        consent = get_consent_store()
        if database is None or consent is None:
            return None
        store = _instances.get("sqlite_recording")
        if store is None:
            store = SQLiteRecordingStore(database, consent)  # type: ignore[arg-type]
            _instances["sqlite_recording"] = store
        return store

    rest = _rest()
    if rest is None:
        return None
    consent = get_consent_store()
    if consent is None:
        return None
    store = _instances.get("recording")
    if store is None:
        store = SupabaseRecordingStore(rest=rest, consent_store=consent)  # type: ignore[arg-type]
        _instances["recording"] = store
    return store


def get_consent_store() -> ConsentStore | None:
    """The consent state, or ``None`` when storage is off."""
    backend = storage_backend()
    if backend == "memory":
        return _memory_consent()
    if backend == "sqlite":
        database = _sqlite_database()
        if database is None:
            return None
        store = _instances.get("sqlite_consent")
        if store is None:
            store = SQLiteConsentStore(database)
            _instances["sqlite_consent"] = store
        return store

    rest = _rest()
    if rest is None:
        return None
    consent = _instances.get("consent")
    if consent is None:
        consent = SupabaseConsentStore(rest=rest)
        _instances["consent"] = consent
    return consent


def reset_stores() -> None:
    """Forget the process-wide instances. Used by tests."""
    _instances.clear()
