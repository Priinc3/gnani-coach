$ wc -l apps/mobile/README.md
38 apps/mobile/README.md

$ cat apps/mobile/README.md
# Speaking Coach Android app

Capacitor 8 shell that loads the hosted Speaking Coach web app in an Android WebView. Debug-signed, sideload only.

## Build it on GitHub Actions

1. The workflow must exist on `main`; it only runs after it is pushed there.
2. Run it with the https URL of the hosted app:

   `gh workflow run android-apk.yml -f app_url=https://your-app.example`

   If `app_url` is omitted, the repository variable `APP_URL` is used.
3. Open the run in the Actions tab and download the `speaking-coach-debug-apk` artifact. It contains `app-debug.apk` and is kept for 14 days.

## Download URL

The published build is at:

https://13-205-26-178.sslip.io/apk/speaking-coach.apk

Phase 13 publishes the APK there.

## Install (sideload)

1. Copy `app-debug.apk` to the phone.
2. Open it and allow "install unknown apps" for the app you opened it from (Files, Chrome, and so on).
3. Confirm the install, then open Speaking Coach.

## If the error page appears

The app shows "Can't reach Speaking Coach" when the phone cannot load the hosted site. Check mobile data or Wi-Fi, then tap Retry. The error page is a local fallback; nothing is cached for offline use.

## Honest limits

- Debug-signed: fine for sideloading, not for the Play Store.
- Loads the hosted site; there is no offline mode and no bundled copy of the web app.
- Sign-in is email + password on our own server, so it works inside the WebView. Guest mode works too.
- The app declares only `INTERNET`, `RECORD_AUDIO`, and `MODIFY_AUDIO_SETTINGS`; the WebView asks for microphone access on first use.
