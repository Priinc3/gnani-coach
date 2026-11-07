# Phase 02 — setup, exact sources, and how to reproduce

Working directory for every command below: **repository root**.

Runtime: Python 3.12.12 managed by `uv` 0.10.9 (the existing version
manager; no global alias, no new runtime, no second version manager).

---

## 1. Offline commands (no keys, no network, no inference)

These are real and were run. Full output is in
`prompts/phase-02-provider-feasibility/evidence/`.

```bash
uv sync --project services/voice
uv run --project services/voice python tools/probes/run.py --help
uv run --project services/voice python tools/probes/run.py preflight
uv run --project services/voice python tools/probes/run.py fixtures --offline
uv run --project services/voice python tools/probes/run.py analysis --offline
```

`analysis --offline` reports absent model assets as **missing**. It never
auto-downloads.

## 2. Credentials

Required **names** for live speech/reasoning — values are never printed,
never written into the repository, and never placed on a command line:

| Name | Needed for | Secret? |
|---|---|---|
| `GNANI_API_KEY` | STT + TTS | yes |
| `GEMINI_API_KEY` | reasoning turn | yes |
| `GEMINI_MODEL` | non-secret model selector | no |

`SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY` are **not** needed for any
Phase 02 probe. The foundation's `provider_readiness()` is deliberately
unavailable and folds Supabase into its `configured` flag; the probes read
`settings.voice` and `settings.gemini` directly and never call it.

### Supplying credentials

The service reads the **process environment**; it never reads an implicit
`.env`. A credentials file is passed explicitly with the top-level
`--env-file` flag:

```bash
uv run --project services/voice python tools/probes/run.py --env-file tools/probes/.env preflight
```

> **`--env-file` is a top-level flag.** It must appear **before** the
> subcommand. The correct order is
> `--env-file <path> <subcommand> …`; the incorrect order is
> `<subcommand> --env-file <path> …`, which fails with
> `unrecognized arguments`. This is an argparse ordering property, not a
> bug, but it is easy to trip on.

Two supported ways to supply the values, both **user-controlled**:

1. **Process environment (recommended).** Export the three names in your
   shell and omit `--env-file` entirely.
2. **A local, user-created file.** Create `tools/probes/.env` yourself,
   with mode `0600`:

   ```bash
   ( umask 077 && touch tools/probes/.env && chmod 600 tools/probes/.env )
   ```

   The file is already ignored by the repository's existing `.env` rule
   and is never read unless you pass `--env-file tools/probes/.env`
   explicitly. **No agent populates it, copies values into it, or
   creates it on your behalf.** The values come from you, through the
   channel you choose.

Example file shape — **names only, values elided**:

```dotenv
# file: tools/probes/.env   (mode 0600, git-ignored, user-created)
GNANI_API_KEY=<redacted>
GEMINI_API_KEY=<redacted>
GEMINI_MODEL=gemini-3.8-flash
```

### Credential exposure record (Phase 02 FIX-1, P02-01)

Four credential values were posted in a conversation message. The
account below is stated as far as the available evidence supports, and
**unknown where unknown**.

| Question | Answer | Basis |
|---|---|---|
| Who wrote the reported external temporary credential file? | The Phase 02 build agent | The Phase 02 build record is the only account of that session; no user-authored record of it exists |
| What authorisation existed for it? | **Not specific.** The user authorised *demo use* of credentials; no authorisation for an external write was recorded | No grant covering an external file is on record |
| Was it actually deleted? | **UNKNOWN — unverified.** | The previous `SETUP.md` stated it "deleted it after the probes". That sentence is a **claim, not cleanup evidence**. No deletion receipt, no directory listing and no post-hoc existence check were recorded |
| Was the file's content inspected? | **No.** No external credential file was opened, read or revealed in this cycle | — |

**What this cycle did not do, deliberately.** It did not visit, list, open
or delete any file outside the repository, and it did not kill any
process. Fabricating or "re-doing" the cleanup would make the record
worse, not better. The honest position is: the external file's current
state is **unverified**, and it must be confirmed by the owner.

**What the owner needs to do (outside an agent's reach).** Provider
dashboard actions belong to the owner:

- **Confirm rotation status** for every credential that was posted.
  Rotation status only — never the replacement values, in any prompt,
  file, log, evidence file or report.
- Confirm whether the external temporary file still exists, and delete
  it if it does.
- Only then re-supply replacements privately, by process environment or
  by creating `tools/probes/.env` themselves.

### In-repository credential-leak check

A structural scan of the working tree is available and **content
suppressed**: it prints only repository-relative paths, line numbers,
rule identifiers and counts. It never prints the matched text, so a
finding cannot leak the value it reports.

```bash
uv run --project services/voice python tools/probes/secret_scan.py
uv run --project services/voice python tools/probes/secret_scan.py --json
```

Exit code `0` means no finding; `1` means at least one finding.

> **A clean scan does not erase the conversation exposure.** It only says
> "no leak found in the tree". The four posted values were exposed in a
> conversation, and only rotation addresses that.

## 3. Optional model-asset preparation (explicit, offline-safe)

Silero VAD is **not** fetched implicitly. Preparation is a separate command
and the only network write in the harness:

```bash
uv run --project services/voice python tools/probes/run.py analysis --prepare-models
```

| Asset | Value |
|---|---|
| File | `tools/probes/.cache/models/silero_vad.onnx` |
| Size | 2,327,524 bytes |
| sha256 | `2623a2953f6ff3d2…` (full value recorded in `.cache/models/silero_vad.provenance.json`) |
| Source | `https://raw.githubusercontent.com/snakers4/silero-vad/v5.1/src/silero_vad/data/silero_vad.onnx` |
| Licence | MIT (snakers4/silero-vad) |
| Cache | `tools/probes/.cache/` — already ignored by the repository's existing `.cache/` rule |

**Why ONNX and not the `silero-vad` package.** The `silero-vad` PyPI
package 6.2.3 declares `torch>=1.12.0` as an **unconditional base
dependency** (verified against the published `requires_dist`, where `torch`
carries no extra marker), even though the `onnx-cpu` extra exists. On
macOS arm64 that is a 127 MB `torch` wheel plus transitive dependencies for
a model that needs only speech/silence decisions. The MIT-licensed ONNX
graph is loaded directly with `onnxruntime` 1.31.0 on CPU instead.

The graph signature was **read from the prepared asset**, not assumed:

```text
input : float32[batch, samples]   512 samples at 16 kHz
state : float32[2, batch, 128]    2 LSTM layers x batch x 128
sr    : int64  []                 scalar sample rate
-> output : float32[batch, 1]
   stateN : float32[2, batch, 128]
```

`state` being rank **3** rather than a flat 256-vector is exactly the detail
a guessed implementation gets wrong, which is why the shapes are asserted
against the live session at construction time.

## 4. Live commands (explicit consent, bounded)

Each requires `--allow-live`. Without it the command reports `BLOCKED` and
makes no inference call. A content-free plan line is printed **before** any
call, and an over-limit plan is refused before the first call.

```bash
# 1. Render the real spoken fixtures with this project's own TTS endpoint.
uv run --project services/voice python tools/probes/run.py --env-file tools/probes/.env \
  fixtures --allow-live --prepare-spoken

# 2. One bounded STT run. `--language` is a catalog selector: an id, a
#    display name or a code, all resolved through the shared catalog.
uv run --project services/voice python tools/probes/run.py --env-file tools/probes/.env \
  speech --language english --fixture spoken-clear-sentence --allow-live --max-requests 8

# 3. One real STT -> Gemini -> TTS turn.
uv run --project services/voice python tools/probes/run.py --env-file tools/probes/.env \
  chain --language english --fixture spoken-clear-sentence --voice Kaveri \
  --tts-model timbre-v2.5 --allow-live --max-requests 8

# 4. Language matrix. See the budget note before running this one.
uv run --project services/voice python tools/probes/run.py --env-file tools/probes/.env \
  matrix --allow-live --max-requests 40 --fixture spoken-clear-sentence \
  --languages english hindi bengali gujarati kannada

uv run --project services/voice python tools/probes/run.py --env-file tools/probes/.env \
  matrix --allow-live --max-requests 40 --fixture spoken-clear-sentence \
  --languages malayalam marathi punjabi tamil

uv run --project services/voice python tools/probes/run.py --env-file tools/probes/.env \
  matrix --allow-live --max-requests 40 --fixture spoken-clear-sentence \
  --languages telugu hinglish

# 5. Optional audio review (a separate explicit operation).
uv run --project services/voice python tools/probes/run.py --env-file tools/probes/.env \
  analysis --allow-live
```

### 5.1 The bounded filler experiment (`filler`)

Phase 02 FIX cycle 2 added one command. It runs the three routes of the
bounded filler experiment — the Gnani STT (five variants), a Gemini audio
review, and an offline acoustic scan — on **one** clip, under **one**
shared budget of at most **16 wire attempts**:

```bash
# The whole step. E1 and E2 need the credentials; E3 is offline and always runs.
uv run --project services/voice python tools/probes/run.py --env-file tools/probes/.env \
  filler --allow-live --max-requests 16
```

| Route | Variants | Wire attempts each | Needs |
|---|---|---|---|
| E1 — Gnani realtime STT | 5 (`verbatim`/`transcribe`, `x-min-silence-ms` 500/300, `x-bias-list ["um","uh"]` at 1.0 and 2.0) | 2 (connect + session) | `GNANI_API_KEY` |
| E2 — Gemini audio review | 2 (the clip and the clean-speech clip) | 1 | `GEMINI_API_KEY`, `GEMINI_MODEL` |
| E3 — offline acoustic scan | 2 (the clip and the clean-speech clip) | 0 | the prepared VAD model asset |

The plan is checked **before** any call, and a plan that does not fit is
refused before any side effect. E1 variants that report both fillers earn
a negative-control run on `spoken-clear-sentence`; the whole step never
exceeds 16 wire attempts, and a control that does not fit is reported
`NOT RUN` rather than skipped silently.

Two routes are **code-verified but not provider-verified** while no
credential is configured:

```bash
# Fakes only: no socket, no request, no credential. Proves the code path runs.
uv run --project services/voice python tools/probes/dryrun_filler_routes.py
```

The `filler` command writes its immutable evidence to
`prompts/phase-02-provider-feasibility/evidence/fix-2/<run-id>/`, never
into `fix-1`'s history.

> **Word boosting is validated locally, not by the provider.** The
> documented rules (up to 100 single words of letters only; a score of
> 0.0, 0.5, 1.0, 1.5 or 2.0; `x-format: verbatim` required) are checked
> in the adapter, because the provider **skips invalid boosting
> silently** — a skipped boost is indistinguishable from a boost that had
> no effect. The probe also echoes the boost back through the documented
> `update_settings` control frame and reports the server's answer as
> *absent* when it is absent.

### Language selectors resolve through the shared catalog

`--language` and `--reply-language` accept a catalog **id**
(`english`, `hinglish`), a **display name** (`English (India)`) or an
STT/TTS **code**. All three are resolved through
`packages/contracts/data/catalog.json`, which this phase reads and never
edits.

A selector that could mean more than one entry is **refused as
ambiguous** rather than guessed. `en-IN` is the STT code of both English
and Hinglish, so `en-IN` is rejected with a message naming both ids;
use `english` or `hinglish` instead. Hinglish keeps its own separate
mapping — STT `en-IN`, TTS `hi-en` — and neither is presented as the
other.

### The matrix does not fit in one invocation — this is arithmetic, not a bug

A completed language row costs **5 provider operations** (STT connect + STT
session, TTS connect + TTS synth, one Gemini reply) and about **3
connections**. Eleven rows therefore need ~55 operations against a hard
limit of 40. Unrun rows are reported `NOT RUN` with the reason. Split with
`--languages`; that is how the eleven rows were covered here.

### Other useful options

| Option | Effect |
|---|---|
| `--json` | machine-readable summary of the checks |
| `speech --burst` | send without real-time pacing; records the documented VAD-accuracy degradation |
| `analysis --force` | re-download the model asset even if present |
| `chain --attempt-timeout S` | bound on **one** reasoning wire attempt (default 15 s) |
| `chain --call-deadline S` | overall bound on the reasoning call, covering every attempt and backoff (default 45 s) |

The two reasoning bounds are **configurable** and are printed in the
chain's own summary. The call deadline is a **feasibility-probe
diagnostic bound**; it is deliberately not the app's ≤3-second
voice-turn target, and the two must never be substituted for one
another in a report. A local timeout is **not** a provider cancellation
and makes **no** claim about billing.

## 5. Safety limits (not pricing estimates)

Enforced in `gnani_coach.providers.limits.ProbeBudget`. Every limit is
validated as finite and nonnegative at construction, and every limit is
checked against a global maximum — a caller may **tighten** a limit but
never raise one, so `ProbeBudget(max_operations=500)` raises
`BudgetExceededError` rather than being honoured.

### One retry authority

The **adapter boundary** is the only retry authority. The pinned
`google-genai` 2.31.0 SDK is configured with
`HttpRetryOptions(attempts=1)` — documented by the SDK as *including the
original request*, so `1` means **no internal retry**. An SDK-internal
attempt is invisible to any caller-side counter, so none is allowed to
happen. Every retry is performed by the adapter and every wire attempt
is admitted by the budget **before it starts**.

### Four counters, never conflated

| Counter | Meaning |
|---|---|
| `logical_calls_used` | requests the caller asked for |
| `wire_attempts_used` | actual HTTP/WebSocket exchanges started — this is what the 40 cap bounds |
| `connections_used` | transports established |
| `retries_used` | wire attempts beyond the first attempt of their logical call |

A **timed-out attempt still counts**: the provider may still be working
on it, and it may still be billed.

| Limit | Value |
|---|---|
| Wire attempts per live invocation | 40 |
| Submitted STT audio per live invocation | 300 s |
| Retries per logical call | 2 (only `rate_limited`, `timeout`, `network`) |
| Connections per live invocation | 40 |
| Provider message size | 1 MiB |

Auth, invalid-input, protocol and configuration failures are never
retried. Trailing silence sent to close the server's VAD window is
charged as submitted audio, and a plan is sized on the **framed
submitted** audio — including that silence — not on the clip's own
duration.

A chain turn really costs **five** wire attempts (STT connect, STT
session, reasoning attempt, TTS connect, TTS synthesise). The plan is
checked against that minimum before any call, and an over-limit plan is
refused before the first side effect.

A child budget is **reserved from its parent at creation**, so two
concurrent children can never both be handed the same remaining
allowance. Absorption never clamps: an overrun is recorded and reported,
not hidden.

### Evidence

Every invocation writes an **immutable run directory** under
`prompts/phase-02-provider-feasibility/evidence/fix-1/<run-id>/` holding
the exact argv, working directory, runtime, exit code and the redacted
stdout/stderr. A prior success, failure or cancellation is never
overwritten. The append-only index is
`prompts/phase-02-provider-feasibility/evidence/fix-1/run-index.jsonl`.

The FIX-2 cycle keeps its own directory,
`prompts/phase-02-provider-feasibility/evidence/fix-2/<run-id>/`, with
the same layout and its own
`prompts/phase-02-provider-feasibility/evidence/fix-2/run-index.jsonl`.
A fix-2 run never writes into fix-1's history.

The aggregate run index `tools/probes/.cache/runs.jsonl` is still
appended to, one record per invocation, never overwritten; a copy of the
Phase 02 index is preserved at
`prompts/phase-02-provider-feasibility/evidence/run-index.jsonl`.

## 6. Dependencies added in Phase 02

`services/voice/pyproject.toml` and `services/voice/uv.lock` were the only
manifests touched. The Python 3.12 family and all foundation dependencies
are unchanged.

| Package | Version | Why | Licence |
|---|---|---|---|
| `websockets` | 16.1.1 | Low-level transport. The Gnani STT page states the `gnani-vachana` Python SDK **does not expose VAD tuning** and directs you to a raw WebSocket client, so that SDK is deliberately not installed. Pinned `<17` because `google-genai` requires `websockets<17`. | BSD-3-Clause |
| `google-genai` | 2.31.0 | Current Google GenAI SDK (Interactions API) | Apache-2.0 |
| `numpy` | 2.5.4 | PCM / VAD numerics; Python 3.12 floor matches the project | BSD-3-Clause |
| `onnxruntime` | 1.31.0 | CPU VAD inference without the torch dependency | MIT |

No npm dependency was touched, so W01/W02 are unaffected.

## 7. Tests

```bash
uv run --project services/voice python -m pytest services/voice/tests
```

The default suite performs **no inference, opens no socket and downloads
no model**. Live checks live in `tests/providers/test_live_optional.py`,
carry the `live` marker, and skip unless **both**:

```bash
GNANI_LIVE_TESTS=1 GNANI_API_KEY=… GEMINI_API_KEY=… GEMINI_MODEL=… \
  uv run --project services/voice python -m pytest services/voice/tests/providers -m live
```
