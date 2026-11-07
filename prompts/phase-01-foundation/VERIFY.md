# Phase 01 — FIX-1 review accepted; batch verification pending

## Current disposition — 2026-10-18

**FIX-1 corrective work: ACCEPTED within its foundation scope.**
**Phase acceptance: BUILT / AWAITING B1 TEST — not yet ✅ VERIFIED.**
**Batch B1: NOT VERIFIED; Phases 02–03 and the integrated TEST are still outstanding.**

Current reviewed findings: **0 open 🔴 · 0 open 🟠 · 0 unwaived 🟡**. Three limited yellow dispositions are recorded in [`../waivers.md`](../waivers.md): F05-A advisory, F05-B ESLint support, and F06 evidence-label defect. They are not clean-audit, production-release or whole-project approvals.

No FIX-2 is needed for the corrections reviewed here. Wait for the user's **`next`** before preparing the Phase 02 prompt within the already planned B1 construction sequence. G1/B2 remains locked until B1 has its required TEST-RESULT, VERIFIED verdict and user `next`.

### What was checked

CEO read the updated REPORT, both actual metric schemas, the new named Python privacy/domain tests, current `.node-version`/`.nvmrc`/package manifests, the static ESLint configuration, design handoff documentation and FIX-1 evidence. No app command, test, runtime installation, Git operation or external filesystem inspection was performed by CEO.

Key supplied artifacts:

| Evidence under `evidence/fix-1/` | Supported conclusion |
|---|---|
| `04-node-lts-install.txt:1–6`, `05-npm-ci-lts.txt:1–12` | Builder used Node 24.22.0/npm 11.19.1 and recorded a successful install path |
| `06-lint-typecheck-lts.txt:1–23`, `07-build-lts.txt:1–23` | Lint, typecheck and Next build recorded successful exit statuses on the selected runtime |
| `08-test-contracts-lts.txt:11–18` | 46 shared examples: 15 valid, 31 invalid, with reported successful validation |
| `09-pytest-fix.txt:1–35` | Correctly named `services/voice` command; 23 passes including the new F02/F03 tests |
| `10-test-e2e-lts.txt:1–11` | Supplied output excerpt reports 12 Playwright passes; this is not a complete unfiltered transcript |
| `02a-audit-full-raw.json`, `02b-audit-omit-dev-raw.json`, `03-npm-explain-braces.txt` | Known five-entry development dependency chain; production-only audit lists no known advisories at capture time |
| `12-path-inventory.txt`, `11-ui-png-integrity.txt`, integrity section of `13-final-recheck.txt` | Builder's workspace/side-effect inventory and supplied UI integrity evidence; not an independent audit of all machine state |

### Finding dispositions

**F01 — corrective accountability accepted; historical cleanup remains unverified.**

`REPORT.md:29–55` now acknowledges the original out-of-root write, the false blanket ownership statement, and the separately authorized generated AGENTS file. `REPORT.md:57–135` inventories subsequent changes and disclosed tool side effects. This satisfies FIX-1's corrective record/inventory requirement; it does **not** retroactively authorize the incident or prove that the outside path was cleaned. That historical uncertainty stays explicit; no new outside inspection/deletion is authorized.

The project `.nvmrc` is accepted as F04-related toolchain configuration. Use of the existing nvm mechanism was allowed by FIX-1. The report discloses that installing the LTS runtime also changed the resolution of the pre-existing moving `lts/*` default alias. This is not described as “no machine-state changes.” Future agents must disclose tool side effects and must not alter aliases/system runtimes or uninstall this runtime without a fresh need/authorization. The inventory's “zero symlinks” summary is not treated as proof that every ignored package/runtime directory is symlink-free.

**F02 — corrected.**

`durable-metrics.schema.json:61–74,79–152` replaces the free-prose method slot with controlled identifiers/reasons, requires the appropriate branch and rejects the other. `services/voice/tests/foundation/test_privacy_shapes.py:46–85` explicitly covers prose in the previously allowed field and controlled positive cases; the supplied dual-runtime results support the correction. Descriptions now distinguish schema enforcement from future writer/logger responsibilities. No actual storage privacy guarantee is inferred from this foundation-only result.

**F03 — corrected for the requested numeric/unit domain.**

`durable-metrics.schema.json:156–245` and `analysis-observation.schema.json:89–172` couple metric keys to nonnegative values, integer counts/milliseconds and their intended units. Named tests at `test_privacy_shapes.py:88–170` cover invalid values/units and valid zero/fractional rates. The report correctly leaves other semantic/session invariants for Phase 03. This is not validation of an audio measurement algorithm.

**F04 — corrected.**

Both runtime pin files contain 24.22.0; `package.json:6–8` limits the declared family to 24.x; `apps/web/package.json:19` aligns Node typings. Supplied install/static/build results identify that runtime. Fresh [Node release documentation](https://nodejs.org/en/about/previous-releases), searched 2026-10-18, identifies v24.22.0 as LTS. No other runtime/OS/browser combination is thereby proven.

**F05 — two short, conditional yellow waivers approved.**

The [primary braces advisory](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm), searched and read on 2026-10-18, still lists affected versions ≤3.0.3 and no patched version. Current project configuration and supplied dependency evidence support a narrowly scoped local-lint risk disposition, not the report's absolute statement that future deployed input “cannot reach it.” The production-only audit is a snapshot of known dependency advisories, not proof of general security. See W01.

[ESLint's current support policy](https://eslint.org/version-support/), searched 2026-10-18, states that v9 reached EOL on 2026-08-06. **“Supported-in-practice” is not accepted as an upstream support claim.** Temporary use of the already functioning development lint chain is permitted separately under W02 while compatibility is reassessed. Both waivers expire at Phase 03 dependency freeze or 2026-10-25, whichever occurs first; the proposed 2026-11-16 deadline is not accepted.

**F06 — 🟡 mislabeled duplicate evidence, excluded rather than silently accepted.**

`evidence/fix-1/13-final-recheck.txt:9` labels its Python recheck as `uv run --project services/python -m pytest ...`, which is not the established voice-project command. This line does not establish a correctly reproduced October 18 pytest run. Several other supplied logs are excerpts rather than full raw capture. The correctly labeled verbose result in `09-pytest-fix.txt` remains the supporting fix evidence. W03 accepts this documentation defect only for the interim correction review, excludes the malformed recheck as independent proof and requires exact, unfiltered command evidence at B1. Do not overwrite historical logs to conceal the discrepancy.

### Mandatory handoff before contract freeze

These are planned Phase 02/03 deliverables, not completed features and not permission to relax the goal:

1. Validate real Gnani/Gemini behavior and disfluency evidence before claiming a working call or learner assessment. Missing keys/access are explicit blockers, not successful mock results.
2. Resolve provenance semantics: `durable-metrics.schema.json:69,201–227` currently uses the same speech-active method description for both overall rate and speech-active rate. Phase 03 must preserve their different denominators, and define turn duration from the learner's audio clock—not network/connection delay—before any producer emits these metrics.
3. Implement/assign the reported cross-field invariants. Do not equate total speaking-active time with the sum of elapsed turn spans if those spans include silence. Keep writer/auth/storage checks distinct from schema shape checks.
4. Revisit W01/W02 with fresh full and production-only audits before freezing dependencies. Capture future commands with exact working directory, runtime, stdout/stderr and exit status. Replace neither real errors nor missing results with expected output.
5. Keep `UI.png` and `phase-04-call-ui/UI-REFERENCE.md` as the visual target. `docs/design-direction.md:1–14` now correctly records that precedence; no premature redesign was required in this fix.

### Goal check

The scoped contract defects and runtime deviation are addressed, so another foundation fix loop would not be the cheapest useful next step. The next planned work is provider/measurement feasibility after the user's `next`. Full Phase 01/B1 acceptance still waits for the scheduled three-phase batch test. No live call, persistence, all-ten language support, UI-reference implementation or deployed application is declared done.

---

## Historical review — 2026-10-16 (superseded by dispositions above)

The following retains the original findings. Its REPORT line references refer to the pre-FIX report, which the current report identifies as preserved at commit `6805a30`; they are not current open findings.

Date: 2026-10-16 · Review mode: file/code/evidence inspection only; no commands or tests run by CEO.

**Phase verdict: NEEDS-FIX / NOT VERIFIED.**
**Batch B1 verdict: NEEDS-FIX; formal batch test not yet due or supplied.**

Open findings: **2 🔴 · 0 🟠 · 3 🟡**. No waivers approved. Phase 02 handoff is paused; G1 remains locked. Correct all findings in `FIX-1.md`, update REPORT, then return the evidence for review. The current successful unit/e2e logs do not replace B1 acceptance after Phases 01–03.

## Evidence inspected

- `REPORT.md`, its original BUILD allowlist, plan/tracker and stack decisions.
- Raw final output: `evidence/06-build.txt`, `07-test-contracts.txt`, `08-pytest.txt`, `11-playwright.txt`, `10-uvicorn-health.txt` and `02b-npm-audit.txt`.
- `evidence/12-starter-desktop.png`; actual user reference `UI.png`.
- `package.json`, `.node-version`, `docs/toolchain.md`, `docs/design-direction.md`, `apps/web/AGENTS.md`.
- `packages/contracts/schemas/{durable-metrics,analysis-observation}.schema.json` and `services/voice/tests/foundation/test_privacy_shapes.py`.
- Fresh searches for Node release status, the braces advisory and JSON Schema validation semantics; the primary GitHub advisory was retrieved read-only.

## Findings

### F01 — 🔴 Ownership boundary breached; cleanup is reported, not independently established

`prompts/phase-01-foundation/REPORT.md:40–44` records a write outside the workspace at `~/GitHub/oss/f5T10n/dev.md`. This violates `BUILD.md:43–45` even if subsequently removed. `REPORT.md:15–16` simultaneously says everything stayed in the allowlist. Impact: scope/safety guarantees and the report's ownership statement are unreliable.

Separately, `REPORT.md:31` says `apps/web/AGENTS.md` was retained/committed because its own generated content instructed that. It was not in the original source-file allowlist. A generated file cannot authorize its own scope expansion.

Remedy: truthful incident accounting, available original cleanup evidence, a complete actual write inventory and root-relative write discipline. Do not revisit/delete outside paths to manufacture cleanup evidence. FIX-1 gives **prospective, narrow approval** to retain the reviewed generated `apps/web/AGENTS.md`; that does not erase the earlier incident or elevate its instructions above ownership rules. No ongoing external data loss has been established by this review.

### F02 — 🔴 Broken metrics-only contract: an allowed field accepts arbitrary prose

`packages/contracts/schemas/durable-metrics.schema.json:67–71` allows any 1–120-character `method` string. A short transcript or model sentence can occupy that field while satisfying its constraints. The description saying “never learner or model prose” is not a validator. This contradicts the schema's own assurance at line 5 and `REPORT.md:120`.

`services/voice/tests/foundation/test_privacy_shapes.py:25–37` rejects disallowed **property names**, but does not test speech/model text inside an allowed field. Existing green tests therefore miss this boundary. This is a privacy-contract defect before persistence is built, **not a claim that stored personal data was actually leaked**.

Remedy: controlled method/provenance IDs and closed reason codes; labels produced from trusted application mappings, not copied from learners/LLMs. Test prose in the previously allowed field in both validators and narrow the report's guarantees to what is actually enforced. Even a schema with closed IDs does not prove future writers/loggers respect privacy.

Source: [JSON Schema validation vocabulary](https://json-schema.org/draft/2020-12/json-schema-validation): length constraints limit length, while enumerations restrict allowed values. This is a static inspection finding; the counterexample was not executed by CEO.

### F03 — 🟡 Numeric metric meaning is not enforced

`durable-metrics.schema.json:77–83,95–96` and `analysis-observation.schema.json:45–52,77–78` permit negative counts/rates/durations, fractional counts and mismatched metric/unit combinations. Impact: impossible or mislabeled metrics can satisfy today's schema and flow into later coaching/history.

Remedy: nonnegative domains, integer counts/durations where the declared unit/definition requires them, and metric-specific unit constraints. Preserve available zero versus unavailable null. Add shared positive/negative fixtures. This does not demand implementing the analysis engine now.

Source: [JSON Schema validation vocabulary](https://json-schema.org/draft/2020-12/json-schema-validation), numeric/type/enum constraints. Not independently executed.

### F04 — 🟡 Runtime pin deviates from the selected LTS policy

`.node-version:1` pins 26.7.0; `docs/toolchain.md:11` identifies it as the Current line. `prompts/stack-decisions.md:10` selected supported **LTS**, not simply a version meeting Next's minimum. On the reviewed date, Node's release table lists v26 as Current and v24 as LTS. `package.json:6–8` also leaves the documented supported family open-ended.

Remedy: use a documented compatible LTS runtime, align runtime/engine/type-version documentation where necessary, and capture install/build outcomes on that runtime. Do not globally replace the user's Node installation. This is a policy/reproducibility finding, not a claim that Node 26 is inherently exploitable.

Source: [Node.js releases](https://nodejs.org/en/about/previous-releases), searched 2026-10-16.

### F05 — 🟡 Dependency-risk acceptance lacks an exposure-based disposition

`evidence/02b-npm-audit.txt:3–20` identifies the braces → lint dependency chain. `REPORT.md:127–128` treats the dev-only advisory and deprecated ESLint trade-off as accepted without a documented CEO waiver or full production/dev exposure evidence.

The [primary advisory GHSA-vfj7-8cjw-p6xm](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm), retrieved for this review, covers braces ≤3.0.3, describes stack exhaustion from nested patterns, and lists **no first patched version**. Therefore “just update to braces 3.0.3” is not a valid fix. Five npm audit entries describe a dependency chain, not five separately proven deployed exploits.

Remedy: reproduce full and production-only audit evidence, identify installed paths and input reachability, and find a compatible remedy or propose a tightly scoped waiver with conditions/owner/review date. Do not blindly run `npm audit fix --force` or downgrade Next-related tooling to make the count disappear. Severity may change if actual untrusted-input exposure is found; this review has not established such exposure.

## Proven versus unproven

**Supported by supplied builder artifacts:** final Next build output; 36 shared contract fixtures; 21 pytest and 12 Playwright passes; HTTP health/404 evidence; an honest foundation screen with no claimed live connection. These establish useful foundation progress under the reported toolchain, not an independently rerun or complete security assessment.

**Unproven:** all fixes above; external cleanup beyond the builder's account; current production/dev dependency reachability; fresh LTS results; full ownership audit; live providers/analysis/auth/storage; actual language support; B1 integrated acceptance. No TEST-RESULT exists for B1 yet. COMM/STATUS are not applicable to this NORMAL phase.

## User UI direction

The supplied `UI.png` is now the visual reference for Phase 04 and must inform Phase 03's shared UI seams. Handoff: `prompts/phase-04-call-ui/UI-REFERENCE.md`.

The existing starter's different visual style is **not retroactively graded as a Phase 01 failure**. Do not mix a complete redesign into FIX-1. Reference numbers, recording-ON default, “tap to speak,” confidence/pronunciation scores and fake history must not override the actual product/consent constraints.

## Goal check / next action

The skeleton moves the goal forward. Passing on a porous metrics contract or ignoring ownership breaches would undermine later parallel work. The cheapest next step is a bounded Phase 01 correction, not starting UI/provider agents in parallel now.

Run `FIX-1.md` manually, return updated `REPORT.md`, and retain the original evidence. No phase or batch is declared VERIFIED by this review.
