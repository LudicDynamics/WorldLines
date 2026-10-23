"""Static HTML report for one run's turn traces (ENGINE-V3-MASTER-PLAN §11).

One renderer, no second data source: it reads ``.neonrp/orchestration/<branch>.jsonl``
(or a list of trace dicts) and draws, per turn, the span Gantt, the ops,
the ApplyResult and the narration length. It is the "complete record" the
test pyramid archives under ``docs/playrecords/`` (§9 layer 3) and what
``neonrp trace html <root>`` writes.
"""

from __future__ import annotations

import html
import json
import statistics
from pathlib import Path
from typing import Any

from neonrp.core.orchestration_trace import read_turn_traces

_CSS = """
:root{--bg:#F3F1EC;--paper:#fff;--ink:#22211E;--ink2:#5B5850;--ink3:#8A867C;--line:#DDD9D0;
--eng:#2F6B8F;--llm:#A6641A;--jev:#6C3FA6;--bad:#B8383D;--ok:#2E7D4F;--py:#2F6B8F}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#141312;--paper:#1C1B19;--ink:#ECE9E1;--ink2:#B5B0A4;--ink3:#847F73;--line:#2E2C28;
--eng:#7FB2D6;--llm:#E0A35A;--jev:#B590E6;--bad:#F07A7E;--ok:#5CC68A;--py:#7FB2D6}}
:root[data-theme=dark]{--bg:#141312;--paper:#1C1B19;--ink:#ECE9E1;--ink2:#B5B0A4;--ink3:#847F73;--line:#2E2C28;
--eng:#7FB2D6;--llm:#E0A35A;--jev:#B590E6;--bad:#F07A7E;--ok:#5CC68A;--py:#7FB2D6}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.6 "Noto Sans SC","PingFang SC",system-ui,sans-serif}
.wrap{max-width:1040px;margin:0 auto;padding:32px 20px 80px}h1{font-size:24px;margin:0 0 6px}h2{font-size:17px;margin:32px 0 8px}
.mono{font-family:"JetBrains Mono",ui-monospace,Menlo,monospace;font-size:12px}.dim{color:var(--ink3)}
table{border-collapse:collapse;width:100%;font-size:13px;margin:8px 0}th,td{text-align:left;vertical-align:top;padding:6px 8px;border-bottom:1px solid var(--line)}
th{font-family:ui-monospace,Menlo,monospace;font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--ink3)}td.n{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.turn{background:var(--paper);border:1px solid var(--line);border-radius:6px;padding:12px 14px;margin:12px 0}
.turn h3{margin:0 0 6px;font-size:15px}.narr{white-space:pre-wrap;font-size:13.5px;color:var(--ink2);max-height:9em;overflow:auto;border-left:3px solid var(--line);padding-left:10px;margin:8px 0}
svg text{font-family:ui-monospace,Menlo,monospace;font-size:10.5px;fill:var(--ink2)}
.b-python,.b-engine{fill:var(--py)}.b-llm,.b-jev\\+llm{fill:var(--llm)}.b-jev,.b-stub,.b-proxy{fill:var(--jev)}.b-bad{fill:var(--bad)}
pre{font-family:ui-monospace,Menlo,monospace;font-size:12px;background:var(--bg);border:1px solid var(--line);border-radius:4px;padding:8px 10px;overflow-x:auto;margin:6px 0}
.pill{display:inline-block;font-family:ui-monospace,Menlo,monospace;font-size:11px;padding:0 6px;border-radius:3px;border:1px solid var(--line);margin-right:4px}
"""


def _esc(x: Any) -> str:
    return html.escape(str(x if x is not None else ""))


def _gantt(spans: list[dict[str, Any]], width: int = 900) -> str:
    if not spans:
        return '<div class="dim">no spans (v2b turn)</div>'
    t_end = max(float(s.get("t1") or 0) for s in spans) or 1.0
    left = 170
    scale = (width - left - 20) / t_end
    rows = []
    for i, s in enumerate(spans):
        y = 18 + i * 18
        x0 = left + float(s.get("t0") or 0) * scale
        x1 = left + float(s.get("t1") or 0) * scale
        backend = str(s.get("backend") or "python")
        cls = "b-bad" if s.get("refused") and s.get("phase") == "verify" and s["refused"] else f"b-{backend}"
        label = f"{s.get('phase')} · {s.get('actor')}" + (f" (loop {s['loop']})" if s.get("loop") else "")
        rows.append(f'<text x="4" y="{y + 11}">{_esc(label)[:28]}</text>'
                    f'<rect class="{cls}" x="{x0:.1f}" y="{y + 3}" width="{max(2.0, x1 - x0):.1f}" height="11" rx="2"/>'
                    f'<text x="{x1 + 4:.1f}" y="{y + 12}" class="dim">{(float(s.get("t1") or 0) - float(s.get("t0") or 0)) / 1000:.2f}s</text>')
    h = 18 + len(spans) * 18 + 6
    ticks = "".join(f'<line x1="{left + t * scale:.1f}" y1="14" x2="{left + t * scale:.1f}" y2="{h}" stroke="var(--line)"/><text x="{left + t * scale + 2:.1f}" y="11" class="dim">{t / 1000:.0f}s</text>'
                    for t in _ticks(t_end))
    return f'<svg viewBox="0 0 {width} {h}" width="100%">{ticks}{"".join(rows)}</svg>'


def _ticks(t_end: float) -> list[float]:
    step = 1000.0
    while t_end / step > 12:
        step *= 2
    out, t = [], 0.0
    while t <= t_end:
        out.append(t)
        t += step
    return out


def _turn_ms(tr: dict[str, Any]) -> float | None:
    spans = tr.get("spans") or []
    if spans:
        return max(float(s.get("t1") or 0) for s in spans)
    t = tr.get("timing") or {}
    parts = [t.get("plan_ms"), t.get("souls_ms"), t.get("world_agent_ms")]
    vals = [float(x) for x in parts if isinstance(x, (int, float))]
    return sum(vals) if vals else None


def render_html(traces: list[dict[str, Any]], *, title: str = "回合记录", narrations: dict[int, str] | None = None) -> str:
    """Render a whole run. ``narrations`` (turn_seq → text) is optional: the
    trace itself only stores narration length."""
    ms = [m for m in (_turn_ms(t) for t in traces) if m is not None]
    n = len(traces)
    med = statistics.median(ms) / 1000 if ms else 0
    p90 = sorted(ms)[min(len(ms) - 1, int(0.9 * len(ms)))] / 1000 if ms else 0
    n_ops = sum(len((t.get("world_agent") or {}).get("tool_calls", [])) for t in traces)
    n_ref = sum(len((t.get("apply") or {}).get("refused", [])) for t in traces)
    n_loops = sum(((t.get("timing") or {}).get("v3") or {}).get("loops", 0) for t in traces)
    n_v3 = sum(1 for t in traces if t.get("spans"))
    head = (f'<div class="wrap"><h1>{_esc(title)}</h1><div class="dim mono">{n} 回合 · v3 回合 {n_v3} · 墙钟中位 {med:.1f}s · p90 {p90:.1f}s · ops {n_ops} · 拒绝 {n_ref} · 环 {n_loops}</div>')
    summary = ['<h2>每回合</h2><table><thead><tr><th>#</th><th>输入</th><th>墙钟</th><th>plan</th><th>souls</th><th>ops</th><th>applied</th><th>refused</th><th>repaired</th><th>环</th><th>叙事</th><th>land</th></tr></thead><tbody>']
    for t in traces:
        ap = t.get("apply") or {}
        tm = t.get("timing") or {}
        w = _turn_ms(t)
        souls = ",".join(f"{k.split('-')[-1]}:{v}" for k, v in ((tm.get("souls") or {}).items()))
        summary.append(f'<tr><td class="n">{t.get("turn_seq")}</td><td>{_esc((t.get("player") or {}).get("input", ""))[:60]}</td>'
                       f'<td class="n">{(w or 0) / 1000:.1f}s</td><td class="mono">{_esc((t.get("plan") or {}).get("source", "—"))}</td>'
                       f'<td class="mono">{_esc(souls)}</td><td class="n">{len((t.get("world_agent") or {}).get("tool_calls", []))}</td>'
                       f'<td class="n">{len(ap.get("applied", []))}</td><td class="n">{len(ap.get("refused", []))}</td><td class="n">{len(ap.get("repaired", []))}</td>'
                       f'<td class="n">{((tm.get("v3") or {}).get("loops", 0))}</td><td class="n">{(t.get("world_agent") or {}).get("narration_chars", 0)}</td>'
                       f'<td class="mono">{"✓" if (t.get("land") or {}).get("ok") else "✗"} {_esc(((t.get("land") or {}).get("commit_id") or "")[:8])}</td></tr>')
    summary.append("</tbody></table>")
    body = ["<h2>逐回合</h2>"]
    for t in traces:
        ap = t.get("apply") or {}
        seq = t.get("turn_seq")
        body.append(f'<div class="turn"><h3>T{seq} · {_esc((t.get("player") or {}).get("input", ""))[:80]}</h3>')
        body.append(_gantt(t.get("spans") or []))
        ops = (t.get("world_agent") or {}).get("tool_calls", [])
        if ops:
            body.append("<div>" + "".join(f'<span class="pill">{_esc(o.get("name"))} {_esc(o.get("args", ""))[:60]}</span>' for o in ops) + "</div>")
        if ap:
            slim = {k: v for k, v in ap.items() if k in ("applied", "refused", "created", "repaired", "requests", "triggered", "souls") and v}
            if slim:
                body.append(f"<pre>{_esc(json.dumps(slim, ensure_ascii=False, indent=1))[:3000]}</pre>")
        if narrations and seq in narrations:
            body.append(f'<div class="narr">{_esc(narrations[seq])}</div>')
        body.append("</div>")
    return f"<title>{_esc(title)}</title><style>{_CSS}</style>" + head + "".join(summary) + "".join(body) + "</div>"


def write_run_report(root: Path, out: Path, *, branch: str = "main", title: str | None = None,
                     narrations: dict[int, str] | None = None) -> dict[str, Any]:
    traces = read_turn_traces(root, branch)
    html_text = render_html(traces, title=title or f"{root.name} · {branch}", narrations=narrations)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html_text, encoding="utf-8")
    return {"turns": len(traces), "path": str(out), "v3_turns": sum(1 for t in traces if t.get("spans"))}
