#!/usr/bin/env bash
# 工作台「捏角色」开关 e2e(10-25):隔离 HOME + 假模型 + 本机引擎(界面构建在临时目录),Playwright Chromium 1366×900。
#   bash worldlines/ui/app/e2e-builder/run.sh
#   WL_PB_SHOTS=<目录> 截图放这里(默认 docs/playrecords/builder-toggle-1025/)· WL_PB_PORT(默认 8801)· WL_PB_AI_PORT(默认 8802)
#   WL_NEONRP=<命令> 起引擎用的命令(默认 uv run neonrp)
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../../../.." && pwd)"
PORT="${WL_PB_PORT:-8801}"
AI_PORT="${WL_PB_AI_PORT:-8802}"
NEONRP="${WL_NEONRP:-uv run neonrp}"
TMP="$(mktemp -d "${TMPDIR:-/tmp}/wl-pb-e2e.XXXXXX")"
cleanup() { kill "${SRV:-}" "${MOCK:-}" 2>/dev/null || true; wait 2>/dev/null || true; rm -rf "$TMP"; }
trap cleanup EXIT

mkdir -p "$TMP/wl/ui"
cp -R "$REPO/worldlines/ui/app" "$TMP/wl/ui/app"
if [ -d "$REPO/worldlines/private" ]; then cp -R "$REPO/worldlines/private" "$TMP/wl/private"; fi
( cd "$TMP/wl/ui/app" && WL_PLAYER=off node build.mjs >/dev/null )

H="$TMP/home"; mkdir -p "$H/.worldlines/souls" "$H/.neonrp" "$H/templates" "$H/store" "$H/worldlines-assets"
cp -R "$REPO/worldlines/templates/." "$H/templates/"
printf '{"llm": {"model_ref": "mock"}, "models": {"mock": {"provider": "openai", "model": "mock-1", "base_url": "http://127.0.0.1:%s/v1", "api_key": "mock"}}}\n' "$AI_PORT" > "$H/.neonrp/config.json"
. "$REPO/worldlines/ui/e2e-ports.sh"
wl_ports_free "$PORT" "$AI_PORT" || exit 3
export NEONRP_STRICT_PORT=1
python3 "$REPO/worldlines/ui/player/e2e/mock_ai.py" --port "$AI_PORT" > "$TMP/mock.log" 2>&1 & MOCK=$!
wl_wait_server "http://127.0.0.1:$AI_PORT/_mock/state" "$MOCK" "$TMP/mock.log" || exit 3
# 内置模板(只读)在 templates/,复制出来的进 store/(可写)
( cd "$REPO" && exec env HOME="$H" NEONRP_TEMPLATE_PATH="$H/templates:$H/store" NEONRP_TEMPLATE_WRITE_DIR="$H/store" WORLDLINES_ASSETS_DIR="$H/worldlines-assets" \
    NEONRP_DISABLE_CLAUDE_CODE=1 NEONRP_SPA_DIR="$TMP/wl/ui/dist-local" $NEONRP web --port "$PORT" --no-browser ) > "$TMP/engine.log" 2>&1 & SRV=$!
wl_wait_engine "$PORT" "$SRV" "$TMP/engine.log" 120 || exit 3

cd "$HERE"
WL_PB_BASE="http://127.0.0.1:$PORT" WL_PB_HOME="$H" WL_PB_SHOTS="${WL_PB_SHOTS:-$REPO/docs/playrecords/builder-toggle-1025}" \
  npx playwright test -c playwright.config.ts "$@" || { tail -40 "$TMP/engine.log"; exit 1; }
