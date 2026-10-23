"""Resolve output shape, A vs B, on identical inputs (「lines / ops / options 直出,和以 lines 为基础生成 ops
的对比做了没有」— not since ADV; 09-27 E9 compared the JSON-era shapes).

    A · together (today's default): one call → <lines> <ops> <options>
    B · lines first: call 1 → <lines> only (streamable); call 2 → <ops> <options> conditioned on the finished lines.
        Both calls send the identical system + history + user prefix (the provider's prefix cache serves call 2).

Inputs are the first solve of every Resolve, captured during a suite run (NEONRP_CAPTURE_SOLVE=<file>); both arms replay
exactly the same text. Each arm's ops are judged against its own narration by one judge prompt (deepseek):
    missing     — lasting changes the prose says happened, with no op
    ungrounded  — ops for things the prose does not show
plus timing (B: time to the finished narration, and total) and the ops / options counts. Writes
docs/playrecords/solve-ab-<label>/{ab.json, index.html}.

    NEONRP_CAPTURE_SOLVE=/tmp/cap.jsonl uv run python benchmarks/suite.py --label 1003-cap
    uv run python benchmarks/solve_ab.py --captures /tmp/cap.jsonl --label 1003 [--limit 40] [--workers 6]
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[0]))
import common as C  # noqa: E402,F401  (sets up the import path / env like the other benches)

OUT = Path(__file__).resolve().parents[1] / "docs" / "playrecords"

B_LINES = "\n\n## 这一次只写叙事\n只输出 <lines>…</lines> 这一块(写法照上面),不要 <ops>,不要 <options>。"
B_OPS = ("\n\n# 刚写好的叙事(已经定稿,一个字都不改)\n<lines>\n{lines}\n</lines>\n\n"
         "## 这一次只输出 <ops> 和 <options>\n"
         "按上面 <ops> 的写法,把这段叙事里**已经发生**的变化一行一个写出来——移动、花钱收钱、受伤、时间、新地点、新出现的人、"
         "东西给出 / 收下 / 用掉、写下或撕掉的文字、接下的差事、答应的约定、角色的去向……叙事里没发生的不写。"
         "然后 <options> 给 2–4 个。不要再写 <lines>。")

# C · narrate, then transition: ① prose only, the tools
# whose result decides what comes next written inline; ② one clean-context call writes the state transition in two parts —
# <vars> the registered variables' new values (closed schema), <files> the file-system changes (open schema)
C_NARRATE = ("\n\n## 这一次:只写叙事\n只输出 <lines>…</lines>,不写 <ops> 和 <options>。已经写进叙事的后果(花钱、给出收下、写下的字、"
             "别人去哪、新出现的人、时间……)不用另外记账——叙事写完会有人统一整理状态。只有**结果会决定你接下来怎么写**的事,"
             "才在那一行用方括号工具,写到这里停:\n"
             "- [dice …] / [roll …] / [referee …]:成没成要掷要裁\n"
             "- [ask 名字]:要在场角色先回话\n"
             "- [move player 去哪]:玩家去远处、可能到不了\n"
             "- [new_location 名字 near=… / between=… / in=… / over=…]:这一拍就要走进一个地图上没有的地方\n"
             "- [new_town 名字 from=…]:要去一个世界地图上还没有的城镇\n"
             "- [link A B] / [unlink A B]:这一拍就要走一条新路、或一条路断了挡住去路\n"
             "- [pay 数额 为了什么]:钱可能不够\n"
             "- [combat …]…[/combat]:打起来了\n"
             "- [~map] / [~sheet]:给玩家看地图 / 人物卡(不等)\n"
             "- [options 选项1 | 选项2 | 选项3]:想把选择交给玩家时写在最后一行;不需要就不写")
C_TRANSITION = ("\n\n# 这一拍写好的叙事(已经定稿,一个字都不改;方括号是叙述者调过的工具)\n<lines>\n{lines}\n</lines>\n\n"
                "## 现在只做状态转移:这一拍世界从什么变成了什么。分两段输出:\n"
                "<vars>\n登记变量的新值,一行一个「变量名 = 新值」,只写这一拍变了的;变量名只用上面「能改的变量」里的;玩家的位置写 location\n</vars>\n"
                "<files>\n其余落进文件系统的变化,一行一个,按上面 ops 的写法:\n"
                "- new / patch / remove:登记类的实例(物品、委托、状态效果、携带物……)\n"
                "- new_npc:叙事里新出现的人\n"
                "- move 谁 去哪:玩家以外的人的去向\n"
                "- write / rm / edit / mkdir / rmdir:写下、改动、删掉的文字和文件\n"
                "- new_location / new_town / link / unlink:只是听说或提到、这一拍没走进去的地方和路\n"
                "- define:世界里需要一种还没有的东西(少见)\n"
                "</files>\n"
                "叙事里发生了的都要有——方括号工具要求的变化也写进来;没发生的不写;带 (角色) 标记的角色的状态和情绪不写。不要再写 <lines> 和 <options>。")
CONSIST = """你是对账员。给你一段叙事(里面的方括号是叙述者调用的工具)和据此写出的状态转移(<vars> 变量新值、<files> 文件系统变化)。
只看会改世界的工具——[move …]、[new_location …]、[new_town …]、[link …]、[unlink …]、[pay …]:每一个在状态转移里有没有对上?
输出 JSON:{"tool_writes": 这类工具的个数, "conflicts": ["对不上的那个工具和原因", …]}"""

JUDGE = """你是对账员。给你一段刚发生的叙事,和引擎据此要写进世界的状态操作(ops,一行一个)。
找两类问题:
- missing:叙事里写成**已经发生**、下一拍仍然算数的变化(移动、钱、受伤、物品给出收下用掉、写下撕掉的文字、接下的差事、答应的约定、
  新地点新人物、角色去向),ops 里却没有对应的一行。只算**会影响下一拍怎么玩**的变化;对话内容、情绪、动作和环境描写
  (划了一道、抬了抬下巴、翻了个身)、可能会发生的事都不算;时间推进不算。
- ungrounded:ops 里有、叙事里却没有发生的变化。
只输出 JSON:{"missing": ["一句话说清", …], "ungrounded": ["那一行 op", …]}"""


def _adapter(root: str) -> Any:
    from neonrp.core.turn_v3 import _adapter as a

    return a(Path(root), None, "adv")


def _chat(ad: Any, system: str, history: list[dict[str, str]], user: str) -> tuple[str, float]:
    from neonrp.core.llm import Message

    t0 = time.perf_counter()
    res = ad.chat([Message(role="system", content=system), *[Message(role=h["role"], content=h["content"]) for h in history],
                   Message(role="user", content=user)])
    return (getattr(getattr(res, "message", None), "content", None) or "").strip(), round((time.perf_counter() - t0) * 1000)


def _block(text: str, tag: str) -> str:
    m = re.search(rf"<{tag}>(.*?)</{tag}>", text or "", re.S)
    return m.group(1).strip() if m else ""


def _lines_of(text: str) -> str:
    from neonrp.core.turn_v3 import parse_solve_output

    return _block(text, "lines") or parse_solve_output(text).narration or ""


def arm_a(rec: dict[str, Any]) -> dict[str, Any]:
    ad = _adapter(rec["root"])
    raw, ms = _chat(ad, rec["system"], rec["history"], rec["user"])
    return {"lines": _lines_of(raw), "ops": _block(raw, "ops"), "options": _block(raw, "options"), "ms_lines": ms, "ms_total": ms, "raw": raw}


def arm_b(rec: dict[str, Any]) -> dict[str, Any]:
    ad = _adapter(rec["root"])
    raw1, ms1 = _chat(ad, rec["system"], rec["history"], rec["user"] + B_LINES)
    lines = _lines_of(raw1)
    raw2, ms2 = _chat(ad, rec["system"], rec["history"], rec["user"] + B_OPS.format(lines=lines[:4000]))
    return {"lines": lines, "ops": _block(raw2, "ops"), "options": _block(raw2, "options"), "ms_lines": ms1, "ms_total": ms1 + ms2,
            "raw": raw1 + "\n---\n" + raw2}


def arm_c(rec: dict[str, Any]) -> dict[str, Any]:
    ad = _adapter(rec["root"])
    raw1, ms1 = _chat(ad, rec["system"], rec["history"], rec["user"] + C_NARRATE)
    lines = _block(raw1, "lines") or _lines_of(raw1)
    raw2, ms2 = _chat(ad, rec["system"], rec["history"], rec["user"] + C_TRANSITION.format(lines=lines[:4000]))
    vars_, files = _block(raw2, "vars"), _block(raw2, "files")
    opts = re.findall(r"\[options\s+([^\]]+)\]", lines)
    return {"lines": lines, "ops": ("<vars>\n" + vars_ + "\n</vars>\n<files>\n" + files + "\n</files>") if (vars_ or files) else "",
            "options": opts[-1] if opts else "", "ms_lines": ms1, "ms_total": ms1 + ms2, "raw": raw1 + "\n---\n" + raw2,
            "tools_inline": re.findall(r"\[~?(dice|roll|referee|ask|read|move|new_location|new_town|link|unlink|pay|combat|map|sheet|options)\b", lines)}


def consistency(root: str, lines: str, ops: str) -> dict[str, Any]:
    if not re.search(r"\[(move|new_location|new_town|link|unlink|pay)\b", lines):
        return {"tool_writes": 0, "conflicts": []}
    raw, _ms = _chat(_adapter(root), CONSIST, [], f"# 叙事\n{lines[:3000]}\n\n# 状态转移\n{ops or '(没有)'}")
    m = re.search(r"\{.*\}", raw, re.S)
    try:
        d = json.loads(m.group(0)) if m else {}
    except ValueError:
        d = {}
    return {"tool_writes": int(d.get("tool_writes") or 0), "conflicts": [str(x) for x in d.get("conflicts") or []]}


def judge(root: str, lines: str, ops: str) -> dict[str, Any]:
    ad = _adapter(root)
    raw, _ms = _chat(ad, JUDGE, [], f"# 叙事\n{lines[:3000]}\n\n# ops\n{ops or '(没有)'}")
    m = re.search(r"\{.*\}", raw, re.S)
    try:
        d = json.loads(m.group(0)) if m else {}
    except ValueError:
        d = {}
    return {"missing": [str(x) for x in d.get("missing") or []], "ungrounded": [str(x) for x in d.get("ungrounded") or []]}


ARMS = {"A": arm_a, "B": arm_b, "C": arm_c}
ARM_NAME = {"A": "A 一次直出", "B": "B 先叙事后 ops", "C": "C 叙事带工具 + 两段状态转移"}


def one(i: int, rec: dict[str, Any], arms: list[str] = ("A", "B"), reuse: dict[int, dict[str, Any]] | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {"i": i, "root": rec["root"], "turn": rec["turn"], "case": Path(rec["root"]).parent.name.split("-")[2] if "-" in Path(rec["root"]).parent.name else "",
                           "user_tail": rec["user"][-600:]}
    for name in arms:
        if reuse and i in reuse and name in reuse[i]:
            out[name] = reuse[i][name]
            continue
        try:
            r = ARMS[name](rec)
            r["judge"] = judge(rec["root"], r["lines"], r["ops"])
            if name == "C":
                r["consistency"] = consistency(rec["root"], r["lines"], r["ops"])
        except Exception as exc:  # noqa: BLE001
            r = {"error": str(exc)[:200]}
        out[name] = r
    print(f"  #{i} {out['case']} " + " ".join(f"{a} miss={len((out[a].get('judge') or {}).get('missing') or [])}" for a in arms), flush=True)
    return out


def _stat(rows: list[dict[str, Any]], arm: str) -> dict[str, Any]:
    ok = [r[arm] for r in rows if "judge" in r.get(arm, {})]
    n = max(1, len(ok))
    ms = sorted(x["ms_total"] for x in ok) or [0]
    ml = sorted(x["ms_lines"] for x in ok) or [0]
    cons = [x.get("consistency") for x in ok if x.get("consistency")]
    tw = sum(c["tool_writes"] for c in cons)
    extra = {"tool_writes": tw, "conflicts": sum(len(c["conflicts"]) for c in cons),
             "consistency": round(1 - sum(len(c["conflicts"]) for c in cons) / tw, 3) if tw else None,
             "options_given": sum(1 for x in ok if x["options"].strip())} if cons or arm == "C" else {}
    return {**extra, "n": len(ok), "missing": sum(len(x["judge"]["missing"]) for x in ok), "beats_with_missing": sum(1 for x in ok if x["judge"]["missing"]),
            "ungrounded": sum(len(x["judge"]["ungrounded"]) for x in ok), "beats_with_ungrounded": sum(1 for x in ok if x["judge"]["ungrounded"]),
            "ops_lines": round(sum(len([y for y in x["ops"].splitlines() if y.strip()]) for x in ok) / n, 1),
            "no_options": sum(1 for x in ok if not x["options"].strip()), "lines_chars": round(sum(len(x["lines"]) for x in ok) / n),
            "ms_lines_med": ml[len(ml) // 2], "ms_total_med": ms[len(ms) // 2], "ms_total_p90": ms[int(len(ms) * 0.9)]}


def page(label: str, rows: list[dict[str, Any]], arms: list[str] = ("A", "B")) -> Path:
    e = html.escape
    st = {a: _stat(rows, a) for a in arms}
    keys = [("n", "样本(清算拍)"), ("beats_with_missing", "有漏记的拍"), ("missing", "漏记条数"), ("beats_with_ungrounded", "有乱记的拍"),
            ("ungrounded", "乱记条数"), ("ops_lines", "平均 ops 行数"), ("no_options", "没给选项的拍"), ("lines_chars", "平均叙事字数"),
            ("ms_lines_med", "叙事出完(中位 ms)"), ("ms_total_med", "整拍(中位 ms)"), ("ms_total_p90", "整拍(p90 ms)")]
    if "C" in arms:
        keys += [("tool_writes", "叙事里改世界的工具(C)"), ("conflicts", "工具与状态转移对不上(C)"), ("consistency", "①② 一致率(C)"), ("options_given", "给了选项的拍")]
    table = "".join(f"<tr><td>{e(t)}</td>" + "".join(f"<td class=n>{e(str(st[a].get(k, '—')))}</td>" for a in arms) + "</tr>" for k, t in keys)

    def side(r: dict[str, Any]) -> str:
        if "judge" not in r:
            return f"<div class=err>{e(str(r.get('error')))}</div>"
        j = r["judge"]
        return (f"<div class=lines>{e(r['lines'])}</div><pre>{e(r['ops'] or '(没有 ops)')}</pre>"
                + "".join(f"<div class=miss>漏记:{e(x)}</div>" for x in j["missing"])
                + "".join(f"<div class=ung>乱记:{e(x)}</div>" for x in j["ungrounded"])
                + "".join(f"<div class=ung>工具对不上:{e(x)}</div>" for x in (r.get("consistency") or {}).get("conflicts") or [])
                + f"<div class=t>叙事 {r['ms_lines'] / 1000:.1f}s · 整拍 {r['ms_total'] / 1000:.1f}s</div>")
    body = "".join(f"<section><h3>#{r['i']} {e(r['case'])} · 回合 {r['turn']}</h3><div class=pair style='grid-template-columns:repeat({len(arms)},minmax(0,1fr))'>"
                   + "".join(f"<div><h4>{e(ARM_NAME[a])}</h4>{side(r[a])}</div>" for a in arms) + "</div></section>" for r in rows)
    doc = f"""<!doctype html><html lang="zh-Hans"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>清算输出形状 A/B {e(label)}</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Noto+Serif+SC:wght@700&family=Noto+Sans+SC:wght@400;600&family=JetBrains+Mono:wght@400&display=swap">
<style>
:root{{--bg:#f4f3ef;--paper:#fffefa;--ink:#1f2123;--ink2:#62645f;--line:#e2dfd6;--a:#2e6a8e;--b:#8a5a1f;--bad:#b4442f;--warn:#9a6b12;
--mono:"JetBrains Mono",ui-monospace,monospace;--sans:"Noto Sans SC",system-ui,sans-serif;--serif:"Noto Serif SC",serif}}
@media (prefers-color-scheme:dark){{:root:not([data-theme="light"]){{--bg:#161817;--paper:#1d201f;--ink:#e5e2da;--ink2:#a3a29b;--line:#30332f;--a:#7fb6d8;--b:#d9a868;--bad:#e58a74;--warn:#e0b45a}}}}
:root[data-theme="dark"]{{--bg:#161817;--paper:#1d201f;--ink:#e5e2da;--ink2:#a3a29b;--line:#30332f;--a:#7fb6d8;--b:#d9a868;--bad:#e58a74;--warn:#e0b45a}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font:14.5px/1.7 var(--sans)}}
.wrap{{max-width:1180px;margin:0 auto;padding:24px 16px 80px}}h1{{font:700 24px/1.3 var(--serif);margin:0 0 6px;text-wrap:balance}}
.sub{{color:var(--ink2);font-size:13px;max-width:70ch}}table{{border-collapse:collapse;margin:16px 0;background:var(--paper);border:1px solid var(--line)}}
td,th{{padding:6px 12px;border-bottom:1px solid var(--line);text-align:left}}td.n{{font:13px var(--mono);font-variant-numeric:tabular-nums;text-align:right}}
th.a{{color:var(--a)}}th.b{{color:var(--b)}}section{{background:var(--paper);border:1px solid var(--line);border-radius:6px;margin:14px 0;padding:12px 14px}}
h3{{margin:0 0 8px;font:600 13px var(--mono);color:var(--ink2)}}h4{{margin:0 0 6px;font-size:13px}}.pair{{display:grid;grid-template-columns:1fr 1fr;gap:14px}}
.pair>div:first-child h4{{color:var(--a)}}.pair>div:last-child h4{{color:var(--b)}}.lines{{white-space:pre-wrap;font-size:14px}}
pre{{white-space:pre-wrap;font:12px/1.6 var(--mono);background:var(--bg);border:1px solid var(--line);border-radius:4px;padding:8px;margin:8px 0}}
.miss{{color:var(--bad);font-size:13px}}.ung{{color:var(--warn);font-size:13px}}.t{{color:var(--ink2);font:12px var(--mono);margin-top:4px}}.err{{color:var(--bad)}}
@media (max-width:760px){{.pair{{grid-template-columns:1fr}}}}
</style></head><body><div class=wrap>
<h1>清算输出形状对比</h1>
<p class=sub>同一份清算输入(从全量用例的每个清算拍原样抓下),两种出法各跑一遍。A = 一次调用出 &lt;lines&gt; &lt;ops&gt; &lt;options&gt;(现在的默认);
B = 先只出 &lt;lines&gt;,再以写好的叙事为条件出 &lt;ops&gt; &lt;options&gt;(09-27 §10 的两批路线,两次调用前缀相同吃缓存)。
漏记 / 乱记由同一个对账提示判(deepseek),只是一个评审的看法,逐条可在下面核对。</p>
<div style="overflow-x:auto"><table><thead><tr><th></th>{"".join(f"<th>{e(ARM_NAME[a])}</th>" for a in arms)}</tr></thead><tbody>{table}</tbody></table></div>
{body}</div></body></html>"""
    out = OUT / f"solve-ab-{label}" / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(doc, encoding="utf-8")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--captures", required=True)
    ap.add_argument("--label", default="1003")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--arms", default="A,B")
    ap.add_argument("--reuse", default="", help="an earlier ab.json: arms already run there are taken as they are")
    a = ap.parse_args()
    files = sorted(Path(a.captures).parent.glob(Path(a.captures).name + "*"))  # <file> and its per-process parts <file>.<pid>
    recs = [json.loads(x) for f in files for x in f.read_text(encoding="utf-8").splitlines() if x.strip()]
    if a.limit:
        recs = recs[: a.limit]
    print(f"{len(recs)} captured resolves", flush=True)
    arms = [x for x in a.arms.split(",") if x]
    reuse = {int(r["i"]): r for r in json.loads(Path(a.reuse).read_text(encoding="utf-8"))["rows"]} if a.reuse else None
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        rows = list(ex.map(lambda p: one(p[0], p[1], arms, reuse), enumerate(recs)))
    d = OUT / f"solve-ab-{a.label}"
    d.mkdir(parents=True, exist_ok=True)
    stats = {x: _stat(rows, x) for x in arms}
    (d / "ab.json").write_text(json.dumps({**stats, "arms": arms, "rows": rows}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(stats, ensure_ascii=False, indent=1))
    print(page(a.label, rows, arms))


if __name__ == "__main__":
    main()
