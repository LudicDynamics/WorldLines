#!/usr/bin/env bash
# 一键 E2E:对隔离引擎跑 Playwright 全部用例。
# S3.2 去壳后 UI 源码住壳仓(LudicDynamics/WorldLines);本脚本按序解析:
#   ①$WORLDLINES_UI_DIR ②本仓 worldlines/ui(10-02 起产品在 NeonRP 里开发) ③同级 ../Publishment/WorldLines/ui(旧)
#   ③CI 由 test.yml checkout 到 shell-repo/ui 并设 ①。
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

UI_DIR="${WORLDLINES_UI_DIR:-}"
if [ -z "$UI_DIR" ]; then
  for cand in "$REPO_ROOT/worldlines/ui" "$REPO_ROOT/../worldlines/ui" "$REPO_ROOT/../Publishment/WorldLines/ui" "$REPO_ROOT/ui"; do  # dev repo · public repo(neonrp/ 与 worldlines/ 平级)
    if [ -f "$cand/package.json" ]; then UI_DIR="$cand"; break; fi
  done
fi
if [ -z "$UI_DIR" ] || [ ! -f "$UI_DIR/package.json" ]; then
  echo "e2e: 找不到 WorldLines 壳的 ui/。设 WORLDLINES_UI_DIR 或把壳仓放在 ../Publishment/WorldLines" >&2
  exit 1
fi
echo "e2e: UI_DIR=$UI_DIR"

# 刷新引擎内置 SPA 兜底(webui/spa),同一份 UI 源码构建。
WORLDLINES_UI_DIR="$UI_DIR" bash "$REPO_ROOT/scripts/sync_play_ui.sh"

# Playwright 的 webServer 需要能找到引擎仓的 e2e-server(壳仓 config 读此 env)。
export NEONRP_E2E_SERVER="$REPO_ROOT/scripts/e2e-server.sh"
# 两仓分离(形态 B)后引擎瘦、只认 NEONRP_SPA_DIR(不再自动服务 webui/spa)。
# 指到刚构建的 dist-local,e2e-server 起的引擎经由此环境变量继承,否则 /local 返 404。
export NEONRP_SPA_DIR="$UI_DIR/dist-local"
cd "$UI_DIR"
npx playwright test "$@"
