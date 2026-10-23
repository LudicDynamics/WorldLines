#!/usr/bin/env bash
# Build "WorldLines Installer.app" — a script-only bootstrap installer.
#
# Why this exists: Apple Silicon Gatekeeper flags downloaded, un-notarized
# *binaries* (the Tauri shell) as「已损坏」with no bypass. Script-only apps
# still get the soft "unverified developer" dialog (right-click → Open works).
# So the installer is a tiny script app the user CAN open; it curl-downloads
# the Tauri DMG (curl sets no quarantine attribute), installs it into
# /Applications, and launches it — after which the desktop app double-clicks
# cleanly forever. Retire this once Developer ID signing + notarization land.
#
# Usage: scripts/build_macos_installer.sh [version] [out_dir]

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"  # repo root (10-05: moved to worldlines/packaging/)
VERSION="${1:-$(awk -F'"' '/^version *=/{print $2; exit}' "$ROOT_DIR/pyproject.toml")}"
OUT_DIR="${2:-$ROOT_DIR/dist/installer}"

APP_NAME="WorldLines Installer.app"
APP_DIR="$OUT_DIR/$APP_NAME"
STAGE_DIR="$OUT_DIR/dmg-root"
ZIP_PATH="$OUT_DIR/WorldLines-Installer.zip"
DMG_PATH="$OUT_DIR/WorldLines-Installer.dmg"
ICON_SOURCE_PATH="$ROOT_DIR/assets/icons/worldlines.png"
ICON_PNG_PATH="$OUT_DIR/WorldLines-icon-1024.png"
ICONSET_DIR="$OUT_DIR/WorldLines.iconset"
ICON_ICNS_PATH="$APP_DIR/Contents/Resources/WorldLines.icns"
MAIN_SCRIPT="$APP_DIR/Contents/MacOS/WorldLinesInstaller"
INSTALL_SCRIPT="$APP_DIR/Contents/Resources/install-desktop.command"
PLIST_PATH="$APP_DIR/Contents/Info.plist"

if [[ ! -f "$ICON_SOURCE_PATH" ]]; then
    printf 'error: icon source missing at %s\n' "$ICON_SOURCE_PATH" >&2
    exit 1
fi

rm -rf "$APP_DIR" "$STAGE_DIR" "$ZIP_PATH" "$DMG_PATH" "$ICONSET_DIR" "$ICON_PNG_PATH"
mkdir -p "$APP_DIR/Contents/MacOS" "$APP_DIR/Contents/Resources" "$STAGE_DIR"

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

# --- the actual installer logic (runs inside Terminal.app) ----------------
cat > "$INSTALL_SCRIPT" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

URL="https://github.com/LudicDynamics/WorldLines/releases/latest/download/WorldLines-Desktop-macos-arm64.dmg"
DEST="/Applications/WorldLines.app"

printf '\n  WorldLines Desktop 安装程序\n  ──────────────────────────\n\n'
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

printf '▸ 正在下载最新版 WorldLines Desktop…\n'
curl -fL --progress-bar -o "$tmp/wl.dmg" "$URL"

printf '▸ 正在安装到 /Applications…\n'
mnt="$(hdiutil attach -nobrowse -readonly "$tmp/wl.dmg" | awk -F'\t' '/\/Volumes\//{print $NF; exit}')"
if [[ -z "$mnt" ]]; then
    printf '✗ 无法挂载安装镜像\n' >&2
    exit 1
fi
rm -rf "$DEST"
ditto "$mnt/WorldLines.app" "$DEST"
hdiutil detach "$mnt" -quiet || true

# curl 下载不带隔离标记,这里再兜一层底
xattr -cr "$DEST" 2>/dev/null || true

printf '\n✓ 安装完成,正在启动 WorldLines…\n'
printf '  之后直接双击「应用程序」里的 WorldLines 即可,本安装器可以删除。\n\n'
open "$DEST"
EOF
chmod 755 "$INSTALL_SCRIPT"

# --- app entry: open Terminal on the install script -----------------------
cat > "$MAIN_SCRIPT" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

bundle_dir="$(cd "$(dirname "$0")/.." && pwd)"
installer="$bundle_dir/Resources/install-desktop.command"

if [[ ! -x "$installer" ]]; then
    chmod +x "$installer" 2>/dev/null || true
fi

escaped_installer=${installer//\\/\\\\}
escaped_installer=${escaped_installer//\"/\\\"}

osascript <<OSA
set installerPath to "$escaped_installer"
tell application "Terminal"
    activate
    do script quoted form of installerPath
end tell
OSA
EOF
chmod 755 "$MAIN_SCRIPT"

cat > "$PLIST_PATH" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleDevelopmentRegion</key>
  <string>en</string>
  <key>CFBundleDisplayName</key>
  <string>WorldLines Installer</string>
  <key>CFBundleExecutable</key>
  <string>WorldLinesInstaller</string>
  <key>CFBundleIdentifier</key>
  <string>gg.worldlines.installer</string>
  <key>CFBundleInfoDictionaryVersion</key>
  <string>6.0</string>
  <key>CFBundleIconFile</key>
  <string>WorldLines</string>
  <key>CFBundleName</key>
  <string>WorldLines Installer</string>
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
hdiutil create -volname "WorldLines Installer" -srcfolder "$STAGE_DIR" -ov -format UDZO "$DMG_PATH" >/dev/null

rm -rf "$STAGE_DIR" "$ICONSET_DIR"

printf 'built:\n  %s\n  %s\n  %s\n' "$APP_DIR" "$ZIP_PATH" "$DMG_PATH"
