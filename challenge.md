# The Great Indian AI Internship Challenge — Gnani AI

> Source: https://www.gnani.ai/internship (deadline page). Full terms live on the registration page: https://www.gnani.ai/great-indian-ai-internship-registration-form

Build sovereign AI for India on Gnani AI's own models. Ship a working project, post a public demo, get interviewed, earn a paid internship.

| | |
|---|---|
| **Contest start** | Oct 1, 2026 |
| **Final deadline** | Nov 10, 2026 (fixed) |
| **Internships** | Up to **100** paid six-month internships |
| **Stipend** | Up to **₹1,00,000/month**, paid per person (ceiling, not fixed) |
| **Internship start** | Jan 1, 2027 |
| **Awards** | 10 categories × **₹50,000** each (separate from internship selection) |
| **Build window** | 31 days |

---

## 1. Eligibility (all three must be true)

- Currently enrolled in a degree/course at a college or university **in India**.
- **18 years or older** on the day you register.
- Building **solo**, or with **one teammate** who also meets both conditions above.

### Solo vs Team of Two
- **Solo:** you register, build, submit alone.
- **Team of two:** primary registrant registers first, then invites one teammate by email. Teams **cannot** be larger than two.
- Teammate accepts the terms independently; their email is kept only for verification/testing.
- All contest communication goes to the **primary registrant**.
- Each member is **interviewed and considered for an offer individually** — one can be selected without the other.
- Stipend is **per person**, never split across the team.

---

## 2. What you MUST do

1. **Register** — full name, email, phone; college name, degree/course, discipline; solo or team + teammate's email; other details. Each teammate is deemed to accept the contest terms.
2. **Describe your project** (Stage 2, editable until final submission):
   - Project title
   - The problem you are solving
   - Who will use it
   - The Gnani AI models/APIs you **plan** to use
   - Each member's contribution (record this clearly — it matters for individual selection)
3. **Build on Gnani AI technology** — your submission **names the Gnani AI models or APIs it uses** and each member's contribution. A submission without Gnani tech doesn't qualify.
4. **Public demo** — post your project on **LinkedIn or X** with a live demo, tagged **#GreatIndianAIInternshipChallenge** and **#GnaniAI**.
5. **Nominate your posts** so Gnani AI can verify their community engagement.
6. **Submit (Stage 3)** before **Nov 10, 2026**:
   - A demo or video of the **working** project
   - A written project explanation
   - The Gnani AI models/APIs used
   - Links to your nominated LinkedIn/X posts
7. **Track status** in the participant workspace; you get a confirmation receipt on submission.
8. **Interview individually** if shortlisted — every shortlisted person (including both teammates) interviews on their own.
9. **Wait for a written offer** — only a written offer from Gnani AI after the interview confirms an internship.

---

## 3. What you must NOT do

- ❌ **No teams larger than two.**
- ❌ **No real personal data in your project or demo** — never put anyone's real phone numbers, account numbers, Aadhaar, PAN, or recorded calls into the project. **Use synthetic data.**
- ❌ **No relying on verbal/implicit offers** — only written offers count.
- ❌ **No splitting the stipend** — it's per person.
- ❌ **No winning more than one award** per individual or team.
- ❌ **No missing the deadline** — Nov 10, 2026 is fixed (you can edit details until you submit, but not after).
- ❌ **No skipping the public post** — the demo on LinkedIn/X with both hashtags is stage 1 of selection; unverified engagement means you don't advance.
- ❌ **No ignoring the programme terms** — ownership of your project, credit usage, and data handling are defined in the terms on the registration page. Read them (and have your teammate read them) before accepting.
- Gnani AI may **modify, suspend, or cancel** any part of the contest, including rules, timelines and prizes.

---

## 4. Selection process (5 stages)

1. **Public demo** — post on LinkedIn or X with live demo + both hashtags.
2. **Verified engagement** — Gnani verifies engagement on the posts you nominate.
3. **Shortlisting** — they review submissions and shortlist for interview.
4. **Interviews** — every shortlisted person interviews individually (1:1).
5. **Written offers** — selected interns get a written offer with stipend and terms.

A working, public project is the **entry point**; the **interview decides the offer**.

**What likely gets you selected:**
- A genuinely working project (not a pitch deck) that visibly uses Gnani APIs/models.
- Clear, real-world problem + identifiable users.
- Documented per-member contribution (especially for teams).
- Real engagement on your nominated posts (comments/shares from community, not just likes).
- Strong communication in the individual interview — you must explain your architecture, why you chose those models, trade-offs, and what you'd do next.
- Indian-language / low-resource / noisy-audio / code-mixed angles map directly onto what Gnani values (see award categories).

---

## 5. The ten awards (₹50,000 each)

Decided purely on category criteria, **irrespective of internship selection**. Max one award per individual/team.

| # | Award | Best build for |
|---|---|---|
| 01 | **Main Character** | Regional or low-resource Indian language |
| 02 | **Mixed Vibes** | Code-mixed voice: Hinglish, Tanglish, Benglish |
| 03 | **Real Deal** | Real-world problem (farmers, kirana stores, rural health workers) |
| 04 | **Noise Canceller** | Messy, noisy, real telephonic audio |
| 05 | **Two-Person Army** | Best team-of-two project |
| 06 | **Solo Ninja** | Best solo project |
| 07 | **Jugaad Genius** | Most creative/unexpected use of Gnani models |
| 08 | **Small Town, Big Build** | Best entry from a Tier 2/Tier 3 college or city |
| 09 | **Demo Day Drop** | Best 60-second demo video |
| 10 | **Crowd Favourite** | Public votes on LinkedIn/X with the two hashtags |

---

## 6. Models you can build on

All are Gnani AI's **own** models — no third-party models. Part of **Artha**, India's sovereign AI stack (deployed on customer-controlled infrastructure).

### Speech-to-Text — **Prisma v2.5**
- Trained on **14M+ hours** of real telephonic audio.
- Streams in **under 200ms** (P95 ~200ms).
- **10+ Indian languages** plus Hinglish, Tanglish, Benglish.
- **40+ languages** total; #1 in 8 of 9 Indian languages on Kathbath Noisy 8kHz.
- Handles overlapping speech, code-switching, regional accents without special config. Diarization, noisy 8kHz telephony support.
- APIs: **REST** (≤60s clips), **Realtime WebSocket** (live mic/streaming), **Batch** (long/multi-file).
- Docs: https://www.gnani.ai/speech-to-text-api · https://docs.gnani.ai/api/STT/speech-to-text

### Text-to-Speech — **Timbre v2.5** (Beta)
- **21+ languages** (10+ Indic), context-aware prosody.
- Knows Indian names, numerals, **lakh/crode cadence**.
- Sub-100ms time-to-first-audio; streaming over **WebSocket** and **SSE**; SSML support.
- Voices: empathetic (support), assertive (collections) — no robotic affect.
- APIs: **TTS REST**, **TTS Streaming (SSE)**, **TTS Realtime (WebSocket)**, voice catalog.
- Note: Timbre v2.0 is deprecated; use **v2.5**.
- Docs: https://www.gnani.ai/text-to-speech-api · https://docs.gnani.ai/api/TTS/tts-inference

### Speech-to-Speech — **Warp v2.0**
- India's first foundational **5B** speech-to-speech model. Native S2S — **no STT, no TTS, no intermediate text layer**. Sub-200ms P95. Real-time, telephony, agentic.

### Reasoning LLM — **Evon v3.3** (open weights)
- **30B params, ~3.5B active per token**, Mamba2–Transformer hybrid MoE.
- **128K context**, **11 Indian languages** natively.
- Trained on **2T+ tokens** of Indic data; **163,072-token** vocabulary rebuilt for Indian scripts; ~20% fewer tokens per Indian word than GPT-5 family tokenizer.
- First token **302ms**, **257 tok/s**, runs on a **single node**.
- **Apache 2.0** weights, available **by request** on Hugging Face: https://www.gnani.ai/resources/introducing-evon-v3-3-large-language-model
- Tool orchestration, on-prem/air-gapped capable.

### Extras
- **Voice cloning:** embeddings from short reference audio → REST, SSE, WebSocket.
- **Integrations:** LiveKit, Pipecat plugins.
- **Audio formats (STT):** WAV, MP3, OGG, FLAC, AAC, M4A.
- Base URL: `https://api.vachana.ai` · Auth header: `X-API-Key-ID: <key>`
- Docs: https://docs.gnani.ai · Quick start: https://docs.gnani.ai/api/introduction/quick-start

---

## 7. Resources & credits

- **5,000 programme credits** per registration (teams: credits go to the **primary registrant's** account; access instructions emailed after signup). Terms explain what credits cover; dashboard shows usage.
- **API dashboard / keys:** https://app.gnani.ai
- **Docs:** https://docs.gnani.ai
- **Evon on Hugging Face:** request access via the release-notes page above.
- **Model overview:** https://www.gnani.ai/models
- **Discord support:** https://discord.gg/aECcvtABpq
- **GitHub:** https://github.com/gnani-ai

---

## 8. Training your own model / using your own dataset

The rules don't ban it — but read this carefully, because how you do it decides whether you're disqualified or advantaged:

### What the rules actually require
- Rule 3: *"Your project uses Gnani AI technology — your submission names the Gnani AI models or APIs it uses."* This is a **floor, not a ceiling**. Your project must visibly use Gnani APIs/models; it doesn't say "only" Gnani models.
- So a **hybrid project** — your own model/dataset **plus** Gnani APIs in the pipeline — is compliant **as long as Gnani tech is genuinely load-bearing** (named in the submission, actually called by the working demo, not bolted on at the last screen).
- A project that never calls a Gnani API will not qualify, no matter how good your custom model is.

### How to make a custom model work with theirs
- **Fine-tune, don't replace.** Evon v3.3 is Apache 2.0 — you can fine-tune it on your own dataset legally and it still counts as "using Gnani AI technology" (it *is* Gnani technology). This is the cleanest path: custom dataset → fine-tune Evon → serve alongside Prisma/Timbre in the app.
- **Pipeline pattern:** Prisma (STT) → your model or fine-tuned Evon (task logic) → Timbre (TTS). Every stage names a Gnani model; your custom piece is the differentiator, not a replacement.
- **Domain adaptation:** fine-tune Evon on a synthetic corpus for your vertical (e.g., kirana inventory phrasing, crop advisory in a regional language) and show before/after in the demo.
- **Own STT/TTS from scratch** is almost certainly a waste of 31 days — Prisma/Timbre already beat what you'd build; the judges want to see *your* application logic on *their* models.

### Data rules (critical)
- **Synthetic data only.** No real phone numbers, account numbers, Aadhaar, PAN, or recorded calls anywhere in the project or demo.
- Generate synthetic call audio/text (TTS it through Timbre, or use text-only corpora) — this is explicitly the expected approach.
- If your own dataset contains real people's data, strip it or don't use it. Privacy policy: https://www.gnani.ai/privacy
- Your custom model's training data must also be license-clean (don't scrape copyrighted audio).

### How to present it
- In Stage 2, list **both**: the Gnani models/APIs you plan to use, *and* your custom component.
- In Stage 3, the written explanation must spell out the architecture: what your model does, what Gnani does, why the split — plus each member's contribution.
- For Jugaad Genius / Main Character awards, a custom model fine-tuned on a low-resource language dataset is exactly the kind of "creative use" they're rewarding.

---

## 9. Timeline checklist

| Date | Action |
|---|---|
| **Oct 1, 2026** | Register → workspace opens → claim 5,000 credits → create API keys |
| Week 1 | Pick problem, read docs (quick start), make first STT + TTS calls |
| Weeks 1–3 | Build working project (Gnani APIs core; optional fine-tuned Evon on your data) |
| Ongoing | Post progress on LinkedIn/X, build genuine engagement |
| By **Nov 10, 2026** | Final submission: demo/video, written explanation, models used, nominated post links |
| After close | Shortlisting → individual interviews |
| **Jan 1, 2027** | Six-month paid internship begins (location/arrangements in written offer) |

---

## 10. FAQ quick answers

- **Stipend:** up to ₹1L/month per intern, ceiling not fixed, not shared between teammates; exact figure in your written offer.
- **Team selected together?** No — interviewed and offered separately.
- **Project ownership:** per the programme terms on the registration page — read before accepting.
- **Internship:** six months, from Jan 1, 2027; location/working arrangements in the written offer.
- **Cost:** free; you get 5,000 credits.
- **Change project after registering?** Yes — title, problem, users, models, contributions all editable until final submission.
- **Help:** Discord (https://discord.gg/aECcvtABpq) + docs (https://docs.gnani.ai).
- **Awards vs shortlist:** independent — you can win an award without an internship offer and vice versa.
- **Data handling:** registration data used to run the programme, assess submissions, contact you about selection.

---

*Compiled from gnani.ai/internship, gnani.ai/models, and docs.gnani.ai. Programme terms on the registration page are the final word.*
