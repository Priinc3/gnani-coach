# Speaking Coach Android app

Capacitor 8 shell that loads the hosted Speaking Coach web app in an Android WebView. Debug-signed, sideload only.

## Build it on this machine

```bash
bash scripts/mobile/build-apk.sh          # writes apps/mobile/dist/speaking-coach.apk
bash scripts/mobile/install-apk.sh        # adb install + launch, if a device is connected
```

Full prerequisites, install and troubleshooting: [docs/release/APK-LOCAL.md](../../docs/release/APK-LOCAL.md).

The APK is **not published at any URL**. Phase 13's sslip.io host serves the
voice service only. GitHub Actions (`android-apk.yml`) remains the future CI
path but is currently blocked by billing.

## Install (sideload)

1. Copy `speaking-coach.apk` to the phone.
2. Open it and allow "install unknown apps" for the app you opened it from (Files, Chrome, and so on).
3. Confirm the install, then open Speaking Coach.

## If the error page appears

The app shows "Can't reach Speaking Coach" when the phone cannot load the hosted site. Check mobile data or Wi-Fi, then tap Retry. The error page is a local fallback; nothing is cached for offline use.

## Honest limits

- Debug-signed: fine for sideloading, not for the Play Store.
- Loads the hosted site; there is no offline mode and no bundled copy of the web app.
- Sign-in is email + password on our own server, so it works inside the WebView. Guest mode works too.
- The app declares only `INTERNET`, `RECORD_AUDIO`, and `MODIFY_AUDIO_SETTINGS`; the WebView asks for microphone access on first use.
