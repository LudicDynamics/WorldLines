#!/usr/bin/env bash
# Copy the art a client example shows from the asset workshop (worldlines-assets) and the template, resized for the web.
#   WORLDLINES_ASSETS_DIR=~/Workspaces/worldlines/worldlines-assets bash pull.sh [world]
# Missing pictures are reported and skipped — the clients draw a placeholder until they exist.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
WORLD="${1:-pct-house}"
ASSETS="${WORLDLINES_ASSETS_DIR:-$HOME/Workspaces/worldlines/worldlines-assets}/worlds/$WORLD"
TPL="$HERE/../../../templates/$WORLD.template"
OUT="$HERE/$WORLD"
put() {  # put <dest relative to OUT> <max px> <source>…  (first source that exists wins)
  local dest="$1" px="$2"; shift 2
  for src in "$@"; do
    if [ -f "$src" ]; then
      mkdir -p "$OUT/$(dirname "$dest")"
      case "$dest" in
        *.png) sips -Z "$px" "$src" --out "$OUT/$dest" >/dev/null ;;
        *) sips -Z "$px" -s format jpeg -s formatOptions 82 "$src" --out "$OUT/$dest" >/dev/null ;;
      esac
      echo "  ✓ $dest"; return
    fi
  done
  echo "  · $dest (not drawn yet)"
}
echo "art for $WORLD → $OUT"
put title.jpg 1920 "$ASSETS/cover/cover-wide.png" "$TPL/assets/cover.jpg"
for r in hall study garden cellar; do put "backgrounds/$r.jpg" 1920 "$ASSETS/backgrounds/$r.png"; done
put characters/chara.jpg 1200 "$ASSETS/characters/chara/base.png" "$TPL/world-overlay/souls/chara-si-chara0001/assets/portrait.jpg"
put characters/chara-resolute.jpg 1200 "$ASSETS/characters/chara/variants/resolute.png"
put characters/chara-afraid.jpg 1200 "$ASSETS/characters/chara/variants/afraid.png"
put characters/butler.jpg 1200 "$ASSETS/characters/butler/base.png"
put characters/butler-blocking.jpg 1200 "$ASSETS/characters/butler/variants/blocking.png"
for e in 01 02 09; do put "endings/e$e.jpg" 1920 "$ASSETS/plots/P01/e$e.png" "$TPL/plots/P01/assets/ending-E$e.jpg"; done
for i in diary cellar-key fresh-plaster; do put "items/$i.jpg" 900 "$ASSETS/items/$i.png"; done
put map/house.jpg 1920 "$ASSETS/map/house.png"
put ui/dice-d100.png 512 "$ASSETS/ui/dice-d100.png"
