"""The rpg narrator's world-side contract (③ SOLVE system prompt) and the 远行段 pack hint (rpg pack).
Bound from the pack's ``contract`` and ``pack_hints`` seams."""
from __future__ import annotations

from pathlib import Path

from neonrp.core.paths import get_data_dir_name
from neonrp.core.registry import Registry
from neonrp import prompts as _prompts

_TAGS_FORMAT = (
    "## 输出格式(严格)\n先写叙事正文。正文写完后另起一行,每个状态变化占一行、用方括号;这一回合什么都没变就写一行 [无变化](必须有,不能什么都不写):\n"
    "[无变化]\n"
    "[player.gold -3]   变量:名字 + 数字,带 + / − 号 = 增减,不带 = 设定\n"
    "[time.day 4]\n"
    "[move player inn]   移动:move 谁 去哪(谁 = player 或在场角色 / NPC 的名字,去哪 = 本镇地点 id)\n"
    "[move 某人 inn]\n"
    "[flag paid]   story flag\n"
    "[ask 某人]   需要某个在场角色先回话才能写下去时,写这一行并把叙事停在那里\n"
    "[new quest 找失踪的人]   登记类的新实例(只有词条包列出「可登记的类」时)\n"
    "叙事正文里不要出现方括号。\n"
)


_PROSE_JSON_FORMAT = (
    "## 输出格式(严格)\n先写叙事正文(纯文字,正文里不要出现 JSON、方括号指令或状态块)。"
    "正文写完后另起一行,用一个 ```json 围栏给出这一回合的状态变化,没有变化也必须给 {\"ops\": []}:\n"
    "```json\n{\"ops\": [ … ]}\n```\n"
    "ops 只能是下列形状:\n"
)


RULES = _prompts.md_by_lang("rpg_rules")

TAIL = _prompts.by_lang("rpg_contract", "TAIL")


def _voice(root: Path, game: Path) -> str:
    """The world's own voice notes: agents/world-agent/voice.md (v3, short) first; narrative.md (v2 orchestrator) is not used —
    it carries v2-only instructions (ask_user menus, dice in parentheses, paragraphs) that fight the ADV shape."""
    for cand in (root / "agents" / "world-agent" / "voice.md", game / "agents" / "voice.md"):
        try:
            return cand.read_text(encoding="utf-8")[:1500]
        except OSError:
            continue
    return ""


# 「得加一些跑团主持(GM)的提示词,张弛有度地推进剧情」 / 「这是 referee 的松紧问题」: how the table is run.
PACING = _prompts.by_lang("rpg_contract", "PACING")
STRICTNESS = _prompts.inner_lang("rpg_contract", "STRICTNESS")


def table_rules(root: Path, lang: str) -> str:
    from neonrp.core import engine_config

    level = str(engine_config.get(root, "turn.referee.strictness", "fair") or "fair").lower()
    s = STRICTNESS.get(level) or STRICTNESS["fair"]
    return (PACING.get(lang) or PACING["zh"]) + "\n" + (s.get(lang) or s["zh"])


def contract(root: Path, reg: Registry, structured: str = "together", lang: str | None = None) -> str:
    """The rpg narrator's system prompt: rules (i18n) + the world's voice + the ADV format with this template's op lines.
    Other structured modes (json_object / tags / prose_json / split2 …) are the benchmark arms and keep their own format text."""
    from neonrp.core.output_lang import prompt_lang

    lang = lang or prompt_lang(root)
    game = root / get_data_dir_name(root)
    voice = _voice(root, game)
    ops = [a for a in reg.actions.values() if a.scope == "world" and a.enabled]
    grammar = "\n".join(f'  {{"op": "{a.op}", ' + ", ".join(f'"{f}": …' for f in a.fields) + "}" + (f"  // {a.doc}" if a.doc else "") for a in ops)
    vars_ = "、".join(k for k, v in reg.variables.items() if not v.readonly)
    from neonrp.core.adv import lang_rule

    rules = (RULES.get(lang) or RULES["zh"]).replace("{LANG}", lang_rule(root, lang)) + "\n" + table_rules(root, lang)
    if structured in ("adv", "together"):
        from neonrp.core.adv import assemble
        from neonrp.packs import resolve as _resolve_pack

        tail = (TAIL.get(lang) or TAIL["zh"]).format(vars=vars_ or "—")
        # rules / voice / entries / blocks / op docs may all be changed in manifest.json["prompt"] (or game/meta/prompt.json)
        return assemble(root, reg, rules=rules, lang=lang, blocks=tuple(_resolve_pack(root).blocks), tail=tail, voice=voice)
    if structured == "tags":
        fmt = _TAGS_FORMAT
    elif structured == "prose_json":
        fmt = _PROSE_JSON_FORMAT + grammar + "\n"
    else:
        fmt = ("## 输出格式(严格)\n只输出一个 JSON 对象,不要别的文字:\n"
               '{"narration": "<叙事>", "ops": [ … ]}\n'
               "ops 只能是下列形状(没有变化就给空数组):\n" + grammar + "\n")
    tail = (TAIL.get(lang) or TAIL["zh"]).format(vars=vars_ or "—")
    if structured not in ("adv", "together", "tags", "prose_json"):
        tail += ' JSON 字符串里的换行写成 \\n,引号写成 \\".'
    voice_block = (voice if voice.lstrip().startswith("#") else f"## 世界文风\n{voice}") + "\n\n" if voice else ""
    return rules + "\n\n" + voice_block + fmt + "\n" + tail


def travel_hints(root: Path, reg: Registry) -> str:
    """What the map allows this turn for every other town (E5 C4: the model wrote
    the player into 碧石镇 in one turn; the engine clamps cross-town travel to
    the gate). Deterministic, from judge_move; a few ms. Sentences from packs/rpg/i18n (zh / en / ja)."""
    from neonrp.core.place_nav import judge_move, qualify_location
    from neonrp.packs.rpg import travel as _travel
    from neonrp.packs.rpg.i18n import t as _t
    from neonrp.packs.rpg.travel import route_days, route_facts

    cur = reg.player_location
    if not cur:
        return ""
    head = _t(root, "travel_head")
    lines = []
    j = _travel.journey(root)
    if j:
        lines.append(_travel.hint(reg, root))
        here = reg.entries.get(cur)
        if here is not None and here.cls == "road":  # on the road there is nowhere else to go
            return head + "\n" + "\n".join(lines)
    def on_road(tid: str) -> str:  # a road straight there: the party may stop on it (10-19, travel.set_out)
        rid = route_facts(root, reg.current_town or "", tid).get("id") if reg.current_town else None
        return _t(root, "hint_on_road", rid=rid) if rid else ""

    for t in sorted([*reg.of_class("town"), *reg.of_class("dungeon")], key=lambda e: e.id):
        if t.id == reg.current_town:
            continue
        if t.cls == "dungeon":  # a dungeon is entered through its entry room; distance from the map like a town
            entry = next((r for r in reg.of_class("room") if r.parent == t.id and str(r.props.get("type")) == "entry"), None)
            days = route_days(root, reg.current_town or "", t.id) if reg.current_town else None
            how = _t(root, "days_about", n=days) if days else _t(root, "same_day")
            lines.append(_t(root, "hint_dungeon", id=t.id, name=t.name, how=how, entry=entry.name if entry else "?", entry_id=entry.id if entry else "?",
                            theme=t.props.get("theme") or "", danger=t.props.get("danger")) + on_road(t.id))
            continue
        try:
            v = judge_move(root, current_location=qualify_location(root, cur), target=t.id)
        except Exception:  # noqa: BLE001
            continue
        days = route_days(root, reg.current_town or "", t.id) if reg.current_town else None
        trip = ""
        if days:
            rf = route_facts(root, reg.current_town or "", t.id)
            road = (_t(root, "road_is", kind=rf.get("kind")) + (f", {rf['note']}" if rf.get("note") else "")) if rf else ""
            tags = ", ".join(str(x) for x in (rf.get("tags") or [])) if rf else ""
            trip = _t(root, "days_engine", n=days) + (f"; {road}" if road else "") + (_t(root, "road_tags", tags=tags) if tags else "") + _t(root, "road_ruled")
        elif days == 0:
            trip = _t(root, "same_day")
        if j and j.get("to") == t.id:
            continue  # the journey line above says it all
        if v.allowed and v.resolved:
            lines.append(_t(root, "hint_enter", id=t.id, name=t.name, at=v.resolved) + (f"; {trip}" if trip else "") + on_road(t.id))
        elif v.clamped_to and str(v.clamped_to).split("/")[0] == t.id:  # landing at its gate is arriving there (10-19)
            lines.append(_t(root, "hint_enter", id=t.id, name=t.name, at=v.clamped_to) + (f"; {trip}" if trip else "") + on_road(t.id))
        elif v.clamped_to:
            lines.append(_t(root, "hint_clamp", id=t.id, name=t.name, why=v.reason, at=v.clamped_to) + (f"; {trip}" if trip else ""))
        else:
            lines.append(_t(root, "hint_no", id=t.id, name=t.name, why=v.reason or _t(root, "cannot_go")))
    return (head + "\n" + "\n".join(lines)) if lines else ""


solve_contract = contract  # old name


_ROOM = _prompts.by_lang("rpg_contract", "_ROOM")
_UNIT = _prompts.inner_lang("rpg_contract", "_UNIT")


def price_hints(root: Path, reg: Registry) -> str:
    """This town's price list, from the facility files (adversarial2 I2: three runs quoted three different prices —
    2 silver, 8 copper, 3 silver — for the same room; the file said 3 / 8 and the narrator never saw it)."""
    from neonrp.core.adv import run_lang
    from neonrp.packs.rpg.i18n import t as _t

    town = reg.current_town
    if not town:
        return ""
    lang = run_lang(root)
    rows = []
    unit_key = "gold"
    for e in sorted(reg.entries.values(), key=lambda x: x.id):
        fac = e.props.get("facility") if e.cls == "place" and str(e.id).startswith(f"{town}/") else None
        if not isinstance(fac, dict):
            continue
        unit_key = str(fac.get("currency") or unit_key)
        items = []
        for r in fac.get("rooms") or []:
            if isinstance(r, dict) and r.get("price") is not None:
                items.append(f"{(_ROOM.get(lang) or _ROOM['zh']).get(str(r.get('type')), str(r.get('type')))} {r['price']}")
        idx = float(fac.get("price_index") or 1.0)
        for it in fac.get("inventory") or []:
            if isinstance(it, dict) and it.get("price") is not None:
                pr = round(float(it["price"]) * idx)
                items.append(f"{it.get('name') or it.get('id')} {pr}" + (f"(×{it['stock']})" if it.get("stock") is not None else ""))
        if items:
            rows.append(f"- {e.id} {e.name}:" + " · ".join(items))
    if not rows:
        return ""
    unit = (_UNIT.get(unit_key) or {}).get(lang) or unit_key
    var = f"player.{unit_key}" if f"player.{unit_key}" in reg.variables else "player.gold"
    return _t(root, "price_head", unit=unit, var=var) + "\n" + "\n".join(rows)


def pack_hints(root: Path, reg: Registry) -> str:
    """rpg's extra pack text: travel (what the map allows) + this town's prices."""
    return "\n\n".join(x for x in (travel_hints(root, reg), price_hints(root, reg)) if x)
