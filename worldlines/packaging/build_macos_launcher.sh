#!/usr/bin/env bash
# Build a thin WorldLines.app wrapper plus distributable archives.
#
# The app does not bundle Python or the NeonRP runtime. It simply opens
# Terminal.app and delegates to the same bootstrap logic as
# `WorldLines.command`, which installs/upgrades `worldlines` via `uv`
# and then launches the TUI.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"  # repo root (10-05: moved to worldlines/packaging/)
VERSION="${1:-$(awk -F'"' '/^version *=/{print $2; exit}' "$ROOT_DIR/pyproject.toml")}"
OUT_DIR="${2:-$ROOT_DIR/dist/macos}"

APP_NAME="WorldLines.app"
APP_DIR="$OUT_DIR/$APP_NAME"
STAGE_DIR="$OUT_DIR/dmg-root"
ZIP_PATH="$OUT_DIR/WorldLines.app.zip"
DMG_PATH="$OUT_DIR/WorldLines.dmg"
ICON_SOURCE_PATH="$ROOT_DIR/assets/icons/worldlines.png"
ICON_PNG_PATH="$OUT_DIR/WorldLines-icon-1024.png"
ICONSET_DIR="$OUT_DIR/WorldLines.iconset"
ICON_ICNS_PATH="$APP_DIR/Contents/Resources/WorldLines.icns"
LAUNCHER_SCRIPT="$APP_DIR/Contents/MacOS/WorldLines"
RESOURCE_SCRIPT="$APP_DIR/Contents/Resources/WorldLines.command"
PLIST_PATH="$APP_DIR/Contents/Info.plist"

if [[ ! -f "$ICON_SOURCE_PATH" ]]; then
    printf 'error: icon source missing at %s\n' "$ICON_SOURCE_PATH" >&2
    exit 1
fi

rm -rf "$APP_DIR" "$STAGE_DIR" "$ZIP_PATH" "$DMG_PATH" "$ICONSET_DIR" "$ICON_PNG_PATH"
mkdir -p "$APP_DIR/Contents/MacOS" "$APP_DIR/Contents/Resources" "$STAGE_DIR"

# Use the canonical brand icon (RGBA PNG, ~1000×1000) — sips normalizes
# to the exact 1024×1024 master that iconset slices feed off of.
cp "$ICON_SOURCE_PATH" "$ICON_PNG_PATH"
sips -z 1024 1024 "$ICON_PNG_PATH" --out "$ICON_PNG_PATH" >/dev/null
mkdir -p "$ICONSET_DIR"

for size in 16 32 128 256 512; do
    sips -z "$size" "$size" "$ICON_PNG_PATH" --out "$ICONSET_DIR/icon_${size}x${size}.png" >/dev/null
done
for size in 16 32 128 256 512; do
    double_size=$((size * 2))
    sips -z "$double_size" "$double_size" "$ICON_PNG_PATH" --out "$ICONSET_DIR/icon_${size}x${size}@2x.png" >/dev/null
done
cp "$ICON_PNG_PATH" "$ICONSET_DIR/icon_512x512@2x.png"
iconutil -c icns "$ICONSET_DIR" -o "$ICON_ICNS_PATH"

cp "$ROOT_DIR/worldlines/packaging/launchers/WorldLines.command" "$RESOURCE_SCRIPT"
chmod 755 "$RESOURCE_SCRIPT"

cat > "$LAUNCHER_SCRIPT" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

bundle_dir="$(cd "$(dirname "$0")/.." && pwd)"
launcher="$bundle_dir/Resources/WorldLines.command"

if [[ ! -x "$launcher" ]]; then
    chmod +x "$launcher" 2>/dev/null || true
fi

escaped_launcher=${launcher//\\/\\\\}
escaped_launcher=${escaped_launcher//\"/\\\"}

osascript <<OSA
set launcherPath to "$escaped_launcher"
tell application "Terminal"
    activate
    do script quoted form of launcherPath
end tell
OSA
EOF
chmod 755 "$LAUNCHER_SCRIPT"

cat > "$PLIST_PATH" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleDevelopmentRegion</key>
  <string>en</string>
  <key>CFBundleDisplayName</key>
  <string>WorldLines</string>
  <key>CFBundleExecutable</key>
  <string>WorldLines</string>
  <key>CFBundleIdentifier</key>
  <string>gg.worldlines.launcher</string>
  <key>CFBundleInfoDictionaryVersion</key>
  <string>6.0</string>
  <key>CFBundleIconFile</key>
  <string>WorldLines</string>
  <key>CFBundleName</key>
  <string>WorldLines</string>
  <key>CFBundlePackageType</key>
  <string>APPL</string>
  <key>CFBundleShortVersionString</key>
  <string>${VERSION}</string>
  <key>CFBundleVersion</key>
  <string>${VERSION}</string>
  <key>LSMinimumSystemVersion</key>
  <string>12.0</string>
  <key>NSHighResolutionCapable</key>
  <true/>
</dict>
</plist>
EOF

plutil -lint "$PLIST_PATH" >/dev/null

ditto -c -k --sequesterRsrc --keepParent "$APP_DIR" "$ZIP_PATH"

cp -R "$APP_DIR" "$STAGE_DIR/$APP_NAME"
ln -s /Applications "$STAGE_DIR/Applications"
hdiutil create -volname "WorldLines" -srcfolder "$STAGE_DIR" -ov -format UDZO "$DMG_PATH" >/dev/null

rm -rf "$STAGE_DIR" "$ICONSET_DIR"

printf 'Built macOS launcher assets:\n'
printf '  %s\n' "$APP_DIR" "$ZIP_PATH" "$DMG_PATH"
