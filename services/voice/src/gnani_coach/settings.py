"""Central configuration boundary for the voice service.

Design rules for this phase:

- Parsing lives here and only here. ``main`` does not read environment
  variables directly.
- Provider credentials are separate, prefixed settings objects
  (``GNANI_*``, ``GEMINI_*``, ``SUPABASE_*``); app-level values use the
  ``SPEAKING_COACH_*`` prefix. Secrets are ``SecretStr`` so they do not
  leak through reprs or logs.
- Everything is optional. Missing credentials never crash foundation
  startup, and their presence never makes provider readiness "live":
  ``provider_readiness()`` reports ``unavailable`` and ``live=False`` in
  Phase 01 no matter what is configured.
- No model id or endpoint beyond the reviewed documentation is defaulted.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# Reviewed realtime documentation endpoints only (checked 2026-10-16).
# https://docs.gnani.ai/api/STT/stt-websocket and
# https://docs.gnani.ai/api/TTS/tts-websocket
GNANI_STT_WS_URL_DEFAULT = "wss://api.vachana.ai/stt/v3/stream"
GNANI_TTS_WS_URL_DEFAULT = "wss://api.vachana.ai/api/v1/tts"


class GnaniSpeechSettings(BaseSettings):
    """Gnani speech (STT/TTS) credentials and endpoints.

    The key is optional: the foundation build never makes a provider call.
    """

    model_config = SettingsConfigDict(env_prefix="GNANI_", extra="ignore")

    api_key: SecretStr | None = None
    stt_ws_url: str = GNANI_STT_WS_URL_DEFAULT
    tts_ws_url: str = GNANI_TTS_WS_URL_DEFAULT


class GeminiSettings(BaseSettings):
    """Google Gemini credentials for later coaching/analysis phases.

    ``model`` stays ``None`` until Phase 03 selects a model from evidence;
    guessing a model id here would be inventing a fact.
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
    voice: GnaniSpeechSettings = Field(default_factory=GnaniSpeechSettings)
    gemini: GeminiSettings = Field(default_factory=GeminiSettings)
    supabase: SupabaseSettings = Field(default_factory=SupabaseSettings)


@dataclass(frozen=True)
class ProviderReadiness:
    """Truthful provider status. ``configured`` is not ``live``."""

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


def provider_readiness(settings: AppSettings | None = None) -> ProviderReadiness:
    """Describe provider readiness for the current configuration.

    Always ``unavailable`` in Phase 01: the boundary can be configured, but no
    adapter, connection or verification exists yet. ``configured`` only says
    whether all four credential slots are present, and it must never be shown
    as "healthy" or "live".
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
            "Phase 01 defines the configuration boundary only; no provider adapter "
            "is implemented or verified, regardless of which credentials exist."
        ),
    )
