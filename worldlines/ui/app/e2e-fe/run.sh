#!/usr/bin/env bash
# 前端台 e2e(10-17 · 三个重前端工作台 + 新建):隔离 HOME + 假模型 + 本机引擎(界面连同标准前端 / 小手机构建在临时目录,不动 dist-local),
# Playwright Chromium 1366×900。Godot 那页的冒烟要本机有 Godot(GODOT= / PATH / /Applications/Godot.app),没有就跳过那一条。
#   bash worldlines/ui/app/e2e-fe/run.sh
#   WL_FE_SHOTS=<目录> 截图(默认 docs/playrecords/frontends-1017/)· WL_FE_PORT(默认 8799)· WL_FE_AI_PORT(默认 8643)
#   WL_FE_SERVE=1 只把引擎起好、不跑用例(手动看:打印地址,Ctrl-C 收)
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../../../.." && pwd)"
PORT="${WL_FE_PORT:-8799}"
AI_PORT="${WL_FE_AI_PORT:-8643}"
TMP="$(mktemp -d "${TMPDIR:-/tmp}/wl-fe-e2e.XXXXXX")"
cleanup() { kill "${SRV:-}" "${MOCK:-}" 2>/dev/null || true; wait 2>/dev/null || true; rm -rf "$TMP"; }
trap cleanup EXIT

mkdir -p "$TMP/wl/ui"
cp -R "$REPO/worldlines/ui/app" "$TMP/wl/ui/app"
cp -R "$REPO/worldlines/ui/player" "$TMP/wl/ui/player"
ln -s "$REPO/worldlines/ui/node_modules" "$TMP/wl/ui/node_modules"
if [ -d "$REPO/worldlines/private" ]; then cp -R "$REPO/worldlines/private" "$TMP/wl/private"
elif [ -n "${NEONRP_PRIVATE_DIR:-}" ] && [ -d "$NEONRP_PRIVATE_DIR/ui" ]; then mkdir -p "$TMP/wl/private" && cp -R "$NEONRP_PRIVATE_DIR/ui" "$TMP/wl/private/ui"; fi
( cd "$TMP/wl/ui/app" && node build.mjs >/dev/null )

H="$TMP/home"; mkdir -p "$H/.worldlines/souls" "$H/.neonrp" "$H/templates" "$H/worldlines-assets"
cp -R "$REPO/worldlines/templates/." "$H/templates/"
printf '{"llm": {"model_ref": "mock"}, "models": {"mock": {"provider": "openai", "model": "mock-1", "base_url": "http://127.0.0.1:%s/v1", "api_key": "mock"}}}\n' "$AI_PORT" > "$H/.neonrp/config.json"
. "$REPO/worldlines/ui/e2e-ports.sh"   # 端口防护:已经有别人的服务就不跑;引擎只绑这个端口
wl_ports_free "$PORT" "$AI_PORT" || exit 3
export NEONRP_STRICT_PORT=1
python3 "$REPO/worldlines/ui/player/e2e/mock_ai.py" --port "$AI_PORT" > "$TMP/mock.log" 2>&1 & MOCK=$!
wl_wait_server "http://127.0.0.1:$AI_PORT/_mock/state" "$MOCK" "$TMP/mock.log" || exit 3
( cd "$REPO" && exec env HOME="$H" NEONRP_TEMPLATE_PATH="$H/templates" NEONRP_TEMPLATE_WRITE_DIR="$H/templates" WORLDLINES_ASSETS_DIR="$H/worldlines-assets" \
    NEONRP_DISABLE_CLAUDE_CODE=1 NEONRP_SPA_DIR="$TMP/wl/ui/dist-local" uv run neonrp web --port "$PORT" --no-browser ) > "$TMP/engine.log" 2>&1 & SRV=$!
wl_wait_engine "$PORT" "$SRV" "$TMP/engine.log" 120 || exit 3

if [ -n "${WL_FE_SERVE:-}" ]; then echo "engine http://127.0.0.1:$PORT  (HOME=$H · mock ai :$AI_PORT · log $TMP/engine.log)"; wait "$SRV"; exit 0; fi
cd "$HERE"
WL_FE_BASE="http://127.0.0.1:$PORT" WL_FE_AI="http://127.0.0.1:$AI_PORT" WL_FE_HOME="$H" WL_FE_SHOTS="${WL_FE_SHOTS:-$REPO/docs/playrecords/frontends-1017}" \
  npx playwright test -c playwright.config.ts "$@" || { tail -40 "$TMP/engine.log"; exit 1; }
