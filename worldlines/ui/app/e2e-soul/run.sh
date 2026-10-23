#!/usr/bin/env bash
# 角色编排台 + 世界编排台 e2e(10-16 · 10-17 orchbench.spec):隔离 HOME + 假模型 + 本机引擎(界面构建在临时目录,不动 dist-local),Playwright Chromium 1366×900。
#   bash worldlines/ui/app/e2e-soul/run.sh
#   WL_SOUL_SHOTS=<目录> 截图放这里(默认 docs/playrecords/soulorch-1016/)· WL_SOUL_PORT(默认 8796)· WL_SOUL_AI_PORT(默认 8629)
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../../../.." && pwd)"
PORT="${WL_SOUL_PORT:-8796}"
AI_PORT="${WL_SOUL_AI_PORT:-8629}"
TMP="$(mktemp -d "${TMPDIR:-/tmp}/wl-soul-e2e.XXXXXX")"
cleanup() { kill "${SRV:-}" "${MOCK:-}" 2>/dev/null || true; wait 2>/dev/null || true; rm -rf "$TMP"; }
trap cleanup EXIT

# 界面:拷一份 worldlines/ui/app(+ 私有层界面)到临时目录再构建,产物 = $TMP/wl/ui/dist-local
mkdir -p "$TMP/wl/ui"
cp -R "$REPO/worldlines/ui/app" "$TMP/wl/ui/app"
if [ -d "$REPO/worldlines/private" ]; then cp -R "$REPO/worldlines/private" "$TMP/wl/private"
elif [ -n "${NEONRP_PRIVATE_DIR:-}" ] && [ -d "$NEONRP_PRIVATE_DIR/ui" ]; then mkdir -p "$TMP/wl/private" && cp -R "$NEONRP_PRIVATE_DIR/ui" "$TMP/wl/private/ui"; fi   # 私有层不在 worldlines/private:按引擎用的那份
( cd "$TMP/wl/ui/app" && if [ -n "${WL_SOUL_PLAYER:-}" ]; then cp -R "$REPO/worldlines/ui/player" "$TMP/wl/ui/player" && ln -s "$REPO/worldlines/ui/node_modules" "$TMP/wl/ui/node_modules" && node build.mjs >/dev/null; else WL_PLAYER=off node build.mjs >/dev/null; fi )   # WL_SOUL_PLAYER=1:连小手机 chat.html 一起构建(worldsel.spec 的直聊)

H="$TMP/home"; mkdir -p "$H/.worldlines/souls" "$H/.neonrp" "$H/templates" "$H/worldlines-assets"
cp -R "$REPO/worldlines/templates/." "$H/templates/"
# 角色库里一个没 link 任何世界的独立角色
A="$H/.worldlines/souls/awu"; mkdir -p "$A/long-term-memo"
printf '{"schema_version": 1, "sid": "awu", "name": "Awu", "name_local": "阿雾"}\n' > "$A/soul.json"
printf '码头卖鱼的姑娘,说话很冲。\n' > "$A/soul.md"
printf '去年冬天你帮她修过船。\n' > "$A/long-term-memo/old.md"
printf '{"llm": {"model_ref": "mock"}, "models": {"mock": {"provider": "openai", "model": "mock-1", "base_url": "http://127.0.0.1:%s/v1", "api_key": "mock"}}}\n' "$AI_PORT" > "$H/.neonrp/config.json"
. "$REPO/worldlines/ui/e2e-ports.sh"   # 端口防护:已经有别人的服务就不跑;引擎只绑这个端口
wl_ports_free "$PORT" "$AI_PORT" || exit 3
export NEONRP_STRICT_PORT=1
python3 "$REPO/worldlines/ui/player/e2e/mock_ai.py" --port "$AI_PORT" > "$TMP/mock.log" 2>&1 & MOCK=$!
wl_wait_server "http://127.0.0.1:$AI_PORT/_mock/state" "$MOCK" "$TMP/mock.log" || exit 3
( cd "$REPO" && exec env HOME="$H" NEONRP_TEMPLATE_PATH="$H/templates" NEONRP_TEMPLATE_WRITE_DIR="$H/templates" WORLDLINES_ASSETS_DIR="$H/worldlines-assets" \
    NEONRP_DISABLE_CLAUDE_CODE=1 NEONRP_SPA_DIR="$TMP/wl/ui/dist-local" uv run neonrp web --port "$PORT" --no-browser ) > "$TMP/engine.log" 2>&1 & SRV=$!
wl_wait_engine "$PORT" "$SRV" "$TMP/engine.log" 120 || exit 3

cd "$HERE"
WL_SOUL_PRIVATE="$([ -d "$TMP/wl/private" ] && echo 1 || true)" WL_SOUL_BASE="http://127.0.0.1:$PORT" WL_SOUL_HOME="$H" WL_SOUL_SHOTS="${WL_SOUL_SHOTS:-$REPO/docs/playrecords/soulorch-1016}" \
  npx playwright test -c playwright.config.ts "$@" || { tail -40 "$TMP/engine.log"; exit 1; }
