#!/usr/bin/env bash
# 「在浏览器里玩」e2e:构建 Hub 静态站(ai / auth / billing 指到本机的假服务)→ Chromium + WebKit 各跑一遍。
#   bash worldlines/ui/e2e-play/run.sh                       # 完整版(线上就是它)
#   WL_PLAY_PUBLIC_ONLY=1 bash worldlines/ui/e2e-play/run.sh # 只带开源导出的部分
#   WL_PLAY_SHOTS=<目录> 截图放这里(默认 worldlines/ui/test-results/play-shots)· 其余参数原样给 playwright(--project webkit …)
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../../.." && pwd)"
SITE="${WL_PLAY_SITE:-$(mktemp -d)/site}"
FAKE=http://127.0.0.1:8611
( cd "$REPO" && uv run python worldlines/ui/app/hub/build_static.py --out "$SITE" --play --bench --player-worktree --no-packages \
    --ai "$FAKE/v1" --auth "$FAKE" --billing "$FAKE" --platform "$FAKE" ${WL_PLAY_PUBLIC_ONLY:+--public-only} )
cd "$HERE"
[ -d ../node_modules/@playwright/test ] || ( cd .. && npm ci --no-audit --no-fund )
WL_PLAY_SITE="$SITE" npx playwright test -c playwright.config.ts "$@"
