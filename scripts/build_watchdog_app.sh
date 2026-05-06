#!/bin/bash
# build_watchdog_app.sh
# Builds MemoryWatchdog and wraps it in a proper .app bundle
# so macOS System Settings > Privacy > Accessibility can recognize it.
#
# Usage: ./scripts/build_watchdog_app.sh
# Output: ./native/mac/MemoryWatchdog/MemoryWatchdog.app

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WATCHDOG_DIR="$REPO_ROOT/native/mac/MemoryWatchdog"
APP_NAME="MemoryWatchdog"
BUNDLE_ID="com.shail.MemoryWatchdog"
APP_DIR="$WATCHDOG_DIR/$APP_NAME.app"

echo "==> Building MemoryWatchdog (release)…"
cd "$WATCHDOG_DIR"
swift build -c release 2>&1 | tail -5

BINARY="$WATCHDOG_DIR/.build/release/$APP_NAME"
if [ ! -f "$BINARY" ]; then
  echo "ERROR: Binary not found at $BINARY"
  exit 1
fi

echo "==> Creating .app bundle structure…"
rm -rf "$APP_DIR"
mkdir -p "$APP_DIR/Contents/MacOS"
mkdir -p "$APP_DIR/Contents/Resources"

cp "$BINARY" "$APP_DIR/Contents/MacOS/$APP_NAME"
chmod +x "$APP_DIR/Contents/MacOS/$APP_NAME"

echo "==> Writing Info.plist…"
cat > "$APP_DIR/Contents/Info.plist" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleIdentifier</key>
    <string>$BUNDLE_ID</string>
    <key>CFBundleName</key>
    <string>$APP_NAME</string>
    <key>CFBundleExecutable</key>
    <string>$APP_NAME</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0</string>
    <key>CFBundleVersion</key>
    <string>1</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>LSMinimumSystemVersion</key>
    <string>13.0</string>
    <key>LSUIElement</key>
    <true/>
    <key>NSAccessibilityUsageDescription</key>
    <string>SHAIL Memory Watchdog reads active window text to build your personal memory.</string>
    <key>NSPasteboardUsageDescription</key>
    <string>SHAIL Memory Watchdog captures clipboard text for memory storage.</string>
</dict>
</plist>
PLIST

echo "==> Writing entitlements…"
cat > /tmp/watchdog.entitlements << ENT
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>com.apple.security.app-sandbox</key>
    <false/>
    <key>com.apple.security.network.client</key>
    <true/>
</dict>
</plist>
ENT

echo "==> Signing with entitlements…"
codesign --force --sign - \
  --entitlements /tmp/watchdog.entitlements \
  --options runtime \
  "$APP_DIR" 2>/dev/null || \
codesign --force --sign - "$APP_DIR"

echo ""
echo "✓ Built: $APP_DIR"
echo ""
echo "Next steps:"
echo "  1. Open System Settings > Privacy & Security > Accessibility"
echo "  2. Click the lock to unlock (admin password)"
echo "  3. Click  +  and navigate to:"
echo "     $APP_DIR"
echo "  4. Toggle it ON"
echo "  5. Launch: open '$APP_DIR'"
echo ""
echo "To launch the app bundle:"
echo "  open '$APP_DIR'"
