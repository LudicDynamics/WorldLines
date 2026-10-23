"""The RPG template's world layout — how a stoneford-style folder becomes registry entries.

This is the rpg pack's ``load`` seam (``mechanics.load``): towns / places / player / souls /
NPCs / items and the rpg variables (time · location · player.* · town.alert · reputation.*).
The core knows none of these paths; a template with another layout registers its own loader,
and a template with none relies on the generic class folders (werewolf, monopoly).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from neonrp.core.paths import get_data_dir_name
from neonrp.core.place_nav import canonical_node, join_location, split_location
from neonrp.core.playthrough import read_playthrough
from neonrp.core.registry import SOUL_OWN, _ROLE_SUFFIX, Envelope, Registry, VarSpec, _head, _norm, _read


def _S(reg: Registry) -> dict[str, str]:
    """The pack's composed texts in the run's language (prompts/rpg_pack.<lang>.json, 10-06): they reach the model."""
    from neonrp import prompts
    from neonrp.core.output_lang import prompt_lang

    cache = getattr(reg, "_rpg_s", None)  # once per load: the run's language does not change mid-load (and is costly)
    if cache is None:
        lang = prompt_lang(Path(reg.root)) if getattr(reg, "root", None) else "zh"
        cache = reg._rpg_s = prompts.strings("rpg_pack", lang)
    return cache


def load(reg: Registry, root: Path) -> None:
    """Fill the registry from the rpg world layout (the pack's ``load`` seam)."""
    game = root / get_data_dir_name(root)
    run_state = _read(reg, game / "meta" / "run_state.json") or {}
    loc = run_state.get("location") if isinstance(run_state.get("location"), dict) else {}
    town_id = str(loc.get("node_id") or "") or None
    node = canonical_node(str(loc.get("subnode_id") or loc.get("node") or "") or None)
    if node and "/" in node:
        t, n = split_location(node)
        town_id, node = (t or town_id), n
    reg.current_town = town_id
    reg.player_location = join_location(town_id, node) if (town_id and node) else (node or None)
    tl = _read(reg, game / "timeline" / "current.json") or {}
    reg.timeline = {k: tl.get(k) for k in ("day", "period", "clock", "weather", "active_threads") if k in tl}
    reg.texts = {
        "lore": _head(reg, game / "lore" / "story.md", 4000),
        "rumors": _head(reg, game / "lore" / "rumors.md", 800),
        "rules": _rules_text(reg, game),  # game/rules/*.md — read by the referee / combat layers, not by the narrator's base pack
    }
    _load_world(reg, game)
    _load_road(reg, run_state)
    _load_towns(reg, game)
    _load_locations(reg, game)
    _load_dungeons(reg, game)
    _load_ways(reg, game)
    _load_quests(reg, game)
    _load_player(reg, game, run_state)
    _load_souls(reg, root)
    _load_soul_roads(reg, root)
    _load_npcs(reg, game)
    _load_items(reg, game)
    from neonrp.packs.rpg import character_state as _cs, data as _data

    _cs.overlay(reg, int(_data.rules(root).get("npc_hp_default", 8)))  # this run's state over each character's base (10-05)
    _load_variables(reg, game, run_state)


def _load_road(reg: Registry, run_state: dict[str, Any]) -> None:
    j = run_state.get("travel") if isinstance(run_state.get("travel"), dict) else None
    add_road(reg, j)


def _load_soul_roads(reg: Registry, root: Path) -> None:
    """A character on a road of her own (travel.soul_set_out, 10-23): that road is a place too, so the away line and
    the map judge see 「在路上」 and not a bare id."""
    from neonrp.packs.rpg import travel

    for e, j in travel.soul_journeys(root, reg):
        if str(e.parent).startswith("road_") and e.parent not in reg.entries:
            add_road(reg, {**j, "day": max(0, int(j.get("days") or 0) - travel.soul_days_left(reg, j))})


def add_road(reg: Registry, j: dict[str, Any] | None) -> None:
    """While run_state.travel exists the party is on the road: a place of its own (parent world), so the pack, the
    souls' presence and the map judge all see 「在路上」 instead of the gate they left from."""
    if not j or not j.get("to"):
        return
    from neonrp.packs.rpg.travel import road_id

    wid = getattr(reg, "_world_id", None) or next((e.id for e in reg.of_class("world")), "world")
    st = j.get("pending") or {}
    a = reg.entries.get(str(j.get("from")))
    b = reg.entries.get(str(j.get("to")))
    reg.add(Envelope(road_id(str(j["from"]), str(j["to"])), "road", wid, [],
                     {"name": _S(reg)["road_name"].format(a=a.name if a else j["from"], b=b.name if b else j["to"]), "from": j["from"], "to": j["to"],
                      "day": j.get("day"), "days": j.get("days"),
                      "stop_text": (_S(reg)["road_blocked"].format(text=st.get("text")) if st else _S(reg)["road_clear"])},
                     aliases={"路上", "驿路", "the road"}, source="game/meta/run_state.json"))


def _load_ways(reg: Registry, game: Path) -> None:
    """The roads out of where the player stands, as places a move may name (its map id / its name → the road, 10-19:
    the prose stopped on the trail and the state had nowhere to stand but the dungeon's door). ``way``: nobody is on
    it — the pack does not list it; travel.set_out puts the party there."""
    from neonrp.packs.rpg.travel import road_id

    routes = (_read(reg, game / "world" / "world_map.json") or {}).get("routes") or []
    on = reg.entries.get(reg.player_location or "")
    if on is not None and on.cls == "road":  # on the road already: its map id / name still name it
        r = next((r for r in routes if isinstance(r, dict) and {str(r.get("from")), str(r.get("to"))} == {on.props.get("from"), on.props.get("to")}), None)
        if r is not None:
            reg.add(Envelope(on.id, on.cls, on.parent, list(on.links), dict(on.props),
                             aliases={*on.aliases, *(str(x) for x in (r.get("id"), r.get("name")) if x)}, source=on.source))
        return
    here = reg.current_town
    if not here:
        return
    wid = getattr(reg, "_world_id", None) or "world"
    for r in routes:
        if not isinstance(r, dict) or (r.get("state") or {}).get("blocked") or here not in (str(r.get("from")), str(r.get("to"))):
            continue
        other = str(r.get("to")) if str(r.get("from")) == here else str(r.get("from"))
        rid = road_id(here, other)
        if rid in reg.entries or other not in reg.entries:
            continue
        name = _S(reg)["road_name"].format(a=reg.entries[here].name if here in reg.entries else here, b=reg.entries[other].name)
        reg.add(Envelope(rid, "road", wid, [], {"name": r.get("name") or name, "from": here, "to": other, "way": True},
                         aliases={str(x) for x in (r.get("id"), r.get("name")) if x}, source="game/world/world_map.json"))


def _rules_text(reg: Registry, game: Path) -> str:
    rdir = game / "rules"
    if not rdir.is_dir():
        return ""
    return "\n\n".join(t for t in (_head(reg, p, 3000) for p in sorted(rdir.glob("*.md"))) if t)


def _load_dungeons(reg: Registry, game: Path) -> None:
    """``game/dungeons/<D>/`` — dungeon.json (theme / danger / boss / state), layout.json (rooms + links),
    rooms/<id>.json (description / features / state), encounter_tables.json (per room), loot_tables.json (on the dungeon)."""
    ddir = game / "dungeons"
    if not ddir.is_dir():
        return
    wid = getattr(reg, "_world_id", None) or next((e.id for e in reg.of_class("world")), "world")
    for dd in sorted(p for p in ddir.iterdir() if p.is_dir()):
        d = _read(reg, dd / "dungeon.json") or {}
        did = str(d.get("id") or dd.name)
        st = d.get("state") if isinstance(d.get("state"), dict) else {}
        boss = d.get("boss") if isinstance(d.get("boss"), dict) else {}
        loot = _read(reg, dd / "loot_tables.json") or {}
        env = reg.entries.get(did)
        props = {"name": d.get("name") or did, "theme": d.get("theme") or "", "danger": d.get("danger"), "recommended_level": d.get("recommended_level"),
                 "boss": boss, "state": st, "state_text": _S(reg)["dg_cleared" if st.get("cleared") else ("dg_found" if st.get("discovered") else "dg_unknown")],
                 "loot": loot.get("tables") or {}, "entrance_from": d.get("entrance_from")}
        if env is not None:  # world_map.json already placed it (type: dungeon → region); re-class it
            env.cls = "dungeon"
            env.props.update(props)
        else:
            env = reg.add(Envelope(did, "dungeon", wid, [], props, source=f"game/dungeons/{dd.name}/dungeon.json"))
        enc = ((_read(reg, dd / "encounter_tables.json") or {}).get("tables")) or {}
        # rooms: their folders (locations/<D>/<room>/, 10-05 MAP-SCALES G3) when the dungeon has them, else layout.json
        from neonrp.core.place_tree import dungeon_rooms

        rooms = dungeon_rooms(reg.root, did)
        from neonrp.packs.rpg import combat as _combat

        _fight = _combat.read(reg.root)
        here_now = {str(_fight.get("at")): [str(f.get("name")) for f in _combat.standing(_fight).values()]} if _fight else {}
        env.links = [f"{did}/{r['id']}" for r in rooms]
        for r in rooms:
            rid = str(r["id"])
            detail = _read(reg, dd / "rooms" / f"{rid}.json") or {}
            rst = detail.get("state") if isinstance(detail.get("state"), dict) else (r.get("state") or {})
            table = [x for x in (enc.get(rid) or []) if isinstance(x, dict)]
            feats = detail.get("features") or []
            reg.add(Envelope(f"{did}/{rid}", "room", did, [f"{did}/{x}" for x in (r.get("links") or [])],
                             {"name": detail.get("name") or r.get("name") or rid, "type": r.get("type") or "room",
                              "description": detail.get("description") or "", "features": feats,
                              "features_text": _S(reg)["list_sep"].join(str(f) for f in feats) or _S(reg)["none"], "state": rst,
                              "encounters": table,
                              # what is here now, not the table's odds (10-19: a 50% row read as foes present after the roll missed)
                              "encounter_text": _S(reg)["list_sep"].join(here_now.get(f"{did}/{rid}") or []) or _S(reg)["none"],
                              "dungeon": did},
                             aliases={rid, str(detail.get("name") or r.get("name") or rid)}, source=f"game/dungeons/{dd.name}/layout.json"))


def _load_quests(reg: Registry, game: Path) -> None:
    """``game/towns/<T>/quests.json`` — the guild board; one ``job`` entry per row, parented to the town."""
    towns = game / "towns"
    if not towns.is_dir():
        return
    for td in sorted(p for p in towns.iterdir() if p.is_dir()):
        data = _read(reg, td / "quests.json") or {}
        for q in data.get("quests") or []:
            if not isinstance(q, dict) or not (q.get("qid") or q.get("id")):
                continue
            qid = str(q.get("qid") or q.get("id"))
            eid = f"{td.name}/{qid}"  # town-scoped like places; the bare qid stays an alias (authors may register their own Q001)
            rw = q.get("reward") if isinstance(q.get("reward"), dict) else {}
            rw_text = _S(reg)["list_sep"].join(x for x in (_S(reg)["gold"].format(n=rw["gold"]) if rw.get("gold") else "",
                                                           (rw.get("item") or {}).get("name", "") if isinstance(rw.get("item"), dict) else "") if x) or _S(reg)["none"]
            known = {"qid", "id", "title", "tier", "summary", "state", "reward", "hooks", "unlocks"}
            extra = {k: v for k, v in q.items() if k not in known}  # open props written in play (progress, clues) come back (10-02 N6)
            reg.add(Envelope(eid, "job", td.name, [],
                             {"name": q.get("title") or qid, "tier": q.get("tier"), "summary": q.get("summary") or "", "state": q.get("state") or "available",
                              "reward": rw, "reward_text": rw_text, "hooks": q.get("hooks") or [], "town": td.name, **extra},
                             aliases={str(q.get("title") or qid)}, source=f"game/towns/{td.name}/quests.json"))  # not the bare qid: authors register their own Q001


def _load_world(reg: Registry, game: Path) -> None:
    from neonrp.core.place_tree import WORLD, is_tree, level_doc

    wm = _read(reg, game / "world" / "world_map.json") or {}
    if is_tree(game.parent):  # tree form: the top place folders are the world's nodes
        wm = level_doc(game.parent, WORLD) or wm
    wid = str(wm.get("world_id") or "world")
    reg.add(Envelope(wid, "world", None, [], {"name": wm.get("name") or wid}, source="game/world/world_map.json"))
    reg._world_id = wid  # type: ignore[attr-defined]
    for n in wm.get("nodes") or []:
        if not isinstance(n, dict) or not n.get("id"):
            continue
        nid = str(n["id"])
        cls = "town" if str(n.get("type") or "town") == "town" else "region"
        reg.add(Envelope(nid, cls, wid, [str(x) for x in n.get("links") or []],
                         {k: v for k, v in n.items() if k not in ("id", "links", "pos")},
                         source="game/world/world_map.json"))


def _load_towns(reg: Registry, game: Path) -> None:
    from neonrp.core.place_tree import folder_nodes, level_doc, level_in_folders, level_label, town_ids

    root = game.parent
    towns = game / "towns"
    tids = [p.name for p in sorted(towns.iterdir()) if p.is_dir()] if towns.is_dir() else []
    tids += [t for t in town_ids(root) if t not in tids]  # tree form: a world place with places inside is a town level
    wid = getattr(reg, "_world_id", "world")
    for tid in tids:
        td = towns / tid
        town = _read(reg, td / "town.json") or {}
        env = reg.entries.get(tid) or reg.add(Envelope(tid, "town", wid, [], {}, source=f"game/towns/{tid}/town.json"))
        env.cls = "town"
        env.props.update({k: v for k, v in town.items() if k not in ("id",)})
        env.props.setdefault("name", town.get("name") or tid)
        folders = level_in_folders(root, tid)
        tmap = (level_doc(root, tid) or {}) if folders else (_read(reg, td / "town_map.json") or {})
        recs = {n["id"]: f / "location.json" for n, f in folder_nodes(root, tid)} if folders else {}
        legacy_src = level_label(root, tid) if folders else f"game/towns/{tid}/town_map.json"
        for n in tmap.get("nodes") or []:
            if not isinstance(n, dict) or not n.get("id"):
                continue
            nid = str(n["id"])
            pid = join_location(tid, nid)
            links = [join_location(tid, str(x)) for x in n.get("links") or []]
            props = {"name": n.get("name") or nid, "type": n.get("type") or "", "node": nid}
            for k in ("summary", "description", "tags", "notes", "enter_if", "enter_refused"):  # a place folder's own record carries these
                if n.get(k):
                    props[k] = n[k]
            if n.get("facility_file"):
                props["facility_file"] = n["facility_file"]
                fac = _read(reg, td / "facilities" / str(n["facility_file"])) if not str(n["facility_file"]).startswith("/") else None
                if not isinstance(fac, dict):
                    fac = _read(reg, td / str(n["facility_file"]))
                if isinstance(fac, dict):
                    props["facility"] = {k: v for k, v in fac.items() if k not in ("facility_id", "rumor_pool_ref")}
            if n.get("parent"):  # one layer down, inside another place: in and out through it (10-02)
                props["within"] = join_location(tid, str(n["parent"]))
                links.append(props["within"])
            aka = {str(a) for a in n.get("aliases") or []}
            # a place folder's record is its source (patches land there); an old town map is one file for all
            src = str(recs[nid].relative_to(root)) if nid in recs else legacy_src
            e = Envelope(pid, "place", tid, links, props, aliases={nid, *aka}, source=src)
            reg.add(e)
        for n in tmap.get("nodes") or []:
            if isinstance(n, dict) and n.get("id") and n.get("parent"):
                up = reg.entries.get(join_location(tid, str(n["parent"])))
                me = join_location(tid, str(n["id"]))
                if up is not None and me not in up.links:
                    up.links.append(me)


def _load_locations(reg: Registry, game: Path) -> None:
    """``game/locations/*.json`` — merge into town nodes by canonical id or name; else standalone."""
    ldir = game / "locations"
    if not ldir.is_dir():
        return
    by_name = {_norm(e.name): e for e in reg.of_class("place")}
    for p in sorted(ldir.glob("*.json")):
        data = _read(reg, p)
        if not isinstance(data, dict) or not data.get("id"):
            continue
        slug = str(data["id"])
        node = canonical_node(slug) or slug
        target: Envelope | None = None
        if reg.current_town and join_location(reg.current_town, node) in reg.entries:
            target = reg.entries[join_location(reg.current_town, node)]
        else:
            for e in reg.of_class("place"):
                if e.props.get("node") == node:
                    target = e
                    break
        if target is None:
            target = by_name.get(_norm(data.get("name")))
        rel = f"game/locations/{p.name}"
        if target is not None:
            target.aliases.add(slug)
            for k in ("summary", "tags", "notes"):
                if data.get(k) and k not in target.props:
                    target.props[k] = data[k]
            target.provenance.setdefault("also", []).append(rel)
            reg._alias.setdefault(_norm(slug), target.id)
            continue
        parent = data.get("parent") or reg.current_town
        links = [str(x) for x in data.get("connections") or []]
        reg.add(Envelope(slug, "place", parent, links,
                         {k: v for k, v in data.items() if k not in ("id", "kind", "connections")},
                         source=rel))
    # scene folders: game/locations/<node>/location.json (tree form: those folders are the map, loaded above)
    from neonrp.core.place_tree import is_tree

    for d in sorted(p for p in ldir.iterdir() if p.is_dir()) if not is_tree(game.parent) else []:
        data = _read(reg, d / "location.json")
        if not isinstance(data, dict) or not data.get("id"):
            continue
        slug = str(data["id"])
        if reg.resolve(slug, cls="place"):
            continue
        reg.add(Envelope(slug, "place", data.get("parent") or reg.current_town,
                         [str(x) for x in data.get("connections") or []],
                         {k: v for k, v in data.items() if k not in ("id", "kind", "connections")},
                         source=f"game/locations/{d.name}/location.json"))


def _load_player(reg: Registry, game: Path, run_state: dict[str, Any]) -> None:
    prof = _read(reg, game / "player" / "profile.json") or {}
    stats = _read(reg, game / "player" / "stats.json") or {}
    wallet = _read(reg, game / "player" / "wallet.json") or {}
    name = prof.get("name") or prof.get("display_name") or "player"
    hp = stats.get("hp") if isinstance(stats.get("hp"), dict) else {"current": stats.get("hp"), "max": stats.get("max_hp")}
    equip = _read(reg, game / "player" / "equipment.json") or {}
    inv = _read(reg, game / "player" / "inventory.json") or {}
    attrs = stats.get("attributes") if isinstance(stats.get("attributes"), dict) else {}
    # the attributes' display names in this run's language (stats.json "attribute_labels" {id: label}, a world's i18n layer
    # writes them; the ids stay — rules and checks name them, 10-16: an en run's sheet read 体4 技4)
    labels = stats.get("attribute_labels") if isinstance(stats.get("attribute_labels"), dict) else {}
    skills = [x for x in (stats.get("skills") or []) if isinstance(x, dict)]
    mp = stats.get("mp") if isinstance(stats.get("mp"), dict) else {}
    weapon = equip.get("weapon") if isinstance(equip.get("weapon"), dict) else {}
    armor = equip.get("armor") if isinstance(equip.get("armor"), dict) else {}
    bag = [x for x in (inv.get("items") or []) if isinstance(x, dict)]
    # the one-line character sheet the narrator sees (v2's referee / combat agents read these files themselves)
    S = _S(reg)
    sheet = S["sheet_sep"].join(x for x in (
        (S["sheet_attrs"] + " ".join(f"{labels.get(k) or k.upper()}{v}" for k, v in attrs.items())) if attrs else "",
        (S["sheet_skills"] + S["list_sep"].join(f"{x.get('name')}({x.get('desc')})" if x.get("desc") else str(x.get("name")) for x in skills)) if skills else "",
        S["sheet_weapon"].format(name=weapon.get("name"), atk=weapon.get("atk"), dmg=weapon.get("base_damage")) if weapon else "",
        S["sheet_armor"].format(name=armor.get("name"), defense=armor.get("def")) if armor else "",
        (S["sheet_bag"] + S["list_sep"].join(f"{x.get('name')}×{x.get('qty', 1)}" for x in bag)) if bag else "",
    ) if x)
    reg.add(Envelope("player", "player", reg.player_location, [],
                     {"name": name, "class": prof.get("class"), "hp": hp.get("current"), "max_hp": hp.get("max"),
                      "mp": mp.get("current"), "max_mp": mp.get("max"), "level": stats.get("level"),
                      "gold": wallet.get("gold"), "background": prof.get("background") or "", "summary": prof.get("summary") or "",
                      "origin": prof.get("origin") or "", "attributes": attrs, "skills": skills,
                      "weapon": weapon, "armor": armor, "accessories": equip.get("accessories") or [], "inventory": bag, "sheet": sheet},
                     aliases={"player", "玩家", "you", "你", str(name)}, source="game/player/profile.json"))


_SHEET_KNOWN = ("sid", "hp", "max_hp", "attributes", "skills", "name", "sheet", "active", "persona")


def _load_souls(reg: Registry, root: Path) -> None:
    pt = read_playthrough(root)
    if pt is None:
        return
    for ref in pt.souls:
        sd = root / "souls" / f"{ref.sid}-{ref.instance_id}"
        sj = _read(reg, sd / "soul.json") or {}
        rs = _read(reg, sd / "run_state.json") or {}
        st = rs.get("status") if isinstance(rs.get("status"), dict) else {}
        # her hp lives on her own sheet (character/stats.json) — the one copy that is written (10-05: the combat layer hit
        # 「foe1」 instead of Elena); run_state.status.hp is only a fallback for souls without a sheet
        cs = _read(reg, sd / "character" / "stats.json") or {}
        if cs.get("hp") is not None:
            st = {**st, "hp": cs.get("hp"), "max_hp": cs.get("max_hp", st.get("max_hp") or cs.get("hp"))}
        raw_loc = str(rs.get("location") or "")
        t, n = split_location(raw_loc)
        n = canonical_node(n)
        if n and not t and not n.startswith("road_"):  # a road is nobody's town (her own road, 10-23)
            t = reg.current_town
        loc = join_location(t, n) if (t and n) else (t or n or None)
        if loc and loc not in reg.entries:
            # a bare town id or unknown node: keep as-is for the chain
            pass
        names = {sj.get("name"), sj.get("name_local"), ref.sid, ref.instance_id, *(sj.get("aliases") or [])}  # aliases: a form's old names
        persona = _head(reg, sd / "soul.md", 900)
        rules = _head(reg, sd / "rules" / "decision_rules.md", 500)
        traits = _read(reg, sd / "persona" / "core_traits.json") or {}
        motiv = _read(reg, sd / "persona" / "motivations.json") or {}
        rel = _read(reg, sd / "persona" / "relationships.json") or {}
        memo = _read(reg, sd / "short-term-memo" / "recent_events.json") or {}
        events = [e for e in (memo.get("events") or []) if isinstance(e, dict)][-5:]
        reg.add(Envelope(ref.instance_id, "soul", loc, [],
                         {"name": sj.get("name_local") or sj.get("name") or ref.sid, "name_en": sj.get("name"),
                          "sid": ref.sid, "role": ref.role, "mood": st.get("mood"), "hp": st.get("hp"),
                          "max_hp": st.get("max_hp"), "persona": persona, "rules": rules,
                          # her own sheet's numbers, as an NPC record's (checks / dying / combat read them off the entry)
                          **{k: cs[k] for k in ("attributes", "skills") if cs.get(k) is not None},
                          # what the world wrote on her sheet (arrows, a wound, gear: patch <her> …), never her own side
                          **{k: v for k, v in cs.items() if k not in _SHEET_KNOWN and k not in SOUL_OWN},
                          "sheet": f"souls/{sd.name}/character/stats.json" if (sd / "character" / "stats.json").is_file() else "",
                          "personality": traits.get("personality_type") or "",
                          "traits": [str(t.get("trait")) for t in (traits.get("core_traits") or []) if isinstance(t, dict) and t.get("trait")][:6],
                          "goals": [str(g) for g in (motiv.get("motivations") or motiv.get("goals") or []) if isinstance(g, str)][:6],
                          "relationships": {k: v for k, v in (rel.get("relationships") or {}).items() if isinstance(v, dict) and v.get("known", True)},
                          "recent": [{"turn": e.get("turn"), "event": str(e.get("event") or "")[:160], "my_reaction": str(e.get("my_reaction") or "")[:120]} for e in events],
                          "trust": (st.get("trust") or {}).get("player") if isinstance(st.get("trust"), dict) else None,
                          "intention": st.get("intention"),
                          "active": ref.instance_id in (pt.active_souls or [])},
                         aliases={str(x) for x in names if x}, source=f"souls/{sd.name}/soul.json"))


def _load_npcs(reg: Registry, game: Path) -> None:
    towns = game / "towns"
    if towns.is_dir():
        for td in sorted(p for p in towns.iterdir() if p.is_dir()):
            data = _read(reg, td / "npcs.json") or {}
            for n in data.get("npcs") or []:
                if not isinstance(n, dict) or not n.get("id"):
                    continue
                nid = str(n["id"])
                eid = nid if nid not in reg.entries else f"{td.name}/{nid}"
                raw_name = str(n.get("name") or nid)
                short = _ROLE_SUFFIX.sub("", raw_name).strip()
                at = n.get("location")
                parent = join_location(td.name, canonical_node(str(at))) if at else td.name
                reg.add(Envelope(eid, "npc", parent, [],
                                 {"name": short or raw_name, "full_name": raw_name, "role": n.get("role"),
                                  "traits": n.get("traits"), "state": n.get("state"), "town": td.name,
                                  # the record's own sheet, when it has one: the base Character State lays this run over
                                  **{k: n[k] for k in ("hp", "max_hp", "attributes", "skills") if n.get(k) is not None}},
                                 aliases={raw_name, short, nid}, source=f"game/towns/{td.name}/npcs.json"))
    ndir = game / "npc"
    if ndir.is_dir():
        for p in sorted(ndir.glob("*.json")):
            n = _read(reg, p)
            if isinstance(n, dict) and n.get("id"):
                reg.add(Envelope(str(n["id"]), "npc", n.get("location") or reg.current_town, [],
                                 {k: v for k, v in n.items() if k != "id"}, source=f"game/npc/{p.name}"))


def _load_items(reg: Registry, game: Path) -> None:
    for d in ("item", "items"):
        idir = game / d
        if not idir.is_dir():
            continue
        for p in sorted(idir.rglob("*.json")):
            n = _read(reg, p)
            if isinstance(n, dict) and n.get("id"):
                reg.add(Envelope(str(n["id"]), "item", n.get("owner") or n.get("location"), [],
                                 {k: v for k, v in n.items() if k != "id"},
                                 source=str(p.relative_to(game.parent))))


def _load_variables(reg: Registry, game: Path, run_state: dict[str, Any]) -> None:
    g = get_data_dir_name(reg.root)
    stats = _read(reg, game / "player" / "stats.json") or {}
    wallet = _read(reg, game / "player" / "wallet.json") or {}
    flags = _read(reg, game / "player" / "flags.json") or {}
    hp = stats.get("hp") if isinstance(stats.get("hp"), dict) else None

    def var(name: str, typ: str, path: str, key: str, value: Any, **kw: Any) -> None:
        reg.variables[name] = VarSpec(name, typ, path, key, value, **kw)

    var("location", "str", f"{g}/meta/run_state.json", "location.node", reg.player_location, readonly=True)
    t = run_state.get("time") if isinstance(run_state.get("time"), dict) else {}
    var("time.day", "int", f"{g}/meta/run_state.json", "time.day", t.get("day", 1), min=1, max_step=1, monotonic=True)
    var("time.clock", "str", f"{g}/meta/run_state.json", "time.clock", t.get("clock", ""), monotonic=True, carry="time.day")
    if hp is not None:
        var("player.hp", "int", f"{g}/player/stats.json", "hp.current", hp.get("current"), min=0, max_key="hp.max")
    for coin in ("gold", "silver", "copper"):
        if coin in wallet:
            var(f"player.{coin}", "int", f"{g}/player/wallet.json", coin, wallet.get(coin), min=0)
    from neonrp.packs.rpg.combat import foe_vars

    from neonrp.packs.rpg import character_state as _cs

    _cs.register_vars(reg, var)
    for fid, f in foe_vars(reg.root).items():  # a fight under way: foes are variables (hp / status), written through ops like everything else
        ref = reg.entries.get(str(f.get("ref") or ""))
        if ref is not None and _cs.has_hp(reg, ref.cls):  # a character on the other side: her own hp (her state), not a copy (10-05)
            var(f"foe.{fid}.hp", "int", _cs.rel_path(reg.root, ref.id), "hp", ref.props.get("hp", f.get("hp")), min=0,
                max=ref.props.get("max_hp"), doc=f"{f.get('name')} hp → 0 = down (her own state)")
        else:
            var(f"foe.{fid}.hp", "int", f"{g}/meta/run_state.json", f"combat.foes.{fid}.hp", f.get("hp"), min=0, max_key=f"combat.foes.{fid}.max_hp",
                doc=f"{f.get('name')} hp → 0 = down")
        var(f"foe.{fid}.status", "str", f"{g}/meta/run_state.json", f"combat.foes.{fid}.status", f.get("status") or "")
    if reg.current_town:
        town = _read(reg, game / "towns" / reg.current_town / "town.json") or {}
        if isinstance(town.get("state"), dict) and "alert" in town["state"]:
            var("town.alert", "int", f"{g}/towns/{reg.current_town}/town.json", "state.alert", town["state"]["alert"], min=0, max=5)
    for k, v in (flags.get("reputation") or {}).items():  # flag.* are the core's (pack.flags)
        var(f"reputation.{k}", "int", f"{g}/player/flags.json", f"reputation.{k}", v)


