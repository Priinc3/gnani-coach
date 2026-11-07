"""Explicit provider error taxonomy.

Every failure surfaced by an adapter in this package is one of these
categories. Callers (probe CLI, future conversation runtime) switch on the
category; they never parse exception strings.

Categories exist so that the probe harness can make honest retry decisions:
only ``transient`` categories are ever retried, and never more than the
budget in :mod:`gnani_coach.providers.limits` allows.

Nothing in this module contains provider credentials, headers or raw
exception dumps — see :mod:`gnani_coach.providers.redaction`.
"""

from __future__ import annotations

from typing import Final


class ProviderError(Exception):
    """Base class for every provider adapter failure.

    ``category`` is the stable, machine-readable reason. ``detail`` is a
    short, already-redacted, human-readable hint. Provider payloads are
    untrusted input and are never interpolated into ``detail``.
    """

    category: str = "unknown"
    retryable: bool = False

    def __init__(self, detail: str, *, provider: str = "unknown") -> None:
        super().__init__(f"{provider}:{self.category}: {detail}")
        self.detail = detail
        self.provider = provider


class ConfigurationError(ProviderError):
    """Required configuration is missing or invalid.

    Never retryable. The CLI reports the missing *name*, never the value.
    """

    category = "configuration"


class EndpointError(ProviderError):
    """Endpoint/host is malformed, refused, or not an allowed provider host.

    This is the key-confinement guard: a provider key is never sent to a
    host outside the reviewed allowlist, and never to a redirect target.
    """

    category = "endpoint"


class AuthenticationError(ProviderError):
    """Provider rejected the credential.

    Never retryable — retrying an invalid key is exactly the unbounded
    retry loop this project forbids.
    """

    category = "authentication"


class InvalidRequestError(ProviderError):
    """Provider rejected our request as invalid (language code, voice, text).

    Never retryable: the same request will fail the same way.
    """

    category = "invalid_request"


class ProtocolError(ProviderError):
    """A response violated the documented wire contract.

    Covers malformed JSON, unknown message types, oversized frames and
    out-of-band ordering surprises. Retrying a protocol violation against
    a live provider is never appropriate; tests exercise it with fakes.
    """

    category = "protocol"


class RateLimitError(ProviderError):
    """Provider signalled throttling (HTTP 429 or equivalent)."""

    category = "rate_limited"
    retryable = True


class UpstreamTimeoutError(ProviderError):
    """A bounded wait expired."""

    category = "timeout"
    retryable = True


class NetworkError(ProviderError):
    """Transport-level failure (DNS, TLS, reset)."""

    category = "network"
    retryable = True


class CancelledError(ProviderError):
    """Consumer cancelled. Consumption stopped; provider work may continue.

    This name is deliberately distinct from ``asyncio.CancelledError``:
    *stopping consumption of our own adapter* is not the same event as
    *cancelling provider computation or billing*. See ``tts.py``.
    """

    category = "cancelled"


class BudgetExceededError(ProviderError):
    """A probe safety limit would be crossed.

    Raised before the operation is issued, never after.
    """

    category = "budget_exceeded"


RETRYABLE_CATEGORIES: Final[frozenset[str]] = frozenset(
    {
        RateLimitError.category,
        UpstreamTimeoutError.category,
        NetworkError.category,
    }
)


def is_retryable(exc: BaseException) -> bool:
    """True only for bounded transient categories.

    Authentication, invalid input, protocol and configuration failures are
    permanent for a given request shape and are never retried.
    """
    return isinstance(exc, ProviderError) and exc.category in RETRYABLE_CATEGORIES
