#!/usr/bin/env bash
# ⚠️ 已停用（2026-09 两仓 tag 彻底分开 / 形态 B）：引擎 wheel 不再内嵌 SPA，
#    release 不再调用本脚本，pyproject 也已 exclude webui/spa。SPA 由开源壳仓
#    WorldLines 独立发布/伺服，引擎运行时经 NEONRP_SPA_DIR 找。保留仅供本地手动
#    调试内置 SPA 兜底之用；正常发布链路勿用。
#
# Sync the LocalShell SPA build into the neonrp package
# (S3.2 去壳后 UI 源码住壳仓 LudicDynamics/WorldLines;本脚本从
#  WORLDLINES_UI_DIR / 同级壳仓构建并刷新引擎内置 SPA 兜底。)
#
# Builds ui/ (build:local → dist-local, the app in worldlines/ui/app; it
# fetches by relative path) and copies dist-local/ into src/neonrp/webui/spa/,
# which `neonrp web` serves at /local and pyproject packages into the wheel.
#
# Run before every /deploy (the shipped spa must be the current UI).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# S3.2 去壳:UI 源码住壳仓;解析序 = env → 同级壳仓 → (过渡)本仓 ui/
UI_DIR="${WORLDLINES_UI_DIR:-}"
if [ -z "$UI_DIR" ]; then
  for cand in "$REPO_ROOT/worldlines/ui" "$REPO_ROOT/../worldlines/ui" "$REPO_ROOT/../Publishment/WorldLines/ui" "$REPO_ROOT/ui"; do  # dev repo · public repo(neonrp/ 与 worldlines/ 平级)
    if [ -f "$cand/package.json" ]; then UI_DIR="$cand"; break; fi
  done
fi
UI_DIR="${UI_DIR:-$REPO_ROOT/ui}"
SPA_DIR="$REPO_ROOT/src/neonrp/webui/spa"

if [ ! -f "$UI_DIR/package.json" ]; then
  echo "error: UI source not found at $UI_DIR" >&2
  echo "       (override with WORLDLINES_UI_DIR=/path/to/ui)" >&2
  exit 1
fi

echo "building LocalShell SPA (same-origin: VITE_PLAY_ENDPOINT= VITE_CREATE_ENDPOINT=)…"
(
  cd "$UI_DIR"
  [ -d node_modules ] || npm install --no-audit --no-fund
  VITE_CREATE_ENDPOINT= VITE_PLAY_ENDPOINT= npm run build:local
)

if [ ! -f "$UI_DIR/dist-local/index.html" ]; then
  echo "error: build produced no dist-local/index.html in $UI_DIR" >&2
  exit 1
fi

rm -rf "$SPA_DIR"
cp -R "$UI_DIR/dist-local" "$SPA_DIR"
echo "synced $(find "$SPA_DIR" -type f | wc -l | tr -d ' ') files → src/neonrp/webui/spa"
