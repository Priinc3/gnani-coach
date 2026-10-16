# Design direction — the "conversation studio" (Phase 01)

The starter screen establishes the visual and interaction language every later
phase should extend, not replace.

## Core idea

A calm, warm studio for spoken practice — closer to a well-lit rehearsal room
than a software dashboard. One central practice panel, generous whitespace,
editorial typography. Explicitly avoided: grids of fake metrics, purple
"AI gradient" decoration, and any element that pretends the product is live
when it is not.

## Visual system

- **Palette (CSS custom properties in `apps/web/src/app/globals.css`):**
  - `--ivory #f5f0e4` warm page background (with a subtle radial lift)
  - `--panel #fffdf7` raised surfaces
  - `--ink #211e17` primary text; `--ink-soft #575144` and
    `--ink-faint #837b69` for secondary text
  - `--green #2c6e49` restrained accent (badges, selected states, focus, plan summary); `--green-deep #1d5133` for emphasis
  - `--hairline #ddd4c1` borders
- **Type:** system serif stack (`Iowan Old Style → Palatino → Georgia`) for
  headings and the wordmark; system sans with Noto script fallbacks
  (Devanagari, Bengali, Gujarati, Kannada, Malayalam, Gurmukhi, Tamil,
  Telugu) for body text. **No webfont is self-hosted in this phase** — that
  decision needs a license and script-coverage check, so native fallbacks are
  used instead. Native names render in their own script with `lang` attributes.
- **Shape & rhythm:** 14–20px radii, hairline borders, soft single-direction
  shadow, 1.55 body line-height, 62ch measure for paragraphs.

## Honesty as a design material

Truthfulness is part of the look, not a footnote:

- Every language row carries a `Not yet verified` badge; nothing is labeled
  "available" that hasn't been tested.
- The single call-to-action is visibly disabled with the plain reason
  "Live calling will be enabled after speech-provider setup."
- The optional sample preview is labeled **"sample preview — no live AI or
  recording"** and hidden behind a `<details>` disclosure.
- A "What is real in this build" panel states plainly what works and what
  does not, and that sign-in/history are planned rather than working.

## Interaction & accessibility decisions

- Native controls only (radio group, selects, checkbox) — real keyboard
  behavior for free; custom widgets were deliberately avoided.
- Fieldset/legend grouping, explicit `label[for]`, `aria-describedby` on the
  disabled button and the checkbox.
- The live plan summary is a `role="status"` region so screen readers hear
  configuration changes.
- `:focus-visible` gets a 3px green outline; the scenario cards carry a real
  120ms border transition so the reduced-motion path is testable, and
  `prefers-reduced-motion: reduce` zeroes all motion.
- 360px-wide screens stack single-column with no horizontal overflow
  (asserted by an e2e test); ≥960px uses a two-column studio layout with a
  sticky masthead.

## Rules for later phases

1. Keep the warm ivory/ink/green system; do not introduce neon, glassmorphism
   or dark-first styling without revisiting this document.
2. Never show a waveform, score, transcript or connection state that isn't
   real. New honest states should follow the badge/disabled-with-reason
   pattern already on the page.
3. Any self-hosted font must pass license and script-coverage review
   (including all nine Indic scripts) before it replaces the system stack.
4. New controls must remain native-first with associated labels and visible
   focus.
