"""The failure vocabulary of the call runtime.

Every failure the runtime reports to a client uses the **frozen error
shape** (``packages/contracts/schemas/error-shape.schema.json``):

* ``code`` is a stable machine identifier, never shown to the learner;
* ``category`` is the stable machine category;
* ``message`` is plain-word, bounded and written for the learner;
* ``retryable`` is true only for genuinely transient conditions.

Nothing in this module formats a secret, a provider payload or learner
content into a message. The messages are written by hand, so a transcript
can never leak into an error.
"""

from __future__ import annotations

from dataclasses import dataclass

from gnani_coach.ports.error_shape import error_payload
from gnani_coach.ports.types import ErrorCategory
from gnani_coach.providers.errors import ProviderError


@dataclass(frozen=True)
class Failure:
    """One mapped failure: the code, the category and the plain message."""

    code: str
    category: ErrorCategory
    message: str
    retryable: bool

    def payload(self, *, correlation_id: str | None = None) -> dict[str, object]:
        """The frozen error-shape payload for this failure."""
        return error_payload(
            code=self.code,
            category=self.category,
            message=self.message,
            retryable=self.retryable,
            correlation_id=correlation_id,
        )


#: The learner never sent a usable ``start`` event.
INVALID_START = Failure(
    code="invalid_start",
    category="invalid_request",
    message=(
        "The call could not start because the first message was not a valid "
        "start event. Please reload the page and try again."
    ),
    retryable=False,
)

#: The first message was larger than the 16 KiB protocol limit.
MESSAGE_TOO_LARGE = Failure(
    code="message_too_large",
    category="invalid_request",
    message=(
        "One message on this call was too large to accept, so the call was "
        "closed. Please try again."
    ),
    retryable=False,
)

#: A binary audio frame was not the documented 1,024 bytes.
INVALID_FRAME_SIZE = Failure(
    code="invalid_frame_size",
    category="invalid_request",
    message=(
        "An audio frame arrived in the wrong size, so the call was closed. "
        "Please try again."
    ),
    retryable=False,
)

#: The client's audio format is not the one this service accepts.
UNSUPPORTED_AUDIO_FORMAT = Failure(
    code="unsupported_audio_format",
    category="invalid_request",
    message=(
        "This service accepts 16 kilohertz mono audio only. Please use a "
        "supported browser or microphone."
    ),
    retryable=False,
)

#: The caller's token could not be verified.
UNAUTHENTICATED = Failure(
    code="unauthenticated",
    category="unauthenticated",
    message=(
        "Your sign-in could not be confirmed, so this call continues as a "
        "guest and nothing will be saved."
    ),
    retryable=False,
)

#: Too many simultaneous calls from one address or one account.
TOO_MANY_CONNECTIONS = Failure(
    code="too_many_connections",
    category="rate_limited",
    message=(
        "Too many calls are already open for this account or device. Please "
        "close one and try again."
    ),
    retryable=True,
)

#: A provider credential is not configured, so the call cannot run.
PROVIDER_NOT_CONFIGURED = Failure(
    code="provider_not_configured",
    category="not_available",
    message=(
        "The speech or coaching service is not configured on this server, so "
        "no call can run right now. Nothing was saved."
    ),
    retryable=False,
)

#: The provider could not be reached.
PROVIDER_UNAVAILABLE = Failure(
    code="provider_unavailable",
    category="provider_unavailable",
    message=(
        "The speech service could not be reached, so the call was closed. "
        "Please try again in a moment."
    ),
    retryable=True,
)

#: The provider rejected our credential.
PROVIDER_AUTHENTICATION = Failure(
    code="provider_authentication_failed",
    category="provider_unavailable",
    message=(
        "The speech service rejected this server's credential, so the call "
        "was closed. Please try again later."
    ),
    retryable=False,
)

#: The provider throttled the call.
PROVIDER_RATE_LIMITED = Failure(
    code="provider_rate_limited",
    category="rate_limited",
    message=(
        "The speech service is busy right now, so the call was closed. Please "
        "try again in a moment."
    ),
    retryable=True,
)

#: A bounded wait expired.
TIMEOUT = Failure(
    code="provider_timeout",
    category="timeout",
    message=(
        "The speech service did not answer in time, so the call was closed. "
        "Please try again."
    ),
    retryable=True,
)

#: The call's own provider budget is exhausted.
BUDGET_EXHAUSTED = Failure(
    code="provider_budget_exhausted",
    category="provider_unavailable",
    message=(
        "This call reached its limit for speech-service requests, so it was "
        "closed cleanly. Nothing was saved."
    ),
    retryable=False,
)

#: An unexpected internal failure.
INTERNAL = Failure(
    code="internal_error",
    category="internal",
    message=(
        "Something went wrong inside the call service, so the call was "
        "closed. Please try again."
    ),
    retryable=False,
)

#: The connection hit the product's call cap.
CALL_CAP_REACHED = Failure(
    code="call_limit_reached",
    category="not_available",
    message=(
        "This call reached the ten minute limit, so it is ending now."
    ),
    retryable=False,
)

#: The connection was idle for too long.
IDLE_TIMEOUT = Failure(
    code="idle_timeout",
    category="timeout",
    message=(
        "This call was closed because no audio arrived for a while."
    ),
    retryable=False,
)

#: The provider adapter refused the request for a permanent reason.
PROVIDER_REJECTED = Failure(
    code="provider_rejected_request",
    category="provider_unavailable",
    message=(
        "The speech service could not accept this request, so the call was "
        "closed. Please try again."
    ),
    retryable=False,
)

#: The provider's answer did not follow the documented protocol.
PROVIDER_PROTOCOL = Failure(
    code="provider_protocol_error",
    category="provider_unavailable",
    message=(
        "The speech service sent something this service could not read, so "
        "the call was closed. Please try again."
    ),
    retryable=False,
)

#: The model answered with something that failed validation.
INVALID_MODEL_OUTPUT = Failure(
    code="invalid_model_output",
    category="internal",
    message=(
        "The coaching service answered with something this service could not "
        "use, so that part of the call was skipped."
    ),
    retryable=False,
)


#: How a provider failure maps onto the runtime's failure vocabulary.
_PROVIDER_FAILURES: dict[str, Failure] = {
    "authentication": PROVIDER_AUTHENTICATION,
    "invalid_request": PROVIDER_REJECTED,
    "protocol": PROVIDER_PROTOCOL,
    "rate_limited": PROVIDER_RATE_LIMITED,
    "timeout": TIMEOUT,
    "network": PROVIDER_UNAVAILABLE,
    "cancelled": PROVIDER_REJECTED,
    "budget_exceeded": BUDGET_EXHAUSTED,
    "configuration": PROVIDER_NOT_CONFIGURED,
    "endpoint": PROVIDER_UNAVAILABLE,
}


def from_provider_error(exc: ProviderError) -> Failure:
    """Map a provider failure onto the frozen error shape.

    The provider's own category decides the mapping, so the runtime never
    parses an exception message.
    """
    return _PROVIDER_FAILURES.get(exc.category, PROVIDER_UNAVAILABLE)


def from_exception(exc: BaseException) -> Failure:
    """Map any unexpected exception onto the frozen error shape."""
    if isinstance(exc, ProviderError):
        return from_provider_error(exc)
    if isinstance(exc, TimeoutError):
        return TIMEOUT
    if isinstance(exc, (ConnectionError, OSError)):
        return PROVIDER_UNAVAILABLE
    return INTERNAL
