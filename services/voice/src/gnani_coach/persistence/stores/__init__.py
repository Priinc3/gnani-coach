"""The storage backends and the accessors that expose them.

Three accessors, one rule: **each returns ``None`` when storage is not
configured.** A caller that gets ``None`` knows that there is no storage
in this process, and does not have to guess whether the storage is empty
or missing.

* ``get_session_store()`` — the metrics-only session store;
* ``get_recording_store()`` — the opt-in recording store;
* ``get_consent_store()`` — the consent state the two share.

The instances are process-wide, so the verification cache of the
identity port and the fence of the recording store are shared by every
request instead of being rebuilt per request.
"""

from __future__ import annotations

from typing import Any

from gnani_coach.persistence.consent import ConsentStore
from gnani_coach.persistence.stores.memory import (
    InMemoryConsentStore,
    InMemoryRecordingStore,
    InMemorySessionStore,
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

__all__ = [
    "ConsentStore",
    "InMemoryConsentStore",
    "InMemoryRecordingStore",
    "InMemorySessionStore",
    "RecordingStorePort",
    "SessionStorePort",
    "SupabaseConsentStore",
    "SupabaseRecordingStore",
    "SupabaseRest",
    "SupabaseSessionStore",
    "get_consent_store",
    "get_recording_store",
    "get_session_store",
]


#: The process-wide instances.
_instances: dict[str, Any] = {}


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


def get_session_store() -> SessionStorePort | None:
    """The metrics-only session store, or ``None`` when storage is off."""
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
    rest = _rest()
    if rest is None:
        return None
    consent = get_consent_store()
    if consent is None:
        return None
    store = _instances.get("recording")
    if store is None:
        store = SupabaseRecordingStore(rest=rest, consent_store=consent)
        _instances["recording"] = store
    return store


def get_consent_store() -> ConsentStore | None:
    """The consent state, or ``None`` when storage is off."""
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
