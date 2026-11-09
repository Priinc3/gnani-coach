# Phase 15 — local APK build (REPORT)

Status: **built on Google Colab at the user's request** (the local `brew` install
was interrupted). The scripts are the deliverable and are portable; they ran
unmodified on the Colab Linux VM. The Mac still has no Android SDK, so a local
re-run needs `scripts/mobile/setup-mac.sh` first.

## Files changed

- `scripts/mobile/build-apk.sh` (new) — preflight, APP_URL injection + trap restore,
  `npm ci`, `cap sync`, `gradlew assembleDebug`, copy + sha256/size.
- `scripts/mobile/setup-mac.sh` (new) — optional, asks before each `brew` install,
  detects `~/Library/Android/sdk`.
- `scripts/mobile/install-apk.sh` (new) — adb install + launch, exits 0 with
  instructions when no device.
- `docs/release/APK-LOCAL.md` (new, 60 lines) — prerequisites, build, install,
  troubleshooting.
- `apps/mobile/.gitignore` (new) — `dist/`, `*.apk`.
- `apps/mobile/package.json`, `apps/mobile/package-lock.json` — added
  `typescript@^5.9.3` (build break fix; see Problems).
- `apps/mobile/README.md` — removed the false sslip.io APK URL; points to
  `docs/release/APK-LOCAL.md`.

No changes to `appId`, permissions, `https` rule, `apps/web`, `services`,
`supabase`, `deploy`, `packages`, `.github`, or root manifests.

Pre-existing unrelated changes left uncommitted: `prompts/_tracker.md` and
`prompts/batch-B5-TEST.md` (present before this phase started).

## Commands run (raw output in `evidence/`)

Local (Mac), for packaging/verification:

```
tar czf /tmp/gnani-mobile.tgz apps/mobile scripts/mobile docs/release
colab upload /tmp/gnani-mobile.tgz /content/gnani-mobile.tgz
colab exec -f /tmp/colab-setup.py      # SDK install + licenses
colab exec -f /tmp/colab-jlinkfix.py   # start build #1 (detached)
colab exec -f /tmp/colab-verify.py     # manifest/versions, start build #2
colab download /content/gnani/apps/mobile/dist/speaking-coach.apk apps/mobile/dist/speaking-coach.apk
shasum -a 256 apps/mobile/dist/speaking-coach.apk
bash scripts/mobile/install-apk.sh
```

On the VM the exact build entry point was:

```
cd /content/gnani && bash scripts/mobile/build-apk.sh
# env: ANDROID_HOME=/root/android-sdk JAVA_HOME=/tmp/jdk21copy \
#      APP_URL=https://gnani-coach.vercel.app
```

Evidence files:

| file | contents |
|---|---|
| `evidence/build-colab.log` | full build #1 (BUILD SUCCESSFUL in 2m 47s) |
| `evidence/build-rerun.log` | full build #2 (52s, same sha256) |
| `evidence/apkanalyzer-manifest.txt` | `apkanalyzer manifest print` |
| `evidence/aapt-badging.txt` | `aapt dump badging` |
| `evidence/apk-info.txt` | size, sha256, `apkanalyzer apk summary` |
| `evidence/versions.txt` | node, java, sdkmanager, Gradle |
| `evidence/local-sha256.txt`, `evidence/local-apk-size.txt` | downloaded artifact |
| `evidence/install-attempt.txt` | no-device path, exit 0 |
| `evidence/git-status.txt` | source-only changes after the build |
| `evidence/colab-status.txt` | Colab machine used |

## Versions detected

- Colab: Ubuntu 24.04, Node **v22.23.4**, JDK **21.0.12.1**, `sdkmanager` **19.0**,
  Gradle **8.14.3**, compileSdk/targetSdk **36**, minSdk **24**.
- Mac: Node v26.13.0, Homebrew OpenJDK 21.0.11 (not registered with
  `/usr/libexec/java_home`; the script falls back to `brew --prefix`).

## APK

- Path: `apps/mobile/dist/speaking-coach.apk` (git-ignored)
- Size: **3,897,287 bytes**
- SHA-256: **`0b2b39c7a2298032b226a71d6b8f477d6e3790ce36ac2c08cb4bfb5132bfc040`**
- Package: `com.gnanicoach.app`, versionCode 1, versionName 1.0, debug-signed.
- Declared permissions in `AndroidManifest.xml`: exactly `INTERNET`,
  `RECORD_AUDIO`, `MODIFY_AUDIO_SETTINGS`.
- Merged APK also contains `com.gnanicoach.app.DYNAMIC_RECEIVER_NOT_EXPORTED_PERMISSION`,
  auto-added by `androidx.core` (signature-level, internal to the library). It is
  not in our manifest and cannot be removed without risking
  `ContextCompat.registerReceiver`. Honest deviation from "exactly three" at the
  merged-APK level.
- `git check-ignore` confirms the APK and `android/local.properties` are ignored.
  `error.html` is byte-identical after the build (trap restored it).

## Install / launch / microphone — UNPROVEN

No Android device and no emulator were available: `adb` is not installed on the
Mac, no phone appeared over USB, and the Colab VM has no KVM/emulator. The install
script was exercised and exits 0 with instructions (`evidence/install-attempt.txt`).
**Install, launch and the WebView microphone path are not proven.** No screenshot
exists because no device ran the app.

To prove it: connect a phone or start an emulator, then run
`bash scripts/mobile/install-apk.sh`, tap Start call, grant the microphone prompt,
and confirm "listening".

## Problems hit and fixes

1. **`cap sync` failed: "Could not find installation of TypeScript."**
   `capacitor.config.ts` was committed without the `typescript` dependency.
   Fixed by adding `typescript@^5.9.3` as a devDependency
   (<https://capacitorjs.com/docs/config>).
2. **Colab build failed in `JdkImageTransform`** (`jmod` exit 2). Colab's JDK
   prints `[warning][os,container] Cgroup ...` on stdout; AGP reads
   `jlink --version` and, when `JavaVersion.toVersion()` fails, uses the whole
   output as `--module-version`. Verified in AGP 8.13.0 sources:
   <https://cs.android.com/android-studio/platform/tools/base/+/mirror-goog-studio-main:build-system/gradle-core/src/main/java/com/android/build/gradle/internal/dependency/JdkImageTransformDelegate.kt>
   Worked around **on the Colab VM only** with a `/tmp/jdk21copy/bin/jlink`
   wrapper that filters those warning lines. No repo change; a normal Mac JDK
   does not emit this warning.
3. **Local `brew install --cask android-commandlinetools` was interrupted** when
   the user asked to use Colab. Switched to Colab; the same `build-apk.sh` ran.

## Limits / help needed

- The Mac has **no Android SDK**, so `bash scripts/mobile/build-apk.sh` will fail
  its preflight locally until `scripts/mobile/setup-mac.sh` is run. The script
  itself is proven on Linux/Colab.
- The APK is **not uploaded or published** anywhere; it exists only locally.
- Install/mic remain UNPROVEN (no device).
- No help needed to finish the build; a phone is needed for the B5 runtime test.

PHASE 15 BUILT — AWAITING B5 TEST
