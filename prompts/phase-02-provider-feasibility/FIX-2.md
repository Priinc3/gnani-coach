# Phase 02 — FIX cycle 2: bounded filler experiment (goal preserved)

Type: **NORMAL** · Batch **B1** · Owner **Phase 02 only** · Siblings: **none** (Phase 03 and G1 stay paused). No COMM/STATUS folder.

## User decisions (2026-10-20)

- Rotation: user said **no need**. Recorded as `WAIVED: owner-accepted risk, user declined rotation 2026-10-20`, scoped to the user's own keys. It does not relax anything else. Keys still never go in prompts, code, logs or reports. The user supplies them privately through the process environment or `tools/probes/.env` (mode `0600`). Preflight currently shows all names missing. If they are still missing, write REPORT as `BLOCKED: credentials not configured` after the offline parts.
- Filler clip `fixtures/synthetic/audio/spoken-filled-hesitation.wav` (sha256 `82900f99…`): the user listened and **hears both "um" and "uh"**. So the recogniser omitted audible events on this sample. This does not prove permanent inability.
- Direction: **preserve the original goal.** One bounded experiment only.
- Reasoning provider: **keep Gemini.** No Groq/NIM work.

## Scope

OWN: `tools/probes/**`, `fixtures/synthetic/**` (sidecar files only; never alter the WAV), `docs/feasibility/**`, your own REPORT and `evidence/fix-2/**` (immutable run-ID dirs as in fix-1). Provider code under `providers/**` only if an experiment needs a small header/param option.

DO NOT TOUCH: shared settings/main/contracts, capability flags, web/UI, Supabase, other phases, CEO prompts/waivers/tracker. No commit/push/deploy/training/delegation.

## Step 0 — Record the annotation (offline, minutes)

Write a sidecar `fixtures/synthetic/audio/spoken-filled-hesitation.annotation.json` with:
- file sha256 (verify it matches before writing)
- reviewer `project owner (user)`
- date `2026-10-20`
- `um_present: true`, `uh_present: true`
- event positions `null` (not provided; do not invent them)
- note: one clip, not the ≥20 positive + ≥20 negative set.

Do **not** flip any capability or "filler supported" flag. Update `DECISION.md` Q3 with this fact.

## Step 1 — Three cheap routes on that one clip

Run each once with fresh private credentials. Cap the whole step at `--max-requests 16`, using the repaired budget. All live calls need `--allow-live` and `--env-file` before the subcommand. Record every setting used.

| Route | What to try | Source |
|---|---|---|
| **E1 Gnani STT** | Same clip through the realtime STT. Variants: `x-format` `verbatim` vs `transcribe`; lower `x-min-silence-ms` (e.g. 300) to stop VAD splitting off or swallowing the fillers; **word boosting** `x-bias-list` `["um","uh"]` at score `1.0` then `2.0`. Boost words must be single words, letters only, with `x-format: verbatim`. Invalid boosting is silently skipped, so confirm via output that it took effect. | https://docs.gnani.ai/api/STT/stt-websocket |
| **E2 Gemini audio review** | Send the clip inline (under 20 MB) with a prompt asking for a verbatim transcript including filled pauses, as JSON with start/end for each "um"/"uh". Use the model from `GEMINI_MODEL` (docs example: `gemini-3.8-flash`). Docs say timestamps are `MM:SS` (second resolution), so **expect it to fail the ≤300 ms boundary target**. Judge presence and rough position only. | https://ai.google.dev/gemini-api/docs/audio |
| **E3 Offline acoustic** | No spend. Extend the existing candidate detector to also look **inside** VAD speech regions for filled pauses (voiced, steady pitch/low spectral change, ~150–800 ms) instead of only gaps between regions. Run it on the clip and on the clean-speech fixture as a negative. | repo only |

## Stop rules (keep this small)

- Run each route **once per variant**. No tuning against the single clip beyond the listed variants. No new detector project, training or extra providers.
- Pass signal per route: reports **both** fillers on this clip **and** does not report any on `spoken-clear-sentence`.
- If **no route** passes: stop and write REPORT with `NO ROUTE PASSED` and the options. Do not loop.
- If **some route passes**: stop and report which one. Do not build the ≥20/≥20 set. That is the next decision.
- One clip passing is a smoke signal only. It does not meet precision ≥90% / recall ≥80% / p95 boundary ≤300 ms and must not be written up as such.

## Report (`REPORT.md`, short)

1. Annotation sidecar path and hash check.
2. A table of route/variant, exact settings, recognised text or detected events, positions, pass/fail, wire attempts used.
3. Raw command output paths under `evidence/fix-2/`.
4. Credentials status (names configured or missing only), and any blocker.
5. A one-line recommendation: continue to the labelled set (and what data is needed), narrow, or pause.

Verify-with (run last, from the repo root): `uv run --project services/voice python -m pytest services/voice/tests -v` (must stay green), `uv run --project services/voice python tools/probes/secret_scan.py` (0 findings).

End with `FIX-2 COMPLETE — AWAITING CEO REVIEW` or `BLOCKED: <reason>`. Stop after REPORT. Do not start Phase 03 or loop into another fix.
