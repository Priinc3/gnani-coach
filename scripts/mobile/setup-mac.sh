#!/usr/bin/env bash
# Optional macOS helper: install the JDK 21 and Android SDK packages needed by
# scripts/mobile/build-apk.sh. It asks before every brew install and is safe to
# re-run.
set -euo pipefail

say() { printf '\n==> %s\n' "$*"; }
confirm() {
  local answer
  read -r -p "$1 [y/N] " answer || answer=""
  [[ "$answer" == "y" || "$answer" == "Y" ]]
}

[[ "$(uname -s)" == "Darwin" ]] || {
  echo "This helper is for macOS. On Linux install openjdk-21-jdk and the Android cmdline-tools yourself." >&2
  exit 1
}

BREW_PREFIX="$(brew --prefix)"
SDK="$HOME/Library/Android/sdk"
CMDLINE_TOOLS="$BREW_PREFIX/share/android-commandlinetools"

say "Plan"
cat <<EOF
This script will:
  1. Install Temurin JDK 21 (brew cask temurin@21) if missing.
  2. Detect an existing Android Studio SDK at ~/Library/Android/sdk.
     - If present: reuse it and skip the command-line-tools install.
     - If absent: brew install --cask android-commandlinetools.
  3. Install SDK packages: platform-tools, platforms;android-36, build-tools;36.0.0.
  4. Accept SDK licenses (interactive, type y).
Nothing is installed without your confirmation.
EOF

# ------------------------------------------------------------------- JDK 21
say "JDK 21"
JAVA21=""
if /usr/libexec/java_home -v 21 >/dev/null 2>&1; then
  JAVA21="$(/usr/libexec/java_home -v 21)"
elif [[ -x "$BREW_PREFIX/opt/openjdk@21/bin/java" ]]; then
  JAVA21="$BREW_PREFIX/opt/openjdk@21"
fi

if [[ -n "$JAVA21" ]]; then
  echo "Found JDK 21 at $JAVA21 - skipping."
else
  if confirm "Install Eclipse Temurin 21 with 'brew install --cask temurin@21'?"; then
    brew install --cask temurin@21
  else
    echo "Skipped. build-apk.sh will fail until a JDK 21 is available." >&2
  fi
fi

# ------------------------------------------------------------------ SDK root
say "Android SDK"
if [[ -d "$SDK" ]]; then
  echo "Found Android Studio SDK at $SDK - skipping the command-line-tools install."
elif [[ -d "$CMDLINE_TOOLS" ]]; then
  SDK="$CMDLINE_TOOLS"
  echo "Found Homebrew command-line tools at $SDK - skipping install."
else
  if confirm "Install Android command-line tools with 'brew install --cask android-commandlinetools'?"; then
    brew install --cask android-commandlinetools
    SDK="$CMDLINE_TOOLS"
  else
    echo "Skipped. build-apk.sh will fail until ANDROID_HOME points at an SDK." >&2
    exit 0
  fi
fi

# -------------------------------------------------------------- SDK packages
SDKMANAGER="$(command -v sdkmanager 2>/dev/null || true)"
for candidate in "$SDK/cmdline-tools/latest/bin/sdkmanager" "$SDK/cmdline-tools/bin/sdkmanager"; do
  [[ -n "$SDKMANAGER" ]] && break
  [[ -x "$candidate" ]] && SDKMANAGER="$candidate"
done
if [[ -z "$SDKMANAGER" ]]; then
  echo "sdkmanager not found. Open Android Studio > SDK Manager once, or reinstall the command-line tools." >&2
  exit 1
fi

export ANDROID_HOME="$SDK"
export ANDROID_SDK_ROOT="$SDK"

if confirm "Install platform-tools, platforms;android-36 and build-tools;36.0.0 into $SDK?"; then
  "$SDKMANAGER" "platform-tools" "platforms;android-36" "build-tools;36.0.0"
fi

if confirm "Accept Android SDK licenses now ('yes | sdkmanager --licenses')?"; then
  yes | "$SDKMANAGER" --licenses
fi

say "Done"
cat <<EOF
Add these to your shell profile (~/.zshrc) if they are not already set:

  export ANDROID_HOME="$SDK"
  export ANDROID_SDK_ROOT="\$ANDROID_HOME"
  export PATH="\$ANDROID_HOME/platform-tools:\$PATH"
  export JAVA_HOME="$BREW_PREFIX/opt/openjdk@21"   # or \$(/usr/libexec/java_home -v 21)

Then run:

  bash scripts/mobile/build-apk.sh
  bash scripts/mobile/install-apk.sh
EOF
