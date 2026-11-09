# Build the Android APK locally

The APK is **not published anywhere**. Build it on your machine and sideload it.
GitHub Actions is blocked by billing; `android-apk.yml` stays as the future CI path.

## Prerequisites

- Node.js >= 22.
- JDK 21 (Temurin 21). Do **not** use JDK 25+: Gradle 8.14.3 does not run on it.
- Android SDK with `platforms;android-36`, `build-tools;36.0.0`, `platform-tools`, licenses accepted.

One-time macOS setup (asks before each `brew` install):

```bash
bash scripts/mobile/setup-mac.sh
```

## Build

```bash
bash scripts/mobile/build-apk.sh
```

Defaults to `https://gnani-coach.vercel.app`. Override with
`APP_URL=https://... bash scripts/mobile/build-apk.sh` (https only). The first
run downloads roughly 1 GB of Gradle/AGP dependencies; later runs are faster.
The script prints the SHA-256 and size at the end.

## Where the APK lands

`apps/mobile/dist/speaking-coach.apk` (debug-signed, git-ignored). Intermediate:
`apps/mobile/android/app/build/outputs/apk/debug/app-debug.apk`.

## Install

```bash
bash scripts/mobile/install-apk.sh
```

With one device or emulator connected over USB, it runs `adb install -r` and
launches `com.gnanicoach.app`. With no device it prints instructions and exits 0.

Without adb: copy `speaking-coach.apk` to the phone (email, cloud drive, USB),
open it in Files, allow "install unknown apps", and confirm.

On first use tap **Start call**, allow the microphone prompt, and confirm the
call screen reaches "listening".

## Troubleshooting

- **`No JDK 21 found`**: `brew install --cask temurin@21`, then
  `export JAVA_HOME=$(/usr/libexec/java_home -v 21)`.
- **`Android SDK not found` / missing platform 36**: run `setup-mac.sh`, or
  `sdkmanager "platform-tools" "platforms;android-36" "build-tools;36.0.0"`.
- **`SDK licenses are not accepted`**: `yes | sdkmanager --licenses`.
- **"Unsupported class file major version"**: a newer JDK is active; point
  `JAVA_HOME` at a 21 install.
- **"Can't reach Speaking Coach"**: the phone cannot reach the hosted site;
  check Wi-Fi/mobile data and tap Retry.
- **`INSTALL_FAILED_UPDATE_INCOMPATIBLE`**: `adb uninstall com.gnanicoach.app`.
