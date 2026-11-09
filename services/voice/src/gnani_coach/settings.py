"""Central configuration boundary for the voice service.

Design rules for this phase:

- Parsing lives here and only here. ``main`` does not read environment
  variables directly.
- Provider credentials are separate, prefixed settings objects
  (``GNANI_*``, ``GEMINI_*``, ``SUPABASE_*``); app-level values use the
  ``SPEAKING_COACH_*`` prefix. Secrets are ``SecretStr`` so they do not
  leak through reprs or logs.
- Everything is optional. Missing credentials never crash startup, and
  their presence never makes provider readiness "live".
- Readiness is reported per provider, and never depends on Supabase:
  ``speech_readiness()`` describes Gnani only and ``reasoning_readiness()``
  describes Gemini only. The combined ``provider_readiness()`` view still
  folds Supabase in and still reports ``unavailable``.
- The states are ``unconfigured`` (no credential), ``configured`` (the
  credential name is present) and ``verified`` (a live check has actually
  passed against this configuration in this process). Presence alone never
  produces ``verified`` and never produces ``live``.

Phase 03 additions (contract freeze)
-------------------------------------
* ``GEMINI_MODEL_DEFAULT`` freezes the reasoning model id. It is a module
  constant rather than a pydantic default on purpose: the Phase 01 test
  ``test_defaults_use_only_reviewed_documentation_endpoints`` asserts that
  ``settings.gemini.model is None`` when nothing is configured, and that
  test file belongs to Phase 01. ``resolved_gemini_model()`` is the single
  place that applies the frozen default, so the effective default is one
  value with one citation.
* A TTS model/voice selector. The voice catalog is model-specific and a
  mismatched pair is a hard error from the provider, so the pairing is
  configuration rather than a constant buried in a call site.
* A VAD settings object. The VAD headers are fixed for the life of a
  connection, so a round-boundary change needs a reconnect; the *current*
  values are carried across that reconnect from this one object.

Phase 03 FIX-1 additions
------------------------
* ``SPEAKING_COACH_ALLOWED_ORIGINS`` — the browser-origin allowlist. It
  is one list with two jobs: the CORS allowlist of the HTTP routes and
  the allowlist of the WebSocket handshake. The default is the local web
  origin only, and the wildcard ``*`` is refused **while the settings
  parse**, so a wildcard can never reach the middleware.

Nothing in this module logs, prints or formats a secret value.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from gnani_coach.providers.stt import VadSettings

# Reviewed realtime documentation endpoints only (checked 2026-10-16).
# https://docs.gnani.ai/api/STT/stt-websocket and
# https://docs.gnani.ai/api/TTS/tts-websocket
GNANI_STT_WS_URL_DEFAULT = "wss://api.vachana.ai/stt/v3/stream"
GNANI_TTS_WS_URL_DEFAULT = "wss://api.vachana.ai/api/v1/tts"

#: The reasoning model id frozen by Phase 03.
#:
#: Observed working in the Phase 02 live chain on 2026-10-18, and listed as
#: a stable model on Google's published models page, checked 2026-10-20:
#: https://ai.google.dev/gemini-api/docs/models ("Gemini 3.8 Flash", endpoint
#: id ``gemini-3.8-flash``).
GEMINI_MODEL_DEFAULT = "gemini-3.8-flash"
#: The date the frozen model id was checked against the published page.
GEMINI_MODEL_CHECKED_ON = "2026-10-20"
#: Where the freeze was recorded, so the citation travels with the value.
GEMINI_MODEL_SOURCE = "https://ai.google.dev/gemini-api/docs/models"

#: Text-to-speech model and voice defaults. Timbre v2.5 is the starting
#: model family; the voice catalog is model-specific (voice page read
#: 2026-10-18, https://docs.gnani.ai/api/TTS/available-voices) and each
#: v2.5 voice has one preferred language, so the runtime must pick a voice
#: that matches the practice language. "Kaveri" is the English (en-IN)
#: voice used in the Phase 02 live chain.
TTS_MODEL_DEFAULT = "timbre-v2.5"
TTS_VOICE_DEFAULT = "Kaveri"

#: The browser origins allowed by default.
#:
#: The default is the **local web origin only** — ``http://localhost:3000``
#: — because that is the origin the Next.js app sends while it runs on the
#: developer machine. A deployment names its real origin explicitly.
#:
#: The wildcard ``*`` is refused: it would defeat the origin check that
#: protects the call socket from cross-site WebSocket hijacking. The OWASP
#: WebSocket Security Cheat Sheet is explicit about this: "Validate the
#: Origin header on every handshake. Always use an explicit allowlist of
#: trusted origins… Avoid wildcards or substring matching which are
#: error-prone."
#: (<https://cheatsheetseries.owasp.org/cheatsheets/WebSocket_Security_Cheat_Sheet.html>,
#: checked 2026-10-20).
DEFAULT_ALLOWED_ORIGINS: tuple[str, ...] = ("http://localhost:3000",)


def normalize_origin(raw: str) -> str:
    """Normalise one origin to its canonical ``scheme://host[:port]`` form.

    The comparison of an incoming ``Origin`` header must be exact, so both
    the allowlist entries and the header value go through this one
    function. The scheme and the host are lower-cased, the default port
    for the scheme is dropped, and a trailing ``/`` is removed. Anything
    that is not a plain ``http(s)`` origin — a path, a query, a fragment,
    a credential, a wildcard — is refused with ``ValueError``.
    """
    text = raw.strip()
    if not text:
        raise ValueError("an origin may not be empty")
    parts = urlsplit(text)
    scheme = parts.scheme.lower()
    if scheme not in ("http", "https"):
        raise ValueError(f"an origin must be an http(s) URL, got {raw!r}")
    try:
        host = parts.hostname
        port = parts.port
    except ValueError as exc:  # an unparseable port
        raise ValueError(f"an origin must carry a valid port, got {raw!r}") from exc
    if not host:
        raise ValueError(f"an origin must carry a host, got {raw!r}")
    if parts.path not in ("", "/") or parts.query or parts.fragment:
        raise ValueError(
            f"an origin carries no path, query or fragment, got {raw!r}"
        )
    if parts.username or parts.password:
        raise ValueError(f"an origin carries no credentials, got {raw!r}")
    if ":" in host:  # an IPv6 literal
        host = f"[{host}]"
    default_port = {"http": 80, "https": 443}.get(scheme)
    netloc = host if port is None or port == default_port else f"{host}:{port}"
    return f"{scheme}://{netloc}"


def parse_allowed_origins(value: object) -> list[str]:
    """Parse the origin allowlist from its environment representation.

    Two forms are accepted, because both are readable in an ``.env`` file:

    * a JSON array — ``SPEAKING_COACH_ALLOWED_ORIGINS='["https://a.example"]'``;
    * a comma-separated list — ``SPEAKING_COACH_ALLOWED_ORIGINS=https://a.example,https://b.example``.

    Every entry is normalised with :func:`normalize_origin`, duplicates are
    dropped and the order is kept. An unset or empty value means the
    default allowlist (:data:`DEFAULT_ALLOWED_ORIGINS`).

    ``ValueError`` is raised — and therefore the settings **parse fails** —
    for a wildcard, for a malformed entry and for an empty list. The
    wildcard is refused on purpose; see :data:`DEFAULT_ALLOWED_ORIGINS`.
    """
    if value is None:
        return list(DEFAULT_ALLOWED_ORIGINS)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return list(DEFAULT_ALLOWED_ORIGINS)
        if text.startswith("["):
            try:
                decoded = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ValueError(f"the origin allowlist is not valid JSON: {exc}") from exc
            if not isinstance(decoded, list):
                raise ValueError("the origin allowlist must be a JSON array of origins")
            entries: list[object] = decoded
        else:
            entries = text.split(",")
    elif isinstance(value, (list, tuple)):
        entries = list(value)
    else:
        raise ValueError("the origin allowlist must be a list of origins")

    origins: list[str] = []
    for entry in entries:
        if not isinstance(entry, str):
            raise ValueError(f"an allowed origin must be a string, got {entry!r}")
        candidate = entry.strip()
        if candidate == "*":
            raise ValueError(
                "the wildcard '*' is not an allowed origin: use an explicit "
                "allowlist of trusted origins"
            )
        normalized = normalize_origin(candidate)
        if normalized not in origins:
            origins.append(normalized)
    if not origins:
        raise ValueError("the origin allowlist may not be empty")
    return origins


class GnaniSpeechSettings(BaseSettings):
    """Gnani speech (STT/TTS) credentials, endpoints and voice selection.

    The key is optional: nothing crashes when it is missing, and its
    presence is never reported as a live provider.
    """

    model_config = SettingsConfigDict(env_prefix="GNANI_", extra="ignore")

    api_key: SecretStr | None = None
    stt_ws_url: str = GNANI_STT_WS_URL_DEFAULT
    tts_ws_url: str = GNANI_TTS_WS_URL_DEFAULT
    #: Text-to-speech model id. A voice that does not belong to this model
    #: is rejected by the provider, so the two are configured together.
    tts_model: str = TTS_MODEL_DEFAULT
    #: Text-to-speech voice id.
    tts_voice: str = TTS_VOICE_DEFAULT
    #: The five documented VAD headers. They are fixed for the life of a
    #: connection, so a change needs a reconnect; the values are carried
    #: across that reconnect from :meth:`vad_settings`.
    vad_threshold: float = 0.7
    #: Phase 19: the conversation range on the STT page is 600-900 ms; the
    #: default 500 ms added avoidable delay before the recogniser closed a
    #: segment. 600 is the documented floor for conversation.
    #: https://docs.gnani.ai/api/STT/stt-websocket (VAD tuning), read 2026-11-09.
    vad_min_silence_ms: int = 600
    vad_min_speech_ms: int = 100
    vad_min_segment_ms: int = 120
    vad_max_speech_s: float | None = None

    def vad_settings(self) -> VadSettings:
        """Build the one VAD settings object for this configuration.

        The object is immutable and is handed to every connection, so a
        reconnect after a round-boundary change keeps the same values
        instead of silently reverting to the defaults. The provider's own
        bounds are checked here, not at import time.
        """
        vad = VadSettings(
            threshold=self.vad_threshold,
            min_silence_ms=self.vad_min_silence_ms,
            min_speech_ms=self.vad_min_speech_ms,
            min_segment_ms=self.vad_min_segment_ms,
            max_speech_s=self.vad_max_speech_s,
        )
        vad.validate()
        return vad


class GeminiSettings(BaseSettings):
    """Google Gemini credentials for the coaching/analysis path.

    ``model`` stays ``None`` when nothing is configured, so an unconfigured
    service never silently picks a model. The frozen default lives in
    :data:`GEMINI_MODEL_DEFAULT` and is applied by
    :func:`resolved_gemini_model`.
    """

    model_config = SettingsConfigDict(env_prefix="GEMINI_", extra="ignore")

    api_key: SecretStr | None = None
    model: str | None = None


class SupabaseSettings(BaseSettings):
    """Supabase identity/storage settings for later phases. Nothing connects."""

    model_config = SettingsConfigDict(env_prefix="SUPABASE_", extra="ignore")

    url: str | None = None
    service_role_key: SecretStr | None = None


class AppSettings(BaseSettings):
    """Top-level settings for the voice service."""

    model_config = SettingsConfigDict(env_prefix="SPEAKING_COACH_", extra="ignore")

    environment: str = "local"
    #: The browser origins allowed to reach this service.
    #:
    #: **One list, two jobs.** It is the CORS allowlist of the HTTP routes
    #: *and* the allowlist of the WebSocket handshake, so the browser
    #: origin that may call ``GET /api/history`` is exactly the origin
    #: that may open ``/ws/call``. The default is the local web origin
    #: only; the wildcard ``*`` is refused at parse time.
    #:
    #: The value is read from ``SPEAKING_COACH_ALLOWED_ORIGINS`` as a JSON
    #: array or as a comma-separated list.
    allowed_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: list(DEFAULT_ALLOWED_ORIGINS)
    )
    #: Per-process concurrency caps. They are read here so an operator can
    #: lower them without editing code. The router's registry is configured
    #: from these values at startup. Counts are per process: a multi-worker
    #: deployment multiplies the effective bound by the worker count.
    max_connections_per_address: int = Field(default=4, ge=1, le=1000)
    max_connections_per_user: int = Field(default=2, ge=1, le=1000)
    max_connections_per_process: int = Field(default=10, ge=1, le=1000)
    #: Per-address request budgets. They are intentionally generous for the
    #: local product and are a coarse resource guard, not a billing meter.
    http_requests_per_minute: int = Field(default=120, ge=1, le=100000)
    ws_handshakes_per_minute: int = Field(default=120, ge=1, le=100000)
    #: Bearer token for the content-free latency endpoint. When unset the
    #: endpoint is not mounted at all (404), so an operator opts in.
    health_token: SecretStr | None = None
    #: Phase 19: spoken reactions ("mm-hmm", the immediate acknowledgement).
    #: On by default; ``SPEAKING_COACH_BACKCHANNEL_ENABLED=false`` turns
    #: every one of them off without a code change.
    backchannel_enabled: bool = True
    voice: GnaniSpeechSettings = Field(default_factory=GnaniSpeechSettings)
    gemini: GeminiSettings = Field(default_factory=GeminiSettings)
    supabase: SupabaseSettings = Field(default_factory=SupabaseSettings)

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def _validate_allowed_origins(cls, value: object) -> list[str]:
        """Refuse a wildcard or a malformed origin while the settings parse."""
        return parse_allowed_origins(value)

    @model_validator(mode="after")
    def _production_boundary(self) -> "AppSettings":
        """Refuse the two configuration mistakes that are unsafe in production.

        1. A production deployment may not keep a loopback origin on the
           allowlist. A localhost/127.0.0.1 origin is a development value;
           allowing it in production would let a local page reach the call
           socket (OWASP WebSocket Security Cheat Sheet: use an explicit
           allowlist of trusted origins).
        2. A Supabase key without a Supabase URL can never verify a caller.
           Refusing at startup is clearer than failing every token as a
           guest in production.
        """
        if self.environment.strip().lower() == "production":
            loopback = [
                origin
                for origin in self.allowed_origins
                if urlsplit(origin).hostname in ("localhost", "127.0.0.1", "::1")
            ]
            if loopback:
                raise ValueError(
                    "a production deployment may not allow a loopback origin: "
                    f"{loopback[0]!r}"
                )
            service_key = self.supabase.service_role_key
            if service_key is not None and service_key.get_secret_value().strip():
                if not (self.supabase.url or "").strip():
                    raise ValueError(
                        "SUPABASE_URL is required when a Supabase key is configured"
                    )
        return self


@dataclass(frozen=True)
class ProviderReadiness:
    """Truthful provider status. ``configured`` is not ``live``.

    ``state`` is one of:

    * ``unconfigured`` — the credential is absent;
    * ``configured`` — the credential name is present, but no live check
      has passed against this configuration;
    * ``verified`` — a live check has passed against this configuration in
      this process;
    * ``unavailable`` — the combined view, which also requires Supabase and
      therefore cannot be resolved by a single provider.

    ``live`` is never set from configuration. It means "a provider session
    is open right now", and no code path in this phase opens one.
    """

    state: str
    configured: bool
    live: bool
    detail: str


def load_settings(env_file: str | Path | None = None) -> AppSettings:
    """Build settings for the current environment.

    Priority: explicit init values > environment variables > ``env_file`` >
    defaults. A missing ``env_file`` is fine. Tests use this factory with a
    temporary file for hermetic runs; the running service uses the process
    environment only (no implicit ``.env`` is read).

    Note: ``env_file`` is passed to each nested provider settings object
    explicitly, because nested ``BaseSettings`` do not inherit the parent's
    file argument.
    """
    return AppSettings(
        _env_file=env_file,
        voice=GnaniSpeechSettings(_env_file=env_file),
        gemini=GeminiSettings(_env_file=env_file),
        supabase=SupabaseSettings(_env_file=env_file),
    )


def resolved_gemini_model(settings: AppSettings | None = None) -> str:
    """The reasoning model id to use.

    The configured ``GEMINI_MODEL`` wins; otherwise the Phase 03 frozen
    default is used. The default is documented with its access date and its
    source in :data:`GEMINI_MODEL_DEFAULT`.
    """
    resolved = settings if settings is not None else load_settings()
    configured = resolved.gemini.model
    if configured and configured.strip():
        return configured.strip()
    return GEMINI_MODEL_DEFAULT


def provider_readiness(settings: AppSettings | None = None) -> ProviderReadiness:
    """Describe readiness for the whole configuration.

    Always ``unavailable``: the combined view folds in Supabase, which
    nothing connects to yet. ``configured`` only says whether all four
    credential slots are present, and it must never be shown as "healthy"
    or "live". Use :func:`speech_readiness` or :func:`reasoning_readiness`
    for a per-provider view.
    """
    resolved = settings if settings is not None else load_settings()
    configured = bool(
        resolved.voice.api_key
        and resolved.gemini.api_key
        and resolved.supabase.url
        and resolved.supabase.service_role_key
    )
    return ProviderReadiness(
        state="unavailable",
        configured=configured,
        live=False,
        detail=(
            "The combined view also requires the storage and identity "
            "configuration, which is not connected yet; no provider adapter "
            "is live, regardless of which credentials exist."
        ),
    )


def speech_readiness(
    settings: AppSettings | None = None, *, verified: bool = False
) -> ProviderReadiness:
    """Readiness of the Gnani speech path only (speech-to-text and speech).

    This view never depends on Supabase, so a probe or a call path can ask
    whether the speech providers are usable without an identity or storage
    configuration.

    ``verified`` is supplied by the caller and is the only way to reach the
    ``verified`` state: it must mean "a live check actually passed against
    this configuration in this process". Credential presence alone never
    produces it.
    """
    resolved = settings if settings is not None else load_settings()
    if not resolved.voice.api_key:
        return ProviderReadiness(
            state="unconfigured",
            configured=False,
            live=False,
            detail=(
                "No Gnani credential is configured, so speech-to-text and "
                "text-to-speech cannot be used."
            ),
        )
    state = "verified" if verified else "configured"
    detail = (
        "A live check passed against the configured Gnani credential."
        if verified
        else (
            "The Gnani credential is present, but no live check has passed "
            "against it in this process. Configured is not live."
        )
    )
    return ProviderReadiness(state=state, configured=True, live=False, detail=detail)


def reasoning_readiness(
    settings: AppSettings | None = None, *, verified: bool = False
) -> ProviderReadiness:
    """Readiness of the Gemini reasoning path only.

    This view never depends on Supabase. The model id is the configured
    ``GEMINI_MODEL`` or the frozen default from
    :func:`resolved_gemini_model`; either way, a configured model is not a
    working provider.
    """
    resolved = settings if settings is not None else load_settings()
    if not resolved.gemini.api_key:
        return ProviderReadiness(
            state="unconfigured",
            configured=False,
            live=False,
            detail=(
                "No Gemini credential is configured, so coaching replies are "
                "not available."
            ),
        )
    state = "verified" if verified else "configured"
    detail = (
        f"A live check passed against the configured Gemini credential "
        f"(model {resolved_gemini_model(resolved)})."
        if verified
        else (
            f"The Gemini credential is present and the model is "
            f"{resolved_gemini_model(resolved)}, but no live check has passed "
            "against it in this process. Configured is not live."
        )
    )
    return ProviderReadiness(state=state, configured=True, live=False, detail=detail)
