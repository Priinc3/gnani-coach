# Scoped waiver register

Decision date: **2026-10-18**. Owner of acceptance: CEO/orchestrator; execution/evidence owner named below. These waivers do not change phase types, grant new file ownership, authorize production deployment, or make a batch VERIFIED without its TEST-RESULT.

## W01 / F05-A — development-only braces advisory

**🟡 WAIVED: temporarily retain the current local lint dependency chain because the supplied dependency/audit evidence confines the known issue to development tooling, the primary advisory lists no patched version, and forcing the offered major downgrade would not be a verified compatible remedy.**

- Exact chain: `eslint-config-next@16.4.2` → `@next/eslint-plugin-next@16.4.2` → `fast-glob@3.3.1` → `micromatch@4.0.8` → `braces@3.0.3`.
- Advisory: [GHSA-vfj7-8cjw-p6xm / CVE-2026-93687](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm). Primary page rechecked 2026-10-18: affected ≤3.0.3, patched versions none, deeply nested patterns can exhaust the stack. “No patched release listed” is not proof that every alternative dependency/configuration strategy is impossible.
- Evidence: `phase-01-foundation/evidence/fix-1/02a-audit-full-raw.json`, `02b-audit-omit-dev-raw.json`, `03-npm-explain-braces.txt`; `apps/web/package.json` and static `eslint.config.mjs`.
- Residual risk: developer-process availability if malicious patterns reach the parser. Absence from a declared production tree does not establish what a future deployed artifact contains.
- Conditions: only controlled local repository linting; no user/network-derived patterns; no untrusted-PR/remote lint service exposure under this waiver. Do not suppress the advisory, disable lint to hide it, or call the full dependency audit clean.
- Reopen immediately on dependency/config/input-trust changes, newly reachable production usage, a relevant fix, or new advisory evidence. CI or production packaging needs a new exposure review.
- **Expiry: Phase 03 dependency freeze or 2026-10-25, whichever comes first.** No automatic renewal. This replaces the proposed 2026-11-16 date.
- **RENEWED 2026-10-20 (CEO):** the Phase 03 audit shows the same dev-only chain, `--omit=dev` clean, advisory still unpatched. New expiry: **Phase 09 release packaging**, which must prove lint tooling is not shipped. Same conditions. No further renewal.
- Follow-up: Phase 03 builder supplies fresh audit/dependency evidence and a supported-path recommendation; CEO decides renewal or removal before G1. Release packaging independently proves development tooling is not exposed.

## W02 / F05-B — EOL ESLint 9 compatibility bridge

**🟡 WAIVED: short-lived development use of the existing passing ESLint 9.39.5 configuration while the Next/plugin compatibility path is reassessed, rather than an untested upgrade solely to remove a warning.**

- [ESLint version support](https://eslint.org/version-support/), searched 2026-10-18, lists v9 as EOL since 2026-08-06. Do not describe this version as maintained or “supported-in-practice.”
- This is a support-risk acceptance separate from W01, not a claim that no unknown vulnerabilities exist or that commercial support was purchased.
- Keep the exact current versions and their warning visible in records. No paid support, new dependency family or ignored peer conflict is authorized by this waiver.
- Scope: existing controlled development linting only, with the same trust-boundary restrictions as W01.
- **Expiry: Phase 03 dependency freeze or 2026-10-25, whichever comes first.** Reopen on a compatible upgrade, support/advisory change, or a new use of linting.
- **DISPOSITION 2026-10-20 (CEO): REMOVE.** Phase 03 verified `eslint@10.13.0` passes lint with the unchanged config (v10 is the current line). Phase 03 FIX-1 applies the pin; **W02 CLOSED 2026-10-20:** the FIX-1 evidence passes (lint 0/0 on eslint 10.13.0, `npm ls --all` exit 0). One leftover hoisted eslint 9.39.5 peer copy is never run by any script; accepted as 🟡 and it falls away with the next lockfile refresh.
- Follow-up owner: Phase 03 dependency owner; acceptance owner: CEO. Future builder documentation should state EOL plainly and link this disposition rather than repeat the unsupported support claim.

## W03 / F06 — duplicate recheck label and excerpted logs

**🟡 WAIVED: do not repeat a foundation fix cycle solely to repair the mislabeled duplicate Python recheck, because the correctly labeled verbose foundation test artifact and inspected code already support this interim correction review.**

- Defect: `phase-01-foundation/evidence/fix-1/13-final-recheck.txt:9` names `services/python` and omits the established `python` executable position. It is not treated as proof that the correct project was tested on October 18.
- Supporting artifact instead: `phase-01-foundation/evidence/fix-1/09-pytest-fix.txt:1–35` records the correct `services/voice` command and 23 named passes. Other log excerpts support only their visible results, not complete raw capture.
- Do not rewrite old artifacts to manufacture a clean history. The B1 tester must capture exact commands/working directories/runtime/exit statuses and full content-free stdout/stderr, with any secret redaction explicitly identified.
- **Expiry: before B1 acceptance.** Not renewable into a batch test waiver; the formal batch must have fresh valid evidence.
- Follow-up owner: B1 tester under its eventual TEST prompt. No change to the agreed three-phase test cadence.

## W04 — key rotation declined by owner (2026-10-20)

**WAIVED: owner-accepted risk.** The user declined to rotate the four keys posted in conversation. Scope: the user's own keys only. All no-secrets rules stay: no values in prompts, code, logs, evidence or reports. Keys come from the process environment or user-created `tools/probes/.env` (0600). Reopen on any sign of misuse or a repo leak. Expiry: before any public deploy (Phase 09).

## W05 — B1 TEST skipped, G1 opened early (2026-10-20)

**WAIVED: user-ordered.** The user told the CEO to skip the B1 batch test and start the parallel group. B1 is NOT VERIFIED and no claim of B1 acceptance is made. The B1 TEST file is kept and its checks (live chain, filler routes, W03 fresh evidence, security probe, ownership-by-git) move into the **B2 TEST**. Risk accepted by the user: G1 builds on a contract and adapters whose live behaviour is unproven, and a late contract FIX on Phase 03 would make the other members wait. Expiry: the B2 TEST (its §4 holds the folded-in live checks). Does not waive any 🔴/🟠, the credential gate, or the filler goal.

## W06 — B2 TEST skipped, B3 opened (2026-10-23)

**WAIVED: user-ordered.** The user told the CEO to skip the B2 batch test and move to Phases 07–09. B2 and B1 stay NOT VERIFIED. The no-credential B2 checks become Phase 07's automated assembled test. The live checks and the independent verification move to the **B3 TEST**, the first test of the whole system. Risk accepted by the user: Phases 07–09 build on code and a contract that no independent test has run, and **no provider has ever been called live**, so a defect found late may cost a phase. Expiry: the B3 TEST. Does not waive any 🔴/🟠, the credential gate, the honesty rules or the filler goal.

**CEO grant (2026-10-23), data only:** Phase 08 may edit the per-language `capabilities` flag values in `packages/contracts/data/catalog.json`. No shape, id or language change.

## Explicit non-waivers

- The historic out-of-root write is not retroactively authorized; external cleanup remains reported, not independently verified. The accepted remediation is the corrected account/inventory and scoped work discipline, not a clean-machine assertion.
- No waiver of audio-grounded analysis, storage consent, access isolation, genuine provider use, missing REPORT/TEST-RESULT, language accuracy, or unresolved 🔴/🟠 defects.
- No waiver is a claim that Phase 01, B1, or the complete application is already VERIFIED.
