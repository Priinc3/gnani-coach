"""The history, consent and recording routes — **Phase 06 owns this file**.

The four routes are real now. Their paths and methods are the frozen
ones:

* ``GET  /api/history`` — the caller's session summaries;
* ``POST /api/consent`` — record or withdraw recording-retention consent;
* ``GET  /api/recordings/{recording_id}`` — a retained recording;
* ``DELETE /api/recordings/{recording_id}`` — delete a retained recording.

The rules every route obeys:

* **The bearer token is the only credential.** There are no cookies: the
  ``Authorization`` header carries the caller's own access token, and the
  history routes are therefore not credentialed CORS.
* **Ownership comes from the verified token**, never from the request
  body and never from the path. A body that carries somebody else's
  ``user_id`` is ignored.
* **A guest gets no history and no audio.** A request without a verified
  token is ``401``.
* **A recording that is not the caller's is ``404``**, byte for byte the
  same answer as a recording that does not exist. There is no existence
  oracle.
* **Nothing is echoed.** No response, no error message and no log line
  carries a token, a request path or a bucket key.
* **The errors use the frozen error shape**
  (:func:`gnani_coach.ports.error_shape.error_payload`).

The routes stay **excluded from the generated OpenAPI document**
(``include_in_schema=False``), exactly as the Phase 03 stub had them.

Why that is the documented choice: the service has no published API
surface at all (``docs_url`` and ``redoc_url`` are ``None``), and the
Phase 01 invariant that *"/health is the only documented route"* is
still asserted by a Phase 01 test file that Phase 06 may not edit. The
seams document says the routes join the OpenAPI document once they are
real; publishing them is a one-line change, and it is raised as a
``HELP:`` item in the report, because the contract that owns the
sentence belongs to Phase 03.
"""

from __future__ import annotations

import json
import re

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse, Response

from gnani_coach.identity import get_identity
from gnani_coach.persistence.consent import SUPPORTED_CONSENT_VERSIONS
from gnani_coach.persistence.errors import (
    ConsentRequiredError,
    RecordingFencedError,
    StorageUnavailableError,
)
from gnani_coach.persistence.stores import (
    get_consent_store,
    get_recording_store,
    get_session_store,
)
from gnani_coach.ports.error_shape import error_payload, not_available_error
from gnani_coach.ports.identity import IdentityPort
from gnani_coach.ports.types import UserId

router = APIRouter()

#: The largest request body a route reads. The consent body is two
#: fields; anything larger is refused before it is parsed.
MAX_BODY_BYTES = 4096

#: The status of an oversized body. The number is written out because the
#: named constant moved between Starlette versions.
HTTP_TOO_LARGE = 413

#: The shape of a recording id. An id that does not match cannot exist,
#: so it is answered like a missing one.
RECORDING_ID_PATTERN = re.compile(r"^rec_[a-z0-9]{6,40}$")


def _error(
    status_code: int,
    *,
    code: str,
    category: str,
    message: str,
    retryable: bool = False,
) -> JSONResponse:
    """One frozen-shape error answer."""
    return JSONResponse(
        status_code=status_code,
        content=error_payload(
            code=code,
            category=category,  # type: ignore[arg-type]
            message=message,
            retryable=retryable,
        ),
    )


def _not_available() -> JSONResponse:
    """The answer of a seam whose storage is not configured."""
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content=not_available_error(),
    )


def _bearer_token(request: Request) -> str | None:
    """The caller's own token, or ``None``.

    The token is read from the ``Authorization`` header and nowhere else.
    It is never logged and never echoed.
    """
    header = request.headers.get("authorization")
    if not header:
        return None
    parts = header.split()
    if len(parts) != 2:
        return None
    if parts[0].lower() != "bearer":
        return None
    token = parts[1].strip()
    return token or None


async def _require_user(request: Request, identity: IdentityPort) -> UserId | None:
    """The verified user id of the caller, or ``None`` for a guest.

    The token is verified against the identity port; a bad, expired or
    wrong-audience token is a guest, not an error and not an exception.
    """
    token = _bearer_token(request)
    if token is None:
        return None
    try:
        return await identity.verify_token(token)
    except Exception:  # a failed verification is a guest, never a crash
        return None


async def _read_json_body(request: Request) -> tuple[dict | None, JSONResponse | None]:
    """Read a small JSON body, or explain why it was refused."""
    declared = request.headers.get("content-length")
    if declared:
        try:
            if int(declared) > MAX_BODY_BYTES:
                return None, _error(
                    HTTP_TOO_LARGE,
                    code="invalid_request",
                    category="invalid_request",
                    message="That request was too large.",
                )
        except ValueError:
            return None, _error(
                status.HTTP_400_BAD_REQUEST,
                code="invalid_request",
                category="invalid_request",
                message="That request could not be read.",
            )

    chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > MAX_BODY_BYTES:
            return None, _error(
                HTTP_TOO_LARGE,
                code="invalid_request",
                category="invalid_request",
                message="That request was too large.",
            )
        chunks.append(chunk)
    if not chunks:
        return None, _error(
            status.HTTP_400_BAD_REQUEST,
            code="invalid_request",
            category="invalid_request",
            message="That request was missing a body.",
        )
    try:
        payload = json.loads(b"".join(chunks).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None, _error(
            status.HTTP_400_BAD_REQUEST,
            code="invalid_request",
            category="invalid_request",
            message="That request could not be read.",
        )
    if not isinstance(payload, dict):
        return None, _error(
            status.HTTP_400_BAD_REQUEST,
            code="invalid_request",
            category="invalid_request",
            message="That request could not be read.",
        )
    return payload, None


@router.get("/api/history", include_in_schema=False)
async def history(
    request: Request, identity: IdentityPort = Depends(get_identity)
) -> Response:
    """The caller's session summaries, newest first.

    A guest is ``401``: the caller renders the guest state, not an error
    page. The list is a real list — it is never padded with sample data.
    """
    user_id = await _require_user(request, identity)
    if user_id is None:
        return _error(
            status.HTTP_401_UNAUTHORIZED,
            code="unauthenticated",
            category="unauthenticated",
            message="Sign in to see your practice history.",
        )
    store = get_session_store()
    if store is None:
        return _not_available()
    try:
        summaries = await store.list_sessions(user_id)
    except StorageUnavailableError:
        return _error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            code="provider.unavailable",
            category="provider_unavailable",
            message="Your history is not available right now.",
            retryable=True,
        )
    return JSONResponse(
        {
            "sessions": [
                {
                    "sessionId": summary.session_id,
                    "recordedAt": summary.recorded_at,
                    "practiceLanguageId": summary.practice_language_id,
                    "scenarioId": summary.scenario_id,
                    "recordingId": summary.recording_id,
                    "turnCount": summary.turn_count,
                    "speakingTimeMs": summary.speaking_time_ms,
                }
                for summary in summaries
            ]
        }
    )


@router.post("/api/consent", include_in_schema=False)
async def consent(
    request: Request, identity: IdentityPort = Depends(get_identity)
) -> Response:
    """Record or withdraw recording-retention consent.

    A withdrawal stops **future** retention. It does **not** silently
    delete what was already retained: the deletion is an explicit action
    with its own route and its own confirmation.
    """
    user_id = await _require_user(request, identity)
    if user_id is None:
        return _error(
            status.HTTP_401_UNAUTHORIZED,
            code="unauthenticated",
            category="unauthenticated",
            message="Sign in to change your recording consent.",
        )

    payload, refusal = await _read_json_body(request)
    if refusal is not None:
        return refusal
    assert payload is not None

    version = payload.get("consentVersion")
    granted = payload.get("recordingRetentionGranted")
    if not isinstance(version, str) or version not in SUPPORTED_CONSENT_VERSIONS:
        return _error(
            status.HTTP_400_BAD_REQUEST,
            code="invalid_request",
            category="invalid_request",
            message="That consent version is not supported.",
        )
    if not isinstance(granted, bool):
        return _error(
            status.HTTP_400_BAD_REQUEST,
            code="invalid_request",
            category="invalid_request",
            message="That consent request could not be read.",
        )

    store = get_consent_store()
    if store is None:
        return _not_available()
    try:
        state = await store.set_state(user_id, consent_version=version, granted=granted)
    except StorageUnavailableError:
        return _error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            code="provider.unavailable",
            category="provider_unavailable",
            message="Your consent could not be saved right now.",
            retryable=True,
        )
    return JSONResponse(
        {
            "recordingRetentionGranted": state.recording_retention_granted,
            "recordingRetentionGrantedAt": state.recording_retention_granted_at,
        }
    )


@router.get("/api/recordings/{recording_id}", include_in_schema=False)
async def get_recording(
    recording_id: str, request: Request, identity: IdentityPort = Depends(get_identity)
) -> Response:
    """Read a retained recording.

    A recording that belongs to somebody else and a recording that does
    not exist produce the **same** answer, so the route is not an
    existence oracle.
    """
    user_id = await _require_user(request, identity)
    if user_id is None:
        return _error(
            status.HTTP_401_UNAUTHORIZED,
            code="unauthenticated",
            category="unauthenticated",
            message="Sign in to listen to a recording.",
        )
    store = get_recording_store()
    if store is None:
        return _not_available()
    if not RECORDING_ID_PATTERN.match(recording_id):
        return _not_found()
    try:
        audio = await store.get_recording(user_id, recording_id)
    except StorageUnavailableError:
        return _error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            code="provider.unavailable",
            category="provider_unavailable",
            message="That recording is not available right now.",
            retryable=True,
        )
    if audio is None:
        return _not_found()
    return Response(
        content=audio,
        media_type="audio/wav",
        headers={
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.delete("/api/recordings/{recording_id}", include_in_schema=False)
async def delete_recording(
    recording_id: str, request: Request, identity: IdentityPort = Depends(get_identity)
) -> Response:
    """Delete a retained recording.

    The deletion is a **state**: the record of the recording stays, with
    the time of the deletion, and the audio is gone. A repeated delete is
    ``404``, like a recording that never existed.
    """
    user_id = await _require_user(request, identity)
    if user_id is None:
        return _error(
            status.HTTP_401_UNAUTHORIZED,
            code="unauthenticated",
            category="unauthenticated",
            message="Sign in to delete a recording.",
        )
    store = get_recording_store()
    if store is None:
        return _not_available()
    if not RECORDING_ID_PATTERN.match(recording_id):
        return _not_found()
    try:
        deleted = await store.delete_recording(user_id, recording_id)
    except StorageUnavailableError:
        return _error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            code="provider.unavailable",
            category="provider_unavailable",
            message="That recording could not be deleted right now.",
            retryable=True,
        )
    except ConsentRequiredError:
        return _not_found()
    except RecordingFencedError:
        return _not_found()
    if not deleted:
        return _not_found()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _not_found() -> JSONResponse:
    """The one answer for "not yours" and "not there".

    The two cases are deliberately indistinguishable: the body, the
    status and the wording are identical.
    """
    return _error(
        status.HTTP_404_NOT_FOUND,
        code="not_found",
        category="not_found",
        message="That recording is not available.",
    )
