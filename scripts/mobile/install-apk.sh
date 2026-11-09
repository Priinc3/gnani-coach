#!/usr/bin/env bash
# Install and launch the built APK on a connected Android device or emulator.
# Never fails the shell when no device is present: it prints what to do instead.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
APK="${1:-$REPO_ROOT/apps/mobile/dist/speaking-coach.apk}"
PACKAGE="com.gnanicoach.app"
ACTIVITY="$PACKAGE/.MainActivity"

[[ -f "$APK" ]] || {
  echo "APK not found: $APK" >&2
  echo "Build it first: bash scripts/mobile/build-apk.sh" >&2
  exit 1
}

# Find adb via PATH, then the SDK.
ADB="$(command -v adb 2>/dev/null || true)"
if [[ -z "$ADB" ]]; then
  for sdk in "${ANDROID_HOME:-}" "${ANDROID_SDK_ROOT:-}" "$HOME/Library/Android/sdk"; do
    [[ -n "$sdk" && -x "$sdk/platform-tools/adb" ]] && ADB="$sdk/platform-tools/adb" && break
  done
fi

if [[ -z "$ADB" ]]; then
  cat <<'EOF'
adb was not found, so no device can be checked.

Enable USB debugging and install platform-tools:
  - Phone: Settings > About phone > tap "Build number" 7 times, then
    Settings > System > Developer options > USB debugging.
  - Mac: install platform-tools (Android Studio, or:
    sdkmanager "platform-tools"), plug the phone in, and accept the
    "Allow USB debugging" prompt.
  - Or start an emulator from Android Studio > Device Manager.

Then re-run: bash scripts/mobile/install-apk.sh
EOF
  exit 0
fi

# Plain strings keep this working on macOS's bash 3.2.
DEVICE_LIST="$("$ADB" devices | awk 'NR > 1 && $2 == "device" { print $1 }')"
DEVICE_COUNT="$(printf '%s\n' "$DEVICE_LIST" | grep -c . || true)"

if [[ "$DEVICE_COUNT" -ne 1 ]]; then
  if [[ "$DEVICE_COUNT" -eq 0 ]]; then
    echo "No Android device or emulator is connected."
  else
    echo "More than one device is connected:"
    printf '%s\n' "$DEVICE_LIST" | sed 's/^/  - /'
    echo "Disconnect extras or pass the serial with ANDROID_SERIAL=<serial>."
  fi
  cat <<'EOF'

How to get one:
  - Phone: enable Developer options > USB debugging, plug it in, accept the
    "Allow USB debugging" prompt, then run `adb devices` until it says "device".
  - Emulator: Android Studio > Device Manager > create/start a device.

The APK is ready at apps/mobile/dist/speaking-coach.apk; this is not an error.
EOF
  exit 0
fi

SERIAL="${ANDROID_SERIAL:-$(printf '%s\n' "$DEVICE_LIST" | head -n 1)}"
echo "Installing $APK on $SERIAL"
"$ADB" -s "$SERIAL" install -r "$APK"

echo "Launching $ACTIVITY"
"$ADB" -s "$SERIAL" shell am start -n "$ACTIVITY"

cat <<'EOF'

On the phone:
  1. Wait for the Speaking Coach page to load.
  2. Tap "Start call" and allow the microphone prompt.
  3. Confirm the call screen reaches "listening".
EOF
