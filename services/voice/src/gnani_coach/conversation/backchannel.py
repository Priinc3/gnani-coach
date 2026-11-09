"""Short spoken reactions: the immediate acknowledgement and "mm-hmm".

Phase 19. The learner asked for a call that feels alive: small spoken
reactions while they talk, and a fast first sound when they stop. Both use
**pre-synthesised** clips: one TTS synthesis per phrase per language, cached
in memory, never one per turn. The clips are sent as their own turn id with
``kind: "backchannel"`` so the client treats them as low priority.

What this module does not do
----------------------------
* It never reads back or paraphrases the learner's words: a filler is a
  fixed phrase and the transcript is not an input.
* It never uses a timer to decide that the learner paused. The runtime
  calls it only from a real silence gap measured by the endpointing gate.
* It does not claim the provider was cancelled: the cache is local PCM.
"""

from __future__ import annotations

import asyncio
import time

from gnani_coach.conversation.audio import pcm_duration_ms
from gnani_coach.conversation.config import (
    BACKCHANNEL_ENABLED,
    MAX_BACKCHANNEL_AUDIO_MS,
    MAX_BACKCHANNEL_CLIPS,
)
from gnani_coach.ports.text_to_speech import SpeechChunk, TtsOpenRequest

#: The phrases a turn may be acknowledged with. English is the only
#: language whose voice has passed a live check here, so every other
#: language falls back to these; the report says so plainly.
ENGLISH_PHRASES: tuple[str, ...] = ("Mm-hmm.", "Okay.", "Right.", "I see.")

#: The one phrase used mid-sentence. A longer reaction would talk over the
#: learner, which is exactly what this feature must not do.
MID_TURN_PHRASE = "Mm-hmm."

#: Process-wide clip cache: ``(voice, model, language, phrase) -> PCM``.
_CLIPS: dict[tuple[str, str, str, str], bytes] = {}
#: A per-loop lock, because an ``asyncio.Lock`` binds to the loop that
#: first awaits it and the tests use a fresh loop per case.
_LOCK: asyncio.Lock | None = None
_LOCK_LOOP: asyncio.AbstractEventLoop | None = None


def _lock_for_loop() -> asyncio.Lock:
    global _LOCK, _LOCK_LOOP
    loop = asyncio.get_running_loop()
    if _LOCK is None or _LOCK_LOOP is not loop:
        _LOCK = asyncio.Lock()
        _LOCK_LOOP = loop
    return _LOCK


def clear_cache() -> None:
    """Drop every cached clip. Used by tests; never by a call."""
    _CLIPS.clear()


def phrases_for(language: str) -> tuple[str, ...]:
    """The phrases for a language.

    Only English has a voice that has passed a live check, so a language
    without validated phrases uses English rather than inventing a
    translation.
    """
    del language
    return ENGLISH_PHRASES


class BackchannelCache:
    """Lazily synthesise and cache the fixed reaction clips."""

    def __init__(
        self,
        *,
        tts: object,
        voice: str,
        model: str,
        language: str,
        enabled: bool = True,
    ) -> None:
        self._tts = tts
        self._voice = voice
        self._model = model
        self._language = language
        self._enabled = bool(enabled and BACKCHANNEL_ENABLED)
        self._rotation = 0
        self._last_phrase: str | None = None
        #: Content-free counters, logged by the runtime.
        self.synthesised = 0
        self.skipped_too_long = 0

    @property
    def enabled(self) -> bool:
        return self._enabled

    async def warm(self) -> None:
        """Synthesise every phrase once, ahead of the first turn.

        Called in the background as the call opens. Without it the first
        acknowledgement pays the whole TTS latency, which is exactly the
        dead air this phase exists to remove.
        """
        if not self._enabled:
            return
        for phrase in phrases_for(self._language):
            await self.clip(phrase)

    def next_phrase(self) -> str:
        """Rotate the acknowledgement so it is not repeated twice in a row."""
        phrases = phrases_for(self._language)
        if len(phrases) == 1:
            return phrases[0]
        for _ in range(len(phrases)):
            candidate = phrases[self._rotation % len(phrases)]
            self._rotation += 1
            if candidate != self._last_phrase:
                self._last_phrase = candidate
                return candidate
        return phrases[0]

    async def clip(self, phrase: str) -> bytes | None:
        """The PCM of one phrase, synthesised once and cached.

        ``None`` means the clip is unavailable (the provider failed) or it
        is longer than the bound, in which case the caller simply stays
        silent: a long filler would delay the real reply.
        """
        if not self._enabled:
            return None
        key = (self._voice, self._model, self._language, phrase)
        cached = _CLIPS.get(key)
        if cached is not None:
            return cached
        async with _lock_for_loop():
            cached = _CLIPS.get(key)
            if cached is not None:
                return cached
            pcm = await self._synthesise(phrase)
            if pcm is None:
                return None
            if pcm_duration_ms(pcm) > MAX_BACKCHANNEL_AUDIO_MS:
                self.skipped_too_long += 1
                return None
            if len(_CLIPS) >= MAX_BACKCHANNEL_CLIPS:
                return None
            _CLIPS[key] = pcm
            self.synthesised += 1
            return pcm

    async def _synthesise(self, phrase: str) -> bytes | None:
        session = self._tts.open_session(
            TtsOpenRequest(
                text=phrase,
                voice=self._voice,
                model=self._model,
                language=self._language,
            )
        )
        chunks: list[bytes] = []

        async def collect(chunk: SpeechChunk) -> None:
            if chunk.data:
                chunks.append(chunk.data)

        try:
            await session.synthesize(on_chunk=collect)
        except Exception:  # noqa: BLE001 - a filler is optional, never fatal
            return None
        finally:
            try:
                await session.aclose(reason="backchannel")
            except Exception:  # noqa: BLE001 - close must not mask
                pass
        if not chunks:
            return None
        return b"".join(chunks)


def now_ms() -> int:
    """A monotonic millisecond clock for the backchannel gates."""
    return int(time.monotonic() * 1000.0)
