# Phase 02 — handoff to Phase 03 (contract freeze)

Status: **requests and evidence, not contract changes.** Phase 02 did not
edit `packages/contracts/**`, `settings.py`, `main.py` or any web file.
Everything below is a proposal for the contract owner, with the evidence
that motivates it.

---

## 1. Provider frames — documentation samples and live captures, kept apart

Two different kinds of frame appear below. They are **never** mixed, and a
documentation sample is never presented as a capture.

| Marker | Meaning |
|---|---|
| **DOC SAMPLE** | Copied from published provider documentation. Structure only. Timestamps and identifiers are the publisher's own examples, not observations. |
| **LIVE CAPTURE** | Actually received during a Phase 02 live probe on 2026-10-18, against a synthetic fixture. |

### 1.1 STT — `connected` — **DOC SAMPLE**

```json
{
  "type": "connected",
  "message": "STT service ready — VAD service connected",
  "timestamp": "2024-01-15T10:30:00.000Z",
  "config": { "sample_rate": 16000, "chunk_size": 512 }
}
```

The `2024-01-15T10:30:00.000Z` timestamp above is the **publisher's
example value**. It is not a capture and it is not evidence of anything
this project observed.

**Observed live, beyond the documented example** — the live `config` object
also carried these keys, which are not in the published sample:

```json
"partials_enabled": false,
"partial_interval_ms": 450,
"partial_max_window_s": 15.0
```

A partial-transcript channel therefore appears to exist. **Phase 03 must not
assume it is stable**, but if it is contractable it is materially better
than waiting for a closed VAD segment — see §5.

### 1.2 STT — `speech_start` (**undocumented**)

```json
{ "type": "speech_start", "timestamp": "…", "utterance_id": "01a14e4f-2d68-7ff5-a6da-817e4f3badde" }
```

Present in live traffic on 2026-10-18; **absent from the published message
list**. The adapter records it as an `UnrecognizedFrame` observation rather
than raising or ignoring it. The `utterance_id` is stable across the
segments of one utterance — the two `spoken-known-gap` transcripts shared
`01a14e50-58ea-7ab1-95c5-c56aeac842fb` with suffix `-seg-1` / `-seg-2`.
**This is the only provider-supplied grouping identifier**, and it is the
closest thing observed to an utterance boundary.

### 1.3 STT — `transcript` — **LIVE CAPTURE**

```json
{
  "type": "transcript",
  "timestamp": "2026-10-18T09:21:44.9Z",
  "text": "i have been working on this project for about two years",
  "segment_id": "01a14e4f-2d68-7ff5-a6da-817e4f3badde-seg-1",
  "segment_index": 1,
  "latency": 108
}
```

Three documented/live divergences:

| Field | Docs | Observed | Consequence |
|---|---|---|---|
| `segment_index` | "starting at `0`" | **first segment was `1`** | Do not assume 0-based. Observed, not guaranteed. |
| `audio_duration_ms` | documented as present | **absent in live frames** | The draft contract has no field for it; nothing may depend on it. |
| `text` casing | `verbatim` = "raw spoken-form" | **lowercased output** | Case-sensitive filler matching would be wrong. |

### 1.4 TTS — `start`, `audio`, `complete` — **DOC SAMPLE**

```json
{ "type": "start", "message": "Streaming started", "request_id": "req_abc123" }
{ "type": "audio", "data": { "chunk_index": 0, "audio": "<base64>", "is_final": false } }
{ "type": "complete", "data": { "chunk_index": 12, "audio": "", "is_final": true } }
```

`req_abc123` is a **placeholder from the published documentation**. It is
not a request id this project observed, and it must not be used as one.

**LIVE CAPTURE** (2026-10-18, `container: "raw"`): **52 chunks, 81,920
bytes, 2,560 ms of audio, no RIFF header in any chunk**
(`riff_header_count: 0`). The live run's own request id is recorded in
the run evidence, not here.

**Chunk sizes are not uniform.** Observed sizes within a single synthesis:
`3584, 1024, 3584, 1024, 3584, 1024, 4096, 1024, 1024, 3584, …` A browser
`AudioWorklet` that assumes a fixed chunk size, or any naive index-based
bookkeeping, will misbehave. Concatenation must be append-only and
order-driven by `chunk_index`.

The documented wav behaviour ("WAV file (with header)") was **not** exercised
against live audio; `inspect_container()` reports what arrived, and a
`repeated_header_per_chunk` flag exists precisely so the per-chunk-header
case is detected rather than assumed away.

---

## 2. Adapter lifecycle and interfaces

```
providers/
  errors.py      ProviderError + categories; is_retryable()
  limits.py      ProbeBudget
  redaction.py   redact(); describe_headers()
  transport.py   Transport protocol; WebSocketTransport; FakeTransport
  pcm.py         framing, WAV, resample, SampleClock
  events.py      provider-internal diagnostic events
  stt.py         GnaniSttSession
  tts.py         GnaniTtsSession
  gemini.py      GeminiCoach
```

All three adapters take an **injectable transport** (`stt.py`,
`tts.py`) or an injectable **client factory** (`gemini.py`). That is what
makes the protocol suite run offline with dummy credentials.

### STT

```python
config = build_config("en-IN", sample_rate=16000)   # verbatim, substitution off, no bias
async with GnaniSttSession(config, api_key, budget=budget) as session:
    result = await session.stream_pcm(raw_pcm)       # returns SttResult
result.transcripts        # list[SttTranscriptEvent]  — SEGMENTS, not turns
result.sample_clock       # SampleClock
result.unrecognized_frames
```

### TTS

```python
config = TtsConfig(text=..., voice="Kaveri", model="timbre-v2.5",
                   language="en-IN", audio=AudioConfig(container="raw"))
async with GnaniTtsSession(config, api_key, budget=budget) as session:
    result = await session.synthesize(forward=consumer, cancel_after_chunks=2)
result.first_nonempty_chunk_ms   # BACKEND timing only
result.container_observation
```

### Gemini

```python
client = GeminiCoach(GeminiConfig(model="gemini-3.8-flash", store=False), key,
                     budget=budget, attempt_timeout=15.0, deadline=45.0)
event = await client.reply(CoachRequest(recognized_text=..., reply_language="English"))
event.text, event.model, event.store, event.tools_enabled
client.lifecycle.created, client.lifecycle.closed   # every client is closed
client.attempts_made                                 # per-attempt outcomes
```

`reply()` is a coroutine and awaits the SDK's async Interactions API
directly. `attempt_timeout` bounds one wire attempt; `deadline` bounds the
whole call. `max_concurrent_calls` (default 2) bounds simultaneous calls.
`max_retries` (default 2) bounds adapter-level retries, independently of
the budget's own retry ceiling.

---

## 3. Frame and clock rules

| Rule | Value | Why |
|---|---|---|
| Wire format | raw mono s16le, **no container mid-stream** | documented |
| Frame size | **exactly 1,024 bytes** (512 samples) | documented |
| Frame cadence | 32 ms @ 16 kHz, 64 ms @ 8 kHz | documented |
| End padding | zero-pad to a frame boundary, recorded as padding | `pad_to_frame()` |
| Trailing silence | **800 ms appended** by default | see below |

**Trailing silence is not optional.** The server's VAD closes a segment on
*silence*, and it cannot know a stream has ended until the socket closes.
Without it, the final segment never closed and **zero transcripts were
returned** — observed directly. The adapter appends 800 ms of silence,
charges it to the audio budget as submitted audio, and records it as
**padding** so it never enters the learner speech span.

### The clock is the only anchor

`SampleClock` counts samples actually submitted and keeps three figures
separate:

```json
{ "genuine_samples": 38400, "submitted_samples": 51200, "padding_samples": 12800,
  "genuine_ms": 2400, "padding_ms": 800, "submitted_ms": 3200 }
```

- `genuine_ms` — the elapsed learner audio span. **This is `turn.duration_ms`.**
- `padding_ms` — deliberate end padding. Never learner speech.
- `submitted_ms` — everything written to the socket. Only this is charged to
  the audio budget.

Never used as an anchor: wall-clock connection time, network round trips,
provider `latency`, `audio_duration_ms`, or segment emission order.

---

## 4. Cancellation, timeouts and limits

### Cancellation — the important distinction

The reviewed TTS page documents **no cancel control message**. The adapter
sends exactly one frame: the synthesis request. Verified by a test that
asserts no key named `cancel` ever reaches the provider.

| Action | What it does | What it does **not** do |
|---|---|---|
| `cancel_consumption()` | fences the consumer; later chunks recorded with status `fenced` and never forwarded | does **not** cancel provider computation or billing |
| `drain()` | finishes the in-flight request without forwarding | does not cancel |
| `close_on_cancel=True` | closes the socket — the only provider-side stop available | may still bill the in-flight synthesis |

**Stop consuming ≠ cancel the provider.** Phase 05's interruption design
must present this to the user honestly ("the coach stopped talking", not
"the coach's request was cancelled").

### Timeouts actually enforced

| Path | Bound | Note |
|---|---|---|
| WS handshake | 15 s | `websockets` `open_timeout` |
| STT receive | 30 s | yields an `idle` notice, then drains |
| TTS receive | 30 s | idle-based, ends on `complete` |
| Gemini per attempt | **15 s** (configurable) | `HttpOptions(timeout=…)` |
| Gemini SDK-internal retries | **0** | `HttpRetryOptions(attempts=1)` — the SDK's own documented "including the original request", so `1` means no retry |
| Gemini adapter-level retries | **2**, 0.5 s backoff | budget-admitted; each attempt counted before it starts |
| Gemini overall call deadline | **45 s** (configurable) | bounds the whole call, including retries and backoff |

The **overall call deadline is a feasibility-probe diagnostic bound, not
the product's voice-turn target.** The app's eventual target is ≤3 s
end-of-turn-to-first-audible; the two are different things on purpose and
neither may be substituted for the other in a report. The old
70-second outer wait is gone.

### The defect that was found, and what replaced it

**The defect.** With SDK defaults, a throttled Gemini call blocked for
**>100 s**: `google-genai` retried internally, so the caller could not
bound the wait, and the process hung at shutdown joining the stuck
worker.

**The first fix, and why it was replaced.** The adapter executed the call
on an *abandonable daemon thread* and reported a bounded
`UpstreamTimeoutError`. That fixed the hang but introduced three new
problems, all of which Phase 02 FIX-1 (P02-03) corrected:

1. **Unbounded workers.** One fresh thread per call, with no cap on
   outstanding work.
2. **A closed loop could be called into.** A late completion could try to
   touch an event loop that had already closed.
3. **Capacity was released early.** A caller timing out freed a worker
   slot while the abandoned request was still running.

**The replacement.** The adapter now uses the pinned SDK's **documented
async surface** — `Client.aio` (`AsyncClient`), `await
client.aio.interactions.create(...)`, and `await client.aio.aclose()` —
and awaits the request directly. Consequences:

- The request is **cancellable**: a cancelled turn cancels the in-flight
  call instead of abandoning a thread.
- Concurrency is **bounded** by a semaphore (`max_concurrent_calls`,
  default 2). A slot is held by the attempt itself and released only when
  the attempt's `finally` runs, so a caller timing out does not free
  capacity that is still in use.
- The client is **closed on every exit path** — success, error, timeout
  and cancellation — via both `client.aio.aclose()` and `client.close()`.
- A **late response from a cancelled turn is fenced**: it is never
  returned to the caller and never reaches TTS.

The semaphore is rebuilt when the running event loop changes, so a coach
reused across loops does not carry a semaphore bound to a dead loop.

### What a timeout means — and what it does not

| Term | Meaning |
|---|---|
| **Bounded local wait** | Our wait expired. The request may still be running provider-side. |
| **Closed local connection** | Our socket or HTTP client was closed. The provider may still be working. |
| **Provider-side cancellation** | The provider cancelled the work. **Never claimed** by a local timeout. |
| **Billing** | A local timeout makes **no claim** either way. |

`UpstreamTimeoutError` therefore says exactly that: the local wait
expired, the last attempt may still be running provider-side, and a local
timeout is not a provider cancellation. The adapter never advertises
"cancels cleanly" when only the wait ended.

### Budget

40 wire attempts · 300 s submitted STT audio · 2 retries per logical
call · 40 connections, per live invocation. `ProbeBudget.__post_init__`
**rejects** any attempt to raise a limit above the global cap, and
rejects negative or non-finite limits outright.

Four counters are kept distinct and never conflated: `logical_calls_used`,
`wire_attempts_used`, `connections_used`, `retries_used`. **A timed-out
attempt still counts** — the provider may still be working on it.

A child budget is **reserved from its parent at creation**, so two
concurrent children can never both be handed the same remaining
allowance. Absorption never clamps: an overrun is recorded and reported.

**Historical wire-attempt counts are UNKNOWN.** Runs recorded before this
accounting existed carry no measured attempt count, and are reported as
`"unknown"` — never reconstructed as zero.

---

## 5. Shared-contract issues for Phase 03

### 5.1 The metric denominators must be split (carried from the Phase 01 VERIFY handoff)

`durable-metrics.schema.json` currently gives `speech.rate_wpm` and
`speech.active_rate_wpm` **the same** `stt_words_over_speech_regions`
method description, which conflates two quantities. The implementation
already keeps four values separate and reports them side by side:

| Quantity | Numerator | Denominator | Excluded |
|---|---|---|---|
| `clip_span_ms` | elapsed learner audio | the learner's own span | end padding |
| `speech_active_ms` | VAD speech-active time | same sample clock | — |
| `speech.rate_wpm` | recognised words | **`clip_span_ms`** | assistant audio, connection time, session time, network round trips, provider emission timestamps |
| `speech.active_rate_wpm` | recognised words | **`speech_active_ms`** | same |

**Request:** distinct `methodId` values for the two rates (or a per-observation
denominator field), plus a schema description stating that neither denominator
may ever be total connection or session time.

### 5.1a Recognition status and source trust — a required DTO change

Raised by Phase 02 FIX-1 (P02-07). The probe-level implementation now
exists in `tools/probes/analysis/metrics.py`; **the shared schema has not
been edited**, because Phase 03 owns it. Phase 03 needs to encode two
things that the current draft has no place for.

**(a) A recognition status, so a missing transcript is never a measured
zero.** The draft has `speech.rate_wpm` with no way to say *why* it is
absent. The probe now distinguishes three outcomes:

| Status | Meaning | `rate_wpm` |
|---|---|---|
| `measured` | a transcript exists | the computed rate |
| `no-analyzable-speech` | the recogniser ran and returned nothing | **absent**, not `0` |
| `missing-transcription` | no transcript was obtained at all | **absent**, not `0` |

**Request:** a per-observation status field alongside the rate, with
`rate_wpm` **omitted** rather than zero for the two non-measured states. A
missing transcription must never be readable as "measured: zero words per
minute". The same applies to `active_rate_wpm`.

**(b) The source of the measured audio, and what a source label does not
prove.** A measurement is only taken over an explicitly trusted learner or
synthetic-learner source. Empty, assistant-only, mixed and unknown source
classifications are refused before a measurement is produced.

**Request:** the durable schema should carry the measured clip's source
classification, and its description should say in terms that a **source
label is a declaration, not a proof** — it does not establish diarization
and it does not establish echo cancellation. Full stream ownership and
echo exclusion remain runtime work for Phase 04/05.

**(c) Span contents.** The span **includes** the source's leading and
trailing silence (that is the elapsed span the learner produced) and
**excludes** the end padding. The schema should state both, rather than
leaving a consumer to assume.

### 5.2 `turn.duration_ms` must be sample-clock based

The draft couples it to `turn_connection_timer`. Observation: connection
time and learner span diverge materially — the `spoken-known-gap` probe
submitted 5.06 s of audio to obtain a 4.24 s clip. **Request:** redefine
`turn_connection_timer` as a learner-audio sample clock, or add a separate
method id, and state that end padding is excluded.

### 5.3 `totals.speakingTimeMs` is ambiguous

`totals` requires `turnCount` and `speakingTimeMs`. Phase 01 VERIFY handoff
item 3 warns: do not equate total speaking-active time with the sum of
elapsed turn spans when spans include silence. **Request:** document
`speakingTimeMs` as the *sum of detected speech-active time*, not the sum
of elapsed turn spans, and state the invariant that
`speakingTimeMs ≤ Σ turn.durationMs`.

### 5.4 Missing identifier and span semantics

| Need | Provider can supply | Provider **cannot** supply | Request |
|---|---|---|---|
| Turn / utterance grouping | `utterance_id` on the undocumented `speech_start`; shared `segment_id` prefix across segments | an explicit turn id | define whether `turnId` may derive from `utterance_id`, and mark it unstable |
| Word positions | **nothing** | word-level timing entirely | `evidenceSpan` must remain estimated-region only; state that no word timing exists |
| Event spans for a filler | nothing | any span for a word the recogniser dropped | keep `status: insufficient_evidence` + `too_little_speech`, and do **not** map a missing filler to `0` |
| Frame/clock provenance | nothing | — | consider a controlled provenance id for "learner audio sample clock" distinct from connection timing |
| Provider latency | `latency` ms per segment | — | store as metadata, never as a metric value |

### 5.5 Settings changes (Phase 03 owns `settings.py`)

**Request: per-provider readiness, without a Supabase dependency.**
`provider_readiness()` folds Supabase into `configured` and is hard-wired to
`unavailable`. Phase 02 never calls it. The probes need, and did not have:

```python
def speech_readiness(settings) -> ProviderReadiness:   # Gnani only
def reasoning_readiness(settings) -> ProviderReadiness # Gemini only
```

each reporting `state ∈ {unconfigured, configured, verified}` and
`configured` meaning "the credential name is present" — never `live`.
A combined view may still require Supabase; the *speech* view must not.

Also requested:

- `GEMINI_MODEL` currently has no default **by design** (Phase 01 chose not
  to guess an id). Observed working id: `gemini-3.8-flash`. Phase 03 should
  freeze it explicitly with its access date.
- A non-secret selector for the TTS model/voice pairing (defaulted to
  `timbre-v2.5`), since the voice catalog is model-specific and a mismatch
  is a hard `400`.
- A per-connection VAD settings object (`threshold`, `min_silence_ms`,
  `min_speech_ms`, `min_segment_ms`, `max_speech_s`) — VAD headers are
  fixed for the life of a connection, so a round-boundary change requires a
  reconnect, and the *current* values must be carried across that reconnect.

### 5.6 Observed behaviour that a contract must not encode by accident

- `segment_index` began at **1**, not the documented 0.
- `audio_duration_ms` was **absent** from live frames.
- Output was **lowercased** under `x-format: verbatim`.
- A 1,200 ms mid-sentence gap split one sentence into **two** segments
  (`'i think the main issue is'` + `'we did not test it properly'`), each
  with its own `speech_start`. **A VAD-closed segment is not a turn.**
- A full eleven-language matrix needs ~55 operations and cannot fit the
  40-operation probe limit in one invocation.
- **A language row is not covered by an STT-only success.** The matrix
  now aggregates every requested stage (STT, TTS, reasoning); a row is
  covered only when all of them pass, and a failed stage is never masked
  by a successful one.
- **Parameter acceptance is not language coverage.** English audio sent
  with a Tamil parameter proves the endpoint took the value. It is
  reported in a separate `*_param` column and never counts as coverage.
- **A code can be ambiguous.** `en-IN` is the STT code of both English
  and Hinglish, so the catalog resolver refuses it and names both ids
  rather than picking one.

### 5.7 Where a validated prototype could be promoted in Phase 05

Phase 02 must not move code into another phase's tree. When — and only
when — the analysis approach is validated, these are the candidates and the
note for each:

| Module | Note for Phase 05 |
|---|---|
| `tools/probes/analysis/vad.py` | Promote the **measurement contract**, not the file. It must be re-homed under `services/voice/src/gnani_coach/analysis/` and re-reviewed; do not import from `tools/`. |
| `tools/probes/analysis/metrics.py` | The four-denominator separation, the recognition-status distinction and the source-trust rule are the parts worth keeping. Promote once the contract encodes them (§5.1, §5.1a). |
| `tools/probes/analysis/filler.py` | Prototype only. Its events are `candidate`, never `confirmed_filler`. Nothing here is validated. On `spoken-filled-hesitation` the fillers are **absent from the recognition output**; whether they were present in the rendered audio **was not reviewed**, so the candidate count is unvalidated in both directions. |
| `SampleClock` (in `providers/pcm.py`) | Already in the service package and reusable as-is. |

**Do not maintain two measurement implementations.** If Phase 05 needs
measurement, it should adopt the Phase 02 semantics and delete the probe
path, not fork it.

---

## 6. UI honesty requirement (Phase 03/04)

`UI.png` / Speakify remains the visual target. The observed capabilities
mean the UI must be able to render honest states:

- **loading** — a live call is genuinely in progress
- **error** — a provider actually failed (category known, message redacted)
- **insufficient evidence** — no speech, too little speech, or a metric that
  could not be computed

The reference image's recording-ON default, tap-to-speak interaction and
any mock score remain **not** product requirements. Observed capabilities
must drive the states; the design must not invent numbers the backend cannot
produce. No confidence percentage, pronunciation grade or guaranteed
improvement may appear anywhere, because nothing in Phase 02 can produce a
defensible one.
