"""Shared setup for the assembled stack.

The launcher (browser suite) and the assembled Python tests must use the
**same** environment and the **same** two injection points, or they would
be testing different products. This module is that one definition.

Only the provider ports are replaced:

* ``build_call_providers`` — the factory the router resolves at call time;
* ``get_analysis`` — the accessor the options builder resolves at call time.

The runtime, router, envelope, identity verifier, stores and browser are
the product's own code.
"""

from __future__ import annotations

import importlib
import json
import os
from typing import Any

VOICE_PORT = 8017
FAKE_SUPABASE_PORT = 8018
CONTROL_PORT = 8019
WEB_PORT = 3107

SUPABASE_URL = f"http://127.0.0.1:{FAKE_SUPABASE_PORT}"
WEB_ORIGIN = f"http://127.0.0.1:{WEB_PORT}"
VOICE_HTTP_URL = f"http://127.0.0.1:{VOICE_PORT}"


def configure_environment() -> None:
    """Every value is explicit: no ambient development default is trusted."""
    values = {
        "SUPABASE_URL": SUPABASE_URL,
        "SUPABASE_PUBLISHABLE_KEY": "assembled-publishable-key",
        "SUPABASE_SERVICE_ROLE_KEY": "assembled-service-role-key",
        "SPEAKING_COACH_ALLOWED_ORIGINS": json.dumps(
            [WEB_ORIGIN, f"http://localhost:{WEB_PORT}"]
        ),
        "SPEAKING_COACH_ENVIRONMENT": "local",
        "SPEAKING_COACH_MAX_CONNECTIONS_PER_ADDRESS": "4",
        "SPEAKING_COACH_MAX_CONNECTIONS_PER_USER": "2",
        "SPEAKING_COACH_MAX_CONNECTIONS_PER_PROCESS": "10",
        "SPEAKING_COACH_HTTP_REQUESTS_PER_MINUTE": "6000",
        "SPEAKING_COACH_WS_HANDSHAKES_PER_MINUTE": "600",
        "SPEAKING_COACH_HEALTH_TOKEN": "assembled-health-token",
        # Provider keys are present so the real *configuration path* runs;
        # the ports are replaced before any provider is constructed.
        "GNANI_API_KEY": "assembled-gnani-key",
        "GEMINI_API_KEY": "assembled-gemini-key",
        "GEMINI_MODEL": "assembled-model",
        "GNANI_STT_WS_URL": "wss://api.vachana.ai/assembled-stt",
        "GNANI_TTS_WS_URL": "wss://api.vachana.ai/assembled-tts",
        "GNANI_VOICE": "Kaveri",
        "GNANI_TTS_MODEL": "timbre-v2.5",
    }
    for key, value in values.items():
        os.environ[key] = value


def patch_ports() -> Any:
    """Patch the two factories the product itself calls, and return the fakes."""
    fake_stack = importlib.import_module("fake_stack")
    analysis_module = importlib.import_module("gnani_coach.analysis")
    # ``gnani_coach.conversation`` exports an object named ``router``, so
    # ``import ... .router as m`` binds the APIRouter, not the module.
    # ``import_module`` returns the actual module whose global the runtime
    # factory resolves at call time.
    router_module = importlib.import_module("gnani_coach.conversation.router")

    def fake_providers(settings: Any, *, practice_language_id: str, budget: Any = None) -> Any:
        del settings, budget
        return fake_stack.build_fake_providers(practice_language_id)

    router_module.build_call_providers = fake_providers  # type: ignore[assignment]
    analysis_module.get_analysis = lambda: fake_stack.FAKE_ANALYSIS  # type: ignore[assignment]
    return fake_stack
