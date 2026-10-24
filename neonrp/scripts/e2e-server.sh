#!/usr/bin/env bash
# E2E 引擎(docs/WEBUI-UNIFICATION.md T2.5):隔离 HOME 起 neonrp web,
# 测试怎么折腾都碰不到真实的 ~/.worldlines / ~/.neonrp。
# Playwright 的 webServer 调这个;端口 8799,退出时临时 HOME 自清。
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${E2E_PORT:-8799}"

# 兜底:上次被直接 kill -9 的(trap 跑不了)留下的临时 HOME,超过 3 小时的清掉(一次 e2e 十分钟上下)
find /tmp -maxdepth 1 -name 'neonrp-e2e-home.*' -type d -mmin +180 -exec rm -rf {} + 2>/dev/null || true
FAKE_HOME="$(mktemp -d /tmp/neonrp-e2e-home.XXXXXX)"
trap 'rm -rf "$FAKE_HOME"' EXIT
mkdir -p "$FAKE_HOME/.worldlines" "$FAKE_HOME/.neonrp"
# 模板库用一份临时副本:素材上传等用例会写模板目录,绝不能写进仓库的模板目录
# (10-05 去重:模板只有一个家 worldlines/templates;原 examples/templates 已并入)
mkdir -p "$FAKE_HOME/templates"
for tdir in "$REPO_ROOT/worldlines/templates" "$REPO_ROOT/../worldlines/templates"; do  # dev repo · public repo(neonrp/ 与 worldlines/ 平级)
  [ -d "$tdir" ] && { cp -R "$tdir/." "$FAKE_HOME/templates/"; break; }
done
mkdir -p "$FAKE_HOME/worldlines-assets"

# 端口防护(worldlines/ui/e2e-ports.sh):端口上已经有别人的服务就不起;引擎只绑这个端口(被占就退出,不悄悄换端口)
PORTS_SH="$REPO_ROOT/worldlines/ui/e2e-ports.sh"; [ -f "$PORTS_SH" ] || PORTS_SH="$REPO_ROOT/../worldlines/ui/e2e-ports.sh"  # dev repo · public repo
. "$PORTS_SH"
wl_ports_free "$PORT" || exit 3
export NEONRP_STRICT_PORT=1
echo "e2e engine: HOME=$FAKE_HOME port=$PORT"
cd "$REPO_ROOT"
# 只给引擎进程换 HOME;uv 用项目 .venv,不受影响
# NEONRP_DISABLE_CLAUDE_CODE:e2e 绝不静默烧开发者的 claude CLI 额度
# 不用 exec:exec 会把这个 shell 换成引擎进程,上面的 trap 就永远不跑 —— 每跑一次 e2e 漏一个临时 HOME
# (10-08 查到 /tmp/neonrp-e2e-home.* 攒了 98 个 · 8.3 GB)。前台跑引擎,收到 TERM / INT 转给它,退出时清 HOME
env HOME="$FAKE_HOME" NEONRP_TEMPLATE_PATH="$FAKE_HOME/templates" NEONRP_TEMPLATE_WRITE_DIR="$FAKE_HOME/templates" \
  WORLDLINES_ASSETS_DIR="$FAKE_HOME/worldlines-assets" NEONRP_DISABLE_CLAUDE_CODE=1 uv run neonrp web --port "$PORT" --no-browser &
ENGINE=$!
trap 'kill -TERM "$ENGINE" 2>/dev/null || true; wait "$ENGINE" 2>/dev/null || true; rm -rf "$FAKE_HOME"' EXIT   # set -e 下 wait 返回非零也要接着删
trap 'exit 0' TERM INT
wait "$ENGINE"
