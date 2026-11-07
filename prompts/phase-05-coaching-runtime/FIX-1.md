# Phase 05 — FIX 1: saved recordings are raw PCM, not WAV (small)

Type: PARALLEL:G1 member (B2). Owner: Phase 05 only. Siblings: 04 and 06 are DONE and wait. Do not edit their files or any sibling file. Comm: `prompts/parallel-G1/COMM.md` (append your entry only).

## Problem 🟠
`conversation/runtime.py` `_persist_recording()` (about line 1305) passes `bytes(self._recording)` to `save_recording()`. That buffer is raw 16 kHz mono s16le PCM with no header. Phase 06's store records it as `content_type: audio/wav`, container `wav`, `codec pcm_s16le` (`stores/supabase.py` ~lines 456-486). The `GET /api/recordings/{id}` route returns it as `audio/wav` (`router.py:347`). Phase 04 plays it with the `Content-Type` the service sends. A browser cannot decode headerless PCM as WAV, so the opt-in replay would fail on every saved recording. The tests passed only because they use fakes that never decode.

## Fix
- Wrap the buffer in a canonical 44-byte RIFF/WAVE header (PCM, 1 channel, 16 000 Hz, 16-bit) before `save_recording()`. Use the stdlib `wave` module writing to `io.BytesIO`. No new dependency. Put the helper in your own tree (for example `conversation/audio.py`). Set `duration_ms` from the sample count as now.
- Keep the empty-buffer, size-cap and consent behaviours unchanged.

## Verify with
- Unit test: the saved bytes start with `RIFF....WAVEfmt `, parse with `wave.open`, and report 1 channel, 16 000 Hz, 2-byte samples and the right frame count.
- Extend the existing persistence test so the bytes the fake recording store received are a valid WAV.
- Consent withdrawal: with the real `SupabaseConsentStore` semantics, a withdrawal before the write means `save_recording` raises `ConsentRequiredError`, and the call ends cleanly with metrics saved and no recording. Add a test with the in-memory store from `persistence.stores`. Read-only import, no edits there.
- Re-run `uv run --project services/voice python -m pytest services/voice/tests -v`, `npm run test:contracts` and `secret_scan.py`.

## Report
Append `## FIX-1` to your REPORT.md with the changed files, raw output paths and one line on what remains fake-proven. End with `PHASE 05 FIX-1 BUILT — AWAITING B2 TEST`. Stop there.
