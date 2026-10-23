"""Full historical log of one real run (「我要看到所有的细节」): every world-side LLM call with its whole
system prompt, user block and raw reply; the Jev plan; the souls' replies and judgments; the gate; tool returns (dice /
referee); verify (accepted / refused); apply; the run_state before → after. Writes docs/playrecords/fulllog-<label>/
{fulllog.json, fulllog.md, fulllog.html}.

    uv run python benchmarks/fulllog.py --label 1001 [--script c4]
"""
from __future__ import annotations

import argparse
import html
import json
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[0]))
import common as C  # noqa: E402

SCRIPTS = {
    "en": [  # the 10-01 English smoke: the road never started and the narrator invented bandits at the gate
        ("E1", 'I tell Elena: "I\'m going to Bistone to find Rowan. Come with me." We set out.'),
        ("E2", "We keep going toward Bistone."),
        ("E3", "I draw my sword and charge the bandits."),
        ("E3+", "Keep fighting."),
        ("E4", "Keep going into Bistone."),
    ],
    "c4": [
        ("C4a", "我对艾琳娜说:「我要去碧石镇找罗文,你一起来。」我们出发。"),
        ("C4b", "我们继续赶路,往碧石镇去。"),
        ("C4c", "山贼拦路,我拔剑迎上去。"),
        ("C4c+", "继续打。"),  # repeats while the combat layer is on (≤ 4)
        ("C4d", "继续赶路,进碧石镇。"),
        ("C4e", "到了碧石镇,我去找罗文。"),
    ],
}

CSS = """:root{--bg:#EEF1F2;--paper:#fff;--ink:#1B2229;--ink-2:#4B5760;--ink-3:#7A8791;--line:#D5DBDF;--llm:#B7791F;--llm-bg:#FBEFD6;--jev:#7C3AAD;--jev-bg:#EDE3F7;--mono:"JetBrains Mono",ui-monospace,Menlo,monospace;--sans:"Noto Sans SC","PingFang SC",system-ui,sans-serif;--serif:"Noto Serif SC","Songti SC",serif}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#0E1316;--paper:#151B20;--ink:#E6EAED;--ink-2:#AEB8C0;--ink-3:#7C8891;--line:#26303A;--llm:#E0A33A;--llm-bg:#3A2A10;--jev:#B78CE6;--jev-bg:#2C1F3E}}
:root[data-theme="dark"]{--bg:#0E1316;--paper:#151B20;--ink:#E6EAED;--ink-2:#AEB8C0;--ink-3:#7C8891;--line:#26303A;--llm:#E0A33A;--llm-bg:#3A2A10;--jev:#B78CE6;--jev-bg:#2C1F3E}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font-family:var(--sans);font-size:14.5px;line-height:1.65}.wrap{max-width:1100px;margin:0 auto;padding:32px 16px 80px}
h1{font-family:var(--serif);font-size:28px;margin:0}h2{font-family:var(--serif);font-size:20px;margin:0 0 8px}h3{font-size:13px;font-family:var(--mono);letter-spacing:.06em;text-transform:uppercase;color:var(--ink-3);margin:16px 0 6px}
.turn{background:var(--paper);border:1px solid var(--line);border-radius:6px;padding:14px 16px;margin:18px 0}.state{font-family:var(--mono);font-size:12px;color:var(--ink-2);background:var(--bg);border-radius:4px;padding:6px 10px;margin:6px 0;white-space:pre-wrap}
pre{font-family:var(--mono);font-size:11.5px;line-height:1.5;background:var(--bg);border:1px solid var(--line);border-radius:4px;padding:8px 10px;overflow-x:auto;white-space:pre-wrap;margin:6px 0;max-height:520px;overflow-y:auto}pre.reply{max-height:none;border-color:var(--llm)}
details{margin:4px 0}summary{cursor:pointer;font-family:var(--mono);font-size:12px;color:var(--ink-2)}.call{border-left:3px solid var(--llm);padding-left:10px;margin:10px 0}.call .hd{font-family:var(--mono);font-size:12px;color:var(--ink-3);margin:4px 0}
.pill{display:inline-block;font-family:var(--mono);font-size:11px;padding:1px 7px;border-radius:3px}.pill.l{background:var(--llm-bg);color:var(--llm)}.pill.j{background:var(--jev-bg);color:var(--jev)}
.narr{white-space:pre-wrap;line-height:1.7;padding:6px 10px;border-left:3px solid var(--line);margin:4px 0}.rep{margin:6px 0}.small{font-size:12px;color:var(--ink-3)}.k{font-family:var(--mono);font-size:.9em}ul{margin:4px 0;padding-left:18px}"""

_CALLS: list[dict[str, Any]] = []


def _label_of(system: str) -> str:
    if "# 战斗裁判" in system:
        return "combat-layer"
    if "三种调用场景" in system or "规则裁判" in system[:400]:
        return "referee"
    if "# 地穴主持" in system:
        return "dungeon-layer"
    return "narrator"


def install_recorder() -> None:
    from neonrp.core import turn_v3
    from neonrp.core.config import load_config, resolve_provider
    from neonrp.core.llm import get_adapter_from_config

    def factory(root: Path, provider: str | None) -> Any:
        config = load_config(root, include_user_config=True)
        pc = resolve_provider(config, None, provider)
        real = get_adapter_from_config(pc)

        class Rec:
            def __getattr__(self, k: str) -> Any:
                return getattr(real, k)

            def chat(self, messages: list[Any], tools: Any = None) -> Any:
                t0 = time.perf_counter()
                res = real.chat(messages, tools) if tools is not None else real.chat(messages)
                text = (getattr(getattr(res, "message", None), "content", None) or "")
                sysm = next((m.content for m in messages if m.role == "system"), "")
                _CALLS.append({"label": _label_of(sysm), "ms": round((time.perf_counter() - t0) * 1000),
                               "messages": [{"role": m.role, "content": m.content or ""} for m in messages],
                               "reply": text, "usage": dict(getattr(res, "usage", None) or {})})
                return res

        return Rec()

    turn_v3.ADAPTER_FACTORY = factory


def snapshot(root: Path) -> dict[str, Any]:
    rs = json.loads((root / "game" / "meta" / "run_state.json").read_text(encoding="utf-8"))
    stats = json.loads((root / "game" / "player" / "stats.json").read_text(encoding="utf-8"))
    loc = rs.get("location") or {}
    return {"location": f"{loc.get('node_id')}/{loc.get('subnode_id') or loc.get('node')}", "time": rs.get("time"), "travel": rs.get("travel"),
            "mode": rs.get("mode"), "last_combat": rs.get("last_combat"), "player_hp": (stats.get("hp") or {}).get("current")}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", default="1001")
    ap.add_argument("--script", default="c4")
    ap.add_argument("--arm", default="v3-adv")
    args = ap.parse_args()
    from consistency import force_bandits  # noqa: E402  (benchmarks/suites on sys.path below)

    install_recorder()
    g = C.Game(args.arm, f"fulllog-{args.label}")
    force_bandits(g.root)
    from neonrp.core.modes import read_mode
    from neonrp.core.orchestration_trace import read_turn_traces

    turns: list[dict[str, Any]] = []
    print(f"== fulllog {args.label} @ {g.root}", flush=True)

    def play(tid: str, text: str) -> None:
        before = snapshot(g.root)
        _CALLS.clear()
        t = g.play(tid, text)
        tr = (read_turn_traces(g.root, g.session.branch, last=1) or [{}])[0]
        after = snapshot(g.root)
        ap_ = tr.get("apply") or {}
        rec = {"id": tid, "input": text, "ms": t.ms, "narration": t.narration, "options": ap_.get("options"), "panels": ap_.get("panels"),
               "plan": tr.get("plan"), "reports": ap_.get("reports"), "spans": tr.get("spans"),
               "calls": list(_CALLS), "tool_returns": ap_.get("tool_returns"), "proposals": ap_.get("proposals"), "annotated": ap_.get("annotated"),
               "verify": {"accepted": ap_.get("applied"), "refused": ap_.get("refused"), "repaired": ap_.get("repaired")},
               "before": before, "after": after}
        turns.append(rec)
        print(f"  {tid} {t.ms/1000:5.1f}s calls={[c['label'] for c in _CALLS]} loc={after['location']} mode={(after['mode'] or {}).get('name')} hp={after['player_hp']}", flush=True)

    for tid, text in SCRIPTS[args.script]:
        if tid.endswith("+"):
            n = 0
            while (read_mode(g.root) or {}).get("name") == "combat" and n < 4:
                n += 1
                play(f"{tid}{n}", text)
            continue
        play(tid, text)
    out = Path("docs/playrecords") / f"fulllog-{args.label}"
    out.mkdir(parents=True, exist_ok=True)
    (out / "fulllog.json").write_text(json.dumps({"label": args.label, "arm": args.arm, "world": C.WORLD, "preset": C.PRESET, "turns": turns}, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "fulllog.md").write_text(render_md(turns, args.label), encoding="utf-8")
    (out / "fulllog.html").write_text(render_html(turns, args.label), encoding="utf-8")
    print(f"→ {out}", flush=True)


def _ptext(v: Any) -> str:
    from neonrp.core.panels import as_text

    return as_text(v)


def _j(x: Any, n: int = 4000) -> str:
    s = json.dumps(x, ensure_ascii=False, indent=1)
    return s if len(s) <= n else s[:n] + f"\n… ({len(s)} chars)"


def render_md(turns: list[dict[str, Any]], label: str) -> str:
    L = [f"# 完整历史日志 · {label}\n", "每回合:玩家 → Jev 预判 → 角色回包(判断链) → gate → 每次世界侧 LLM 调用(system / user / 原样回复)→ 工具回包 → 校验 → 落地 → 状态前后。\n"]
    for t in turns:
        L.append(f"\n## {t['id']} · {t['input']} · {t['ms']/1000:.1f}s\n")
        L.append(f"**状态前** `{t['before']['location']}` day {(t['before']['time'] or {}).get('day')} hp {t['before']['player_hp']} travel={'pending' if (t['before']['travel'] or {}).get('pending') else ('on' if t['before']['travel'] else '-')} mode={(t['before']['mode'] or {}).get('name')}\n")
        if t.get("plan"):
            p = t["plan"]
            L.append(f"**Jev 预判** intent={p.get('intent')} tension={p.get('tension')} souls={ {k: {kk: v.get(kk) for kk in ('depth', 'reacts', 'present')} for k, v in (p.get('souls') or {}).items()} }\n")
        for r in t.get("reports") or []:
            L.append(f"**角色回包 {r.get('name')}**({r.get('kind')}) 判断:{_j({k: v for k, v in (r.get('judgment') or {}).items() if k in ('attitude', 'register', 'follow', 'stay', 'want_move', 'move_to', 'decision', 'answers')}, 1500)}\n\n> {r.get('text')}\n")
        for s in t.get("spans") or []:
            if s.get("actor") in ("gate", "switch", "tools", "world.retry"):
                L.append(f"- span `{s['phase']}.{s['actor']}` {s.get('t1', 0) - s.get('t0', 0):.0f}ms {_j({k: v for k, v in s.items() if k not in ('phase', 'actor', 'backend', 't0', 't1')}, 400)}\n")
        for i, c in enumerate(t.get("calls") or []):
            L.append(f"\n### 调用 {i + 1} · {c['label']} · {c['ms']/1000:.1f}s\n")
            for m in c["messages"]:
                L.append(f"\n<details><summary>{m['role']} ({len(m['content'])} chars)</summary>\n\n```\n{m['content']}\n```\n</details>\n")
            L.append(f"\n**回复(原样)**\n\n```\n{c['reply']}\n```\n")
        if t.get("tool_returns"):
            L.append("\n**工具回包** " + _j(t["tool_returns"], 2000) + "\n")
        L.append("\n**校验 / 落地** " + _j(t["verify"], 3000) + "\n")
        L.append(f"\n**叙事(玩家看到的)**\n\n{t['narration']}\n\n**options** {t.get('options')}\n")
        a = t["after"]
        L.append(f"\n**状态后** `{a['location']}` day {(a['time'] or {}).get('day')} hp {a['player_hp']} travel={_j(a['travel'], 600)} mode={_j(a['mode'], 800)} last_combat={_j(a['last_combat'], 600)}\n")
    return "\n".join(L)


def sections_html(turns: list[dict[str, Any]]) -> str:
    """The per-turn sections (one <section class=turn> each) — shared by the single-run page and the tabbed index."""
    return "".join(_turn_sections(turns))


def render_html(turns: list[dict[str, Any]], label: str) -> str:
    parts = _turn_sections(turns)
    e = html.escape
    css = CSS
    return f"""<!doctype html><html lang="zh-Hans"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>完整历史日志</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Noto+Serif+SC:wght@700&family=Noto+Sans+SC:wght@400;700&family=JetBrains+Mono:wght@400;600&display=swap"><style>{css}</style></head><body><div class=wrap>
<div class=small style="font-family:var(--mono);letter-spacing:.12em;text-transform:uppercase">NeonRP · fulllog {e(label)} · stoneford-elena · deepseek · v3-adv</div><h1 style="margin-top:6px">一轮真机的全部细节</h1>
<p class=small>每回合:状态前 → Jev 预判 → 角色回包(她的判断链在叙事之前就跑完了)→ 引擎 span(gate / 切层 / 工具)→ 世界侧每一次 LLM 调用的 system / user / 原样回复 → 工具回包 → 校验与落地 → 玩家看到的叙事 → 状态后。角色自己那次 LLM 调用不在这里(soul 侧走另一条适配器),只有它的回包和判断链。</p>
{''.join(parts)}</div></body></html>"""


def _turn_sections(turns: list[dict[str, Any]]) -> list[str]:
    e = html.escape
    parts = []
    for t in turns:
        b, a = t["before"], t["after"]
        calls = []
        for i, c in enumerate(t.get("calls") or []):
            msgs = "".join(f"<details><summary>{m['role']} · {len(m['content'])} 字</summary><pre>{e(m['content'])}</pre></details>" for m in c["messages"])
            calls.append(f"<div class=call><div class=hd>调用 {i + 1} · <span class='pill {'l' if c['label'] == 'narrator' else 'j'}'>{c['label']}</span> · {c['ms']/1000:.1f}s</div>{msgs}<div class=hd>回复(原样)</div><pre class=reply>{e(c['reply'])}</pre></div>")
        reports = "".join(f"<div class=rep><b>{e(str(r.get('name')))}</b>({e(str(r.get('kind')))}) <span class=small>判断 {e(_j({k: v for k, v in (r.get('judgment') or {}).items() if k in ('attitude', 'register', 'follow', 'stay', 'want_move', 'move_to', 'decision')}, 700))}</span><div class=narr>{e(str(r.get('text') or ''))}</div></div>" for r in t.get("reports") or [])
        spans = "".join(f"<li><span class=k>{e(s['phase'])}.{e(s['actor'])}</span> {s.get('t1', 0) - s.get('t0', 0):.0f}ms {e(_j({k: v for k, v in s.items() if k not in ('phase', 'actor', 'backend', 't0', 't1')}, 300))}</li>" for s in (t.get("spans") or []) if s.get("actor") in ("gate", "switch", "tools", "world.retry", "jev"))
        parts.append(f"""<section class=turn><h2>{e(t['id'])} · {e(t['input'])} <span class=small>{t['ms']/1000:.1f}s</span></h2>{('<p class=small>玩家模型的意图:' + e(t['aim']) + '</p>') if t.get('aim') else ''}
<div class=state><b>前</b> {e(b['location'])} · 第 {(b['time'] or {}).get('day')} 天 · hp {b['player_hp']} · travel {'pending' if (b['travel'] or {}).get('pending') else ('on' if b['travel'] else '—')} · mode {(b['mode'] or {}).get('name') or '—'}</div>
<h3>Jev 预判</h3><pre>{e(_j(t.get('plan'), 1500))}</pre>
<h3>角色回包(② 并行,在叙事之前)</h3>{reports or '<p class=small>无</p>'}
<h3>引擎 span(gate / 切层 / 工具 / Jev)</h3><ul class=small>{spans}</ul>
<h3>世界侧 LLM 调用({len(t.get('calls') or [])} 次)</h3>{''.join(calls)}
<h3>工具回包</h3><pre>{e(_j(t.get('tool_returns'), 2500))}</pre>
<h3>校验 / 落地</h3><pre>{e(_j(t['verify'], 3500))}</pre>
{f"<h3>带标记的输出(模型写的 [ ] · 引擎回的 &lt; &gt; · 前端默认只显示正文)</h3><pre class=reply>{e(t['annotated'])}</pre>" if t.get('annotated') else ''}<h3>叙事(玩家看到的)</h3><div class=narr>{e(t['narration'])}</div>{''.join(f"<h3>panel · {e(k)}</h3><pre>{e(_ptext(v))}</pre>" for k, v in (t.get('panels') or {}).items())}<p class=small>options: {e(str(t.get('options')))}</p>
<div class=state><b>后</b> {e(a['location'])} · 第 {(a['time'] or {}).get('day')} 天 · hp {a['player_hp']}<br>travel {e(_j(a['travel'], 700))}<br>mode {e(_j(a['mode'], 900))}<br>last_combat {e(_j(a['last_combat'], 600))}</div>
</section>""")
    return parts



if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[0] / "suites"))
    main()
