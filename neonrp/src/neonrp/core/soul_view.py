"""The world's narration for a soul: the player and the souls are players alike. The player reads the
world's prose and acts; a soul reads the world's prose — from where she stands — and acts. Not a list of blocks.

    after a turn   write_views(): the turn's narration retold from each present soul's view (second person, only what
                   she could see and hear), appended to her soul folder ``short-term-memo/perceived.json``. It is
                   also what she remembers of the turn.
    her next beat  beat_text(): her last views + the player's beat as she meets it (the gate's ``seen``: actions and
                   spoken words, never thoughts) + her own context (from her soul folder) + what she must know (time,
                   where, who is here, where one can go). The player's items and the place's contents are not listed —
                   she finds them in the world, as the player does.

No judge model → the views are the narration as told (marked as such) and the beat is ``旅人说:「…」``.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

PERCEIVED = ("short-term-memo", "perceived.json")
OWN_MARK = "【你自己】"  # the line where the prose ends and her own context begins (soul_step reads the beat before it)

OWN_MARKS = ("【你自己】", "[Yourself]", "【あなた自身】", "[너 자신]")  # every language's mark: any of them splits a beat


def _L(root: Path | None) -> dict[str, Any]:
    """This module's strings (src/neonrp/prompts/soul_view.<lang>.json) in the run's language."""
    from neonrp import prompts
    from neonrp.core.output_lang import prompt_lang

    return prompts.strings("soul_view", prompt_lang(root) if root is not None else "zh")


def _f(s: str, /, **kw: Any) -> str:
    for k, v in kw.items():
        s = s.replace("{" + k + "}", str(v))
    return s


def own_mark(root: Path | None) -> str:
    return _L(root)["own_mark"]


def has_own(text: str) -> bool:
    return any(m in (text or "") for m in OWN_MARKS)


def before_own(text: str) -> str:
    """The prose before her own context (whatever language marked it)."""
    cut = [i for i in ((text or "").find(m) for m in OWN_MARKS) if i >= 0]
    return text[: min(cut)] if cut else (text or "")


def _soul_dir(root: Path, iid: str) -> Path | None:
    hits = sorted((root / "souls").glob(f"*-{iid}")) if (root / "souls").is_dir() else []
    return hits[0] if hits else None


def _read(path: Path) -> dict[str, Any]:
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _small_model() -> Any:
    from neonrp.core import system_one as s1

    if s1.LLM_ADAPTER_FACTORY is None and not s1.fallback_judge_preset():
        return None
    try:
        return s1._llm_adapter()
    except Exception:  # noqa: BLE001
        return None


def player_name(reg: Any) -> str:
    p = getattr(reg, "entries", {}).get("player")
    dflt = _L(getattr(reg, "root", None))["traveller"]
    return str(getattr(p, "name", "") or dflt) if p is not None else dflt


def write_views(root: Path, *, narration: str, turn: int, iids: list[str], place: str = "", player: str = "旅人") -> dict[str, str]:
    """Retell the turn for each present soul and append it to her soul folder. Returns {iid: text}."""
    text = (narration or "").strip()
    if not text or not iids:
        return {}
    from neonrp.core.llm import Message

    model = _small_model()
    L = _L(root)
    out: dict[str, str] = {}
    for iid in iids:
        sd = _soul_dir(root, iid)
        if sd is None:
            continue
        name = iid
        try:
            name = str(json.loads((sd / "soul.json").read_text(encoding="utf-8")).get("name") or iid)
        except (OSError, ValueError):
            pass
        view = ""
        if model is not None:
            try:
                res = model.chat([Message(role="system", content=_f(L["view_sys"], player=player)),
                                  Message(role="user", content=_f(L["view_user"], name=name, text=text[-3000:]))])
                view = (getattr(getattr(res, "message", None), "content", None) or "").strip()
            except Exception:  # noqa: BLE001 — a view is best-effort; the narration as told is the fallback
                logger.debug("soul view rewrite failed", exc_info=True)
        if not view:
            view = _f(L["as_told"], player=player, text=text[-1500:])
        f = sd.joinpath(*PERCEIVED)
        d = _read(f)
        beats = d.get("beats") if isinstance(d.get("beats"), list) else []
        beats.append({"turn": turn, "place": place, "text": view[:2000]})
        d["beats"] = beats[-30:]
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        out[iid] = view
    return out


def last_views(root: Path, iid: str, n: int = 2) -> list[str]:
    sd = _soul_dir(root, iid)
    if sd is None:
        return []
    beats = _read(sd.joinpath(*PERCEIVED)).get("beats") or []
    return [str(b.get("text") or "") for b in beats[-n:] if isinstance(b, dict) and b.get("text")]


def seen_fallback(player_text: str, player: str = "旅人", root: Path | None = None) -> str:
    """No small model: the player's words as one spoken line (the gate's ``seen`` replaces this when it runs)."""
    t = re.sub(r"\s+", " ", (player_text or "").strip())
    return _f(_L(root)["said"], player=player, text=t) if t else ""


def own_context(reg: Any, iid: str) -> str:
    """Her own context (from her soul folder, as loaded) + what she must know: time, where, who is here, ways out."""
    me = reg.entries.get(iid)
    if me is None:
        return ""
    here = reg.entries.get(me.parent or "")
    L = _L(getattr(reg, "root", None))
    lines = []
    mood = me.props.get("mood")
    intent = me.props.get("intention") or me.props.get("current_intention")
    lines.append(L["now"] + L["now_sep"].join(x for x in (_f(L["mood"], mood=mood) if mood else "", _f(L["intent"], intent=intent) if intent else "") if x) if (mood or intent) else "")
    # her body this run (her Character State, 10-05): hp, down / dead, the effects on her — it shapes what she does and says
    body = []
    if me.props.get("hp") is not None and me.props.get("max_hp"):
        body.append(_f(L["body_hp"], hp=me.props.get("hp"), max=me.props.get("max_hp")))
    if int(me.props.get("dead") or 0):
        body.append(L["body_dead"])
    elif int(me.props.get("down") or 0):
        body.append(L["body_down"])
    try:
        from neonrp.core import effects as _fx

        fx = [e.name + (f"({e.props['rule']})" if e.props.get("rule") else "") for e in _fx.instances(reg, iid)]
    except Exception:  # noqa: BLE001
        fx = []
    if fx:
        body.append(_f(L["body_fx"], fx=L["list_sep"].join(fx)))
    if body:
        lines.append(L["body"] + L["now_sep"].join(body))
    own = me.props.get("inventory") or me.props.get("items")
    if isinstance(own, list) and own:
        lines.append(L["carrying"] + L["list_sep"].join(str(x.get("name") if isinstance(x, dict) else x) for x in own[:12]))
    tl = getattr(reg, "timeline", {}) or {}
    when = _f(L["when"], day=tl.get('day', '?'), clock=tl.get('clock') or '').strip()
    present = [e.name for e in [*reg.of_class("soul"), *reg.of_class("npc")] if e.id != iid and e.parent == me.parent]
    if reg.player_location == me.parent:
        present.insert(0, player_name(reg))
    exits = [e.name for e in reg.exits(me.parent)] if me.parent else []
    lines.append(_f(L["moment"], when=when, here=here.name if here else '?') + (_f(L["present"], names=L["list_sep"].join(present)) if present else "")
                 + (_f(L["exits"], names=L["list_sep"].join(exits)) if exits else ""))
    return "\n".join(x for x in lines if x)


def beat_text(root: Path, reg: Any, iid: str, *, seen: str) -> str:
    """What a soul reads this beat: the world's prose for her, the player's beat as she meets it, then her context."""
    views = last_views(root, iid)
    if not views:  # the first beat: where she stands, told plainly
        me = reg.entries.get(iid)
        here = reg.entries.get(me.parent or "") if me is not None else None
        if here is not None:
            views = [_f(_L(root)["you_are_at"], place=here.name) + str(here.props.get("summary") or here.props.get("description") or "")[:400]]
    parts = ["\n\n".join(views), seen, own_mark(root) + "\n" + own_context(reg, iid)]
    return "\n\n".join(p for p in parts if p and p.strip())


def split_beat(situation: str) -> tuple[str, str]:
    """(scene, the player's beat) from a beat_text — the judge reads the beat; the scene is everything before it."""
    prose = before_own(situation).strip()
    paras = [p for p in prose.split("\n\n") if p.strip()]
    if len(paras) < 2:
        return prose, prose
    return "\n\n".join(paras[:-1]), paras[-1]
