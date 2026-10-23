"""测试台「本轮编排」显示时间预算的四个字段(lead 10-19:玩家画面不加提示,只放调试页)——
beat.truncated / beat.advance_deferred 两个标记、主持每次调用的首字毫秒(beat.calls[].first_ms)、这一回合的模型调用表(trace.timing.llm_calls)。
worldlines/ui/app/real/bench.js 的 benchOrch 在 node vm 里跑(tests/bench_orch_timing.mjs);engine.js 把 beat 的两个标记带进 s.rounds。"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
REAL = ROOT / "worldlines" / "ui" / "app" / "real"


@pytest.fixture(scope="module")
def out() -> dict[str, str]:
    node = shutil.which("node")
    if not node:
        pytest.skip("node needed")
    r = subprocess.run([node, str(ROOT / "tests" / "bench_orch_timing.mjs"), str(REAL / "bench.js")], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_flags_for_the_beat(out: dict[str, str]) -> None:
    h = out["html"]
    assert "半句" in h and "beat.truncated" in h
    assert "推进延后" in h and "beat.advance_deferred = world:settled" in h


def test_host_calls_first_chunk_ms(out: dict[str, str]) -> None:
    calls = re.search(r"<table class=\"btab\" data-bcalls>(.*?)</table>", out["html"], re.S)
    assert calls, "a table of the host's calls"
    rows = re.findall(r"<tr><td>(.*?)</td><td class=\"mono\">(.*?)</td><td class=\"mono\">(.*?)</td><td>(.*?)</td></tr>", calls.group(1))
    assert rows[0][:3] == ("host", "12.3 s", "19.8 s") and "半句" in rows[0][3]
    assert rows[1][:3] == ("si-xiulian0001", "2.1 s", "6.3 s") and "半句" not in rows[1][3]


def test_turn_llm_calls_table(out: dict[str, str]) -> None:
    t = re.search(r"<table class=\"btab\" data-bllm>(.*?)</table>", out["html"], re.S)
    assert t, "the turn's llm_calls table"
    assert "这一回合 2 次" in out["html"]
    body = t.group(1)
    assert body.count("<tr>") == 3  # header + two calls
    assert "plan" in body and "12.3 s" in body and "84" in body and "model=deepseek-v4" in body
    assert "resolve" in body and "0.9 s" in body and "4.1 s" in body


def test_tui_has_the_same(out: dict[str, str]) -> None:
    t = out["tui"]
    for s in ("半句", "推进延后", "主持调用", "模型调用", "12.3 s", "timing.llm_calls"):
        assert s in t, s


def test_old_engine_shows_none_of_it(out: dict[str, str]) -> None:
    p = out["plain"]
    assert "推进延后" not in p and "beat.truncated" not in p and "data-bllm" not in p
    assert "data-bcalls" in p and "—" in p  # the call is listed; no first-chunk time recorded


def test_engine_passes_the_flags_into_rounds() -> None:
    src = (REAL / "engine.js").read_text(encoding="utf-8")
    assert "truncated: !!(b && b.truncated)" in src and "deferred: (b && b.advance_deferred) || null" in src
    assert "timing: d.timing || null" in src
