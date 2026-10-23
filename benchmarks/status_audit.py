"""Status health check over a run's archived traces (「这个可能需要测试」 — effects as one free rule line).

    uv run python benchmarks/status_audit.py docs/playrecords/plan-loop-1005-status

Per status created in the run: from the table by name or the model's own line; the mechanisms the engine read (turns /
hours→until / each); whether it then ticked (tick:effects add / countdown patch) and went away (remove), and why. Per
agreed check: whether the host wrote a status modifier (「-2(扭伤)」) while the roller carried a status. Writes
<run>/STATUS-AUDIT.md and prints it.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

_ADJ = re.compile(r"[+-]\s*\d{1,2}\s*[((][^()()]{1,24}[))]")


def audit_case(cid: str, trs: list[dict[str, Any]]) -> dict[str, Any]:
    made: dict[str, dict[str, Any]] = {}
    checks: list[dict[str, Any]] = []
    active: set[str] = set()
    for i, tr in enumerate(trs):
        ap = tr.get("apply") or {}
        # the checks of this beat were agreed before it landed: what she carried then
        bt = ap.get("beat") if isinstance(ap.get("beat"), dict) else {}
        for c in bt.get("checks") or []:
            text = c.get("text") if isinstance(c, dict) else str(c)
            checks.append({"case": cid, "beat": i, "text": text, "adj": bool(_ADJ.search(text or "")), "carrying": sorted(
                str(made[k]["name"]) for k in active)})
        for c in ap.get("created") or []:
            if isinstance(c, dict) and c.get("class") == "status":
                made[str(c.get("id"))] = {"case": cid, "beat": i, "name": c.get("name"), "ticks": 0, "hp": 0, "countdown": 0,
                                          "patched": [], "removed": None}
                active.add(str(c.get("id")))
        # a status that was there before the game (or created where the trace does not show it): known from the first
        # countdown patch / removal that names it
        for a in ap.get("applied") or []:
            w = str(a.get("who") or "")
            if a.get("op") in ("patch", "remove") and re.match(r"^ST\d+$", w) and w not in made:
                made[w] = {"case": cid, "beat": "开局前", "name": w, "ticks": 0, "hp": 0, "countdown": 0, "patched": [], "removed": None}
                active.add(w)
        for a in ap.get("applied") or []:
            who, by = str(a.get("who") or a.get("_effect") or ""), str(a.get("by") or "")
            if a.get("op") == "add" and by.startswith("tick:effects"):
                eid = str(a.get("_effect") or "")
                for k, m in made.items():
                    if k == eid or (not eid and k in active):
                        m["ticks"] += 1
                        if a.get("var") == "player.hp":
                            m["hp"] += int(a.get("to", 0)) - int(a.get("from", 0))
            if who in made:
                m = made[who]
                if a.get("op") == "patch":
                    props = a.get("props") or {}
                    if "turns" in props:
                        m["countdown"] += 1
                    if "until" in props:
                        m["until"] = (props["until"] or {}).get("to") if isinstance(props["until"], dict) else props["until"]
                    m["patched"].append(",".join(props))
                if a.get("op") == "remove":
                    ticked = any(str(x.get("by") or "").startswith("tick:effects") for x in ap.get("applied") or [])
                    m["removed"] = {"beat": i, "by": by or ("倒计时" if ticked and m["countdown"] else "叙事")}
                    active.discard(who)
    return {"statuses": list(made.values()), "checks": checks}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    a = ap.parse_args()
    run = Path(a.run)
    rows, checks = [], []
    for tf in sorted((run / "traces").glob("*.jsonl")):
        trs = [json.loads(x) for x in tf.read_text(encoding="utf-8").splitlines() if x.strip()]
        r = audit_case(tf.stem, trs)
        rows += r["statuses"]
        checks += r["checks"]
    # the props each status landed with, from the final results (the world's own file is gone; the trace kept ids)
    out = ["# 状态体检", "", f"状态 {len(rows)} 个;检定 {len(checks)} 个(其中身上有状态时约的 {sum(1 for c in checks if c['carrying'])} 个)", "",
           "| 例 | 拍 | 状态 | 生效次数 | HP 变化 | 倒计时 | 时钟到期 | 去除 |", "|---|---|---|---|---|---|---|---|"]
    for m in rows:
        rm = m["removed"]
        out.append(f"| {m['case']} | {m['beat']} | {m['name']} | {m['ticks']} | {m['hp']:+d} | {m['countdown']} | {m.get('until', '')} | "
                   + (f"第{rm['beat']}拍 · {rm['by']}" if rm else "还在") + " |")
    out += ["", "## 身上有状态时约的检定", "", "| 例 | 拍 | 检定 | 写了修正 | 身上的状态 |", "|---|---|---|---|---|"]
    for c in checks:
        if c["carrying"]:
            out.append(f"| {c['case']} | {c['beat']} | {c['text']} | {'是' if c['adj'] else '否'} | {'、'.join(c['carrying'])} |")
    text = "\n".join(out) + "\n"
    (run / "STATUS-AUDIT.md").write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
