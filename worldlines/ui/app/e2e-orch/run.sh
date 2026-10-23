#!/usr/bin/env bash
# 创作台「到编排台编辑」深链接 e2e(orch-preview 10-19):隔离 HOME + 假模型(e2e-create/fake_llm.py)+ 本机引擎(界面构建在临时目录),Playwright Chromium。
#   bash worldlines/ui/app/e2e-orch/run.sh
#   WL_OD_SHOTS=<目录> 截图(默认 docs/playrecords/orch-deeplink-1019/)· WL_OD_PORT(默认 8805)· WL_OD_AI_PORT(默认 8806)
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../../../.." && pwd)"
PORT="${WL_OD_PORT:-8805}"
AI_PORT="${WL_OD_AI_PORT:-8806}"
TMP="$(mktemp -d "${TMPDIR:-/tmp}/wl-od-e2e.XXXXXX")"
cleanup() { kill "${SRV:-}" "${MOCK:-}" 2>/dev/null || true; wait 2>/dev/null || true; rm -rf "$TMP"; }
trap cleanup EXIT

mkdir -p "$TMP/wl/ui"
cp -R "$REPO/worldlines/ui/app" "$TMP/wl/ui/app"
( cd "$TMP/wl/ui/app" && WL_PLAYER=off node build.mjs >/dev/null )

H="$TMP/home"; mkdir -p "$H/.neonrp" "$H/templates" "$H/worldlines-assets"
cp -R "$REPO/worldlines/templates/stoneford-town.template" "$REPO/worldlines/templates/pct-house.template" "$H/templates/"
printf '{"llm": {"model_ref": "mock"}, "create_provider": "mock", "models": {"mock": {"provider": "openai", "model": "mock-1", "base_url": "http://127.0.0.1:%s/v1", "api_key": "mock"}}}\n' "$AI_PORT" > "$H/.neonrp/config.json"
. "$REPO/worldlines/ui/e2e-ports.sh"
wl_ports_free "$PORT" "$AI_PORT" || exit 3
export NEONRP_STRICT_PORT=1
python3 "$HERE/../e2e-create/fake_llm.py" --port "$AI_PORT" > "$TMP/mock.log" 2>&1 & MOCK=$!
wl_wait_server "http://127.0.0.1:$AI_PORT/_mock/state" "$MOCK" "$TMP/mock.log" || exit 3
( cd "$REPO" && exec env HOME="$H" NEONRP_TEMPLATE_PATH="$H/templates" NEONRP_TEMPLATE_WRITE_DIR="$H/templates" WORLDLINES_ASSETS_DIR="$H/worldlines-assets" \
    NEONRP_DISABLE_CLAUDE_CODE=1 NEONRP_SPA_DIR="$TMP/wl/ui/dist-local" uv run neonrp web --port "$PORT" --no-browser ) > "$TMP/engine.log" 2>&1 & SRV=$!
wl_wait_engine "$PORT" "$SRV" "$TMP/engine.log" 120 || exit 3

cd "$HERE"
WL_OD_BASE="http://127.0.0.1:$PORT" WL_OD_SHOTS="${WL_OD_SHOTS:-$REPO/docs/playrecords/orch-deeplink-1019}" \
  npx playwright test -c playwright.config.ts "$@" || { tail -40 "$TMP/engine.log"; exit 1; }
