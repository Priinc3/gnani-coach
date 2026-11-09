"""The runtime's constants and caps.

Every number the call runtime uses is here, so a reviewer can see the
whole budget in one place. The values are **caps**, not targets: nothing
in the runtime raises them.

The transport caps come from the frozen contract
(``docs/contracts/call-transport.md`` §6); the rest are Phase 05's own
limits and are named as such.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# transport caps (frozen)
# ---------------------------------------------------------------------------

#: The largest JSON control message the service accepts: 16 KiB.
MAX_JSON_MESSAGE_BYTES = 16 * 1024

#: The exact size of one binary PCM frame: 512 samples at 16 kHz mono s16le.
BINARY_FRAME_BYTES = 1024

#: The only sample rate the G1 runtime accepts.
ACCEPTED_SAMPLE_RATE_HZ = 16000

#: The heartbeat interval: a ``status`` event every 15 seconds.
HEARTBEAT_INTERVAL_S = 15.0

#: A connection with no client frame for this long is closed.
IDLE_TIMEOUT_S = 90.0

#: The hard call cap: 10 minutes.
MAX_CALL_SECONDS = 600.0

#: The product's call cap, expressed in the session-settings vocabulary.
MAX_SESSION_LIMIT_SECONDS = 600

# ---------------------------------------------------------------------------
# connection limits (Phase 05)
# ---------------------------------------------------------------------------

#: How many simultaneous calls one client address may hold.
MAX_CONNECTIONS_PER_ADDRESS = 4

#: How many simultaneous calls one authenticated user may hold.
MAX_CONNECTIONS_PER_USER = 2

#: How long a client may take to send its ``start`` event.
START_DEADLINE_S = 15.0

# ---------------------------------------------------------------------------
# endpointing (Phase 05)
# ---------------------------------------------------------------------------

#: The silence that ends a learner turn, counted from the last speech.
DEFAULT_TURN_HOLD_MS = 1200

#: Phase 19: the shorter hold used when the recogniser has already closed a
#: segment for this turn. A closed segment means the learner finished an
#: utterance, so waiting the full hold only adds dead air before the model.
#: The longer hold is kept when nothing has been recognised yet, so a
#: thinking pause is not cut.
FAST_TURN_HOLD_MS = 700

#: Phase 19: how much silence inside an open turn counts as a pause for a
#: speculative reasoning call. The recogniser must already have closed a
#: segment, so the speculation has real text to work on.
SPECULATION_SILENCE_MS = 400

#: The fewest words a completed turn must carry.
DEFAULT_MIN_TURN_WORDS = 3

#: The longest a single turn may stay open.
MAX_TURN_MS = 30_000

#: The grace period for the recogniser to close a segment after the hold.
SEGMENT_GRACE_MS = 900

#: The energy gate used by the end-of-turn detector, in dBFS.
#:
#: This is an **endpointing heuristic**, not a measurement: it decides
#: when the learner has finished a turn. It is never written to the
#: durable metrics, and the measured speech regions come from the
#: analysis service's VAD, not from here.
ENDPOINTING_GATE_DBFS = -45.0

#: The energy gate's hangover: speech is held for this long after the
#: last frame above the gate, so a short gap inside a word is not a pause.
ENDPOINTING_HANGOVER_MS = 240

#: How much the hold grows when the learner asks for more time (the
#: frozen client vocabulary carries "give me a moment" as a mute event).
MUTE_HOLD_EXTENSION_MS = 5000

# ---------------------------------------------------------------------------
# backchannels (Phase 19)
# ---------------------------------------------------------------------------

#: One switch for every spoken reaction ("mm-hmm"). Set to ``False`` to
#: turn all of them off without touching the call loop.
BACKCHANNEL_ENABLED = True

#: The longest a cached filler may be, in milliseconds of audio. A filler
#: that synthesised longer is not used: the real reply must not wait behind
#: a long clip.
MAX_BACKCHANNEL_AUDIO_MS = 800

#: The most clips cached in memory at once. Four phrases in each of the
#: catalog languages is well inside this bound.
MAX_BACKCHANNEL_CLIPS = 24

#: Mid-sentence backchannels need this much continuous speech before a
#: pause is long enough to react to.
MID_TURN_MIN_SPEECH_MS = 4000

#: The pause inside a turn that may carry a mid-sentence backchannel.
MID_TURN_PAUSE_MS = 500

#: No more than one mid-sentence backchannel in this window.
MID_TURN_INTERVAL_MS = 12_000

#: No mid-sentence backchannel in the first seconds of a call.
MID_TURN_START_GRACE_MS = 3000

#: A mid-sentence backchannel is dropped if the learner resumes within this
#: long of the trigger, so it never talks over them. The phase requires at
#: least 150 ms; the reaction is also gated by the fast end-of-turn hold, so
#: a pause shorter than this window simply gets no reaction.
MID_TURN_RESUME_GUARD_MS = 150

# ---------------------------------------------------------------------------
# provider budget (Phase 05, on top of the Phase 02 limits)
# ---------------------------------------------------------------------------

#: The wire attempts one call may spend. The Phase 02 global ceiling is
#: 40; a call gets a smaller allowance of its own.
MAX_CALL_WIRE_ATTEMPTS = 36

#: The provider connections one call may open.
MAX_CALL_CONNECTIONS = 8

#: The STT submissions one call may make.
MAX_CALL_SUBMISSIONS = 24

#: The seconds of STT audio one call may submit. This is the Phase 02
#: safety ceiling; the product's wall-clock cap is
#: :data:`MAX_CALL_SECONDS`.
MAX_CALL_AUDIO_SECONDS = 300.0

#: The reasoning deadline for one coach reply, in seconds.
#:
#: Phase 18: a live long turn measured ~9.6 s for one Gemini reply with
#: ``thinking_level=low`` and 300 output tokens, so the old 20 s deadline
#: left no room for a retry. 30 s is still below the browser's 45 s idle
#: watchdog, which heartbeats reset every 15 s.
REASONING_DEADLINE_S = 30.0

#: The per-attempt ceiling for one coach reply, in seconds.
#:
#: Phase 18: raised from 10 s because a normal reply already took ~9.6 s;
#: the old bound timed out twice on a 39-word learner turn.
REASONING_ATTEMPT_TIMEOUT_S = 20.0

# ---------------------------------------------------------------------------
# content bounds (Phase 05)
# ---------------------------------------------------------------------------

#: The longest coach line the runtime will speak or send.
MAX_REPLY_CHARS = 1200

#: The longest transcript the runtime keeps in memory.
MAX_TRANSCRIPT_CHARS = 4000

#: The longest feedback line (a strength, an improvement, a note).
MAX_FEEDBACK_CHARS = 400

#: The largest recording the runtime will keep for an opted-in learner.
#:
#: A recording is only buffered when the learner granted consent *and* is
#: authenticated. The buffer is bounded so a long call cannot grow
#: without limit; when the bound is reached the recording is abandoned
#: (and no recording id is written) rather than truncated silently.
MAX_RECORDING_BYTES = 20 * 1024 * 1024

#: The largest buffer of learner audio one open turn may hold.
MAX_TURN_AUDIO_BYTES = 2 * 1024 * 1024
