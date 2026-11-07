# Project tracker

Goal: deliver the live-call coaching loop, audio-grounded corrections/retry, and consent-correct history in the ten-language target catalog; all batches and final acceptance must have evidence.

| Batch | Phases | Type | Status | 🔴🟠🟡 | Fix |
|---|---|---|---|---|---|
| B1 | 01 foundation → 02 provider-feasibility → 03 contract-freeze | NORMAL | built; TEST skipped (W05) → checks live in the B2 TEST. NOT VERIFIED | 0 🔴 / 0 🟠 on reading; 1 🟠 carried (filler unvalidated) | — |
| B2 | 04 call-ui + 05 coaching-runtime + 06 private-history | PARALLEL:G1 | BUILT; fixes accepted on reading; **TEST skipped by user order 2026-10-23 (W06) → NOT VERIFIED**; checks move to Phase 07 (automated) and the B3 TEST | 0 🔴 / 0 🟠 on reading; filler 🟠 carried; live path never run | — |
| B3 | 07 resilience → 08 language-acceptance → 09 release-package | NORMAL | OPENED 2026-10-23 by user order. BUILDs issued; run 07, then 08, then 09, then `batch-B3-TEST.md`. Deadline 2026-11-10 | Not assessed | phase-07/08/09 BUILD.md |

- Plan: [00-plan.md](00-plan.md) §9 — phase types/parallel map frozen; changes need user approval.
- Research: [research.md](research.md) — public-document evidence only.
- Language findings: [language-support.md](language-support.md) — ten documented shared realtime languages; no runtime verification.
- Stack: [stack-decisions.md](stack-decisions.md) — researched choices; exact pins still a builder deliverable.
- Review: [phase-01-foundation/VERIFY.md](phase-01-foundation/VERIFY.md) — 2026-10-18 corrective review accepted; not a batch acceptance verdict.
- Waivers: [waivers.md](waivers.md) — braces/ESLint exceptions expire at Phase 03 freeze or 2026-10-25; evidence-label exception expires before B1 acceptance.
- Phase 02 review: [VERIFY.md](phase-02-provider-feasibility/VERIFY.md). Positive chain evidence retained; budgets/lifecycle/matrix/evidence need correction and filler localization is unproven.
- Next user actions: rotate exposed keys using [provider-access.md](provider-access.md), then answer [DECISION-NEEDED.md](phase-02-provider-feasibility/DECISION-NEEDED.md). No literal credentials are included in prompts.
- Manual offline repair is prepared in [Phase 02 FIX-1](phase-02-provider-feasibility/FIX-1.md). New live probes require private replacement credentials and repaired safeguards; new reasoning comparison requires the stated user choice.
- UI direction: [phase-04-call-ui/UI-REFERENCE.md](phase-04-call-ui/UI-REFERENCE.md) pins user-selected `UI.png`; no Phase 04 BUILD released and no phase-map change.
- Initial defaults are assumptions following “start the project,” not fabricated answers to A–C. No credentials or public deployment needed for Phase 01.
- Phase 01 and Phase 02 REPORTs were reviewed. No batch TEST-RESULT, active parallel group or VERIFIED batch exists. No Phase 03/UI release occurs while the goal/security gates are unresolved.
- Orchestrator changed only prompt documents; no app commands, tests, paid inference, or automatic engineer delegation.
