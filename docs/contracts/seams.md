# The frozen seams

Status: **FROZEN, 2026-10-20 (Phase 03).** G1 builders build to this
file. Do not read another sibling's source to learn an API: if it is not
here, it is not part of the contract.

**Phase 03 FIX-1 (2026-10-20)** added §6.1 (the browser-visible voice
service URL) and §8 (the origin allowlist, the CORS middleware and the
handshake check), and one row in the seam table of §1 for each. Nothing
that was frozen before was renamed or changed.

Every name below is final unless a change is recorded in this file. A
builder that needs a different name posts `HELP:` in the G1 communication
folder and waits; nobody renames a seam on their own.

---

## 1. The seam table

| Seam | Name / location | Owner after the freeze | Unavailable behaviour |
|---|---|---|---|
| Web mount | `apps/web/src/features/call/index.ts` exports `CallExperience` (React component, no props except `{catalog}`); `page.tsx` renders it | Phase 04 | the stub renders the existing honest starter notice |
| Voice conversation | `gnani_coach/conversation/router.py` exports `router` (FastAPI `APIRouter`) with WebSocket `/ws/call`, mounted in `main.py` | Phase 05 | the stub closes with the error-shape code `not_available` |
| Voice history | `gnani_coach/persistence/router.py` exports `router`: `GET /api/history`, `POST /api/consent`, `GET/DELETE /api/recordings/{id}` | Phase 06 | `503` with error-shape `not_available` |
| Identity | `gnani_coach/identity/__init__.py` exports `get_identity() -> IdentityPort`; injected via FastAPI dependency | Phase 06 | returns the anonymous guest implementation |
| Web auth | `apps/web/src/lib/auth/index.ts` exports `useSession`, `signOut`; `apps/web/src/proxy.ts` placeholder | Phase 06 | guest state |
| Analysis | `gnani_coach/analysis/__init__.py` exports `get_analysis() -> AnalysisPort` | Phase 05 | returns `insufficient_evidence` |
| Origin policy | `gnani_coach/ports/origins.py` exports `origin_allowed(origin: str | None) -> bool` (also re-exported as `gnani_coach.ports.origin_allowed` and `gnani_coach.main.origin_allowed`) | Phase 03 (frozen — Phase 05 must call it) | a foreign origin is refused with close **1008** |
| Browser voice URL | `apps/web/src/lib/voice.ts` exports `VOICE_WS_URL` (from `NEXT_PUBLIC_VOICE_WS_URL`) | Phase 03 (frozen — Phase 04 reads it) | the development default `ws://localhost:8000/ws/call` |

### Names that differ from the Phase 03 BUILD, and why

| Frozen name | BUILD name | Reason |
|---|---|---|
| `apps/web/src/features/call/index.ts` (re-export) + `apps/web/src/features/call/CallExperience.tsx` (the component) | `apps/web/src/features/call/index.ts` | The component contains JSX, which a `.ts` file cannot hold. The **path and the export name are unchanged**: `index.ts` still exports `CallExperience`, and `page.tsx` still renders it. |
| `gnani_coach/ports/**` | `services/voice/src/gnani_coach/ports/**` | Same path; the package root is `gnani_coach`. |
| `get_identity()` / `get_analysis()` are also exposed as `main.identity_dependency` / `main.analysis_dependency` | — | The composition root needs one place to wire the FastAPI dependency; the exported names stay exactly as the BUILD states. |

---

## 2. What the Phase 03 stubs do today

| Stub | Behaviour | What the owner replaces |
|---|---|---|
| `apps/web/src/features/call/*` | Renders the Phase 01 honest starter screen: setup form, ten catalog languages with honest badges, a **disabled** start action with a plain reason, no microphone request, no fake data. Adds the frozen workplace presets and the transient Custom Topic field. | Phase 04: the real call UI. The export name and the `{catalog}` prop do not change. |
| `gnani_coach/conversation/router.py` | Accepts `/ws/call`, sends **one** `error` envelope with the error-shape payload (`code: not_available`, `category: not_available`, `retryable: false`), then closes with WebSocket close code **1011** and the reason `not_available`. **Before** it accepts, it checks the `Origin` header with `origin_allowed()`: a foreign origin is closed with **1008** and the handshake never completes (a real client sees HTTP 403). | Phase 05: the real call loop — **keep the origin check**. The accepted socket's first message is `status` with `state: "connecting"` (decision of 2026-10-22, §9). |
| `gnani_coach/persistence/router.py` | The four routes exist with their final paths and methods. Each answers **503** with the error-shape payload. They are excluded from the OpenAPI document (`include_in_schema=False`), because a placeholder is not a published interface. | Phase 06: the real storage. **Decision (CEO, 2026-10-22): the routes stay out of the OpenAPI document** — see §9. |
| `gnani_coach/identity/__init__.py` | `get_identity()` returns `GuestIdentity`: `verify_token()` and `current_user()` both return `None`. | Phase 06: the real verification. |
| `gnani_coach/analysis/__init__.py` | `get_analysis()` returns `InsufficientEvidenceAnalysis`: every metric comes back `insufficient_evidence` with a null value. | Phase 05: the real measurement. |
| `apps/web/src/lib/auth/index.ts` | `useSession()` returns the guest state (`status: "guest"`, `userId: null`); `signOut()` resolves without doing anything. | Phase 06: the real session. |
| `apps/web/src/proxy.ts` | A placeholder that lets every request through unchanged. | Phase 06: the real guard. |

**Why the close code is 1011.** 1011 is "the server encountered a
condition that prevented it from fulfilling the request" (RFC 6455 §7.4.1).
The conversation runtime does not exist yet, so the request cannot be
fulfilled. It is not a policy violation (1008) and it is not a client
error (1003/1008), and it is deliberately **not** 1013 ("try again later"),
because retrying does not make the seam exist.

**The one exception is the origin.** A handshake from an origin that is
not on the allowlist is refused with **1008** ("policy violation"), and it
is refused *before* the socket is accepted, so the handshake itself never
completes. The rule and the reason are in §8.

---

## 3. The service ports (read-only for G1)

`gnani_coach/ports/**` is frozen and read-only for every G1 builder. The
provider clients from Phase 02 are reached through
`gnani_coach.ports.provider_adapters`, so no provider module was edited.

| Port | Import | Contract |
|---|---|---|
| `SpeechToTextPort` | `gnani_coach.ports` | `open_session(SttOpenRequest) -> SpeechToTextSession`; the session submits raw mono s16le PCM and returns segments plus the three separate durations (genuine / padding / submitted). |
| `TextToSpeechPort` | `gnani_coach.ports` | `open_session(TtsOpenRequest) -> TextToSpeechSession`; chunks are delivered in order; `cancel_consumption()` fences the consumer and is **not** a provider cancellation. |
| `ReasoningPort` | `gnani_coach.ports` | `reply(ReasoningRequest) -> ReasoningReply`; tools off, conversation not stored. |
| `AnalysisPort` | `gnani_coach.ports` | `analyze(AnalysisRequest) -> AnalysisResult`; the result carries the recognition status and the observations. |
| `IdentityPort` | `gnani_coach.ports` | `verify_token(token) -> UserId | None`; `current_user() -> UserId | None`. |
| `SessionStorePort` | `gnani_coach.ports` | `save_metrics(record)` takes the **already validated** durable-metrics document; it never enriches a record with content. Its owner is the verified request context (`identity.current_user()`); `save_metrics_for(user_id, record)` is the explicit owner form. |
| `RecordingStorePort` | `gnani_coach.ports` | Owner-scoped save/read/delete of opted-in audio only. |

---

## 4. The shared contract files (read-only for G1)

| Path | What it is | Who may change it |
|---|---|---|
| `packages/contracts/schemas/*.schema.json` | Eight JSON Schema 2020-12 definitions | Phase 03 (a contract FIX) |
| `packages/contracts/data/catalog.json` | Languages, code-mixed mode, scenarios and presets, levels | Phase 03 |
| `packages/contracts/data/capabilities.json` | The capability states | **Phase 08** (data only) |
| `packages/contracts/examples/**` | The valid/invalid fixtures both runtimes check | Phase 03 |

A G1 builder that needs a new field posts `HELP:` and waits for a
contract FIX on Phase 03. Adding a field is a shape change, and the
shape is frozen.

---

## 5. The rules that apply to every seam

1. **Nothing is invented.** A value is written only when it was measured.
   A missing measurement is `insufficient_evidence` with a null value and
   a reason code — never `0`, never a score, never a confidence.
2. **Content stays transient.** Transcripts, quoted mistakes and model
   text live in transient envelopes only. The durable record rejects them
   by name.
3. **Recording retention is off by default** and is a separate decision
   from the consent to process speech live. Permission to keep audio is
   not permission to keep a transcript.
4. **The learner is a guest by default.** No account is required, and a
   guest has no saved history and no retained audio.
5. **No credential in a URL, and no provider credential in the browser.**
6. **The filler capability is unvalidated.** The UI and the coach render
   `insufficient_evidence`. See
   [capability-states.md](capability-states.md).

---

## 6. The web design tokens

**The global design tokens live in `apps/web/src/app/globals.css`.** That
file is the single source of the palette, the radii, the shadows and the
type scale, and it also styles the layout primitives the starter screen
uses. Phase 04 builds inside `apps/web/src/features/**` and must not need
to edit it.

The baseline applied in Phase 03 is the Speakify reference (`UI.png`):
a warm near-white canvas, softly raised white panels, subtle borders and
shadows, generously rounded corners, dark ink text, pill-shaped dark
primary buttons, mint/teal highlights, restrained pastel tiles, and bold
sans-serif headings on the platform sans stack (no web font is
introduced, so there is no licensing question and no layout shift).

The token names available today are listed at the top of the file:
`--canvas`, `--panel`, `--panel-sunk`, `--hairline`, `--ink`,
`--ink-soft`, `--ink-faint`, `--primary`, `--primary-strong`,
`--primary-ink`, `--accent`, `--accent-tint`, `--accent-line`, the four
pastel tile colours, `--radius-lg|md|sm|pill`, `--shadow-soft`,
`--font-sans` and the type scale.

### 6.1 The browser-visible voice service URL

**`NEXT_PUBLIC_VOICE_WS_URL` is the one browser-visible setting, and it is
not a secret.** It is the WebSocket URL of our own voice service, and it
is frozen in `apps/web/src/lib/voice.ts`, which exports it as
`VOICE_WS_URL`:

```ts
import { VOICE_WS_URL } from "@/lib/voice";
```

| | |
|---|---|
| Variable | `NEXT_PUBLIC_VOICE_WS_URL` |
| Default | `ws://localhost:8000/ws/call` (the voice service on the developer machine) |
| Read by | `apps/web/src/lib/voice.ts` → `VOICE_WS_URL` (Phase 04's call client reads this) |
| Inlined | yes — Next.js inlines `NEXT_PUBLIC_*` into the browser bundle **at build time** |
| Secret? | **No.** It is a URL of a service the browser is allowed to call. |

Rules:

1. **No secret may use the `NEXT_PUBLIC_` prefix.** A `NEXT_PUBLIC_`
   value ends up in the JavaScript bundle and is readable by anyone who
   opens the page. The Gnani key, the Gemini key and the Supabase
   service-role key stay server-side. `NEXT_PUBLIC_VOICE_WS_URL` is the
   only `NEXT_PUBLIC_` value in this repository.
2. **The browser never talks to a speech provider.** It opens one socket,
   to our own voice service, and the provider credentials stay on the
   server (rule 5 of §5).
3. **The URL carries no credential.** The caller's own token travels in
   the first `start` event, never in the URL (§7 of
   [call-transport.md](call-transport.md)).
4. **The origin of the page is what the service checks**, not the URL:
   the browser's `Origin` header must be on the service's allowlist
   (§8). Pointing the browser at another deployment therefore also means
   allowing that deployment's web origin on the service.

---

## 7. The UI states Phase 04 must be able to render

Each state has exactly one source in the contract, so Phase 04 does not
invent a name:

| State | What it means | Where it comes from |
|---|---|---|
| **loading** | A call is genuinely in progress. | The `status` event: `connecting`, `ready`, `reconnecting`, `thinking`, `speaking`, `coaching`. |
| **error** | A provider or the service actually failed. | The `error` event carrying the frozen error shape: a known `category`, a plain-word `message`, and `retryable` that is true only for genuinely transient conditions. |
| **insufficient evidence** | There was not enough speech, or the measurement could not be produced. | An observation (or a durable metric) with `status: "insufficient_evidence"`, a null value and a reason code. This is also the rendering of the **unvalidated filler capability**. |
| **empty history** | The learner has no completed sessions yet. | The history route answers with an empty list. It is a real state, not an error, and it is never padded with sample data. |
| **guest** | Nobody is signed in. | `useSession()` returns `status: "guest"`, `userId: null`. A guest call still works; a guest has no history and no retained audio. |

The states that must **not** exist: an overall score, a confidence
percentage, a pronunciation grade, a guaranteed improvement, a filler
count, and any sample session in the history.

---

## 8. The origin allowlist, the CORS middleware and the handshake check

**One list, two jobs.** The browser-origin allowlist governs the CORS
headers of the HTTP routes **and** the WebSocket handshake, so the origin
that may call `GET /api/history` is exactly the origin that may open
`/ws/call`.

### 8.1 The setting

| | |
|---|---|
| Variable | `SPEAKING_COACH_ALLOWED_ORIGINS` |
| Type | a list of origins (`scheme://host[:port]`) |
| Default | **the local web origin only** — `http://localhost:3000` |
| Accepted forms | a JSON array (`["https://a.example","https://b.example"]`) or a comma-separated list (`https://a.example,https://b.example`) |
| Wildcard `*` | **refused while the settings parse** — the service does not start |
| Read by | `gnani_coach.settings` (the only place that reads the environment) |

The wildcard is refused on purpose. The OWASP WebSocket Security Cheat
Sheet asks for "an explicit allowlist of trusted origins" and warns that
wildcards are "error-prone", and the FastAPI CORS documentation makes the
same point: "It's also possible to declare the list as `"*"`… but that
will only allow certain types of communication… So, for everything to work
correctly, it's better to specify explicitly the allowed origins."

### 8.2 The one reusable check

```python
from gnani_coach.ports import origin_allowed   # or: from gnani_coach.main import origin_allowed

origin_allowed(origin: str | None) -> bool
```

It is the **only** place that answers "may this client?", and it is
frozen. **Phase 05's `/ws/call` router calls it before `accept()`** and
keeps the rule; Phase 03's stub already does.

| The `Origin` header | Result | Why |
|---|---|---|
| on the allowlist | **allowed** | the comparison is exact, after normalisation (lower-cased scheme and host, the default port dropped, no trailing `/`) |
| not on the allowlist | **refused** — close **1008** ("policy violation"), sent *before* the handshake completes, so a real client sees **HTTP 403** | the origin is not trusted |
| malformed (not a plain `http(s)` origin) | **refused** — close **1008** | a malformed origin is not a trusted origin |
| **absent** | **allowed** | **a missing header identifies a non-browser client** — see below |

**The missing-Origin decision, written down.** A browser *always* sends
`Origin` on a WebSocket handshake, and JavaScript cannot remove or
override it: "Validate the Origin header on every handshake. Always use
an explicit allowlist of trusted origins. **Browsers include this header
and malicious JavaScript cannot override it.**" (OWASP WebSocket Security
Cheat Sheet, checked 2026-10-20). So a handshake **without** an `Origin`
header cannot have come from a browser — it is a non-browser client (a
server-side probe, a native client, a test client). Such a client has no
ambient cookie and no ambient credential to hijack, and the caller's own
token still travels in the first `start` event, so allowing it does not
weaken the browser threat model, which is cross-site WebSocket hijacking.
A missing header is therefore **allowed**, and it is **not** a way to
bypass the allowlist for a browser.

### 8.3 The CORS middleware

`gnani_coach/main.py` mounts FastAPI's `CORSMiddleware` with exactly the
configured list:

| Argument | Value | Why |
|---|---|---|
| `allow_origins` | the configured allowlist | never a wildcard — the wildcard is refused at parse time |
| `allow_methods` | `GET`, `POST`, `DELETE`, `OPTIONS` | only the methods the mounted routes use (`GET /health`, `GET /api/history`, `POST /api/consent`, `GET`/`DELETE /api/recordings/{id}`) plus the preflight itself |
| `allow_headers` | `Authorization`, `Content-Type` | the caller's own bearer token and a JSON body; nothing else |
| `allow_credentials` | **off** (`False`) | the history routes authenticate with a **bearer token in the `Authorization` header, never with a cookie**, so credentialed CORS would widen the attack surface for no benefit. With credentials off the middleware echoes the exact allowed origin instead of the wildcard |
| `max_age` | `600` | the preflight cache |

Sources: the FastAPI CORS documentation
(<https://fastapi.tiangolo.com/tutorial/cors/>, checked 2026-10-20) and
the OWASP WebSocket Security Cheat Sheet
(<https://cheatsheetseries.owasp.org/cheatsheets/WebSocket_Security_Cheat_Sheet.html>,
checked 2026-10-20).

### 8.4 What this means for the G1 builders

* **Phase 05** — call `origin_allowed(websocket.headers.get("origin"))`
  before `accept()`. Do not read the allowlist yourself and do not invent
  a second rule. The refusal is close **1008**; the accepted socket's
  first message is `status` with `state: "connecting"` (§9), and an
  invalid `start` is closed with **1008**.
* **Phase 04** — the browser's page origin must be on the service's
  allowlist, or the socket handshake is refused. In development that is
  `http://localhost:3000`, the default.
* **Phase 06** — the history routes need **no** cookie-based CORS. A
  bearer token in the `Authorization` header is enough, and credentials
  stay off.

---

## 9. The 2026-10-22 freeze decisions (CEO)

These four decisions settle questions the G1 builds raised after the
first freeze. None of them renames a schema, a route, a port or a field.

1. **The history, consent and recording routes stay out of the OpenAPI
   document.** The service publishes no API surface (`docs_url` and
   `redoc_url` are `None`), and the Phase 01 invariant that `/health` is
   the only documented route stays true. The routes remain mounted with
   `include_in_schema=False`. This corrects §2, which had said the real
   routes would join the document.
2. **The owner of `SessionStorePort.save_metrics` is the verified request
   context.** The store reads `identity.current_user()`; a guest has no
   owner and writes nothing. `save_metrics_for(user_id, record)` is the
   explicit owner form for a caller that already holds the verified id.
3. **The first `/ws/call` message is `status` with `state:
   "connecting"`.** It is not an error. An invalid `start` is reported
   with the frozen error shape and closed with **1008**; a foreign origin
   is still refused with **1008 before `accept()`**.
4. **A saved recording is a real WAV file: `audio/wav`, 16 kHz, mono,
   16-bit.** The writer must send a real WAV container (the Phase 05
   FIX-1 requirement), not raw PCM with an `audio/wav` label. The
   recording route answers `audio/wav` with `Cache-Control: no-store`.
