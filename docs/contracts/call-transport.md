# The call transport contract

Status: **FROZEN, 2026-10-20 (Phase 03).** The machine-readable part is
`packages/contracts/schemas/event-envelope.schema.json`; this document
explains what the schema cannot say.

One WebSocket carries the whole call, in both directions:

* the **client** sends binary PCM16 audio frames plus six JSON control
  events;
* the **server** sends seven JSON events plus binary TTS audio chunks.

---

## 1. The events

| Direction | Type | Meaning |
|---|---|---|
| client → server | `start` | The first event of every call. Carries the audio format, the session settings and the caller's own token. |
| client → server | `mute` | The learner muted or unmuted. |
| client → server | `end` | The learner ended the call. |
| client → server | `interrupt` | The learner started speaking while the coach was playing. |
| client → server | `retry` | Repeat or reframe one answer. |
| client → server | `coaching_choice` | "Keep talking", "Coach me now" or "Skip feedback". |
| server → client | `status` | Connection and call state, including the heartbeat. |
| server → client | `transcript_partial` | A partial recognition of the learner's speech. |
| server → client | `transcript_final` | A final recognised segment. |
| server → client | `coach_text` | The coach's spoken line as text. |
| server → client | `round_feedback` | One coaching break: at most one strength, at most two changes, each tied to real observations. |
| server → client | `error` | The frozen error shape. |
| server → client | `audio.frame.descriptor` | Tags the binary frames that follow with a turn id and the audio format. |

A type may only travel in its own direction; the schema rejects the other
combination. Every payload is closed: an unknown payload key is rejected,
so adding a field is a contract change, not a guess.

**Phase 19 addition (one optional field).** `coach_text` and
`audio.frame.descriptor` accept an optional `kind`: `"reply"` (the default)
or `"backchannel"`. A backchannel is a short spoken reaction ("mm-hmm")
sent under **its own `turnId`**. It never fences or replaces the real
reply; it never sets the main `speaking` status; it is dropped rather than
queued while the learner is speaking; and the learner's speech over it does
not produce the "You spoke over the coach" message. No other payload field
was added.

---

## 2. The sequence

```
client                                   server
  |                                        |
  |  --- WebSocket upgrade ---------------> |   (wss, Origin allowlisted)
  |                                        |
  |  -- start (JSON, first message) -----> |   token + audio format + settings
  |                                        |   -> verify the token (guest if absent)
  |                                        |   -> open the STT session
  |                                        |
  |  <- status {state:"ready"} ----------- |
  |                                        |
  |  -- binary PCM16 frames -------------> |   exactly 1,024 bytes each
  |                                        |   (raw mono s16le, no container)
  |                                        |
  |  <- transcript_partial (JSON) -------- |   may arrive while speaking
  |  <- transcript_final (JSON) ---------- |   a closed VAD segment
  |                                        |   (a segment is NOT a turn)
  |                                        |
  |                                        |   coach turn:
  |  <- coach_text (JSON) ---------------- |   the line the coach says
  |  <- audio.frame.descriptor (JSON) ---- |   tags the binary frames
  |  <- binary TTS frames ---------------> |   in order, append-only
  |                                        |
  |  -- interrupt (JSON) ----------------> |   learner spoke over the coach
  |                                        |   -> stop playback, fence the turn
  |                                        |
  |  -- retry / coaching_choice ---------> |
  |  <- round_feedback (JSON) ------------ |   strengths / improvements / evidence
  |                                        |
  |  -- end (JSON) ----------------------> |   -> status {state:"ended"}, close
```

**A turn is not a segment.** One sentence can be split into several
recognised segments when the recogniser's VAD closes on a pause, so turn
grouping is the application's own and is never taken from a provider
segment boundary. The counting rule is *four completed learner turns per
coaching round*, not four transcript segments.

**TTS chunk order is index-driven.** Observed chunk sizes are not uniform
(`3584, 1024, 3584, 1024, …`), so concatenation is append-only and
ordered by the provider's chunk index, never by arrival assumption.

**Stopping playback is not cancelling the provider.** The reviewed TTS
documentation has no cancel message. When the learner interrupts, the
server stops delivering audio and fences the coach turn; the provider
request may still be running and may still be billed. The user interface
must not say the request was cancelled.

---

## 3. Ids and clocks

| Id | Prefix | Who mints it | Note |
|---|---|---|---|
| `sessionId` | `ses_` | the server | One practice session. |
| `connectionId` | `con_` | the server | One transport connection. A reconnect gets a new one, so stale events can be fenced. |
| `roundId` | `rnd_` | the server | One coaching round. |
| `turnId` | `trn_` | the server | One conversational turn. |

Two clocks, and they must not be mixed:

* `sampleTimeMs` — the position on the **learner-audio sample clock** when
  the event's content occurred, when that is known. This is the only
  clock that may anchor an evidence span.
* `emittedAt` — the producer's **wall clock**. It is not a word timing
  and not an alignment. A client-supplied `emittedAt` is informational
  only and is never trusted.

`sequence` is a monotonic per-connection counter, incremented by the
producer for every envelope. The runtime uses it for ordering and
duplicate suppression; the schema only checks that it is not negative.

---

## 4. Heartbeat and idle handling

* The server sends a `status` event with `state: "heartbeat"` every 15
  seconds when nothing else has been sent. It carries no measurement.
* The server closes a connection that has received no client frame for 90
  seconds, after a final `status` event with `state: "ended"`. A muted
  microphone is not a dead connection, so the timeout is generous and the
  close is announced.
* A client that reconnects gets a new `connectionId`; events from the
  old connection are fenced off and never applied to the new one.

---

## 5. Stale-turn suppression

Two separate cases, both required:

1. **A stale turn.** Every coach turn has a `turnId`. The client applies
   a coach text, a descriptor or an audio frame only to the turn it
   belongs to; an event for a turn that is no longer current is dropped.
2. **A fenced turn.** After an `interrupt`, the server fences the coach
   turn. A late `coach_text`, a late descriptor or late audio for a
   fenced turn is never sent. The turn's state is preserved, so the
   learner can keep talking, and an acknowledgement is not counted as a
   new practice round.

The recogniser's `utterance_id` is **not** a turn id. It is the closest
observed grouping signal, it is unstable, and it must not be presented as
a turn boundary.

---

## 6. Caps

| Cap | Value | Why |
|---|---|---|
| Call length | **≤ 10 minutes (600 s)** | The product cap. The provider's realtime STT session cap is 15 minutes (900 s); the product stays under it on purpose, and `session-settings` rejects anything above 600. |
| Session settings | 60–900 s in the schema; the transport caps the call at 600 s | The schema keeps the provider's outer limit visible; the call ends at 600 s with a clean summary. |
| Binary frame | exactly **1,024 bytes** (512 samples, 16 kHz mono s16le) | The documented provider frame size. A frame is raw PCM: no container header is ever sent mid-stream. |
| JSON message | **16 KiB** | A `start` payload with its settings is a few hundred bytes. Anything larger is a protocol error, not a bigger message. |
| Transcript text | 4,000 characters | The `text` payload bound. |
| Round turns | 1–8 completed learner turns, default 4 | The coaching round contract. |
| Connections | bounded per user and per address | Resource protection; see the OWASP guidance below. |

The server rejects an oversized or malformed frame with the frozen error
shape and closes with **1009** ("message too big") for size and **1008**
("policy violation") for a malformed payload.

---

## 7. Authentication

**Decision: the caller's own token travels in the first `start` event,
in the message body. It never travels in the URL.**

Why this is the least risky option:

* The Python `websockets` documentation compares the four ways to pass
  credentials and states that sending the credential **as the first
  message is "fully reliable and the most secure mechanism in this
  discussion"**, while adding it to the WebSocket URI in a query
  parameter is "also fully reliable but less secure… URIs end up in logs,
  which leaks credentials"
  (<https://websockets.readthedocs.io/en/stable/topics/authentication.html>,
  checked 2026-10-20).
* The OWASP WebSocket Security Cheat Sheet says the same thing for
  browser clients: "prefer sending the token in the first message over
  WSS. Avoid tokens in URL query strings because they can leak into
  access logs"
  (<https://cheatsheetseries.owasp.org/cheatsheets/WebSocket_Security_Cheat_Sheet.html>,
  checked 2026-10-20).

The rules that follow from the decision:

1. **No credential in a URL.** Not in the query string, not in the path.
2. **No provider credential in the browser.** The only credential a
   browser holds is the caller's own short-lived session access token.
   The Gnani key, the Gemini key and the Supabase service-role key stay
   server-side and never reach the client or the bundle.
3. **A guest call needs no token.** The `auth` block may be omitted; the
   caller is a guest, with no saved history and no retained audio.
4. **Until the token is verified, the server sends nothing protected.**
   The first `start` event is answered with a `status` event; a failure
   is an `error` event with the category `unauthenticated` and the
   connection is closed.
5. **Tokens are never logged.** The OWASP guidance is explicit: never log
   complete message contents, authentication tokens or session ids. The
   error-shape contract has no field for any of them.
6. **The handshake is origin-checked.** The server validates the
   `Origin` header against an explicit allowlist (OWASP: "Validate the
   `Origin` header on every handshake. Always use an explicit allowlist of
   trusted origins"), and the same allowlist governs the CORS headers for
   the HTTP routes.

   **The allowlist, the CORS middleware and the check itself are frozen in
   [`seams.md` §8](seams.md#8-the-origin-allowlist-the-cors-middleware-and-the-handshake-check)**,
   including what a **missing** `Origin` header means (a non-browser
   client, which is allowed) and the refusal (close **1008** before the
   handshake completes). The setting is `SPEAKING_COACH_ALLOWED_ORIGINS`;
   the wildcard `*` is refused while the settings parse.

---

## 8. What the schema cannot say

* **Ordering and duplicate suppression** are runtime behaviour. The
  schema checks the shape of `sequence`, not its monotonicity.
* **Turn grouping** is the application's own, as described above.
* **Authenticity of a client-supplied `emittedAt`** is never trusted.
* **Whether a payload is true** is never a schema question. A transcript
  is untrusted input, and a model reply is not a measurement.
