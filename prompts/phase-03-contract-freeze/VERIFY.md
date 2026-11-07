# Phase 03 review — 2026-10-20 (pre-TEST)

Phase 03: **NEEDS-FIX (small); NOT VERIFIED.** Batch B1: NOT VERIFIED until FIX-1 and the batch TEST.

Method: read REPORT, `seams.md` and `call-transport.md`, plus greps of `main.py`/`settings.py` and the tree. I ran no tests. The builder's test counts are unproven by me.

- ✅ Accepted on reading: the seam table is exact and the stubs exist at the frozen paths; the filler is `unvalidated` → `insufficient_evidence` with the goal preserved and no filler flag true; the HANDOFF §5.x items are mapped with valid and invalid fixtures; the transport is specified (token in the first message, caps, fencing).
- 🟠 `main.py`/`settings.py`: the Origin allowlist and CORS required by `call-transport.md` §7.6 are not implemented, and the browser→voice URL is undefined. G1 cannot edit these files, so Phase 04 and 05 would block. → FIX-1 §1.
- 🟡 W02 is removable by the verified ESLint 10.13.0 pin. → FIX-1 §2. W01 renewed to Phase 09.
- ⚠️ Unproven: the transport has never carried PCM; B2 proves it. The Phase 02 tree is untracked in git, so the ownership check relies on the SHA manifest. I will ask the user to commit before the TEST.

# Phase 03 FIX-1 review — 2026-10-20

Phase 03: **accepted on reading; final VERIFIED waits for the B1 TEST.**

Spot-checked by grep: `origin_allowed` is called before `accept()` and closes with 1008 (`router.py:31,44,60`); CORS uses the settings allowlist, credentials off, methods limited (`main.py:149-151`); `eslint` pinned to `10.13.0` (`apps/web/package.json:22`).
Builder evidence, not run by me: 42 pytest and 5 browser integration checks, 247 service tests, 12 e2e, secret scan 0, handshake and CORS probes against a real uvicorn.

- ✅ 🟠 origin and URL gap closed. A missing Origin is allowed, with a written rationale: browsers always send it, and the token still authenticates.
- ✅ W02 closed. 🟡 A stray hoisted eslint 9.39.5 peer copy remains and no script runs it. `WAIVED: dev-only, never executed; drops on the next lockfile refresh.`
- ⚠️ Unproven: the transport is still only a contract; B2 proves it. The tree is uncommitted (117 changed paths), so the ownership proof stays the SHA manifest. The TEST must reuse it.

# Phase 03 FIX-2 review — 2026-10-22

**Accepted on reading; NOT VERIFIED until the B2 TEST.** Spot checks: the integration asserts now say `401` (`test_seams.py:90-124`, `test_origins.py:198`); `seams.md` records the four decisions (§9: OpenAPI exclusion, the verified-context metrics owner, the `status connecting` first message, real 16 kHz mono 16-bit WAV). Builder evidence, which I did not rerun: integration 45 pytest + 5 browser, e2e 2, voice suite 500 passed, secret scan 0.

- ✅ 🟠 stale-assertion failures closed on reading, with no weakening: error-shape fields are asserted and three new real-service checks were added.
- ✅ The ten retired foundation tests are mapped to Phase 04 tests. One (`sample preview`) has no successor because the element was removed in Phase 04, and I accept that.
- 🟡 `tests/foundation` now holds only 2 browser tests. Fine for the prototype.
