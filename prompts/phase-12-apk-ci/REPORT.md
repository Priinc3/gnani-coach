# Phase 12 — apk-ci report

## What was built

A standalone Capacitor 8 Android shell in `apps/mobile/` plus a `workflow_dispatch` GitHub Actions workflow that builds a debug APK on `ubuntu-24.04`.

- `apps/mobile/package.json` + `apps/mobile/package-lock.json` — own lockfile, private, not in the root workspaces. Only `@capacitor/core`, `@capacitor/cli`, `@capacitor/android`, all pinned to `8.6.0`.
- `apps/mobile/capacitor.config.ts` — `com.gnanicoach.app`, `Speaking Coach`, `webDir: www`, remote `server.url` from `APP_URL`, `androidScheme: https`, `errorPath: error.html`, logging off, WebView debugging off. Throws a clear error when `APP_URL` is unset or not `https://`.
- `apps/mobile/www/index.html` + `error.html` — tiny original offline/error pages with a Retry button, inline CSS, no remote assets, no tracking. The workflow injects the real `APP_URL` into `error.html` before `cap sync` so Retry navigates back to the hosted site.
- `apps/mobile/android/` — generated with `npx cap add android` and committed so the manifest and icon are reviewable. The template's default Capacitor launcher and splash art were replaced with an original speech-bubble/voice-bar mark (vector drawables; no third-party art).
- `.github/workflows/android-apk.yml` — `workflow_dispatch` with optional `app_url`; falls back to `vars.APP_URL`; fails early when empty or not https. `permissions: contents: read` only, `runs-on: ubuntu-24.04`, `timeout-minutes: 30`. Steps: checkout → validate URL → setup Node 22 + npm cache → setup JDK 21 → `npm ci` → inject URL → `npx cap sync android` → Gradle cache → `./gradlew assembleDebug` → sha256 in job summary → upload `app-debug.apk` for 14 days.
- `apps/mobile/README.md` — 38 lines: dispatch, artifact, download URL, sideload, error page, honest limits.
- `prompts/phase-12-apk-ci/evidence/` — raw command output for versions, config checks, sync, manifest, icons, YAML, Capacitor source, README, npm ci.

## Key decisions

- **Committed `android/` rather than generating it in CI.** The manifest, permissions, cleartext setting and launcher icon are reviewable in git. CI still runs `npx cap sync android`, which regenerates the ignored pieces (`assets/`, `capacitor.config.json`, `res/xml/config.xml`, `capacitor-cordova-android-plugins/`) from the committed project.
- **JDK 21.** Capacitor 8.6.0's Android library compiles with `JavaVersion.VERSION_21` (source and target), so the workflow uses `actions/setup-java@v6` with Temurin 21. The runner image also ships `JAVA_HOME_21_X64`, but setup-java makes the selection explicit.
- **Manifest permissions are exactly** `INTERNET`, `RECORD_AUDIO`, `MODIFY_AUDIO_SETTINGS`. No camera, location or storage permissions. `allowBackup="false"`, `usesCleartextTraffic="false"`.
- **Microphone path verified in Capacitor source.** `BridgeWebChromeClient.onPermissionRequest` maps `android.webkit.resource.AUDIO_CAPTURE` to `MODIFY_AUDIO_SETTINGS` + `RECORD_AUDIO` and grants the request, so the hosted page's `getUserMedia` works over https.

## Sources (version and action choices)

- Capacitor 8.6.0 npm: https://www.npmjs.com/package/@capacitor/core/v/8.6.0, https://www.npmjs.com/package/@capacitor/cli/v/8.6.0, https://www.npmjs.com/package/@capacitor/android/v/8.6.0
- Capacitor 8 requirements (Node 22+, Android Studio 2025.2.1): https://capacitorjs.com/docs/getting-started/environment-setup
- Capacitor 8.6.0 Java 21 / SDK 36: https://github.com/ionic-team/capacitor/blob/8.6.0/android/capacitor/build.gradle
- Capacitor 8.6.0 audio permission handling: https://github.com/ionic-team/capacitor/blob/8.6.0/android/capacitor/src/main/java/com/getcapacitor/BridgeWebChromeClient.java
- Capacitor 8.6.0 Android template (AGP 8.13.0, Gradle wrapper 8.14.3, minSdk 24 / compileSdk 36): https://github.com/ionic-team/capacitor/blob/8.6.0/android-template/build.gradle and https://github.com/ionic-team/capacitor/blob/8.6.0/android-template/gradle/wrapper/gradle-wrapper.properties
- `ubuntu-24.04` preinstalled Node 22.23.4, JDK 21, Android SDK 36: https://raw.githubusercontent.com/actions/runner-images/main/images/ubuntu/Ubuntu2404-Readme.md
- `actions/checkout@v7` — latest release v7.0.1: https://github.com/actions/checkout/releases/tag/v7.0.1
- `actions/setup-node@v7` — latest release v7.1.0: https://github.com/actions/setup-node/releases/tag/v7.1.0
- `actions/setup-java@v6` — latest release v6.2.0: https://github.com/actions/setup-java/releases/tag/v6.2.0
- `actions/upload-artifact@v7` — latest release v7.0.2: https://github.com/actions/upload-artifact/releases/tag/v7.0.2
- `gradle/actions/setup-gradle@v6` — latest release v6.4.1: https://github.com/gradle/actions/releases/tag/v6.4.1 (`cache-provider: basic` keeps caching on the MIT/open-source path)

## Commands and evidence

- `prompts/phase-12-apk-ci/evidence/01-versions.txt` — Node/npm, npm registry versions, action releases, runner image excerpts.
- `prompts/phase-12-apk-ci/evidence/02-config-checks.txt` — successful config load, unset `APP_URL`, http rejection.
- `prompts/phase-12-apk-ci/evidence/03-cap-sync.txt` — `APP_URL=https://example.com npx cap sync android`.
- `prompts/phase-12-apk-ci/evidence/04-manifest.txt` — final manifest and a grep proving no camera/location/storage permissions.
- `prompts/phase-12-apk-ci/evidence/05-icon-resources.txt` — resource tree, adaptive icons, original foreground, splash.
- `prompts/phase-12-apk-ci/evidence/06-workflow-yaml.txt` — `python3 -c "import yaml,sys;yaml.safe_load(open(sys.argv[1]))"` result and full YAML.
- `prompts/phase-12-apk-ci/evidence/07-capacitor-source.txt` — Java 21 / SDK 36 lines and the audio permission handler.
- `prompts/phase-12-apk-ci/evidence/08-readme.txt` — README line count (38) and contents.
- `prompts/phase-12-apk-ci/evidence/09-npm-ci.txt` — `npm ci --include=dev` succeeds against the committed lockfile.
- `prompts/phase-12-apk-ci/evidence/10-dispatch-attempt.txt` — one placeholder dispatch, actionlint result, and the queued run state.

Local `npx cap add android`, `npx cap sync android`, config failure checks and `npm ci` all passed. No Gradle, Android SDK build or emulator was run here (box limits).

## UNPROVEN until the first Actions run

- The actual Gradle compile, resource linking (vector launcher icon, splash, manifest) and `app-debug.apk` assembly.
- The exact action-major combinations at runtime (`checkout@v7`, `setup-node@v7`, `setup-java@v6`, `upload-artifact@v7`, `setup-gradle@v6`).
- That `npm ci` on the runner installs the dev-only `@capacitor/cli` (expected, since the runner does not set `NODE_ENV=production`).
- Artifact upload and the sha256 summary output.
- Microphone permission prompt on a real phone.

## Dispatch attempt (placeholder only)

I dispatched the workflow once with `https://example.com` (`gh workflow run android-apk.yml -f app_url=https://example.com`, run `42357747364`). The first attempt ended in `startup_failure` after 1s; the rerun stayed `queued` with zero jobs for more than 20 minutes and never started. `actionlint 1.7.12` reports no errors and Python YAML parses the file, so this looks like runner/billing capacity on the account rather than a workflow-syntax problem. I downloaded no artifact and did not run the real build; that remains Phase 13's job.

## What the user / Phase 13 must do

1. Keep the workflow on `main` (it only runs once pushed).
2. Set the repository variable `APP_URL` to the hosted https URL, or pass it explicitly: `gh workflow run android-apk.yml -f app_url=https://...`.
3. Download `speaking-coach-debug-apk` from the run, or use the published `https://13-205-26-178.sslip.io/apk/speaking-coach.apk` after Phase 13 uploads it.
4. Sideload the debug APK and allow "install unknown apps".
5. If a run stays queued with no jobs, check the account's GitHub Actions minutes/spending limit; the workflow itself passed `actionlint` and Python YAML validation.

## Help needed

None. No sibling files were touched.

PHASE 12 BUILT
