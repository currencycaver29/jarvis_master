#!/bin/bash
# Install MemoryWatchdog binary to a stable path so macOS Accessibility grants
# survive subsequent rebuilds. swift build rewrites .build/release/MemoryWatchdog
# every time which invalidates the inode-based grant.
#
# Usage: bash scripts/install_watchdog.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD="$ROOT/native/mac/MemoryWatchdog/.build/release/MemoryWatchdog"
DEST_DIR="$HOME/Applications/SHAIL"
DEST="$DEST_DIR/MemoryWatchdog"

if [ ! -f "$BUILD" ]; then
  echo "✗ Build artifact not found: $BUILD"
  echo "  Run: (cd $ROOT/native/mac/MemoryWatchdog && swift build -c release)"
  exit 1
fi

mkdir -p "$DEST_DIR"

# Strip any quarantine attribute that would block Gatekeeper.
xattr -dr com.apple.quarantine "$BUILD" 2>/dev/null || true

cp "$BUILD" "$DEST"

# Ad-hoc codesign so macOS treats the binary as a stable identity for
# Accessibility / Screen Recording / Input Monitoring grants. Without this,
# Privacy & Security silently rejects after rebuild.
codesign --force --deep --sign - "$DEST"

echo "✓ Installed: $DEST"
echo "  Add to System Settings → Privacy & Security → Accessibility:"
echo "  $DEST"
