# Phase 02 review — NEEDS-FIX and goal decision required

Date: **2026-10-18**. CEO inspected files, supplied evidence and online documentation; no tests, inference, key validation or application edits were performed.

**Phase: NOT VERIFIED. Batch B1: NEEDS-FIX / NOT VERIFIED. Phase 03 and G1 remain paused.**

Findings: **2 🔴 · 3 🟠 · 2 🟡** for this review, separate from Phase 01's existing temporary waivers. The current filler method is not an accepted route to the original DONE condition. Read `DECISION-NEEDED.md`; do not keep expanding the prototype without the user's decision.

## Useful progress supported by artifacts

- `evidence/live-chain-result.json:1–33` records one English STT → Gemini → TTS chain's counts/timings and 81,920 returned TTS bytes. This supports a plumbing milestone, not reliable calls or the full quoted content provenance.
- `evidence/07-pytest-services.txt:1–14` reports 146 passes and 3 skips. It does not prove the live failure paths, accuracy target or batch acceptance passed.
- `evidence/live-matrix-result-d.json:9–12` explicitly records STT/TTS success and Gemini failure for the Tamil-parameter probe.
- Report and code distinguish candidate filler events from confirmed events, and acknowledge no reviewed filler labels. No shared capability flags were reportedly flipped.

## Findings

### P02-01 — 🔴 Exposed credential material; scope/cleanup account is inconsistent

The user's message contains four credential values; `REPORT.md:380–387` also acknowledges conversation exposure. They must not be propagated into agent prompts, source, command output or reports. Their present validity/misuse was not checked. See `prompts/provider-access.md` for private provisioning and prompt-safe names; rotate now, not at project completion.

`REPORT.md:63–80` describes all side effects as inside normal ignored locations and says everything stayed in the allowlist, but lists an external temp credential file. `docs/feasibility/SETUP.md:65–69` says it was deleted; REPORT does not establish that cleanup, its author or authorization. Treat this as an unresolved scope/credential-handling record, not proof of a second authorized external write. No external secret file was opened by CEO.

Fix: stop live use pending replacement credentials, correct the record and inventory with available evidence, keep future secret provisioning user-controlled, and perform any in-repository secret check with content-suppressed output. [Gemini key guidance](https://ai.google.dev/gemini-api/docs/api-key), [Groq quickstart](https://console.groq.com/docs/quickstart).

### P02-02 — 🔴 Broken operation-budget contract and underplanned requests

`providers/gemini.py:206–210,222–231,253–255` enables SDK-managed attempts but debits the budget only once and explicitly says attempts cannot be counted. Therefore `REPORT.md:155–156` cannot substantiate “inside allowance” and “retries: 0” as actual wire-attempt claims.

`tools/probes/live/probes.py:108–110,218–220` excludes the adapter's trailing silence from speech/chain preflight; the chain plans four operations although its own success evidence records five. Low limits can thus fail only after requests have already spent credit. `providers/limits.py:172–211` neither reserves a child allowance immediately nor reports overrun honestly when absorption clamps totals.

Fix: one authoritative attempt budget across retries/children; preflight includes connections, actual synthesis/inference attempts and padded submitted audio; no silent saturation or invented historical counts. Validate finite/nonnegative limits as well. This is a static contract defect, not a claim CEO observed a billed overrun. Actual retry-setting semantics must be checked against the [installed SDK's primary documentation](https://github.com/googleapis/python-genai).

### P02-03 — 🟠 Timeout returns, but local work and resources are not bounded safely

`providers/gemini.py:264–302,351–378` creates a fresh client and daemon thread per reply, has no explicit client close, and abandons waiting without retaining a worker-capacity limit. The closed-loop check is before the blocking call; a late result can attempt `call_soon_threadsafe` after loop closure. Repeated timeouts in a future long-lived voice service can leave concurrent work accumulating.

`REPORT.md:188–193` confirms a later chain timeout; HANDOFF's timeout table also disagrees with the code's default 70-second outer wait. Calling this “cancels cleanly” overstates the guarantee. Python's [threading documentation](https://docs.python.org/3.12/library/threading.html) distinguishes daemon exit from graceful resource cleanup.

Fix: documented async lifecycle/cancellation where supported, or strictly bounded retained ownership of unavoidable blocking work; no replacement worker while an abandoned one still consumes its slot. Close clients, fence late results and report actual deadlines. Do not blame all failures on the provider without distinguishing adapter, auth, throttle, network and timeout outcomes. Do not freeze a model solely because one attempt worked.

### P02-04 — 🟠 Matrix aggregate can pass despite failed required stages

`tools/probes/live/probes.py:445–473` determines matrix success only from STT, ignoring failed TTS/Gemini cells. The Tamil evidence has a failed Gemini cell. This can falsely green-light the integrated voice path.

The same code feeds one fixture to all STT locale rows (`:488–501`) and English text to every TTS row (`:529–535,583–585`). Those calls demonstrate parameter acceptance/bytes returned, **not recognition or synthesis of the selected language**. The chain also maps only the display string `English` to a TTS locale (`:279–284`); other display names are not a stable language-code mapping.

Fix: distinguish parameter acceptance, native-language fixture coverage and reviewed quality; overall success requires every requested required stage to succeed. Normalize language IDs/codes through the existing catalog. Missing native fixtures stay NOT RUN/INCONCLUSIVE rather than being covered by English substitutes.

### P02-05 — 🟠 Original filler-localization goal remains blocked

`REPORT.md:278–300` provides zero verified positive/negative examples and cannot distinguish synthesis omission from recognition omission. `tools/probes/analysis/filler.py:161–193` searches only gaps between VAD regions, so it does not evaluate filled pauses merged into speech. It is appropriately labeled a candidate, not a validated detector.

`docs/feasibility/DECISION.md:85–106,173–178,202–208` nevertheless calls the recognizer result a correctness failure, describes a speaker who hesitated twice, and makes broad claims about which approach is the only possible route. Those conclusions exceed the unreviewed audio evidence. A short clip review can resolve this fixture's ambiguity; it cannot validate all languages or the ≥90%/≥80% target.

Fix the decision wording and use the user's choice in `DECISION-NEEDED.md`. Do not silently narrow the product, fabricate labels, enable a filler count of zero, or treat a text-LLM provider change as solving audio assessment. No new detector investment is authorized merely because more API keys are available.

### P02-06 — 🟡 Evidence provenance and preservation are incomplete

`tools/probes/live/probes.py:91–95,328,471` overwrites fixed result names. `live-chain-result.json` contains lengths/timings but no fixture hash, recognized text/reply or raw-frame reference; it alone cannot substantiate the fully quoted chain in REPORT. `docs/feasibility/HANDOFF.md:12–24,74–80` calls examples actual received frames while including documentation-style 2024 timestamps and placeholder request IDs. Label examples separately from captures.

`REPORT.md:144–156` gives approximate operation totals despite known SDK retry-count uncertainty. Broken relative links in REPORT point up two levels rather than three to repository docs. Preserve old files; add immutable run IDs, exact command/exit metadata and synthetic-only stage provenance. Missing historical output must stay missing, not be reconstructed as raw evidence.

### P02-07 — 🟡 Learner-only measurement guard accepts invalid source sets

`tools/probes/analysis/metrics.py:46–51` rejects multiple distinct source labels, but accepts an assistant-only set or an empty set. That does not enforce the advertised learner-only boundary (`:20–23`). A trusted source identity is still needed; a label alone cannot establish speaker identity.

Fix the probe-level validation and negative tests, while keeping full stream ownership/echo exclusion for the later runtime. Also distinguish missing recognition/no speech from a genuinely measured zero rate. Do not promote this prototype as fully validated delivery scoring.

## Verdict and next gate

- The positive plumbing evidence is retained. No claim is made that all work is invalid, that credentials were abused, or that Gnani can never preserve fillers.
- `FIX-1.md` batches the concrete repairs; only offline repair is immediately runnable. Fresh live probes require private replacement credentials and repaired budget/lifecycle controls.
- The **goal-level decision remains with the user**. No Phase 03 BUILD, full UI release, batch acceptance or new detector/fine-tuning loop is issued now.
- New Groq/NIM documentation is indexed in `prompts/provider-access.md`; optional comparison remains separate from the filler decision and cannot silently select a production model.
- CEO used read-only searches/documentation and local inspection only. No app code, shell, test, inference, credential storage or agent launch occurred.

---

# FIX-1 review — 2026-10-20

**Phase 02: NOT VERIFIED (code repairs accepted offline; 2 items blocked on user). Batch B1: still NOT VERIFIED. Phase 03 and G1 stay paused.**

Method: read REPORT.md plus spot checks of the code (grep only). I ran no tests. Test counts (247 pass / 3 skip, 46 contract examples, secret scan 0 findings) are the builder's evidence and sit in `evidence/fix-1/`.

## Disposition

| ID | Result | Basis |
|---|---|---|
| P02-02 budgets | ✅ accepted offline | `HttpRetryOptions(attempts=1)` at `gemini.py:274`; `admit_attempt` called before each wire attempt in gemini/stt/tts. Live accounting is unproven |
| P02-03 lifecycle | ✅ accepted offline | Daemon thread removed; async client closed via `aclose` (`gemini.py:294-305`). Real-provider cancellation unproven |
| P02-04 matrix | ✅ accepted offline | `NO_MODEL_TEXT` state exists (`probes.py:77`); all-stage aggregation claimed and tested |
| P02-06 evidence | ✅ accepted | Immutable `evidence/fix-1/<run-id>/` dirs and a ledger exist; historical counts are labelled UNKNOWN |
| P02-07 source check | ✅ accepted | `assert_trusted_learner_source` (`metrics.py:114`) and `missing-transcription` status exist |
| P02-01 credentials | 🔴 open, user action | Repo scan is clean. Rotation is unconfirmed and the external temp file is unverified. The agent correctly did not touch or fabricate either |
| P02-05 filler goal | 🟠 open, user decision | Wording repaired and NO-GO kept. Clip review and direction choice are still pending |

## Notes
- The agent was right to reject the "three levels up" link fix. My FIX-1 had the wrong depth. The error was mine, not a builder defect.
- 🟡 Run noise: 75 fix-1 run dirs for about 6 distinct commands. Waived (`WAIVED: immutable evidence by design`); no further cleanup is requested.
- **Live gate:** No live call until the user confirms rotation. Then one short live re-check under the repaired budget closes the "reliability INCONCLUSIVE" item.

## Next gate (user only)
1. Confirm the keys are rotated and configured privately.
2. Listen to `fixtures/synthetic/audio/spoken-filled-hesitation.wav`: um/uh present, neither, or unclear.
3. Pick the filler direction: preserve, narrow or pause.
4. Reasoning providers: compare, or keep Gemini.

No FIX-2 is needed for code. Depending on answer 3, I issue either a bounded disfluency experiment BUILD or a revised plan, then Phase 03.

---

# FIX-2 review — 2026-10-20

**Phase 02: accepted as feasibility work. Batch B1: NOT VERIFIED (no batch TEST yet).**

- ✅ The annotation sidecar is recorded, with the hash check, positions `null`, and no flags flipped.
- ✅ E3 ran offline: 1 candidate event vs 2 audible fillers → FAILED; negative control clean. The agent tuned no parameters.
- ⚠️ E1 and E2 are BLOCKED: no credentials in the environment and no `tools/probes/.env`. **Unproven:** Gnani with boosting or `transcribe`, and Gemini audio review. The B1 TEST runs both once.
- 🟠 Carried: filler localisation is unvalidated. It is not waived to a success. Phase 03 freezes it as `insufficient_evidence`, and the goal stays preserved for Phase 08.
- 🟡 Run noise in the evidence dirs: `WAIVED: immutable by design`.
