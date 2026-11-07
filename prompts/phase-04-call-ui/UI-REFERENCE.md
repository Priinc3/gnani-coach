# Speakify — user-selected UI reference

Status: **DESIGN INPUT ACCEPTED; Phase 04 is not released for execution.**

Authoritative visual input: **[`../../UI.png`](../../UI.png)**, at repository root `UI.png` (1536 × 1024). The user explicitly selected this image after the Phase 01 report. Open the actual image before implementing; this document is not a substitute for seeing it. Preserve the original unmodified.

This supersedes the Phase 01 starter's serif-heavy “conversation studio” appearance and `docs/design-direction.md` instructions to extend that look unchanged. It does **not** supersede the product's live-call, consent, audio-evidence, or verification requirements. No phase type, parallel group or application write ownership changes are authorized by this design input.

## 1. Visual direction to reproduce

- Use **Speakify** as the working display name from the supplied reference; internal package/schema identifiers need not be renamed.
- Warm near-white canvas, softly raised white panels, subtle borders/shadows and generous rounded corners. Dark ink text and pill-shaped dark primary buttons, mint/teal highlights, restrained pastel icon tiles.
- Bold friendly **sans-serif** headings and clean readable body text, rather than the foundation's large serif headings. Match visual hierarchy, density and spacing; do not guess the original font name. Check licensing and Indic-script coverage before introducing fonts.
- The friendly illustrated coach is a major visual anchor: large on the landing/onboarding view, cropped into a circular avatar on the call and coaching screens. This is an illustration, not a real person or a voice-cloning requirement.
- Desktop landing uses a left text/right illustration composition, compact navigation, floating language/scenario cards and two CTAs. Features and scenario views use tidy card grids.
- Mobile uses focused single-column screens, clear back/close controls, large touch targets, a prominent bottom action and appropriately persistent navigation outside the active call.
- Reference colors are visual guidance, not measured tokens. Derive the final palette from the image and verify legibility rather than claiming exact color matching from this brief.

**Build actual components and responsive layouts, not a full-page image or a screenshot collage.** The image is a design board showing multiple screens, not one page containing seven phone mockups. Do not render device frames/status-bar screenshots in the application.

## 2. Screen map

| Reference area | Required adaptation |
|---|---|
| Desktop landing | Speakify wordmark, compact nav, “Speak with confidence in real life” hierarchy, friendly coach illustration, clear start/preview actions and honest capability copy |
| Desktop features | Six pastel-icon cards for real conversation, audio-grounded feedback, scenarios, supported languages, personalized coaching and progress; only advertise implemented/validated capabilities |
| Desktop scenario browser | Filter pills and cards: Job Interview, Team Meeting, Office Communication, Travel & Tourism, Daily Conversations and Custom Topic |
| **1. Splash / onboarding** | Concise value proposition, illustration, primary start action and sign-in route where available; skip unnecessary carousel friction |
| **2. Select scenario** | Mobile scenario list, category filters, concise descriptions; selected scenario carries into settings |
| **3. Language & settings** | Separate speaking/coaching language selectors, level choice, recording toggle and optional subtitles; persistent explanation of what is saved |
| **4. Call / conversation** | Timer, end action, circular coach avatar, genuine listening/speaking state, optional transcript, mute/speaker controls, interruption support |
| **5. Coaching break** | Strengths / Improve / Language organization, at most two priority changes, evidence links, “Try again” and “Keep talking”; use the existing four-turn round contract |
| **6. Session summary** | Evidence-backed metrics, targeted retry comparison, detailed observations, optional audio player only where audio exists and is authorized |
| **7. Progress & history** | Real completed-session history and comparable measured trends; empty states for new users, metrics-only states for users without retained audio |

Team Meeting and Office Communication can be presets under the existing workplace scenario category. Custom Topic needs an agreed transient-input contract before use; it is not permission to save learner-written text in metrics. Phase 03 must resolve missing preset/custom-topic fields before freezing the shared interface. Phase 04 must not invent or change catalog IDs alone.

## 3. Deliberate differences from the picture

The image is authoritative for **appearance**, not proof that its displayed data or defaults are correct.

1. **Recording defaults OFF**, even though the mockup shows ON. Consent to live processing and optional recording retention remain distinct. No retained audio means no historical replay button that appears to work.
2. **The main experience is a hands-free call.** Replace “Tap to speak” with the appropriate live status/control. Do not turn the central microphone into mandatory push-to-talk.
3. **No invented overall/confidence/pronunciation scores.** The pictured 78/100, confidence 82, pronunciation 80 and +28% are mockup values, not implementation requirements. Use validated pace/pause/filler metrics and uncertainty instead; pronunciation grading remains deferred. Aspirational “speak with confidence” copy is different from inferring a psychological confidence score.
4. **No fake history:** seven sessions, twelve hours and numerical progress require actual data. Use meaningful empty states otherwise. Do not add badges/achievements just to fill the reference tabs.
5. **Language claims follow capability evidence:** ten named languages are documented for the chosen live path; Hinglish is a separately validated mixed mode. Do not mechanically copy “10+,” assume French support, or treat a US flag as a requirement for American English. Prefer language names/native labels to flags alone.
6. **Subtitles are transient**, even if visible in the call. The toggle is not consent to retain transcripts or quoted feedback.
7. **No fabricated pricing/testimonials.** Omit unsupported navigation destinations or use genuine in-page sections. “Watch demo” must open a real, labeled demo/preview, not a dead button.
8. **Feedback must cite actual observations.** The reference's “reduce um and like” example does not establish filler detection. Show unavailable/insufficient-evidence states when the analysis cannot support a claim.

## 4. Asset handling

- The supplied board is a reference, not a full-resolution asset pack. Do not embed its tiny text, UI cards, or entire board as production artwork.
- Prefer separately supplied illustration assets or original, license-verified assets with a similar friendly style. Do not claim rights or invent asset provenance.
- If suitable artwork is unavailable, report the asset gap and use a clearly intentional temporary illustration treatment. Do not claim a faithful finished visual match while that gap remains.
- Keep component assets within Phase 04's existing OWN tree, for example `apps/web/src/features/.../assets/`, using a supported import approach researched by the builder. A new `public/` asset location, shared font loader or global-style edit needs a scoped ownership decision; this brief does not grant it.
- `UI.png` is read-only reference input. Do not delete, overwrite, move, stage or publish it incidentally with a blanket Git operation.

## 5. Ownership and integration instructions

- Phase **03 contract-freeze** must read this brief before mounting feature entry points and freezing global tokens, scenario/custom-topic fields, audio/privacy states and history interfaces. Existing source-owned design documentation must acknowledge this reference's precedence.
- Phase **04 call-ui** implements these screens within its established feature/audio/transport/session-ui/test directories. Its eventual BUILD must link both this file and `UI.png` prominently.
- Phase **05 coaching-runtime** supplies real round state and evidence; Phase **06 private-history** supplies actual identity/history/recording permissions. The screenshot is not a reason to hardcode their outputs in the UI.
- Shared composition roots, contracts, manifests and another sibling's files remain **DO NOT TOUCH** during G1. Post `HELP:` in COMM and wait for CEO FIX if they need changes.
- Do not restyle the Phase 01 foundation as part of its current corrective FIX. The reference is recorded now to avoid rebuilding the UI twice.

## 6. Evidence required from the UI builder

In Phase 04 REPORT, include:

- A mapping from the three desktop areas and seven mobile screens to actual implemented views and their data sources.
- Desktop captures at a declared 1440px or 1280px viewport, and mobile captures at 390px and 360px; no horizontal overflow or obscured primary actions.
- Before/reference/implemented comparisons for landing, settings, call, coaching and summary/history. Name intentional differences from §3.
- Keyboard/focus, responsive text, reduced-motion and Indic-script checks. Retain accessible labels on icon-only call controls.
- Real or clearly fixture-labeled evidence for microphone denied, connecting, listening, coach speaking, coaching break, interrupted speech, reconnect/error, insufficient evidence, empty history and recording OFF/ON states. A fixture screenshot is not proof of live integration.
- Asset provenance/limitations, exact files changed and commands/output. B2's integrated TEST must still prove real service behavior; visual similarity alone is not VERIFIED.

**Provenance:** user-supplied `UI.png`, inspected on 2026-10-16; product constraints from `prompts/00-plan.md` and language evidence from `prompts/language-support.md`. No application files changed by this handoff.
