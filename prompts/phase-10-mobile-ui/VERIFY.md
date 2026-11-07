# Phase 10 — review (pre-TEST), 2026-11-07

**NEEDS-FIX** (one 🟠). Not a batch verdict: B4 closes only after G2 and the Phase 13 smoke. Read REPORT, `git show --stat 88f4b26`, and grepped the tree. I ran no tests; tsc and eslint exit 0 is builder evidence (`evidence/*.log`).

## Proven by reading
- ✅ Ownership kept: commit `88f4b26` touches only `apps/web/{src,public,tests}`, its own REPORT and the G2 files; no `lib/auth`, `app/auth`, `proxy.ts`, `next.config.ts`, `package.json`.
- ✅ Phone layout, PWA manifest (standalone, 192/512/maskable icons), mic pre-check, End confirm, 16 px inputs, safe-area handling: present in the diff. No service worker, no new dependency.
- ✅ Honesty rules kept (no scores, "Not yet verified" badge stays).

## Findings
- 🟠 `apps/web/src/features/**` — no link to `/auth/sign-in`, no caller of `deleteAccount`, sign-out only on the call screen → a learner cannot create an account, so saved history and account deletion are unreachable. → **FIX-1.md**.
- 🟡 `prompts/parallel-G2/STATUS.md` row 10 shows `NOT STARTED` and COMM lacks the Phase 10 entry. Cause: Phase 14's commit overwrote them (see Phase 14 review). → FIX-1 item 3 (restore own row only).
- 🟡 Unproven: the three new Playwright checks and the edited End-confirm steps were never executed (no browser on the 2 GB box). A real phone check is in Phase 13's checklist. No visual render was done; layout was judged from CSS and Phase 04 screenshots.

## Waived / accepted
None needed.
