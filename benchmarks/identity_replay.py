"""Identity check V2 — replay the names in recorded ops through the old and the new lookup.

Every op of every proposal in docs/playrecords/*/traces is read; each name it carries (who / to / name / target) is looked
up the old way (first registration wins, plain casefold) and the new way (`Registry.lookup`) against the benchmark world
at its start. Same answer → nothing to look at. Only the differences are listed (and written for review):
  - old found one, new says ambiguous   (the old one was a silent pick)
  - old found nothing, new found one    (a spelling the old table missed)
  - both found one, but different       (must be read)
Entries the run itself created are not in the start state — both sides miss them equally, so they never show up as a
difference. No model calls.

    uv run python benchmarks/identity_replay.py [--out docs/playrecords/identity-replay-1013]
"""
from __future__ import annotations

import argparse
import collections
import glob
import json
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIELDS = ("who", "to", "name", "target")


def _old_resolve(reg, token: str):
    """The pre-10-13 lookup: a casefold key → the first entry registered under it."""
    from neonrp.core.place_nav import canonical_node, join_location
    from neonrp.core.registry import _ROLE_SUFFIX

    table: dict[str, str] = {}
    for e in reg.entries.values():
        for a in {e.id, e.name, *e.aliases}:
            k = str(a or "").strip().casefold()
            if k and k not in table:
                table[k] = e.id
    cands = [token, _ROLE_SUFFIX.sub("", token), token.split("/")[-1], canonical_node(token) or token]
    if reg.current_town and "/" not in token:
        cands.append(join_location(reg.current_town, canonical_node(token) or token))
    for c in cands:
        hit = table.get(str(c).strip().casefold())
        if hit:
            return hit
    first = re.split(r"[\s\u00b7\u30fb,\uff0c:\uff1a]", token.strip())[0]  # the old last resort: the first word
    return table.get(first.strip().casefold())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="")
    a = ap.parse_args()
    os.environ.setdefault("NEONRP_S1_BACKEND", "off")
    sys.path.insert(0, str(ROOT / "benchmarks"))
    from neonrp.core.registry import load_registry
    from neonrp.worlds import scaffold_template_into

    root = Path(tempfile.mkdtemp()) / "w"
    scaffold_template_into(os.environ.get("BENCH_WORLD", "stoneford-elena"), root)
    reg = load_registry(root)
    seen: dict[tuple[str, str], dict] = {}
    count = collections.Counter()
    for f in sorted(glob.glob(str(ROOT / "docs/playrecords/*/traces/*.jsonl"))):
        for line in open(f, encoding="utf-8"):
            try:
                t = json.loads(line)
            except ValueError:
                continue
            for p in (t.get("apply") or {}).get("proposals") or []:
                for o in p.get("ops") or []:
                    if not isinstance(o, dict):
                        continue
                    for fld in FIELDS:
                        tok = o.get(fld)
                        if not isinstance(tok, str) or not tok.strip():
                            continue
                        count["names"] += 1
                        key = (str(o.get("op")), tok.strip())
                        if key in seen:
                            seen[key]["n"] += 1
                            continue
                        old = _old_resolve(reg, tok.strip())
                        lk = reg.lookup(tok.strip())
                        new = lk.ids
                        kind = ("same" if (old is None and not new) or (old is not None and new == [old])
                                else "ambiguous" if len(new) > 1
                                else "found_now" if old is None
                                else "lost" if not new
                                else "different")
                        seen[key] = {"op": key[0], "field": fld, "name": tok.strip(), "old": old, "new": new, "how": lk.how,
                                     "kind": kind, "n": 1, "trace": str(Path(f).relative_to(ROOT))}
    kinds = collections.Counter()
    for r in seen.values():
        kinds[r["kind"]] += r["n"]
    diffs = sorted((r for r in seen.values() if r["kind"] != "same"), key=lambda r: (r["kind"], -r["n"]))
    print(f"names {count['names']} · distinct {len(seen)} · " + " · ".join(f"{k} {v}" for k, v in kinds.most_common()))
    for r in diffs:
        print(f"  [{r['kind']}] {r['op']} {r['field']}={r['name']!r} ×{r['n']}  old={r['old']} new={r['new']} ({r['how']})")
    if a.out:
        out = ROOT / a.out
        out.mkdir(parents=True, exist_ok=True)
        (out / "replay.json").write_text(json.dumps({"counts": dict(kinds), "names": count["names"], "diffs": diffs},
                                                    ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
