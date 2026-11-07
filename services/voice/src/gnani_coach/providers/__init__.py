"""Reusable provider adapters for the Gnani realtime speech path.

Phase 02 deliverable. These modules are independent of the probe CLI, of
FastAPI routes and of any future UI:

* :mod:`~gnani_coach.providers.stt` — Gnani realtime STT (Prisma)
* :mod:`~gnani_coach.providers.tts` — Gnani realtime TTS (Timbre)
* :mod:`~gnani_coach.providers.gemini` — tool-free reasoning adapter
* :mod:`~gnani_coach.providers.transport` — injectable transports, endpoint
  and key confinement
* :mod:`~gnani_coach.providers.pcm` — PCM framing and the local sample clock
* :mod:`~gnani_coach.providers.limits` — probe safety budget
* :mod:`~gnani_coach.providers.events` — provider-internal diagnostic events
* :mod:`~gnani_coach.providers.redaction` — the content-free logging policy
* :mod:`~gnani_coach.providers.errors` — explicit error categories

Importing this package performs **no** inference, opens no socket, and
downloads no model asset. Heavy or optional dependencies (``websockets``,
``google-genai``, ``onnxruntime``) are imported lazily inside the adapter
that needs them.
"""

from __future__ import annotations

from gnani_coach.providers.errors import (
    AuthenticationError,
    BudgetExceededError,
    CancelledError,
    ConfigurationError,
    EndpointError,
    InvalidRequestError,
    NetworkError,
    ProtocolError,
    ProviderError,
    RateLimitError,
    UpstreamTimeoutError,
    is_retryable,
)
from gnani_coach.providers.limits import (
    MAX_AUDIO_SECONDS,
    MAX_OPERATIONS,
    MAX_RETRIES_PER_OPERATION,
    ProbeBudget,
)
from gnani_coach.providers.redaction import redact

__all__ = [
    "AuthenticationError",
    "BudgetExceededError",
    "CancelledError",
    "ConfigurationError",
    "EndpointError",
    "InvalidRequestError",
    "MAX_AUDIO_SECONDS",
    "MAX_OPERATIONS",
    "MAX_RETRIES_PER_OPERATION",
    "NetworkError",
    "ProbeBudget",
    "ProtocolError",
    "ProviderError",
    "RateLimitError",
    "UpstreamTimeoutError",
    "is_retryable",
    "redact",
]
