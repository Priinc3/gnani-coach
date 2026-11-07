"""Building the provider ports for one call.

Every provider is reached through a **port**. The Phase 02 provider
clients are never edited: the wrappers in
:mod:`gnani_coach.ports.provider_adapters` make them satisfy the ports,
and this module only chooses the configuration.

Two things are decided here:

* the **budget**. Every wire attempt of the call is admitted by the
  Phase 02 budget before it starts, so a mistyped loop cannot turn into
  an unbounded spend. The per-call allowance is tighter than the Phase 02
  global ceiling.
* the **language pairing**. The practice language id of the ``start``
  event is turned into the recogniser's language code and the
  synthesiser's language code through the frozen catalog.

When a credential is missing, the factory returns ``None`` and the call
answers ``not_available``: it never half-starts.
"""

from __future__ import annotations

from gnani_coach.conversation import catalog
from gnani_coach.conversation.config import (
    MAX_CALL_AUDIO_SECONDS,
    MAX_CALL_CONNECTIONS,
    MAX_CALL_WIRE_ATTEMPTS,
    REASONING_ATTEMPT_TIMEOUT_S,
    REASONING_DEADLINE_S,
)
from gnani_coach.conversation.runtime import CallProviders
from gnani_coach.ports.provider_adapters import (
    GeminiReasoningAdapter,
    GnaniSpeechToTextAdapter,
    GnaniTextToSpeechAdapter,
)
from gnani_coach.providers.limits import ProbeBudget
from gnani_coach.settings import AppSettings, resolved_gemini_model


def build_call_providers(
    settings: AppSettings,
    *,
    practice_language_id: str,
    budget: ProbeBudget | None = None,
) -> CallProviders | None:
    """Build the provider ports for one call, or ``None``.

    ``None`` means the call cannot run: a credential is missing or the
    practice language is not in the frozen catalog.

    ``budget`` lets a caller supply its own allowance — the live test
    uses it to count the wire attempts of one chain. When it is ``None``
    the per-call allowance of this module is used.
    """
    voice_key = settings.voice.api_key
    reasoning_key = settings.gemini.api_key
    if voice_key is None or reasoning_key is None:
        return None

    language = catalog.language(practice_language_id)
    if language is None or not language.stt_code or not language.tts_code:
        return None

    if budget is None:
        budget = ProbeBudget(
            max_operations=MAX_CALL_WIRE_ATTEMPTS,
            max_audio_seconds=MAX_CALL_AUDIO_SECONDS,
            max_connections=MAX_CALL_CONNECTIONS,
        )
    return CallProviders(
        stt=GnaniSpeechToTextAdapter(
            voice_key.get_secret_value(),
            budget=budget,
            url=settings.voice.stt_ws_url,
        ),
        tts=GnaniTextToSpeechAdapter(
            voice_key.get_secret_value(),
            budget=budget,
            url=settings.voice.tts_ws_url,
        ),
        reasoning=GeminiReasoningAdapter(
            reasoning_key.get_secret_value(),
            model=resolved_gemini_model(settings),
            budget=budget,
            attempt_timeout=REASONING_ATTEMPT_TIMEOUT_S,
            deadline=REASONING_DEADLINE_S,
        ),
        language_code=language.stt_code,
        stt_vad=settings.voice.vad_settings(),
        tts_voice=catalog.voice_for(
            language.tts_code, fallback=settings.voice.tts_voice
        ),
        tts_model=settings.voice.tts_model,
        tts_language=language.tts_code,
    )
