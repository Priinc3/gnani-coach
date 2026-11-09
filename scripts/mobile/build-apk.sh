#!/usr/bin/env bash
# Build the debug-signed Speaking Coach APK.
#
# Works on macOS (the supported local path) and on Linux (used for the
# Google Colab build). Idempotent: safe to run again.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MOBILE_DIR="$REPO_ROOT/apps/mobile"
DIST_DIR="$MOBILE_DIR/dist"
ERROR_HTML="$MOBILE_DIR/www/error.html"
APK_BUILT="$MOBILE_DIR/android/app/build/outputs/apk/debug/app-debug.apk"
APK_DIST="$DIST_DIR/speaking-coach.apk"

APP_URL="${APP_URL:-https://gnani-coach.vercel.app}"

say() { printf '\n==> %s\n' "$*"; }
die() {
  printf '\nERROR: %s\n' "$*" >&2
  exit 1
}

# ---------------------------------------------------------------- preflight
say "Preflight: APP_URL"
case "$APP_URL" in
  https://*) ;;
  *) die "APP_URL must start with https:// (got \"$APP_URL\"). Cleartext HTTP is not allowed.
  Fix: export APP_URL=https://gnani-coach.vercel.app" ;;
esac
echo "    APP_URL=$APP_URL"

say "Preflight: Node.js >= 22"
command -v node >/dev/null 2>&1 || die "Node.js is not installed.
  Fix (macOS): brew install node@22
  Fix (Ubuntu): curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash - && sudo apt-get install -y nodejs"
NODE_MAJOR="$(node -p 'process.versions.node.split(".")[0]')"
[[ "$NODE_MAJOR" -ge 22 ]] || die "Node.js $(node -v) is too old; Capacitor 8 needs Node >= 22.
  Fix (macOS): brew install node@22 && export PATH=\"\$(brew --prefix)/opt/node@22/bin:\$PATH\""
echo "    node $(node -v)"

say "Preflight: JDK 21"
# Gradle 8.14.3 does not support JVM 25+, and Capacitor 8.6.0 compiles with Java 21.
# Prefer an explicitly-set JAVA_HOME, then the platform's 21 install.
JAVA21=""
is_java21() { [[ -x "$1/bin/java" ]] && "$1/bin/java" -version 2>&1 | grep -qE 'version "21(\.|")'; }
if [[ -n "${JAVA_HOME:-}" ]] && is_java21 "$JAVA_HOME"; then
  JAVA21="$JAVA_HOME"
elif [[ "$(uname -s)" == "Darwin" ]] && JAVA21="$(/usr/libexec/java_home -v 21 2>/dev/null)"; then
  :
elif [[ "$(uname -s)" == "Darwin" ]] && JAVA21="$(brew --prefix 2>/dev/null)/opt/openjdk@21" && is_java21 "$JAVA21"; then
  :
else
  for candidate in /usr/lib/jvm/java-21-openjdk-amd64 /usr/lib/jvm/java-21-openjdk \
                   /Library/Java/JavaVirtualMachines/temurin-21.jdk/Contents/Home; do
    if is_java21 "$candidate"; then JAVA21="$candidate"; break; fi
  done
fi
[[ -n "$JAVA21" ]] || die "No JDK 21 found. Do not use a newer JDK: Gradle 8.14.3 does not run on JVM 25+.
  Fix (macOS): brew install --cask temurin@21
  Fix (Ubuntu): sudo apt-get install -y openjdk-21-jdk-headless"
export JAVA_HOME="$JAVA21"
export PATH="$JAVA_HOME/bin:$PATH"
echo "    JAVA_HOME=$JAVA_HOME"
"$JAVA_HOME/bin/java" -version 2>&1 | sed 's/^/    /'

say "Preflight: Android SDK"
SDK="${ANDROID_HOME:-${ANDROID_SDK_ROOT:-}}"
if [[ -z "$SDK" ]]; then
  for candidate in "$HOME/Library/Android/sdk" \
                   "$(brew --prefix 2>/dev/null)/share/android-commandlinetools" \
                   /usr/lib/android-sdk /opt/android-sdk; do
    if [[ -d "$candidate" ]]; then SDK="$candidate"; break; fi
  done
fi
[[ -n "$SDK" && -d "$SDK" ]] || die "Android SDK not found (ANDROID_HOME is unset).
  Fix (macOS): bash scripts/mobile/setup-mac.sh
  Fix (Ubuntu): install cmdline-tools, then: sdkmanager \"platform-tools\" \"platforms;android-36\" \"build-tools;36.0.0\""
export ANDROID_HOME="$SDK"
export ANDROID_SDK_ROOT="$SDK"
echo "    ANDROID_HOME=$ANDROID_HOME"

[[ -d "$SDK/platforms/android-36" ]] || die "Android SDK platform 36 is missing.
  Fix: sdkmanager \"platforms;android-36\""
ls -d "$SDK"/build-tools/* >/dev/null 2>&1 || die "Android SDK build-tools are missing.
  Fix: sdkmanager \"build-tools;36.0.0\""

SDKMANAGER="$(command -v sdkmanager 2>/dev/null || true)"
for candidate in "$SDK/cmdline-tools/latest/bin/sdkmanager" "$SDK/cmdline-tools/bin/sdkmanager"; do
  [[ -n "$SDKMANAGER" ]] && break
  [[ -x "$candidate" ]] && SDKMANAGER="$candidate"
done
[[ -n "$SDKMANAGER" ]] || die "sdkmanager not found under $SDK.
  Fix (macOS): brew install --cask android-commandlinetools"
if [[ ! -f "$SDK/licenses/android-sdk-license" ]]; then
  die "Android SDK licenses are not accepted.
  Fix: yes | \"$SDKMANAGER\" --licenses"
fi
echo "    sdkmanager=$SDKMANAGER"

# --------------------------------------------------------- error.html inject
say "Injecting APP_URL into www/error.html (restored on exit)"
ERROR_HTML_BACKUP="$(mktemp "${TMPDIR:-/tmp}/error.html.XXXXXX")"
cp "$ERROR_HTML" "$ERROR_HTML_BACKUP"
restore_error_html() {
  cp "$ERROR_HTML_BACKUP" "$ERROR_HTML"
  rm -f "$ERROR_HTML_BACKUP"
}
trap restore_error_html EXIT INT TERM

APP_URL="$APP_URL" node -e '
  const fs = require("fs");
  const p = process.argv[1];
  const s = fs.readFileSync(p, "utf8");
  fs.writeFileSync(p, s.replaceAll("__APP_URL__", () => process.env.APP_URL));
' "$ERROR_HTML"

grep -q "__APP_URL__" "$ERROR_HTML" && die "error.html still contains __APP_URL__ after injection."
echo "    injected $APP_URL"

# ---------------------------------------------------------------- npm + sync
say "Installing npm dependencies (npm ci)"
( cd "$MOBILE_DIR" && npm ci )

say "Syncing Capacitor Android project"
( cd "$MOBILE_DIR" && APP_URL="$APP_URL" npx cap sync android )

# -------------------------------------------------------------------- build
say "Building debug APK (first run downloads ~1 GB of Gradle/AGP dependencies)"
chmod +x "$MOBILE_DIR/android/gradlew"
( cd "$MOBILE_DIR/android" && ./gradlew assembleDebug )

[[ -f "$APK_BUILT" ]] || die "Gradle finished but $APK_BUILT does not exist."

# ---------------------------------------------------------------- publish
say "Copying APK to apps/mobile/dist/"
mkdir -p "$DIST_DIR"
cp "$APK_BUILT" "$APK_DIST"

if command -v shasum >/dev/null 2>&1; then
  SHA="$(shasum -a 256 "$APK_DIST" | awk '{print $1}')"
else
  SHA="$(sha256sum "$APK_DIST" | awk '{print $1}')"
fi
SIZE="$(wc -c < "$APK_DIST" | tr -d ' ')"

# Verify the artifact cannot be committed by accident.
if command -v git >/dev/null 2>&1 && git -C "$REPO_ROOT" rev-parse --git-dir >/dev/null 2>&1; then
  git -C "$REPO_ROOT" check-ignore -q "$APK_DIST" \
    || die "$APK_DIST is not git-ignored. Add apps/mobile/dist/ to apps/mobile/.gitignore."
fi

printf '\nAPK:    %s\n' "$APK_DIST"
printf 'Size:   %s bytes\n' "$SIZE"
printf 'SHA256: %s\n' "$SHA"
printf '\nInstall it with: bash scripts/mobile/install-apk.sh\n'
