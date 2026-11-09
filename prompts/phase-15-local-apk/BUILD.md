# Phase 15 — local-apk (B5, NORMAL)

You are Phase 15. No siblings are running. Type `NORMAL`. This phase exists because GitHub Actions is blocked by billing (Phase 12/13: `startup_failure`, zero jobs), so the APK is built on the user's Mac instead.

## Context

End goal ([00-plan.md](../00-plan.md)): a learner uses the coach from a phone. The web app is live at `https://gnani-coach.vercel.app`, voice is live at `wss://13-205-26-178.sslip.io/ws/call` (Phase 13 smoke passed). The Capacitor 8 shell in `apps/mobile/` (Phase 12) is committed and was never compiled. Nobody has built `app-debug.apk` yet. This phase produces it, on macOS, and proves it installs.

## Goal

One command on this Mac produces a debug-signed `speaking-coach.apk` that loads `https://gnani-coach.vercel.app`, plus a recorded sha256 and a install/launch check.

## Ownership

| OWN (may write) | DO NOT TOUCH |
|---|---|
| `scripts/mobile/**` (new) | `apps/web/**`, `services/**`, `supabase/**`, `deploy/**`, `packages/**` |
| `apps/mobile/**` (only to fix a build break; keep `appId`, permissions, `https` rule unchanged) | `.github/**` (workflow stays as the future CI path) |
| `docs/release/APK-LOCAL.md` (new) | root manifests/locks, `.env.example` |
| `prompts/phase-15-local-apk/{REPORT.md,evidence/**}` | other phases' prompt folders |

Need a change outside OWN → write `HELP:` in REPORT and stop. Do not edit silently.

## Deliverables

1. **`scripts/mobile/build-apk.sh`** (bash, `set -euo pipefail`, idempotent). Steps:
   1. Preflight, each with a plain-word failure and the exact fix command: Node ≥ 22, JDK 21 (see constraint 2), `ANDROID_HOME`/`ANDROID_SDK_ROOT` set and containing `platforms/android-36` and `build-tools`, `sdkmanager` licenses accepted.
   2. `APP_URL` defaults to `https://gnani-coach.vercel.app`; accept override via env; refuse non-`https://`.
   3. `cd apps/mobile && npm ci`.
   4. Inject `APP_URL` into `www/error.html` (replace `__APP_URL__`, same logic as `.github/workflows/android-apk.yml`), and **restore the file on exit with a `trap`** so `git status` stays clean.
   5. `APP_URL=... npx cap sync android`.
   6. `cd android && ./gradlew assembleDebug`.
   7. Copy `app/build/outputs/apk/debug/app-debug.apk` → `apps/mobile/dist/speaking-coach.apk`, print `shasum -a 256` and size. `dist/` and `*.apk` must be git-ignored (verify; add `apps/mobile/dist/` to `apps/mobile/.gitignore` if missing).
2. **`scripts/mobile/setup-mac.sh`** (optional helper, prints what it will do, asks before each `brew` install): installs Temurin 21, `android-commandlinetools`, then `sdkmanager "platform-tools" "platforms;android-36" "build-tools;36.0.0"` and `sdkmanager --licenses`. If the user already has Android Studio, the script must detect `~/Library/Android/sdk` and skip the SDK install.
3. **`scripts/mobile/install-apk.sh`**: if `adb devices` shows exactly one device, `adb install -r` the APK and launch `com.gnanicoach.app`; otherwise print how to enable USB debugging / start an emulator and exit 0 without failing.
4. **`docs/release/APK-LOCAL.md`** (≤ 60 lines): prerequisites, the three commands, where the APK lands, how to sideload by AirDrop-less methods (adb, or copy to phone and open), troubleshooting for the top failures you actually hit.
5. Fix `apps/mobile/README.md` so it no longer says the APK is published at the sslip.io URL unless it truly is. Point to `docs/release/APK-LOCAL.md`.

## Criteria (all must hold)

- `bash scripts/mobile/build-apk.sh` exits 0 from a clean checkout state (after `git clean` of ignored build dirs is acceptable) and prints sha256 + size.
- `apps/mobile/dist/speaking-coach.apk` exists. `apkanalyzer manifest print` (from cmdline-tools) or `aapt dump badging` shows package `com.gnanicoach.app` and permissions exactly `INTERNET`, `RECORD_AUDIO`, `MODIFY_AUDIO_SETTINGS`.
- `git status` after the build shows only intended source changes (no `error.html` injection leftovers, no APK, no `local.properties`).
- Install + launch result is recorded: on an emulator or real phone if available (screenshot of the Speaking Coach landing page in `evidence/`). If no device is available, say so plainly and mark install as UNPROVEN. Do not claim it.
- If a real device or emulator is available: tap Start call, grant the microphone prompt, confirm the call screen reaches "listening". This is the only proof the WebView mic path works. If not run, mark UNPROVEN.
- Re-running the script a second time succeeds (idempotent).

## Constraints (verified, do not re-guess)

1. **Node ≥ 22** for Capacitor 8; Android SDK API 24+ and latest stable API 36: https://capacitorjs.com/docs/getting-started/environment-setup (read 2026-11-09).
2. **JDK 21.** Capacitor 8.6.0's Android library compiles with Java 21 (Phase 12 evidence `07-capacitor-source.txt`). Gradle wrapper is 8.14.3, which runs on JVM 8–24 and is not supported on JVM 25+: https://docs.gradle.org/8.14.3/userguide/compatibility.html. So **do not use a newer default JDK**; the script must set `JAVA_HOME` to a 21 install (`/usr/libexec/java_home -v 21`) and fail clearly if absent.
3. SDK packages: `platform-tools`, `platforms;android-36`, `build-tools;36.0.0`; licenses via `sdkmanager --licenses`: https://developer.android.com/tools/sdkmanager. Gradle also needs `android/local.properties` (`sdk.dir=`) or `ANDROID_HOME`; never commit `local.properties`.
4. Homebrew path: `brew install --cask android-commandlinetools` installs `sdkmanager` and sets default SDK root `$HOMEBREW_PREFIX/share/android-commandlinetools`: https://formulae.brew.sh/cask/android-commandlinetools. Handle both Apple Silicon (`/opt/homebrew`) and Intel (`/usr/local`) through `$(brew --prefix)`.
5. AGP 8.13.0 / Gradle 8.14.3 / compileSdk 36 are fixed by the committed Capacitor template. Do not bump versions. If the build breaks on a version, look it up (cite URL in REPORT) before changing anything.
6. Debug-signed APK only. No release keystore, no Play Store work, no passwords or keys in any file or log.
7. Do not upload the APK to EC2, Vercel, GitHub or anywhere. Do not run `scp`, `gh`, `vercel` or `aws`. Publishing is a separate user decision.
8. Never paste secrets. The only URL baked in is the public Vercel URL.
9. Network/disk: first Gradle run downloads ~1 GB. Say so before it starts; use `--no-daemon` only if memory forces it.

## Order to write `REPORT.md`

`prompts/phase-15-local-apk/REPORT.md` with: files changed; exact commands run and raw output saved under `evidence/` (script output, `shasum`, manifest dump, `git status`); versions detected (`node -v`, `java -version`, `sdkmanager --version`, Gradle version); APK path, size, sha256; install/launch/mic result (PROVEN with screenshot, or UNPROVEN with reason); problems hit and how fixed (cite URLs); limits; help needed. End with `PHASE 15 BUILT — AWAITING B5 TEST`.

Commit with message `phase-15: local mac apk build` and record the hash in REPORT.
