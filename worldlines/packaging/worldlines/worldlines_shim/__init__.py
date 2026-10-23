"""WorldLines launcher — owns the SPA, delegates the engine to neonrp.

两仓彻底分离（2026-09）：neonrp 引擎是**瘦 wheel、不含 SPA**；SPA 归
**worldlines** 自带。本启动器在把控制权交给 neonrp 的 web launcher 之前，
先解析 SPA 目录并写好 `NEONRP_SPA_DIR`，于是 `worldlines` 开箱即服务
`/local`——无需外部 env。neonrp 侧完全不改（只认 `NEONRP_SPA_DIR` 这个缝）。

SPA 解析顺序：
  1. 已显式设了合法 `NEONRP_SPA_DIR` → 原样尊重（外部覆盖优先）。
  2. wheel 内自带：`worldlines_shim/spa/`（发布态，随包分发）。
  3. dev 回退：从本文件向上找到仓库里的 `ui/dist-local`（源码跑）。
"""
from __future__ import annotations

import os
from pathlib import Path


def _resolve_spa() -> Path | None:
    here = Path(__file__).resolve().parent
    # 2) 随包自带的 SPA（发布 wheel）
    bundled = here / "spa"
    if (bundled / "index.html").is_file():
        return bundled
    # 3) dev 回退：向上任一层含 ui/dist-local/index.html
    for parent in [here, *here.parents]:
        cand = parent / "ui" / "dist-local"
        if (cand / "index.html").is_file():
            return cand
    return None


def _ensure_spa_dir() -> None:
    env = os.environ.get("NEONRP_SPA_DIR")
    if env and (Path(env) / "index.html").is_file():
        return  # 尊重外部显式覆盖
    spa = _resolve_spa()
    if spa is not None:
        os.environ["NEONRP_SPA_DIR"] = str(spa)


def main():
    """Console-script 入口 `worldlines`：先备好 SPA，再运行 neonrp 引擎。"""
    _ensure_spa_dir()
    from neonrp.cli import worldlines_cli
    worldlines_cli()
