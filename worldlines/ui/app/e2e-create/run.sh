#!/usr/bin/env bash
# 创作台「用一句话说」e2e(10-18):隔离 HOME + 假模型(fake_llm.py)+ 本机引擎(界面构建在临时目录,不动 dist-local),Playwright Chromium。
#   bash worldlines/ui/app/e2e-create/run.sh
#   WL_CA_SHOTS=<目录> 截图(默认 docs/playrecords/create-agent-1018/)· WL_CA_PORT(默认 8907)· WL_CA_AI_PORT(默认 8908)
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../../../.." && pwd)"
PORT="${WL_CA_PORT:-8907}"
AI_PORT="${WL_CA_AI_PORT:-8908}"
TMP="$(mktemp -d "${TMPDIR:-/tmp}/wl-ca-e2e.XXXXXX")"
cleanup() { kill "${SRV:-}" "${MOCK:-}" 2>/dev/null || true; wait 2>/dev/null || true; rm -rf "$TMP"; }
trap cleanup EXIT

mkdir -p "$TMP/wl/ui"
cp -R "$REPO/worldlines/ui/app" "$TMP/wl/ui/app"
( cd "$TMP/wl/ui/app" && WL_PLAYER=off node build.mjs >/dev/null )

H="$TMP/home"; mkdir -p "$H/.neonrp" "$H/templates" "$H/worldlines-assets"
cp -R "$REPO/worldlines/templates/stoneford-town.template" "$H/templates/"
printf '{"llm": {"model_ref": "mock"}, "create_provider": "mock", "models": {"mock": {"provider": "openai", "model": "mock-1", "base_url": "http://127.0.0.1:%s/v1", "api_key": "mock"}}}\n' "$AI_PORT" > "$H/.neonrp/config.json"
. "$REPO/worldlines/ui/e2e-ports.sh"
wl_ports_free "$PORT" "$AI_PORT" || exit 3
export NEONRP_STRICT_PORT=1
python3 "$HERE/fake_llm.py" --port "$AI_PORT" > "$TMP/mock.log" 2>&1 & MOCK=$!
wl_wait_server "http://127.0.0.1:$AI_PORT/_mock/state" "$MOCK" "$TMP/mock.log" || exit 3
( cd "$REPO" && exec env HOME="$H" NEONRP_TEMPLATE_PATH="$H/templates" NEONRP_TEMPLATE_WRITE_DIR="$H/templates" WORLDLINES_ASSETS_DIR="$H/worldlines-assets" \
    NEONRP_DISABLE_CLAUDE_CODE=1 NEONRP_SPA_DIR="$TMP/wl/ui/dist-local" uv run neonrp web --port "$PORT" --no-browser ) > "$TMP/engine.log" 2>&1 & SRV=$!
wl_wait_engine "$PORT" "$SRV" "$TMP/engine.log" 120 || exit 3

cd "$HERE"
WL_CA_BASE="http://127.0.0.1:$PORT" WL_CA_AI="http://127.0.0.1:$AI_PORT" WL_CA_HOME="$H" WL_CA_SHOTS="${WL_CA_SHOTS:-$REPO/docs/playrecords/create-agent-1018}" \
  npx playwright test -c playwright.config.ts "$@" || { tail -40 "$TMP/engine.log"; exit 1; }
