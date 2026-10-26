#!/usr/bin/env bash
# 工作台「本机 Claude Code / Codex」当创作后端 + 创作台模型下拉 e2e(10-26 · C2):隔离 HOME + 假模型(e2e-create/fake_llm.py,开机用,不被调)
# + 假的 claude / codex(tests/fixtures/fake_agent_cli.py:吐真 CLI 的 JSON 事件流,经真的 neonrp mcp serve-create 改文件;不登录、不花额度)。
#   bash worldlines/ui/app/e2e-create-agent/run.sh
#   WL_AG_SHOTS=<目录> 截图(默认 docs/playrecords/create-mcp-1026/)· WL_AG_PORT(默认 8875)· WL_AG_AI_PORT(默认 8876)
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../../../.." && pwd)"
PORT="${WL_AG_PORT:-8875}"
AI_PORT="${WL_AG_AI_PORT:-8876}"
PY="${WL_AG_PYTHON:-$REPO/.venv/bin/python}"
TMP="$(mktemp -d "${TMPDIR:-/tmp}/wl-ag-e2e.XXXXXX")"
cleanup() { kill "${SRV:-}" "${MOCK:-}" 2>/dev/null || true; wait 2>/dev/null || true; rm -rf "$TMP"; }
trap cleanup EXIT

mkdir -p "$TMP/wl/ui"
cp -R "$REPO/worldlines/ui/app" "$TMP/wl/ui/app"
( cd "$TMP/wl/ui/app" && WL_PLAYER=off node build.mjs >/dev/null )

# 假 CLI:同一个脚本,名字定方言
mkdir -p "$TMP/bin"
for n in claude codex; do { printf '#!%s\n' "$PY"; cat "$REPO/tests/fixtures/fake_agent_cli.py"; } > "$TMP/bin/$n"; chmod +x "$TMP/bin/$n"; done

H="$TMP/home"; mkdir -p "$H/.neonrp" "$H/templates" "$H/worldlines-assets"
cp -R "$REPO/worldlines/templates/stoneford-town.template" "$H/templates/"
# 两个配好 key 的模型(一个 OpenAI 兼容的假模型、一个 Anthropic 的假 key —— 只给下拉列出来,不会被调)
printf '{"llm": {"model_ref": "mock"}, "models": {"mock": {"provider": "openai", "model": "mock-1", "base_url": "http://127.0.0.1:%s/v1", "api_key": "mock"}, "claude-test": {"provider": "anthropic", "model": "claude-test", "api_key": "not-a-key"}}}\n' "$AI_PORT" > "$H/.neonrp/config.json"
. "$REPO/worldlines/ui/e2e-ports.sh"
wl_ports_free "$PORT" "$AI_PORT" || exit 3
export NEONRP_STRICT_PORT=1
"$PY" "$HERE/../e2e-create/fake_llm.py" --port "$AI_PORT" > "$TMP/mock.log" 2>&1 & MOCK=$!
wl_wait_server "http://127.0.0.1:$AI_PORT/_mock/state" "$MOCK" "$TMP/mock.log" || exit 3
( cd "$REPO" && exec env HOME="$H" PATH="$TMP/bin:$PATH" FAKE_AGENT_LOG="$TMP/agent.log" NEONRP_TEMPLATE_PATH="$H/templates" NEONRP_TEMPLATE_WRITE_DIR="$H/templates" \
    WORLDLINES_ASSETS_DIR="$H/worldlines-assets" NEONRP_SPA_DIR="$TMP/wl/ui/dist-local" ANTHROPIC_API_KEY=must-not-reach-the-agent \
    "$PY" -m neonrp web --port "$PORT" --no-browser ) > "$TMP/engine.log" 2>&1 & SRV=$!
wl_wait_engine "$PORT" "$SRV" "$TMP/engine.log" 120 || exit 3

cd "$HERE"
WL_AG_BASE="http://127.0.0.1:$PORT" WL_AG_HOME="$H" WL_AG_LOG="$TMP/agent.log" WL_AG_SHOTS="${WL_AG_SHOTS:-$REPO/docs/playrecords/create-mcp-1026}" \
  npx playwright test -c playwright.config.ts "$@" || { tail -40 "$TMP/engine.log"; exit 1; }
