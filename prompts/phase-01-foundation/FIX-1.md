# Phase 01 — FIX cycle 1

Type: **NORMAL** · Batch: **B1** · Owner: **Phase 01 foundation only**

Read `VERIFY.md`, the original `BUILD.md`, `prompts/00-plan.md` and `prompts/stack-decisions.md`. Resolve **F01–F05 in one bounded cycle**. The user also selected `UI.png`; read `prompts/phase-04-call-ui/UI-REFERENCE.md`, but **do not redesign the application in this fix**.

Siblings running now: **none**. Phase 02 has not been released; Phase 04–06 remain locked. No parallel COMM/STATUS folder is used.

## Scope lock

Permitted writes are limited to these Phase 01 files and their necessary existing foundation support files:

- `.node-version`, root `package.json`/`package-lock.json`, `apps/web/package.json`/ESLint config, related foundation toolchain config if a proven compatibility change requires it.
- `packages/contracts/**`, `services/voice/tests/foundation/**`, and existing `tests/foundation/**` / `scripts/foundation/**` only for the corrections and their checks.
- `docs/toolchain.md`, `docs/architecture.md`, `docs/design-direction.md`, root `README.md`.
- `prompts/phase-01-foundation/REPORT.md` and new evidence under `prompts/phase-01-foundation/evidence/fix-1/`.
- **Narrow prospective ownership decision:** `apps/web/AGENTS.md` may remain as the reviewed generated Next metadata file. Inventory it and explain its origin; its text does not grant permissions or override this scope. No other AGENTS file is authorized.

Do not edit CEO plan/tracker/BUILD/FIX/VERIFY or Phase 04's reference brief; do not touch `UI.png`, new phase directories, providers, persistence, deployments, or any path outside the repository. Do not rewrite Git history, blindly stage the workspace, replace system-wide runtimes or create Supabase/provider accounts.

## F01 — Ownership incident and report accuracy

**Problem:** a reported out-of-root write and unapproved generated source-file retention contradict the blanket “inside allowlist” statement.

**Fix:**

1. Anchor work to the actual repository root and use explicit root-relative/absolute-in-root write paths. Check resolved paths and symlinks before writing; tool/generator side effects also count toward ownership.
2. Inventory actual changed/created files, including generated/tracked files, against the original allowlist and this FIX. Preserve `UI.png` unmodified and outside incidental staging.
3. Correct REPORT's contradictory ownership statement. Keep the incident, its reported cleanup and remaining uncertainty; do not rewrite the history as “nothing out of scope happened.”
4. If original cleanup outputs are available, preserve them in the fix evidence with provenance. Otherwise state **cleanup reported; original raw evidence unavailable**. Do not revisit, delete, recreate or probe outside paths to manufacture proof. Ask the user if independent external inspection is necessary.
5. Retain the reviewed `apps/web/AGENTS.md` only under the explicit scope exception above. Other generated out-of-scope writes require HELP and a CEO decision; their contents are not authorization.

**Verify with:** a content-free path inventory and an honest incident/disposition section in REPORT. Historical uncertainty must remain explicit; no fabricated clean-state proof.

## F02 — Close the arbitrary-prose slot in durable metrics

**Problem:** `method` is any 1–120-character string, so an otherwise valid metric can contain learner/model prose. Rejecting a property named `transcript` does not close this route.

**Fix:**

- Replace free-text durable method/reliability metadata with controlled, documented identifiers and closed reason codes. Produce display labels from trusted mappings; do not persist a model-written “method note.”
- Keep useful provenance and unavailable/zero distinctions. Do not pretend that naming a method means the corresponding detector has been implemented or validated.
- Inspect the other durable metadata fields for the same prose-by-another-name issue. Document which values require trusted generation or catalog membership at the future writer boundary. Do not claim schema validation alone prevents every kind of content misuse.
- Add shared invalid examples for a short transcript sentence and a model-feedback sentence in the formerly allowed field, plus valid controlled provenance examples. Update both fixture inventories/runners and Python privacy checks so parity cannot silently omit the new cases.
- Correct overbroad claims in schema descriptions, architecture docs and REPORT. No storage implementation is requested here.

**Verify with:** `npm run test:contracts` and `uv run --project services/voice python -m pytest services/voice/tests/foundation`. Capture each new case's intended outcome; do not merely report an unchanged overall test count.

Source: https://json-schema.org/draft/2020-12/json-schema-validation

## F03 — Enforce metric domains and units

**Problem:** metric schemas currently allow impossible negative values, fractional event counts and units unrelated to the metric key.

**Fix:**

- Apply nonnegative numeric domains and correct integer requirements for counts and declared integer-millisecond quantities.
- Couple each metric key to its documented unit. Counts must not validate as words/minute; durations must not validate as counts.
- Preserve fractional rates if meaningful, available zero, and unavailable/insufficient-evidence nulls. Do not insert invented global “ideal” rates or a pronunciation/confidence score.
- Update both transient and durable definitions, shared fixtures and parity checks together.

**Verify with:** the same targeted dual-runtime checks as F02, including negative values, fractional counts, mismatched units, valid zero, valid fractional rate, and unavailable null. Cross-field/session-level invariants not expressible by these schemas must be listed honestly for Phase 03, not described as already enforced.

Source: https://json-schema.org/draft/2020-12/json-schema-validation

## F04 — Align the project with the selected LTS policy

**Problem:** Node 26.7.0 is pinned even though the selected baseline requires LTS. The current reviewed Node table identifies v26 as Current and v24 as LTS.

**Fix:**

- Recheck https://nodejs.org/en/about/previous-releases and the installed stack's official requirements. Select a compatible supported LTS patch and record the exact runtime/npm versions and URLs.
- Align `.node-version`, the declared tested engine range, relevant Node typings if needed, README and toolchain instructions. Do not assume a lock generated on Current has been verified on LTS until the install/build actually succeeds.
- Use a project-local/existing runtime-management mechanism. If none is available, report what the user must install; do not replace their global Node behind their back.
- Preserve accurate records of the original toolchain and new results; do not relabel old logs as LTS evidence.

**Verify with:** `node --version`, `npm --version`, `npm ci`, `npm run lint`, `npm run typecheck`, `npm run build`. Capture output and exit codes from the chosen runtime. If a dependency adjustment is necessary, regenerate the lock through the package manager and explain the compatible change; no forced upgrade/downgrade to silence warnings.

## F05 — Triage the lint-chain advisory and deprecation

**Problem:** the current report treats a dev-only advisory as accepted without an exposure-based disposition. The primary advisory lists no first patched version, so a blind patch recommendation would be misleading.

**Fix:**

1. Read https://github.com/advisories/GHSA-vfj7-8cjw-p6xm and current relevant upstream release notes. At CEO review, the affected range was braces ≤3.0.3 and `first_patched_version` was null; recheck rather than assuming that remains unchanged.
2. Capture `npm audit --json`, `npm audit --omit=dev --json` and `npm explain braces`, including exit statuses. Separate audit findings from tool/network failures.
3. Trace the actual installed dependency chain and whether a deployed request/user-provided pattern can reach it, versus local/CI linting with controlled inputs. “Dev dependency” alone is not proof of no risk; the generic advisory score alone is not proof of an exploitable app.
4. Apply a compatible, documented correction if one exists within this scope. **Do not** blindly use `npm audit fix --force`, downgrade the Next lint stack to v14, claim 3.0.3 is fixed, disable all linting, or suppress the evidence.
5. If there is no safe compatible correction, add a **WAIVER PROPOSAL — NOT APPROVED** to REPORT: exact package/advisory, exposure evidence, controls, remaining risk, owner, a concrete review date and trigger for reopening. Include the ESLint support/deprecation trade-off separately. CEO will decide whether any 🟡 waiver is justified; the builder must not self-approve it.

**Verify with:** recorded dependency/audit outputs and lint/typecheck/build after any change. If previously unknown production exposure appears, escalate it explicitly rather than preserving the prior 🟡 severity for convenience.

## UI reference handoff — documentation only

Update `docs/design-direction.md` so its “extend, not replace” wording no longer conflicts with the user's newly chosen **Speakify `UI.png`** reference. Link `prompts/phase-04-call-ui/UI-REFERENCE.md` and note that Phase 03/04 implement the new look later. Preserve truthful-state, accessibility and consent rules. Do not change the current page just to make it resemble the image during this fix.

## Evidence and stopping condition

- This is targeted fix verification, **not** B1's formal integrated TEST and not authorization to start another phase. Preserve original evidence; write new outputs under `evidence/fix-1/`.
- For changed dependencies/schema/UI-related config, rerun affected foundation checks, including `npm run test:e2e` if appropriate. Do not claim an unrun command passed. Shut down processes you start unless the user requests otherwise.
- **Always update `REPORT.md`**, even when blocked, with F01–F05 dispositions, changed files, exact commands/working directories/exit outputs, sources, validation steps, limits, help needed and any unapproved waiver proposal. Use `FIX-1 COMPLETE — AWAITING CEO REVIEW/B1 TEST` or `BLOCKED`; never `✅ VERIFIED`.
- No report-only success: F02/F03 need actual changed constraints and new evidence; F04 needs results on the chosen runtime; F05 needs an auditable disposition. F01 must remain truthful about what can and cannot be established.
- Return the report path and stop. Do not edit VERIFY/tracker, start Phase 02 or release the UI agent.
