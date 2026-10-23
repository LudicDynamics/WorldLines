"""凑齐 — the open engine's way for several people to play one turn (10-10).

Each person in the world plays a character; a second human joins as a ``character`` seat (net.seats). Before the plain
turn settles, every human-played character in the player's scene is asked what they do this turn — all at once, each
until they answer or the hard deadline passes (soul_remote.HUMAN_TIMEOUT). Their words go to the narrator as those
characters' intents; whoever did not answer hesitates this turn (never stood in for: their words are only theirs).

There is no host model here: the engine just asks and gathers. Ludic Dynamics' planning beat (private) does the same
the natural way — a group chat where the host turns to whoever has not decided.
"""
from __future__ import annotations

import concurrent.futures as cf
from pathlib import Path
from typing import Any


def human_characters_here(root: Path) -> list[str]:
    """Instance ids of the characters people are playing right now, in the player's scene."""
    from neonrp.core import light_chat, soul_remote
    from neonrp.core.playthrough import read_playthrough

    humans = [i for i in soul_remote.remote_iids() if soul_remote.is_human(i)]
    if not humans:
        return []
    pt = read_playthrough(root)
    if pt is None:
        return []
    here = light_chat._player_node(root)
    out = []
    for s in pt.souls:
        if s.instance_id not in humans:
            continue
        d = root / "souls" / f"{s.sid}-{s.instance_id}"
        node = light_chat._soul_node(root, d) if d.is_dir() else None
        if not (node and here and node != here):  # same place (or unknown: treat as here)
            out.append(s.instance_id)
    return out


def collect(root: Path, player_line: str = "") -> list[dict[str, Any]]:
    """Ask every human-played character here what they do this turn (in parallel) → reports for the narrator."""
    iids = human_characters_here(root)
    if not iids:
        return []
    from neonrp import prompts
    from neonrp.core import light_chat
    from neonrp.core.output_lang import prompt_lang

    q = str(prompts.strings("light_chat", prompt_lang(root)).get("gather_q") or "What do you do this turn?")
    if player_line:
        q = f"{q}\n\n> {player_line}"
    out: list[dict[str, Any]] = []
    with cf.ThreadPoolExecutor(max_workers=min(8, len(iids))) as ex:
        futs = {ex.submit(light_chat.ask_soul_deliver, root, iid, q, asker="gather"): iid for iid in iids}
        for f in cf.as_completed(futs):
            try:
                r = f.result()
            except Exception:  # noqa: BLE001
                continue
            if r.get("ok"):
                out.append({"iid": r["iid"], "name": r.get("name"), "kind": "intent", "text": r.get("answer") or "",
                            **({"hesitated": True} if r.get("hesitated") else {})})
    return sorted(out, key=lambda x: iids.index(x["iid"]))
