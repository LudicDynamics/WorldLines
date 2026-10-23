"""Specs an agent can read straight from the engine (「spec 也还是需要放在一些地方可以直接用 agent 去读」).

Two kinds, one list:

- **written** — ``documents/spec/<name>.<lang>.md`` (world · soul · template · contract · pack · player), the source of truth. A source
  checkout reads them there; the wheel carries a copy under ``neonrp/_spec/`` (pyproject force-include).
- **generated** — read off the code every time, so they never drift: ``ops`` (each play pack's ops · classes ·
  variables · triggers · seams · mode layers), ``authoring`` (the template authoring ops), ``contracts`` (the play
  contracts in force), ``http`` (every path the web runtime answers).

Three ways in, the same text: ``neonrp spec [name] [--lang] [--pack]`` · ``GET /api/v1/spec[/<name>]`` ·
``GET /llms.txt`` (an index an agent can start from).
"""
from __future__ import annotations

import ast
import json
import re
from pathlib import Path
from typing import Any

PKG = Path(__file__).resolve().parent
WRITTEN = ("world", "soul", "template", "contract", "pack", "player")
GENERATED = ("ops", "authoring", "contracts", "http")
LANGS = ("zh", "en")
TITLES = {
    "world": "the world folder",
    "soul": "the character folder and the character library",
    "template": "the template: cast, plots, slots, packages — the unit you play and publish",
    "contract": "the play contract: what a kind of game must deliver",
    "player": "the player's own data: avatars, the record across runs, chat threads",
    "pack": "the rule pack: rule tables, rule panels, checks, statuses, the clock — how to write or change one",
    "ops": "the op space: what the model may write, per play pack (generated)",
    "authoring": "template authoring ops (generated)",
    "contracts": "the play contracts in force (generated)",
    "http": "every HTTP path the engine answers (generated)",
}
PACKS = ("rpg", "pct", "werewolf", "monopoly")


def spec_dir() -> Path | None:
    for d in (PKG.parents[1] / "documents" / "spec", PKG / "_spec"):  # source checkout · wheel
        if (d / "README.md").is_file():
            return d
    return None


def names() -> list[dict[str, Any]]:
    d = spec_dir()
    out = []
    for n in WRITTEN:
        langs = [lg for lg in LANGS if d is not None and (d / f"{n}.{lg}.md").is_file()]
        if langs:
            out.append({"name": n, "kind": "written", "title": TITLES[n], "langs": langs})
    out += [{"name": n, "kind": "generated", "title": TITLES[n], "langs": ["zh"]} for n in GENERATED]
    return out


def read(name: str, *, lang: str = "zh", pack: str | None = None) -> str:
    if name in WRITTEN:
        d = spec_dir()
        if d is None:
            raise KeyError("specs are not installed with this engine")
        for lg in (lang, "zh", "en"):
            p = d / f"{name}.{lg}.md"
            if p.is_file():
                return p.read_text(encoding="utf-8")
        raise KeyError(f"no spec {name!r}")
    if name == "ops":
        return "\n\n".join(_pack_md(p) for p in ([pack] if pack else PACKS))
    if name == "authoring":
        return ("# Template authoring ops\n\n`POST /api/v1/local/templates/<id>/ops {ops: [...]}` — every op is verified first; "
                "one refusal and nothing is written; the template is re-linted afterwards. CLI: `neonrp template --help`.\n\n```\n"
                + _doc("template/author.py") + "\n```\n")
    if name == "contracts":
        return _contracts_md()
    if name == "http":
        return _http_md()
    raise KeyError(f"no spec {name!r} (have: {', '.join(n['name'] for n in names())})")


def llms_txt(base: str = "") -> str:
    """An index for agents: what WorldLines is in two lines, then every spec with its URL."""
    rows = [f"- [{n['name']}]({base}/api/v1/spec/{n['name']}): {n['title']}" for n in names()]
    return ("# WorldLines engine (NeonRP)\n\n"
            "> A world is a folder; characters (souls) live in a library and are linked into templates; a template binds a world,\n"
            "> its cast, a play pack, a play contract and an orchestration graph, and is the unit you play, export and publish.\n\n"
            "Read the spec for what you are about to write. Written specs take `?lang=zh|en`; `ops` takes `?pack=rpg|pct|werewolf|monopoly`.\n"
            "The same texts: `neonrp spec <name>` on the command line.\n\n## Specs\n\n" + "\n".join(rows) + "\n")


# ── generated ────────────────────────────────────────────────────────────────

def _doc(rel: str) -> str:
    return ast.get_docstring(ast.parse((PKG / rel).read_text(encoding="utf-8"))) or ""


def _cell(x: Any, n: int = 200) -> str:
    s = x if isinstance(x, str) else json.dumps(x, ensure_ascii=False, default=str)
    s = s.replace("|", "\\|").replace("\n", " ")
    return s if len(s) <= n else s[:n] + "…"


def _pack_md(name: str) -> str:
    from neonrp import packs

    p = packs.load(name)
    out = [f"# Play pack `{name}`", "", (p.doc or "").strip(), ""]
    if p.base:
        out += [f"Built on `{p.base}` (its layer prompts are the fallback)", ""]
    out += ["## Ops", "", "| op | alias | kind | fields | scope | validated | doc |", "|---|---|---|---|---|---|---|"]
    out += [f"| `{a.op}` | {a.alias or ''} | {a.kind} | {_cell(', '.join(a.fields or []))} | {a.scope} | {'✓' if a.validator else ''} | {_cell(a.doc, 260)} |"
            for a in p.actions]
    out += ["", "## Classes (open schema)", "", "| class | parent | folder | required | props | growth policy |", "|---|---|---|---|---|---|"]
    out += [f"| `{c.name}` | {c.parent_class or ''} | {c.folder or ''} | {_cell(', '.join(c.required or []))} | {_cell(', '.join((c.props or {}).keys()))} | {c.policy} |"
            for c in p.classes.values()]
    if p.variables:
        out += ["", "## Variables", ""] + [f"- `{k}`: {_cell(v, 240)}" for k, v in p.variables.items()]
    if p.triggers:
        out += ["", "## Triggers", ""] + [f"- `{k}`: {_cell(v, 300)}" for k, v in p.triggers.items()]
    if p.modes:
        out += ["", "## Mode layers", ""] + [f"- `{k}`: {_cell(v, 300)}" for k, v in p.modes.items()]
    out += ["", "## Mechanics seams", ""] + [f"- `{k}` → `{v}`" for k, v in p.mechanics.items()]
    return "\n".join(out) + "\n"


def _contracts_md() -> str:
    from neonrp.template import contract as C

    out = ["# Play contracts in force", "", "How the engine reads them (`neonrp.template.contract`):", "", "```", _doc("template/contract.py"), "```", ""]
    for cid in sorted(C.available()):
        c = C.load(cid)
        out += [f"## `{c.get('id')}@{c.get('version')}`", "", "```json", json.dumps({k: v for k, v in c.items() if not k.startswith("_")}, ensure_ascii=False, indent=2), "```", ""]
    return "\n".join(out)


def _http_md() -> str:
    rows: dict[str, set[str]] = {}
    for f in sorted((PKG / "webui").glob("*.py")) + [PKG / "commands" / "web.py"]:
        txt = f.read_text(encoding="utf-8")
        for m in re.finditer(r'"(/(?:api/v1/[a-z0-9_/<>{}\-.]+|events|cmd|cancel|start|traces|trace|llms\.txt))"', txt):
            rows.setdefault(m.group(1), set()).add(f.stem)
    return ("# HTTP paths\n\nWhat `neonrp web` answers (scanned from the route code; a path with parameters is a prefix).\n\n| path | from |\n|---|---|\n"
            + "\n".join(f"| `{k}` | {', '.join(sorted(v))} |" for k, v in sorted(rows.items())) + "\n")
