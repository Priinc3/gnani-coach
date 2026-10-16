"""The configuration boundary: parsing, secrets and truthful readiness.

Credential presence must never be reported as live capability, and a missing
env file or missing credentials must never crash the foundation.
"""

from pathlib import Path

from pydantic import SecretStr

from gnani_coach.settings import load_settings, provider_readiness

PROVIDER_ENV_NAMES = (
    "GNANI_API_KEY",
    "GNANI_STT_WS_URL",
    "GNANI_TTS_WS_URL",
    "GEMINI_API_KEY",
    "GEMINI_MODEL",
    "SUPABASE_URL",
    "SUPABASE_SERVICE_ROLE_KEY",
    "SPEAKING_COACH_ENVIRONMENT",
)


def _clear_environment(monkeypatch) -> None:
    for name in PROVIDER_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)


def test_loads_with_no_credentials_and_a_missing_env_file(monkeypatch, tmp_path: Path) -> None:
    _clear_environment(monkeypatch)
    settings = load_settings(env_file=tmp_path / "missing.env")
    readiness = provider_readiness(settings)
    assert settings.voice.api_key is None
    assert readiness.state == "unavailable"
    assert readiness.live is False
    assert readiness.configured is False


def test_defaults_use_only_reviewed_documentation_endpoints(monkeypatch, tmp_path: Path) -> None:
    _clear_environment(monkeypatch)
    settings = load_settings(env_file=tmp_path / "missing.env")
    assert settings.voice.stt_ws_url == "wss://api.vachana.ai/stt/v3/stream"
    assert settings.voice.tts_ws_url == "wss://api.vachana.ai/api/v1/tts"
    # No model id is guessed in Phase 01.
    assert settings.gemini.model is None


def test_env_file_values_parse_and_configured_is_not_live(tmp_path: Path, monkeypatch) -> None:
    _clear_environment(monkeypatch)
    env_file = tmp_path / "foundation.env"
    env_file.write_text(
        "GNANI_API_KEY=gnani_test_key_123\n"
        "GEMINI_API_KEY=gemini_test_key_456\n"
        "SUPABASE_URL=https://project-ref.supabase.co\n"
        "SUPABASE_SERVICE_ROLE_KEY=service_role_test_789\n"
        "SPEAKING_COACH_ENVIRONMENT=test\n",
        encoding="utf-8",
    )
    settings = load_settings(env_file=env_file)
    readiness = provider_readiness(settings)
    assert settings.environment == "test"
    assert readiness.configured is True
    # Configured credentials still do not make this phase live.
    assert readiness.state == "unavailable"
    assert readiness.live is False


def test_secrets_do_not_leak_through_reprs(tmp_path: Path, monkeypatch) -> None:
    _clear_environment(monkeypatch)
    env_file = tmp_path / "foundation.env"
    env_file.write_text(
        "GNANI_API_KEY=gnani_test_key_123\n"
        "SUPABASE_SERVICE_ROLE_KEY=service_role_test_789\n",
        encoding="utf-8",
    )
    settings = load_settings(env_file=env_file)
    assert isinstance(settings.voice.api_key, SecretStr)
    rendered = repr(settings)
    assert "gnani_test_key_123" not in rendered
    assert "service_role_test_789" not in rendered


def test_environment_variables_take_precedence_over_env_file(tmp_path: Path, monkeypatch) -> None:
    _clear_environment(monkeypatch)
    env_file = tmp_path / "foundation.env"
    env_file.write_text("SPEAKING_COACH_ENVIRONMENT=from-file\n", encoding="utf-8")
    monkeypatch.setenv("SPEAKING_COACH_ENVIRONMENT", "from-env")
    settings = load_settings(env_file=env_file)
    assert settings.environment == "from-env"
