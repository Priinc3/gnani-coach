# G1 COMM (max 60 lines; prune oldest RESOLVED)
## 00 18:53 — group opened by CEO. Read ADDENDUM.md. INFO
## 01 18:53 — Phase 05 started: coaching runtime and analysis. INFO
## 02 18:55 — STT port has no live send: stream_pcm() closes the session, so one session per connection cannot stream a multi-turn call. HELP
## 03 19:00 — Phase 03 integration assertions on the /ws/call and analysis stubs now fail by design; Phase 05 must not edit them. HELP
## 04 19:18 — Phase 06 deps installed earlier (18:50): web @supabase/ssr 0.12.7, @supabase/supabase-js 2.118.0; python httpx 0.28.1 (already locked). Notice was lost when the file was recreated. INFO
## 05 19:18 — DECISION: sign-out hook for Phase 04 is `onSignOut(handler)` from `@/lib/auth`; subscribe to close a live call socket. INFO
## 06 19:18 — HELP: Phase 03 integration tests expect the old 503 stub: test_seams.py:83,89,96 and test_origins.py:163 now see 401. Not my files. HELP
## 07 19:18 — HELP: `.env.example` entries needed for SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, SUPABASE_PUBLISHABLE_KEY; those files are Phase 03's. HELP
## 08 19:18 — DECISION: the metrics write owner is the verified request context (identity.current_user()); `save_metrics_for(user_id, doc)` also exists. INFO
## 09 19:18 — HELP: seams.md §2 says the routes join the OpenAPI document; Phase 06 kept include_in_schema=False for the Phase 01 invariant. One-line change. HELP
## 10 19:27 — Phase 06 built: identity, metrics-only stores, private-history routes, Supabase assets, web auth, proxy. 351 voice tests, 14 web tests. Report: prompts/phase-06-private-history/REPORT.md. INFO
## 11 19:40 — Phase 04 started: browser call UI, audio capture, transport, history. INFO
## 12 19:55 — Phase 04: the capture worklet loads with new URL('./capture-worklet.js', import.meta.url); Turbopack emits it as a raw asset. INFO
## 13 20:05 — HELP: Phase 03 integration smoke asserts the stub screen; the real UI breaks those assertions. Exact failures in the Phase 04 report. HELP
## 14 21:05 — HELP: Phase 03 integration asserts the replaced stubs. test_origins.py:188,205 and test_seams.py:116 expect the first /ws/call message to be type "error"; the real call answers status connecting. HELP
## 15 21:05 — HELP: Phase 03 test_seams.py:148 expects every analysis observation insufficient_evidence; the real service measures turn.duration_ms as available. HELP
## 16 21:05 — HELP: secret_scan reports one GENERIC_SECRET in apps/web/tests/unit/client.spec.ts:238 (Phase 04's file). The voice tree is clean; the scan is not zero until that line changes. HELP
## 17 21:05 — INFO: Phase 05 built: /ws/call runtime, turn controller, coaching breaks, interruption, durable metrics, real AnalysisPort. 495 voice tests. Report: prompts/phase-05-coaching-runtime/REPORT.md. INFO
## 18 08:50 — Phase 04 built: 8 browser views, capture, transport, history; 77 own tests; secret scan clean. Report: prompts/phase-04-call-ui/REPORT.md. INFO
## 18 21:05 — HELP: the frozen reasoning port has no response-schema field, so the round-feedback JSON cannot be schema-enforced provider-side. It is schema-checked locally instead. HELP
## 19 14:10 — INFO: secret_scan now 0 findings (Phase 04 fixed client.spec.ts:238; HELP 16 resolved). Phase 05 re-ran everything: 495 passed/4 skipped, contracts PASS, integration still 9 failed (Phase 03 stub assertions 14/15 + Phase 06's 401s). Evidence refreshed.
## 20 14:45 — FIX-1: Phase 05 saves a canonical WAV (stdlib wave, 44-byte header) instead of raw PCM; consent withdrawal handled via real in-memory store. 500 passed/4 skipped, contracts PASS, scan 0 findings. Report §FIX-1. INFO
