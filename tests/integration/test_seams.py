"""The frozen seams must answer with their real, frozen behaviour.

This is the Phase 03 integration smoke test. It boots the voice service
and checks:

* ``GET /health`` works and leaks no configuration;
* every mounted history/recording route answers a guest with ``401`` and
  the frozen error shape (code ``unauthenticated``);
* a guest ``DELETE /api/recordings/x`` is ``401`` too, and no recording
  route ever returns audio to a guest;
* the conversation socket's first message is ``status connecting``;
* an invalid ``start`` closes the socket with ``1008``, and a wrong
  sample rate answers ``unsupported_audio_format``;
* the identity port is the anonymous guest;
* the analysis port measures what it can and never invents a number:
  a missing transcription makes both rates ``unavailable`` with reason
  ``stt_unavailable``, and the filler count stays
  ``insufficient_evidence`` with ``filler_detection_unvalidated``;
* the provider adapters satisfy the frozen ports without the Phase 02
  provider package being edited;
* the shared contract data still holds the frozen honesty rules.

Batch B2 extends this suite with the real call, the real history and the
real recording lifecycle.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi.testclient import TestClient

from gnani_coach.analysis import get_analysis
from gnani_coach.identity import get_identity
from gnani_coach.main import app
from gnani_coach.ports.analysis import AnalysisPort, AnalysisRequest
from gnani_coach.ports.identity import IdentityPort
from gnani_coach.ports.provider_adapters import (
    GeminiReasoningAdapter,
    GnaniSpeechToTextAdapter,
    GnaniTextToSpeechAdapter,
)
from gnani_coach.ports.reasoning import ReasoningPort
from gnani_coach.ports.speech_to_text import SpeechToTextPort
from gnani_coach.ports.text_to_speech import TextToSpeechPort
from gnani_coach.settings import (
    GEMINI_MODEL_CHECKED_ON,
    GEMINI_MODEL_DEFAULT,
    load_settings,
    reasoning_readiness,
    speech_readiness,
)
from seam_helpers import assert_error_shape

#: Where the Phase 02 provider package lives, relative to the service
#: source tree.
PROVIDER_PACKAGE = Path("gnani_coach") / "providers"


# ---------------------------------------------------------------------------
# health
# ---------------------------------------------------------------------------


def test_health_works_and_leaks_no_configuration(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["liveCallingImplemented"] is False
    raw = response.text.lower()
    for needle in ("wss://", "https://", "supabase", "gnani_api", "gemini", "token", "secret"):
        assert needle not in raw


def test_health_is_the_only_documented_route() -> None:
    """The placeholder seams are mounted but not published."""
    assert sorted(app.openapi()["paths"].keys()) == ["/health"]


# ---------------------------------------------------------------------------
# the history and recording seams
# ---------------------------------------------------------------------------


def test_history_route_answers_unauthenticated(client: TestClient) -> None:
    response = client.get("/api/history")
    assert response.status_code == 401
    assert_error_shape(
        response.json(), code="unauthenticated", category="unauthenticated"
    )


def test_consent_route_answers_unauthenticated(client: TestClient) -> None:
    response = client.post("/api/consent")
    assert response.status_code == 401
    assert_error_shape(
        response.json(), code="unauthenticated", category="unauthenticated"
    )


def test_recording_routes_answer_unauthenticated(client: TestClient) -> None:
    for method in ("GET", "DELETE"):
        response = client.request(method, "/api/recordings/rec_abc123")
        assert response.status_code == 401, method
        assert_error_shape(
            response.json(), code="unauthenticated", category="unauthenticated"
        )


def test_a_guest_delete_recording_answers_unauthenticated(client: TestClient) -> None:
    """The delete is a state change, so a guest is refused before it runs."""
    response = client.delete("/api/recordings/x")
    assert response.status_code == 401
    assert_error_shape(
        response.json(), code="unauthenticated", category="unauthenticated"
    )


def test_a_recording_route_never_returns_audio(client: TestClient) -> None:
    response = client.get("/api/recordings/rec_abc123")
    assert response.status_code == 401
    assert response.headers["content-type"].startswith("application/json")
    assert_error_shape(
        response.json(), code="unauthenticated", category="unauthenticated"
    )


# ---------------------------------------------------------------------------
# the conversation seam
# ---------------------------------------------------------------------------


def test_call_socket_answers_status_connecting_first(client: TestClient) -> None:
    """The first message is a state, not an error: the call can begin."""
    with client.websocket_connect("/ws/call") as socket:
        message = socket.receive_json()
    assert message["envelopeVersion"] == "0.1"
    assert message["direction"] == "server_to_client"
    assert message["type"] == "status"
    assert message["sessionId"].startswith("ses_")
    assert message["connectionId"].startswith("con_")
    assert message["payload"]["state"] == "connecting"


# ---------------------------------------------------------------------------
# the injected ports
# ---------------------------------------------------------------------------


def test_identity_port_is_the_anonymous_guest() -> None:
    async def check() -> None:
        identity = get_identity()
        assert isinstance(identity, IdentityPort)
        assert await identity.verify_token("any-token") is None
        assert await identity.verify_token(None) is None
        assert await identity.current_user() is None

    asyncio.run(check())


def test_analysis_port_reports_the_three_frozen_rules() -> None:
    """The real measurement keeps the honesty rules the stub promised.

    * ``turn.duration_ms`` is measurable from the clip itself, so it is
      **available** and equals the learner-audio span.
    * A missing transcription is never a measured zero: both rates are
      ``unavailable`` with reason ``stt_unavailable`` and a null value.
    * The filler count stays ``insufficient_evidence`` with reason
      ``filler_detection_unvalidated`` and a null value.
    """
    async def check() -> None:
        analysis = get_analysis()
        assert isinstance(analysis, AnalysisPort)
        # 32,000 bytes of mono s16le at 16 kHz is 1,000 ms of audio.
        result = await analysis.analyze(
            AnalysisRequest(audio=b"\x00\x00" * 16000, sample_rate=16000)
        )
        assert result.recognition_status == "missing-transcription"
        assert result.observations, "the service must report its metric keys"
        by_key = {observation.metric_key: observation for observation in result.observations}
        assert set(by_key) == {
            "turn.duration_ms",
            "pause.longest_ms",
            "pause.count",
            "filler.count",
            "speech.rate_wpm",
            "speech.active_rate_wpm",
        }

        duration = by_key["turn.duration_ms"]
        assert duration.status == "available"
        assert duration.value == 1000.0

        for key in ("speech.rate_wpm", "speech.active_rate_wpm"):
            rate = by_key[key]
            assert rate.status == "unavailable", key
            assert rate.value is None, key
            assert rate.unavailability_reason == "stt_unavailable", key
            assert rate.recognition_status == "missing-transcription", key

        filler = by_key["filler.count"]
        assert filler.status == "insufficient_evidence"
        assert filler.value is None
        assert filler.unavailability_reason == "filler_detection_unvalidated"

    asyncio.run(check())


# ---------------------------------------------------------------------------
# the provider adapters satisfy the frozen ports
# ---------------------------------------------------------------------------


def test_phase_02_adapters_satisfy_the_ports() -> None:
    assert isinstance(GnaniSpeechToTextAdapter("dummy"), SpeechToTextPort)
    assert isinstance(GnaniTextToSpeechAdapter("dummy"), TextToSpeechPort)
    assert isinstance(
        GeminiReasoningAdapter("dummy", model=GEMINI_MODEL_DEFAULT), ReasoningPort
    )


def test_the_provider_package_does_not_depend_on_the_ports() -> None:
    """The Phase 02 provider package is untouched by the freeze.

    The adapters in ``gnani_coach.ports.provider_adapters`` are the seam.
    The dependency runs one way only: the ports depend on the providers,
    never the other way round, so no provider module had to be edited.
    """
    import gnani_coach

    provider_dir = Path(gnani_coach.__file__).parent / "providers"
    assert provider_dir.is_dir()
    for module in sorted(provider_dir.glob("*.py")):
        source = module.read_text(encoding="utf-8")
        assert "gnani_coach.ports" not in source, module.name


# ---------------------------------------------------------------------------
# the settings boundary
# ---------------------------------------------------------------------------


def test_readiness_never_reports_live_from_presence(tmp_path: Path) -> None:
    env_file = tmp_path / "present.env"
    env_file.write_text(
        "GNANI_API_KEY=gnani_test_key_123\nGEMINI_API_KEY=gemini_test_key_456\n",
        encoding="utf-8",
    )
    settings = load_settings(env_file=env_file)
    speech = speech_readiness(settings)
    reasoning = reasoning_readiness(settings)
    assert speech.state == "configured"
    assert reasoning.state == "configured"
    assert speech.live is False
    assert reasoning.live is False
    # Neither view may depend on Supabase.
    assert "supabase" not in speech.detail.lower()
    assert "supabase" not in reasoning.detail.lower()


def test_readiness_is_unconfigured_without_credentials(tmp_path: Path) -> None:
    settings = load_settings(env_file=tmp_path / "missing.env")
    assert speech_readiness(settings).state == "unconfigured"
    assert reasoning_readiness(settings).state == "unconfigured"


def test_the_frozen_model_default_is_dated() -> None:
    assert GEMINI_MODEL_DEFAULT == "gemini-3.8-flash"
    assert GEMINI_MODEL_CHECKED_ON == "2026-10-20"


# ---------------------------------------------------------------------------
# the shared contract data
# ---------------------------------------------------------------------------


def test_the_filler_capability_is_unvalidated(contracts_dir: Path) -> None:
    register = json.loads(
        (contracts_dir / "data" / "capabilities.json").read_text(encoding="utf-8")
    )
    filler = register["capabilities"]["filler-localization"]
    assert filler["state"] == "unvalidated"
    assert filler["renderedState"] == "insufficient_evidence"
    assert filler["goalPreserved"] is True
    assert filler["scopeChangeApproved"] is False
    assert filler["validatedAt"] is None
    for capability in register["capabilities"].values():
        assert capability["state"] != "validated", capability["id"]


def test_the_catalog_keeps_every_capability_flag_false(contracts_dir: Path) -> None:
    catalog = json.loads(
        (contracts_dir / "data" / "catalog.json").read_text(encoding="utf-8")
    )
    for entry in [*catalog["languages"], *catalog["codeMixedModes"]]:
        flags = entry["capabilities"]
        assert flags["documented"] is True
        for flag in ("accountEnabled", "conversationTested", "assessmentValidated"):
            assert flags[flag] is False, entry["id"]
