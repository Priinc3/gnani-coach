# Phase 05 review — 2026-10-22 (pre-TEST)

**NEEDS-FIX (small); NOT VERIFIED.** Read the REPORT plus code spot checks. I ran no tests, so the 495 passed / 4 skipped are builder evidence.

- ✅ Runtime built to the transport contract: origin before accept, 1008/1009 closes, a 1,024-byte frame rule, caps, heartbeat/idle, a fence on interrupt, bounded untrusted text, facts-only fallback, content-free logs, a guest writes nothing.
- ✅ Honest on the live item: `BLOCKED: credentials not configured`. Interrupt timings are fake-stack numbers and are labelled so.
- 🟠 `_persist_recording()` saves raw headerless PCM under `audio/wav`, so the opt-in replay cannot decode it. The fakes never decode, so tests passed. → FIX-1.
- ✅ Deviations (STT reconnect per submission, local schema check for round feedback, 16 kHz only) are documented and acceptable. Provider-side structured output is a later improvement, not a blocker.
- 🟡 Their "integration 9 failed" is Phase 03's stale assertions, covered by Phase 03 FIX-2. Per-process connection caps scale with worker count (documented).

# Phase 05 FIX-1 review — 2026-10-22

**Accepted on reading; NOT VERIFIED until the B2 TEST.** The stdlib `wave` writer is called from `_persist_recording` (`runtime.py:1312-1313`, `conversation/audio.py`). Builder evidence, which I did not rerun: 500 passed / 4 skipped, contracts PASS, secret scan 0. A new test parses the saved bytes with `wave.open`, and a withdrawal test runs against the real in-memory stores.

- ✅ 🟠 recording-not-WAV closed on reading.
- ⚠️ Still fake-proven: no browser has played a stored recording and no real Supabase upload ran. The B2 TEST §1.3 checks it end to end.
