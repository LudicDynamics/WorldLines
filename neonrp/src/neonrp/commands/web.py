"""`neonrp web` — the web runtime: play + observe every agent, in a browser.

M18 §6 made frontends pure subscribers; this is the second frontend after the
TUI. A tiny stdlib HTTP server (no new dependencies) wraps ONE
ConversationSession (in-process continuity, like the REPL) and pushes the
orchestration live to the page over Server-Sent Events:

- narration streams into the left pane (play surface);
- every agent gets a lane on the right (world-agent, each soul, player-agent)
  with live status lights, speech/action/movement extracted from the per-turn
  bus messages — "watch every agent act, live and talk";
- the bottom timeline accumulates turns (turn_seq · location · commit).

Event kinds over /events: hello · turn_start · chunk · soul_status · tool ·
trace · turn_done. Player input arrives via POST /cmd (409 while a turn is
running — one turn at a time, M18 §3.3 lockstep).
"""

from __future__ import annotations

import json
import logging
import os
import queue
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from pathlib import Path
from typing import Any

import click

from neonrp.core.conversation import ConversationSession
from neonrp.core.orchestration_trace import read_turn_traces
from neonrp.core.paths import get_manifest_path, get_project_root
from neonrp.core.runtime_contract import get_startup_entry_agent
from neonrp.webui.engine_routes import EngineRoutes
from neonrp.net.host import NetRoutes
from neonrp.webui.http_util import HttpMixin
from neonrp.webui.launcher_routes import LauncherRoutes


# Tool failures that are EXPECTED guardrail/recoverable feedback — the agent
# gets the message and recovers (re-routes through a proposal, fixes its path,
# retries a unique edit). These are warnings, not red errors, in the UI.
_SOFT_TOOL_ERROR_MARKERS = (
    "direct_write_globs",   # write-scope guardrail → use submit_proposal
    "submit_proposal",
    "not in write",         # write-scope guardrail (variant phrasing)
    "file not found",       # agent guessed a path; it recovers
    "must be unique",       # edit_file matched >1 site; agent retries
    "found 2 times",
    "must be different",    # edit_file no-op guard
)


def _tool_error_severity(error: str) -> str:
    """Classify a tool error string: 'warning' (recoverable guardrail) or 'error'."""
    low = error.lower()
    if any(marker in low for marker in _SOFT_TOOL_ERROR_MARKERS):
        return "warning"
    return "error"


def _billing_payload(error: Any) -> dict[str, Any] | None:
    """A turn stopped by Worldlines billing (core/billing_stop.py) → {code, kind, billing_url, message, messages}."""
    from neonrp.core import billing_stop

    stop = billing_stop.remember(billing_stop.from_text(error))
    return stop.to_dict() if stop else None


class _Broadcast:
    """Fan-out of JSON events to every connected SSE client."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._clients: list[queue.Queue] = []

    def register(self) -> queue.Queue:
        q: queue.Queue = queue.Queue()
        with self._lock:
            self._clients.append(q)
        return q

    def unregister(self, q: queue.Queue) -> None:
        with self._lock:
            if q in self._clients:
                self._clients.remove(q)

    def publish(self, event: dict[str, Any]) -> None:
        with self._lock:
            clients = list(self._clients)
        for q in clients:
            q.put(event)


def _run_branch(root: Path) -> str:
    try:
        data = json.loads((root / ".neonrp" / "manifest.json").read_text(encoding="utf-8"))
        return str(data.get("current_branch") or "main")
    except (OSError, ValueError):
        return "main"


class WebRuntime:
    """One playthrough session + its event fan-out. One turn at a time."""

    def __init__(
        self,
        root: Path,
        agent_id: str,
        startup_commands: list[str] | None = None,
        reopen: bool = False,
    ) -> None:
        self.root = root
        self.agent_id = agent_id
        try:  # the model calls of this run say which world (X-Worldlines-World; billing pays run points on them, 10-21)
            from neonrp.core import chronicle as _chron

            _chron._bind_world(Path(root))
        except Exception:  # noqa: BLE001 — never stops a run
            pass
        # 接着一局(不是新开的):startup_commands 只在这一局一个回合都没有时才给(开场那一拍当时没跑完 —— 关了页 / 模型出错 /
        # 额度用完),kickoff 看回合记录、不看 sessions/(那一拍跑过一半就写了 sessions,之前续这种档永远不再开场,舞台全空,10-16)
        self._reopen = reopen
        self.broadcast = _Broadcast()
        from neonrp.core import run_lock

        self._busy = run_lock.of(root)  # one writer per run: shared with whatever else writes this run (core/run_lock)
        self._session: ConversationSession | None = None
        # The localized opening message (already locale-resolved by the
        # launcher's _build_startup_handoff). On a NEW game the world-agent
        # should play this opening; web previously dropped it. Fired once,
        # on the first /start call — see kickoff().
        self._startup_commands = list(startup_commands or [])
        self._kickoff_done = threading.Lock()
        self._kickoff_fired = False

    # -- locale -----------------------------------------------------------
    def locale(self) -> str:
        from neonrp.tui.i18n import resolve_locale

        return resolve_locale()

    def i18n(self) -> dict[str, Any]:
        from neonrp.webui.i18n import web_strings

        return web_strings(self.locale())

    # -- startup kickoff --------------------------------------------------
    def kickoff(self) -> bool:
        """Submit the localized opening once, on a fresh game.

        Returns True if a kickoff turn was started. Guards against double-fire
        on refresh: a one-shot flag PLUS a check that the game hasn't already
        logged a session (orchestrator/fast/mcp all write .neonrp/sessions/).
        """
        with self._kickoff_done:
            if self._kickoff_fired or not self._startup_commands:
                return False
            self._kickoff_fired = True
        from neonrp.worlds import _is_game_started

        if self._reopen:
            if read_turn_traces(self.root, self._branch(), last=1):
                return False
        elif _is_game_started(self.root):
            return False
        return self.submit(self._startup_commands[0])

    # -- session ----------------------------------------------------------
    def session(self) -> ConversationSession:
        if self._session is None:
            self._session = ConversationSession(
                root=self.root, agent_id=self.agent_id, mode="play"
            )
            self._wire_bus(self._session)
        return self._session

    def _wire_bus(self, session: ConversationSession) -> None:
        """M18 §6 / Phase 4.3 — the web frontend is a PURE SUBSCRIBER of the
        session bus (engine/stream + engine/event), not a callback sink. One
        durable subscription per topic; fan-out to SSE clients."""
        bus = session.bus()

        def _on_stream(msg: Any) -> None:
            p = msg.payload
            k = p.get("kind")
            if k == "chunk":
                self.broadcast.publish({"kind": "chunk", "text": p.get("text", ""), **({"beat": p["beat"]} if p.get("beat") else {})})
            elif k == "thinking":
                # Thinking renders in the agent lane (right), never the story pane.
                self.broadcast.publish({"kind": "thinking", "text": p.get("text", "")})

        def _on_event(msg: Any) -> None:
            p = msg.payload
            kind = p.get("kind")
            if kind == "soul_status":
                self.broadcast.publish(
                    {"kind": "soul_status", "statuses": p.get("statuses", {})}
                )
            elif kind == "tool_use":
                self.broadcast.publish({"kind": "tool", "name": p.get("name", "")})
            elif kind == "tool_result" and p.get("status") == "error":
                _err = str(p.get("error", ""))
                self.broadcast.publish(
                    {
                        "kind": "agent_error",
                        "severity": _tool_error_severity(_err),
                        "tool": p.get("name", ""),
                        "target": p.get("target", ""),
                        "error": _err,
                    }
                )

        def _on_soul_response(msg: Any) -> None:
            """Forward each soul's per-turn psyche to the browser as a
            ``soul_psyche`` SSE event (feature A 双栏灵魂心象). The soul report
            is published off the bus on ``soul/<iid>/response``; we re-broadcast
            only the psyche fields the 灵魂心象 panel needs. Defensive: missing
            fields default to "" / 0.0 so a malformed payload never breaks the
            stream."""
            p = msg.payload

            def _f(key: str) -> float:
                try:
                    return float(p.get(key) or 0.0)
                except (TypeError, ValueError):
                    return 0.0

            state = str(p.get("state") or "completed")
            self.broadcast.publish(
                {
                    "kind": "soul_psyche",
                    "instance_id": str(p.get("instance_id") or ""),
                    "inner_voice": str(p.get("inner_voice") or ""),
                    "confidence": _f("confidence"),
                    "urgency": _f("urgency"),
                    "memory_delta": str(p.get("memory_delta") or ""),
                    "state": state,
                }
            )

        def _on_beat(msg: Any) -> None:
            """Each beat's events the moment it lands (10-14: the planning talk that ends in the switch reaches the page
            as its own segment while the Resolve is still running — not both together at turn_done)."""
            p = dict(msg.payload or {})
            live = getattr(self, "_live_beats", None)
            if live is None:
                # the background write-down lands after the turn (core/write_down_async, 10-22): its news and the state it
                # corrected go out as they come — no turn's end would catch them up
                if str(p.get("kind") or "").startswith("write_down.") or (p.get("kind") == "state.changed" and p.get("corrected")):
                    self.broadcast.publish(p)
                return  # anything else outside a turn of this server (a TUI on the same session): the turn's end catches up
            live.append(p)
            self.broadcast.publish(p)

        bus.subscribe("engine/stream", _on_stream)
        bus.subscribe("engine/event", _on_event)
        bus.subscribe("engine/beat", _on_beat)
        try:  # this run's background write-down reports to this session from now on — not only from its next line (10-23:
            # back into the same run before a new line, the correction's news still went to the session left behind)
            from neonrp.core import write_down_async as _wda

            _wda.listen(session.root, session._write_down_event)
        except Exception:  # noqa: BLE001 — a stand-in session (tests)
            pass
        # Per-soul report topic (soul/<iid>/response) — wildcard so every active
        # soul's psyche reaches the browser.
        bus.subscribe("soul/+/response", _on_soul_response)

    # -- hello / state ----------------------------------------------------
    def hello(self) -> dict[str, Any]:
        souls: list[dict[str, Any]] = []
        try:
            from neonrp.core.playthrough import read_playthrough

            pt = read_playthrough(self.root)
            active_ids = set(pt.active_souls) if pt else set()
            player_loc = self._player_location()
            for s in (pt.souls if pt else []):
                souls.append(
                    {
                        "sid": s.sid,
                        "instance_id": s.instance_id,
                        "role": s.role,
                        "name": self._soul_name(s.sid, s.instance_id),
                        "location": self._soul_location(s.sid, s.instance_id),
                        "where": self._soul_where(s.sid, s.instance_id, active_ids, player_loc),
                        "intro": self._soul_intro(s.sid, s.instance_id),
                    }
                )
        except Exception:  # noqa: BLE001 — hello must never fail the page
            pass
        prof = self._player_profile()
        try:  # R3 (10-09): how this run's beats are shown (the pack's ui.beats), so a reconnect need not fetch it
            from neonrp.core.orchestration import beat_kinds as _beat_kinds

            beat_kinds = _beat_kinds(self.root)
        except Exception:  # noqa: BLE001
            beat_kinds = {"kinds": {}}
        return {
            "kind": "hello",
            "beat_kinds": beat_kinds,
            "world": self.root.name,
            "world_name": self._world_display_name(),
            "agent_id": self.agent_id,
            "pid": "player",
            "souls": souls,
            "player_location": self._player_location(),
            "player_intro": self._player_intro(),
            "player_name": str(prof.get("name_local") or prof.get("name") or ""),
            "player_class": str(prof.get("class") or ""),
            "player_hp": self._player_hp(),
            "places": self._places_map(
                [self._player_location(), *(s.get("location", "") for s in souls)]
            ),
            "world_map": self._world_map(),
            # 物品栏:player folder 全部 + 当前角色一点点,喂
            # ②聊天·画布右栏的背包/物品/状态。数据统一,前端 presenter 消费。
            "player": self._player_entities(),
        }

    def positions(self) -> dict[str, Any]:
        """Current locations of every agent — feeds the map graph."""
        souls: list[dict[str, Any]] = []
        try:
            from neonrp.core.playthrough import read_playthrough

            pt = read_playthrough(self.root)
            active_ids = set(pt.active_souls) if pt else set()
            player_loc = self._player_location()
            for s in (pt.souls if pt else []):
                souls.append(
                    {
                        "instance_id": s.instance_id,
                        "name": self._soul_name(s.sid, s.instance_id),
                        "location": self._soul_location(s.sid, s.instance_id),
                        "where": self._soul_where(s.sid, s.instance_id, active_ids, player_loc),
                        "intro": self._soul_intro(s.sid, s.instance_id),
                    }
                )
        except Exception:  # noqa: BLE001 — map data is best-effort
            pass
        return {
            "kind": "positions",
            "player": self._player_location(),
            "player_hp": self._player_hp(),
            "souls": souls,
            "places": self._places_map(
                [self._player_location(), *(s.get("location", "") for s in souls)]
            ),
        }

    def _player_location(self) -> str:
        try:
            from neonrp.core.paths import get_data_dir_name

            data = json.loads(
                (
                    self.root / get_data_dir_name(self.root) / "meta" / "run_state.json"
                ).read_text(encoding="utf-8")
            )
            from neonrp.core.place_nav import qualify_location

            loc = data.get("location")
            if isinstance(loc, dict):
                raw = str(loc.get("node") or loc.get("node_id") or "")
                town = str(loc.get("node_id") or "")
            else:
                raw, town = str(loc or ""), ""
            # Scoped address ("T###/node") so the map never collapses two
            # towns' same-named spots into one node (the "jumping" bug).
            return qualify_location(self.root, raw, current_town=town or None) or raw
        except (OSError, ValueError):
            return ""

    def _player_intro(self) -> str:
        """Localized 'who is the protagonist' blurb for the player card popup.

        Same locale-resolution as `_soul_intro`: prefers `intro_i18n` in the
        player's `game/player/profile.json` (resolved to the UI locale), so the
        player card description matches the dialogue language. Falls back to the
        profile `summary`/`background` (source-authored) and finally "". """
        try:
            from neonrp.core.i18n_card import card_field
            from neonrp.core.paths import get_data_dir_name

            prof = json.loads(
                (
                    self.root / get_data_dir_name(self.root) / "player" / "profile.json"
                ).read_text(encoding="utf-8")
            )
        except (OSError, ValueError):
            return ""
        intro = card_field(
            prof.get("intro_i18n"),
            self.locale(),
            source_lang=str(prof.get("source_lang") or "en"),
        )
        if intro:
            return intro
        return str(prof.get("summary") or prof.get("background") or "")

    def _player_entities(self) -> dict[str, Any]:
        """物品栏数据源:game/player/ folder 全部 JSON(inventory/
        equipment/stats/profile/flags…)+ 当前主角 soul 的一点展示信息。前端右栏
        背包/物品/状态据此渲染成可点击实体。best-effort、缺文件不炸。"""
        from neonrp.core.paths import get_data_dir_name

        pdir = self.root / get_data_dir_name(self.root) / "player"
        files: dict[str, Any] = {}
        try:
            for f in sorted(pdir.glob("*.json")):
                try:
                    files[f.stem] = json.loads(f.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    continue
        except OSError:
            pass
        # 当前主角(player avatar soul)一点展示信息:名字 + 简介。
        current: dict[str, Any] = {}
        try:
            from neonrp.core.playthrough import read_playthrough

            pt = read_playthrough(self.root)
            for s in (pt.souls if pt else []):
                if str(getattr(s, "role", "")).lower() == "player":
                    current = {
                        "sid": s.sid,
                        "instance_id": s.instance_id,
                        "name": self._soul_name(s.sid, s.instance_id),
                        "intro": self._soul_intro(s.sid, s.instance_id),
                    }
                    break
        except Exception:  # noqa: BLE001 — 展示信息 best-effort
            pass
        return {"files": files, "current_character": current}

    def _player_profile(self) -> dict[str, Any]:
        try:
            from neonrp.core.paths import get_data_dir_name

            data = json.loads(
                (self.root / get_data_dir_name(self.root) / "player" / "profile.json")
                .read_text(encoding="utf-8")
            )
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _player_hp(self) -> dict[str, Any]:
        """The player's HP as {current, max} for the play-pane HUD, or {}."""
        try:
            from neonrp.core.paths import get_data_dir_name

            stats = json.loads(
                (self.root / get_data_dir_name(self.root) / "player" / "stats.json")
                .read_text(encoding="utf-8")
            )
            hp = stats.get("hp") if isinstance(stats, dict) else None
            if isinstance(hp, dict) and hp.get("max"):
                return {"current": hp.get("current"), "max": hp.get("max")}
        except (OSError, ValueError):
            pass
        return {}

    def _world_display_name(self) -> str:
        """Friendly world name for the header (石津镇·艾琳娜 — not the raw game
        dir / agent id). Resolves via the world registry for built-ins; for a
        self-created world (not in the registry) strips the -YYYYMMDD-HHMMSS
        suffix off the dir name."""
        try:
            from neonrp.core.i18n_card import card_name_for_locale
            from neonrp.worlds import WORLDS, infer_world_id_from_game_dir

            wid = infer_world_id_from_game_dir(self.root)
            if wid and wid in WORLDS:
                info = WORLDS[wid]
                return card_name_for_locale(
                    info.get("name", ""),
                    info.get("name_local", ""),
                    self.locale(),
                    source_lang=info.get("source_lang", "en"),
                    name_i18n=info.get("name_i18n"),
                )
        except Exception:  # noqa: BLE001 — header must never fail the page
            pass
        import re

        return re.sub(r"-\d{8}-\d{6}$", "", self.root.name) or self.root.name

    def _soul_name(self, sid: str, iid: str) -> str:
        try:
            data = json.loads(
                (self.root / "souls" / f"{sid}-{iid}" / "soul.json").read_text(
                    encoding="utf-8"
                )
            )
            return str(data.get("name_local") or data.get("name") or sid)
        except (OSError, ValueError):
            return sid

    def _soul_intro(self, sid: str, iid: str) -> str:
        """A short player-facing blurb for the portrait popup, in the UI locale.

        Preferred source is a localized one-liner in the soul's `soul.json`
        (`intro_i18n: {en, zh, ja, ko}`) — resolved through `card_field` to the
        active UI locale, with `source_lang` fallback. The built-in worlds carry
        these, so the card description matches the language the agent narrates
        in (the founder's mismatch report: English card vs Chinese dialogue).

        Falls back to the soul charter (`soul.md`) first prose paragraph when no
        `intro_i18n` exists (imported / non-builtin worlds): the same "who is
        this" text a reader sees up top, trimmed to a couple of sentences so the
        popup stays a card, not a wall of text. Returns "" when there's neither —
        the popup then shows name only.
        """
        # 1. Localized intro from soul.json (builtin/curated worlds).
        try:
            from neonrp.core.i18n_card import card_field

            sj = json.loads(
                (self.root / "souls" / f"{sid}-{iid}" / "soul.json").read_text(
                    encoding="utf-8"
                )
            )
            intro = card_field(
                sj.get("intro_i18n"),
                self.locale(),
                source_lang=str(sj.get("source_lang") or "en"),
            )
            if intro:
                return intro
        except (OSError, ValueError):
            pass
        # 2. Fallback: first prose paragraph of soul.md (verbatim, source lang).
        try:
            text = (self.root / "souls" / f"{sid}-{iid}" / "soul.md").read_text(
                encoding="utf-8"
            )
        except OSError:
            return ""
        para: list[str] = []
        for raw in text.splitlines():
            line = raw.strip()
            if not line:
                if para:  # blank line ends the first paragraph we started
                    break
                continue
            if line.startswith("#"):
                continue  # title / section header — skip
            para.append(line)
        blurb = " ".join(para).strip()
        return blurb[:240].rstrip() + "…" if len(blurb) > 240 else blurb

    def _soul_location(self, sid: str, iid: str) -> str:
        try:
            data = json.loads(
                (self.root / "souls" / f"{sid}-{iid}" / "run_state.json").read_text(
                    encoding="utf-8"
                )
            )
            from neonrp.core.place_nav import qualify_location

            loc = data.get("location")
            raw = loc if isinstance(loc, str) else ""
            # Already-scoped values pass through; legacy bare ids resolve to
            # their (first-match) town so each soul keeps its own town.
            return qualify_location(self.root, raw) or raw
        except (OSError, ValueError):
            return ""

    def _places_map(self, nodes: list[str]) -> dict[str, str]:
        """node id -> friendly place name, for the agent map / labels.

        The browser can't read ``game/locations/*.json``, so resolution must
        happen here. Keyed by the raw node id (which the frontend still uses
        for layout/clustering); the value is the human name (T004 -> 碧石镇)."""
        out: dict[str, str] = {}
        for node in nodes:
            node = (node or "").strip()
            if node and node not in out:
                out[node] = self._location_label(node)
        return out

    def _world_map(self) -> dict[str, Any]:
        """The real world graph for the agent map: town nodes with their
        authored coordinates + routes as edges, plus a sub-location→town map so
        a soul standing in 石津镇·北门 (gate_north) is grouped under its town
        (石津镇). Empty dict when the world ships no world_map (e.g. a freshly
        created world) — the frontend falls back to a synthetic ring layout."""
        from neonrp.core.paths import get_data_dir_name

        from neonrp.core.place_tree import WORLD, level_doc, town_docs

        base = self.root / get_data_dir_name(self.root)
        wm = level_doc(self.root, WORLD)  # world_map.json nodes, or the top place folders (10-05)
        if wm is None:
            return {}

        nodes: list[dict[str, Any]] = []
        for n in wm.get("nodes") or []:
            pos = n.get("pos")
            if not (isinstance(pos, list) and len(pos) >= 2):
                continue
            nid = str(n.get("id") or "")
            if not nid:
                continue
            nodes.append({
                "id": nid,
                "name": self._location_label(nid),
                "pos": [pos[0], pos[1]],
            })

        edges: list[list[str]] = []
        for r in wm.get("routes") or []:
            a, b = r.get("from"), r.get("to")
            if a and b:
                edges.append([str(a), str(b)])

        # sub-location id → parent town id. Two sources, because authored data
        # is inconsistent about where sub-locations live:
        #   1. each town's town_map.json nodes (e.g. inn, gate_north → T001)
        #   2. game/locations/*.json entities, which carry no parent field but
        #      DO name themselves "<town>·<spot>" (石津镇·集市广场) — group by
        #      that name prefix against the town node names.
        # canonical_node aliases are added too (north-gate ↔ gate_north).
        from neonrp.core.place_nav import canonical_node

        subloc_to_town: dict[str, str] = {}
        # Per-town second-level map: town id → {nodes:[{id,name,pos,type}],
        # edges:[[a,b]]}. Lets the frontend drill into a town and show its
        # sub-locations (集市广场, 北门…) laid out by their authored coords.
        town_maps: dict[str, dict[str, Any]] = {}

        def _map(sid: str, tid: str) -> None:
            if not sid or not tid:
                return
            subloc_to_town.setdefault(sid, tid)
            csid = canonical_node(sid)
            if csid:
                subloc_to_town.setdefault(csid, tid)

        # town_map.json or the town's place folders (place_tree, 10-05)
        for tid, tm in town_docs(self.root).items():
            sub_nodes: list[dict[str, Any]] = []
            for sn in tm.get("nodes") or []:
                sid = str(sn.get("id") or "")
                _map(sid, tid)
                pos = sn.get("pos") or {}
                # town_map uses {x,y}; world_map uses [x,y] — normalize.
                if isinstance(pos, dict):
                    xy = [pos.get("x"), pos.get("y")]
                elif isinstance(pos, list) and len(pos) >= 2:
                    xy = [pos[0], pos[1]]
                else:
                    xy = None
                if not sid or not (xy and all(isinstance(v, (int, float)) for v in xy)):
                    continue
                sub_nodes.append({
                    "id": sid,
                    "name": str(sn.get("name") or sid),
                    "pos": [xy[0], xy[1]],
                    "type": str(sn.get("type") or ""),
                })
            sub_edges: list[list[str]] = []
            for r in (tm.get("routes") or tm.get("edges") or []):
                a, b = (r.get("from"), r.get("to")) if isinstance(r, dict) else (
                    (r[0], r[1]) if isinstance(r, list) and len(r) >= 2 else (None, None))
                if a and b:
                    sub_edges.append([str(a), str(b)])
            if sub_nodes:
                town_maps[tid] = {"nodes": sub_nodes, "edges": sub_edges}

        town_id_by_name = {n["name"]: n["id"] for n in nodes if n.get("name")}
        locs_dir = base / "locations"
        if locs_dir.is_dir():
            for lf in locs_dir.glob("*.json"):
                try:
                    ld = json.loads(lf.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    continue
                if not isinstance(ld, dict):
                    continue
                lid = str(ld.get("id") or lf.stem)
                nm = str(ld.get("name") or "")
                if "·" in nm:
                    tid = town_id_by_name.get(nm.split("·", 1)[0])
                    if tid:
                        _map(lid, tid)

        return {
            "nodes": nodes,
            "edges": edges,
            "subloc_to_town": subloc_to_town,
            "town_maps": town_maps,
        }

    def _location_label(self, node: str) -> str:
        """Friendly place name for a node id (riverlamp-inn → 河灯旅店,
        T004 → 碧石镇). Resolves via a canonical-keyed index so data aliases
        (the engine canonicalises ``north-gate`` → ``gate_north``) all map to
        the same name. Falls back to the raw id when nothing is named."""
        if not node:
            return "某处"
        from neonrp.core.place_nav import canonical_node, split_location

        idx = self._place_index()
        if node in idx:
            return idx[node]
        # Scoped "T###/node" → "townname·spotname" (built from parts if the
        # exact scoped key isn't pre-indexed).
        town, sub = split_location(node)
        if town and sub:
            if f"{town}/{sub}" in idx:
                return idx[f"{town}/{sub}"]
            return f"{idx.get(town, town)}·{idx.get(sub, sub)}"
        key = canonical_node(node) or node
        return idx.get(key, node)

    def _place_index(self) -> dict[str, str]:
        """Canonical node id → friendly name, built once per runtime from the
        world_map node graph + per-location/per-town entities. Keys are
        ``canonical_node(id)`` so ``gate_north`` and ``north-gate`` collapse to
        one entry. The browser can't read these files, so this is the single
        server-side source of truth for place labels."""
        cached = getattr(self, "_place_index_cache", None)
        if cached is not None:
            return cached
        from neonrp.core.paths import get_data_dir_name
        from neonrp.core.place_nav import canonical_node

        base = self.root / get_data_dir_name(self.root)
        index: dict[str, str] = {}

        def _add(node_id: Any, name: Any) -> None:
            if node_id and name:
                key = canonical_node(str(node_id)) or str(node_id)
                index.setdefault(key, str(name))

        def _name(data: dict) -> Any:
            return data.get("name_local") or data.get("name") or data.get("display_name")

        # world_map node graph — the authoritative T-node → name table.
        try:
            from neonrp.core.place_tree import WORLD, level_doc

            wm = level_doc(self.root, WORLD) or {}  # world_map.json nodes, or the top place folders (10-05)
            for n in wm.get("nodes") or []:
                _add(n.get("id"), _name(n))
        except (OSError, ValueError):
            pass

        # per-location (locations/<x>.json) + per-town (towns/<x>/town.json)
        for sub, is_dir in (("locations", False), ("towns", True)):
            droot = base / sub
            if not droot.is_dir():
                continue
            for child in droot.iterdir():
                f = (child / "town.json") if is_dir else child
                if f.suffix != ".json":
                    continue
                try:
                    data = json.loads(f.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    continue
                if isinstance(data, dict):
                    _add(data.get("id") or child.stem, _name(data))

        # town_map.json sub-nodes → a scoped label "townname·spotname" (and a
        # bare-id fallback for legacy un-scoped locations, first town wins).
        # This is where the precise spot names (冒险者公会) come from — they
        # don't exist anywhere else in the index.
        from neonrp.core.place_tree import town_docs

        # town_map.json or the town's place folders (place_tree, 10-05)
        for tid, tm in town_docs(self.root).items():
            town_name = index.get(tid, tid)
            for sn in tm.get("nodes") or []:
                sid = canonical_node(str(sn.get("id") or "")) or ""
                if not sid:
                    continue
                spot = str(sn.get("name") or sid)
                index.setdefault(f"{tid}/{sid}", f"{town_name}·{spot}")
                index.setdefault(sid, spot)

        self._place_index_cache = index
        return index

    def image_path(self, kind: str, soul_id: str = "") -> Path | None:
        """Resolve a world cover or a soul portrait to a file, or None.

        Worlds/cards have no art yet — the web UI reserves the space and
        falls back to a placeholder, so this returning None is expected; it
        starts showing real images the moment any are dropped in."""
        exts = (".png", ".jpg", ".jpeg", ".webp", ".gif")
        if kind == "world":
            try:
                from neonrp.core.image_render import discover_world_images

                imgs = discover_world_images(self.root)
                return imgs[0] if imgs else None
            except Exception:  # noqa: BLE001 — art is best-effort
                return None
        if kind == "player":
            from neonrp.core.paths import get_data_dir_name

            pdir = self.root / get_data_dir_name(self.root) / "player"
            stems = ("portrait", "avatar", "face", "card")
            for proot in (pdir / "assets", pdir):
                if not proot.is_dir():
                    continue
                cands = [p for p in proot.rglob("*") if p.is_file() and p.suffix.lower() in exts]
                cands.sort(key=lambda p: (p.stem.lower() not in stems, p.as_posix()))
                if cands:
                    return cands[0]
            return None
        if kind == "soul" and soul_id:
            souls_root = self.root / "souls"
            if not souls_root.is_dir():
                return None
            stems = ("portrait", "avatar", "cover", "face", "card")
            for sdir in souls_root.iterdir():
                if not sdir.is_dir() or not sdir.name.endswith(soul_id):
                    continue
                # Canonical convention: <soul>/assets/ holds the portrait.
                # Fall back to anywhere in the soul folder for tolerance.
                for sroot in (sdir / "assets", sdir):
                    if not sroot.is_dir():
                        continue
                    cands = [p for p in sroot.rglob("*") if p.is_file() and p.suffix.lower() in exts]
                    cands.sort(key=lambda p: (p.stem.lower() not in stems, p.as_posix()))
                    if cands:
                        return cands[0]
        return None

    def portrait_target(self, kind: str, soul_id: str = "") -> tuple[Path | None, str]:
        """生图落点 + 提示词(连生图):返回(assets_dir, prompt),
        assets_dir 与 image_path 读取约定一致(player/assets · souls/<*id>/assets),
        prompt 从实体数据(名字+外貌/描述)拼。找不到实体 → (None, "")。"""
        from neonrp.core.paths import get_data_dir_name

        def _pick(d: dict[str, Any], *keys: str) -> str:
            for k in keys:
                v = d.get(k)
                if isinstance(v, str) and v.strip():
                    return v.strip()
            return ""

        if kind == "player":
            prof = self._player_profile()
            name = _pick(prof, "name_local", "name") or "traveler"
            desc = _pick(prof, "appearance", "look", "description", "desc", "summary", "intro")
            adir = self.root / get_data_dir_name(self.root) / "player" / "assets"
            return adir, f"solo character portrait, {name}. {desc}".strip()
        if kind == "soul" and soul_id:
            souls_root = self.root / "souls"
            if souls_root.is_dir():
                for sdir in souls_root.iterdir():
                    if not sdir.is_dir() or not sdir.name.endswith(soul_id):
                        continue
                    meta: dict[str, Any] = {}
                    try:
                        meta = json.loads((sdir / "soul.json").read_text(encoding="utf-8"))
                    except (OSError, ValueError):
                        meta = {}
                    name = _pick(meta, "name_local", "name") or soul_id
                    desc = _pick(meta, "appearance", "look", "description", "desc", "intro", "summary")
                    if not desc:  # 退到 persona / character/profile
                        for rel in ("persona/appearance.json", "character/profile.json"):
                            try:
                                pj = json.loads((sdir / rel).read_text(encoding="utf-8"))
                                desc = _pick(pj, "appearance", "look", "description", "desc", "summary")
                                if desc:
                                    break
                            except (OSError, ValueError):
                                continue
                    return sdir / "assets", f"solo character portrait, {name}. {desc}".strip()
        return None, ""

    def upload_image(self, kind: str, soul_id: str, ext: str, data: bytes) -> Path | None:
        """Save an uploaded portrait/cover into the SAME folder /image reads.

        - world  → <root>/assets/cover.<ext>
        - soul   → <root>/souls/<sid>-<id>/assets/portrait.<ext>
        - player → <root>/<data>/player/assets/portrait.<ext>

        `soul_id` (= instance_id) is path-traversal guarded by the caller
        (alnum/-/_ only). Returns the written path, or None if no target dir
        could be resolved (e.g. unknown soul). Sibling files with a different
        extension are removed so the new image always wins discovery order.
        """
        if kind == "world":
            dest_dir = self.root / "assets"
            stem = "cover"
        elif kind == "player":
            from neonrp.core.paths import get_data_dir_name

            dest_dir = self.root / get_data_dir_name(self.root) / "player" / "assets"
            stem = "portrait"
        elif kind == "soul" and soul_id:
            souls_root = self.root / "souls"
            sdir = None
            if souls_root.is_dir():
                for cand in souls_root.iterdir():
                    if cand.is_dir() and cand.name.endswith(soul_id):
                        sdir = cand
                        break
            if sdir is None:
                return None
            dest_dir = sdir / "assets"
            stem = "portrait"
        else:
            return None
        dest_dir.mkdir(parents=True, exist_ok=True)
        # Drop stale variants so discovery (which sorts by stem match) shows
        # the just-uploaded file, not an old portrait.png next to a new .webp.
        for old in dest_dir.glob(f"{stem}.*"):
            if old.is_file():
                try:
                    old.unlink()
                except OSError:
                    pass
        dest = dest_dir / f"{stem}.{ext}"
        dest.write_bytes(data)
        return dest

    def _soul_where(self, sid: str, iid: str, active_ids: set[str], player_loc: str) -> str:
        """Plain-language 'where is this character' for the agent lane —
        replaces engine jargon (active · location group … away from player)
        with something an outsider reads as a living world."""
        from neonrp.core.output_lang import prompt_lang
        from neonrp.prompts import strings

        S = strings("soul_where", prompt_lang(self.root))  # the run's language (10-16: was zh in every run)
        loc = self._soul_location(sid, iid)
        place = self._location_label(loc)
        active = iid in active_ids
        # Co-located with the player: either explicitly at the player's node,
        # or no committed location while active — an active location-less soul
        # travels with the player (scene_understanding keeps it in the primary
        # group). A location-less soul that ISN'T active is genuinely off-stage.
        if (loc and loc == player_loc) or (not loc and active):
            here = self._location_label(loc or player_loc)
            return S["here_at"].replace("{place}", here) if (loc or player_loc) else S["here"]
        if active:
            return S["away_active"].replace("{place}", place)
        return S["away"].replace("{place}", place)

    # -- replay (M18 §7: the trace IS the session — replayable) -----------
    def _branch(self) -> str:
        return _run_branch(self.root)

    def traces_summary(self) -> list[dict[str, Any]]:
        """One row per played turn: index, ts, player input, location, commit."""
        rows: list[dict[str, Any]] = []
        for i, t in enumerate(read_turn_traces(self.root, self._branch())):
            rows.append(
                {
                    "i": i,
                    "ts": t.get("ts", ""),
                    "turn_seq": t.get("turn_seq"),
                    "input": (t.get("player", {}).get("input") or "")[:120],
                    "location": t.get("world_location"),
                    "commit": (t.get("land", {}) or {}).get("commit_id"),
                }
            )
        return rows

    def trace_at(self, index: int) -> dict[str, Any] | None:
        traces = read_turn_traces(self.root, self._branch())
        if 0 <= index < len(traces):
            return traces[index]
        return None

    # -- turn -------------------------------------------------------------
    def submit(self, text: str) -> bool:
        """Start a turn on a worker thread. False if one is already running."""
        if not self._busy.acquire(blocking=False):
            return False
        threading.Thread(target=self._run_turn, args=(text,), daemon=True).start()
        return True

    def _run_turn(self, text: str) -> None:
        try:
            self._do_turn(text)
        except Exception as exc:  # noqa: BLE001 — a crashed turn must not kill the server
            done: dict[str, Any] = {"kind": "turn_done", "success": False, "error": str(exc)}
            billing = _billing_payload(str(exc))
            if billing:
                done["billing"] = billing
            self.broadcast.publish(done)
        finally:
            self._busy.release()

    def _do_turn(self, text: str) -> Any:
        """Run one turn and publish its lifecycle to the broadcast bus.

        Shared by the fire-and-forget local path (submit → _run_turn) and the
        blocking gateway facade (gateway_turn), so both drive the exact same
        engine path and the local UI stays live either way. Caller owns the
        _busy lock."""
        bc = self.broadcast
        bc.publish({"kind": "turn_start", "text": text})
        session = self.session()
        # M18 §6: NO callbacks — the frontend already subscribes to the
        # session bus (_wire_bus); chunks, soul statuses, tools and
        # errors arrive as engine/stream + engine/event messages.
        _k0 = len(read_turn_traces(self.root, session.branch))
        self._live_beats: list[dict[str, Any]] | None = []
        try:
            result = session.send(text)
        finally:
            live, self._live_beats = self._live_beats or [], None
        traces = read_turn_traces(self.root, session.branch, last=1)
        if traces:
            bc.publish({"kind": "trace", "trace": traces[0]})
        try:  # contract 1.0 beat events (R6): every trace this line produced, as node / beat / dice / tool / state events
            from neonrp.core import beat_events

            # the beats that already went out as they landed (engine/beat, above) are not sent twice; a trace whose
            # beat was not announced live (an older path) is caught up here, after the node the live events left
            _sent = sum(1 for e in live if e.get("kind") in ("plan.beat", "resolve.beat"))
            _node = next((e.get("node") for e in reversed(live) if e.get("kind") == "node.enter"), None)
            _new = read_turn_traces(self.root, session.branch)[_k0:]
            _evs, self._beat_node = beat_events.from_traces(_new[_sent:], _node or getattr(self, "_beat_node", None), root=self.root)
            for _name, _data in _evs:
                bc.publish({"kind": _name, **_data})
        except Exception:  # noqa: BLE001 — events are an addition; the turn already landed
            logging.getLogger(__name__).debug("beat events skipped", exc_info=True)
        bc.publish(self.positions())
        done: dict[str, Any] = {
            "kind": "turn_done",
            "success": result.success,
            "error": result.error,
            "route_decision": result.route_decision,
            "narration": (result.assistant_message or "")[:4000],
        }
        billing = _billing_payload(result.error)
        if billing:  # quota / credits / claim (core/billing_stop.py): the page shows what to do + the billing link
            done["billing"] = billing
        if getattr(result, "timeouts", None):  # beats that ran out of time (core/beat_budget): the page may say so
            done["timeouts"] = list(result.timeouts)
        bc.publish(done)
        return result

    # -- gateway facade (docs/WEBUI-UNIFICATION.md P0) ---------------------
    # The local server speaks the hosted play_gateway's HTTP shape so the
    # shared play UI (rp-hub/web playClient) can point ENDPOINT at localhost
    # and play a local world with zero UI changes. One wrapped session,
    # addressed by the fixed id "local". No auth, no token caps.
    _LOCAL_SID = "local"
    _UNCAPPED = 10**9  # quota fields the shared UI expects; local = no wall

    def gateway_start(self) -> dict[str, Any]:
        """StartResponse-shaped descriptor for the single local session."""
        self.kickoff()
        last_trace: dict[str, Any] | None = None
        try:
            traces = read_turn_traces(self.root, self._branch(), last=1)
            if traces:
                last_trace = traces[0]
        except Exception:  # noqa: BLE001 — trace repaint is an enhancement
            last_trace = None
        engine_mode = "orchestrator"
        try:
            from neonrp.core.playthrough import read_playthrough

            pt = read_playthrough(self.root)
            if pt and pt.souls:
                engine_mode = "multi-agent"
        except Exception:  # noqa: BLE001
            pass
        # 世界显示名:run 目录名去掉时间戳 → 库/内置注册表的 display name。
        # 共享 PlayPage 在 hosted 靠 registry 拿名字,local 由这里补
        # (否则标题露出原始 run slug,如 "stoneford elena 20260702 024026")。
        import re as _re

        world_id = _re.sub(r"-\d{8}-\d{6}$", "", self.root.name)
        world_name = world_id
        try:
            from neonrp.worlds import get_world

            w = get_world(world_id)
            world_name = (
                str(w.get("display_name") or w.get("name_local") or w.get("name") or "")
                or world_id
            )
        except Exception:  # noqa: BLE001 — display name is cosmetic
            pass
        return {
            "session_id": self._LOCAL_SID,
            "kind": "worlds",
            "slug": self.root.name,
            "scene_dir": str(self.root),
            "agent_id": self.agent_id,
            "note": "local engine session",
            "engine_mode": engine_mode,
            "world_name": world_name,
            "messages": None,
            "last_trace": last_trace,
        }

    def gateway_turn(self, text: str) -> dict[str, Any] | None:
        """Blocking TurnResponse-shaped turn. None means a turn is running."""
        if not self._busy.acquire(blocking=False):
            return None
        t0 = time.monotonic()
        try:
            result = self._do_turn(text)
            usage = getattr(result, "usage", {}) or {}
            turn_tokens = int(usage.get("total_tokens", 0) or 0)
            self._session_tokens = getattr(self, "_session_tokens", 0) + turn_tokens
            return {
                "session_id": self._LOCAL_SID,
                "success": bool(result.success),
                "assistant_message": result.assistant_message or "",
                "options": list(getattr(result, "options", None) or []),
                "error": result.error,
                "billing": _billing_payload(result.error),
                "timeouts": list(getattr(result, "timeouts", None) or []),
                "turn_tokens": turn_tokens,
                "session_tokens": self._session_tokens,
                "session_token_cap": self._UNCAPPED,
                "daily_tokens": 0,
                "daily_token_cap": self._UNCAPPED,
                "elapsed_ms": int((time.monotonic() - t0) * 1000),
            }
        except Exception as exc:  # noqa: BLE001 — surface as a failed turn
            return {
                "session_id": self._LOCAL_SID,
                "success": False,
                "assistant_message": "",
                "error": str(exc),
                "billing": _billing_payload(str(exc)),
                "turn_tokens": 0,
                "session_tokens": getattr(self, "_session_tokens", 0),
                "session_token_cap": self._UNCAPPED,
                "daily_tokens": 0,
                "daily_token_cap": self._UNCAPPED,
                "elapsed_ms": int((time.monotonic() - t0) * 1000),
            }
        finally:
            self._busy.release()

    # -- rollback ---------------------------------------------------------
    def rollback(self, commit_id: str) -> dict[str, Any]:
        """Roll the game back to a past turn's COMMIT_ID on a fresh branch.

        Git-style: the current line is preserved (its ref + session log stay);
        a new sandbox branch is forked at ``commit_id`` (game + souls restored,
        souls re-minted with materialised folders) and becomes the active
        branch. The browser re-syncs from the broadcast ``hello``."""
        if not self._busy.acquire(blocking=False):
            return {"ok": False, "error": "a turn is in progress"}
        try:
            from neonrp.core import rollback as _rb

            res = _rb.rollback(self.root, commit_id, self._branch())  # core/rollback.py — shared with the TUI's /rollback
            if not res.get("ok"):
                return res

            # Drop the cached session so the next turn runs on the new branch,
            # then re-sync the browser. A hello() failure must not fail an
            # already-committed rollback — the browser reloads regardless.
            self._session = None
            try:
                self.broadcast.publish(self.hello())
            except Exception:  # noqa: BLE001
                pass
            return res
        finally:
            self._busy.release()

    def _fork_orchestration(
        self, source: str, dest: str, turn_seq: int | None
    ) -> None:
        """Kept for callers / tests: core.rollback.fork_orchestration."""
        from neonrp.core.rollback import fork_orchestration

        fork_orchestration(self.root, source, dest, turn_seq)

# ── LocalShell SPA (docs/WEBUI-UNIFICATION.md §7.5 LP1) ────────────
# `neonrp web` serves the WorldLines React shell same-origin at /local/*. The
# shell build lives in the open-source WorldLines repo; the engine NEVER embeds
# one — it assembles the shell at runtime from:
#
#   ① NEONRP_SPA_DIR — env var pointing at an unpacked SPA dist dir
#                      (the WorldLines shell build). Serves it if present.
#   ② None           — engine runs API-only; /local/* 404s with a pointer
#                      to the WorldLines shell.
#
# (The old vanilla `_page_html` page + embedded `webui/spa` copy were retired
#  2026-08-31 — finishing the two-repo split; shell now lives only in WorldLines.)


def _spa_root() -> Any | None:
    """Resolve the SPA build to serve, or None when there is no shell.

    Returns an importlib.resources Traversable OR a pathlib.Path — both
    support the joinpath()/is_file()/read_bytes() surface the serving helpers
    use; in a wheel the packaged files may live inside a zip, so callers must
    never assume a real directory. Resolution is ① env NEONRP_SPA_DIR → ② the installed WorldLines shell's own
    screen (``worldlines_shim/spa``, 10-08: the engine's ``worldlines`` command may win the console-script slot) → None.
    An env dir without an index.html is ignored → None (engine runs API-only)."""
    env_dir = os.environ.get("NEONRP_SPA_DIR", "").strip()
    if env_dir:
        p = Path(env_dir).expanduser()
        if (p / "index.html").is_file():
            return p
    from neonrp.core.paths import shell_dir

    shipped = shell_dir("spa")
    if shipped is not None and (shipped / "index.html").is_file():
        return shipped
    return None


# Extension → Content-Type for the vite build's files. Anything unknown is
# served as octet-stream rather than refused (a build may add e.g. .wasm).
_SPA_CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".mjs": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".ico": "image/x-icon",
    ".json": "application/json; charset=utf-8",
    ".map": "application/json",
    ".txt": "text/plain; charset=utf-8",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".ttf": "font/ttf",
}


# ── CREATE contract, local end (docs/WEBUI-UNIFICATION.md L0.1) ─────────────
# Creation = an agentic EDIT session over a world that already exists: scaffold
# the white template (or open an owned world), then each message lets a
# build-mode agent read/write the world's files in place. This is the same
# /api/v1/create/* contract the hosted create gateway converges on.


class EditRuntime:
    """One build-mode edit session over an owned world SOURCE.

    Mirrors the play side's single-swap model: one active edit session,
    addressed by the fixed id "edit-local". The wrapped world dir is a
    WORLDS_HOME source (the library SoT) — playtesting instantiates a run.
    """

    SID = "edit-local"
    # Engine internals the workbench tree doesn't show.
    _TREE_EXCLUDE = (
        ".neonrp/sessions",
        ".neonrp/events",
        ".neonrp/logs",
        ".neonrp/commits",
        ".git",
    )

    def __init__(self, world_dir: Path) -> None:
        self.world_dir = world_dir
        self.world_id = world_dir.name
        from neonrp.core import run_lock

        self._busy = run_lock.of(world_dir)
        self._session: ConversationSession | None = None

    def session(self) -> ConversationSession:
        if self._session is None:
            agent_id = "world-agent"
            try:
                from neonrp.core.runtime_contract import resolve_router_agent_id

                agent_id = resolve_router_agent_id(self.world_dir) or agent_id
            except Exception:  # noqa: BLE001 — default router is fine
                pass
            self._session = ConversationSession(
                self.world_dir, agent_id, mode="build"
            )
        return self._session

    def tree(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for f in sorted(self.world_dir.rglob("*")):
            if not f.is_file():
                continue
            rel = f.relative_to(self.world_dir).as_posix()
            if any(rel == ex or rel.startswith(ex + "/") for ex in self._TREE_EXCLUDE):
                continue
            try:
                size = f.stat().st_size
            except OSError:
                size = 0
            out.append({"path": rel, "size": size})
        return out

    def read_file(self, rel: str) -> tuple[int, str]:
        """(http_status, content_or_error) for a world file, path-guarded."""
        try:
            target = (self.world_dir / rel).resolve()
            target.relative_to(self.world_dir.resolve())
        except (ValueError, OSError):
            return 400, "bad path"
        if not target.is_file():
            return 404, "not found"
        try:
            if target.stat().st_size > 1_000_000:
                return 413, "too large"
            return 200, target.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return 415, "binary file"
        except OSError:
            return 404, "not found"

    # ── canvases(docs/STUDIO-CANVAS-PLAN.md)─────────────────────────
    # map      → 世界内容本身(world_map.json 投影,读写世界文件)
    # story    → STUDIO_HOME/<id>/flow.json(编辑副产物,世界外)
    # relation → STUDIO_HOME/<id>/relationships.json(同上)

    CANVAS_KINDS = ("map", "story", "relation")

    def _data_dir(self) -> Path:
        from neonrp.core.paths import get_data_dir_name

        return self.world_dir / get_data_dir_name(self.world_dir)

    def _studio_file(self, kind: str) -> Path:
        from neonrp.worlds import get_studio_dir

        name = "flow.json" if kind == "story" else "relationships.json"
        return get_studio_dir(self.world_id) / name

    def canvas_get(self, kind: str) -> dict[str, Any]:
        if kind == "map":
            return self._map_canvas_get()
        default: dict[str, Any] = (
            {"nodes": [], "edges": [], "viewport": {}}
            if kind == "story"
            else {"relationships": [], "layout": {"positions": {}, "viewport": {}}}
        )
        f = self._studio_file(kind)
        saved: dict[str, Any] | None = None
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                saved = data
        except (OSError, ValueError):
            saved = None
        if kind == "story":
            draft = _draft_story_canvas(self.world_dir)
            if saved is None:
                # B 自动草拟(issue #14):画布缺席(新导入必然)→ 从世界数据起草。
                return draft if draft is not None else default
            # 增量合并:世界数据更新后,新事件/任务自动补进
            # 已有蓝图(drafted 标),用户布局不动、节点不删。
            return _merge_story_canvas(saved, draft) if draft is not None else saved
        # relation:同款草拟+增量。
        draft_r = _draft_relationships(self.world_dir)
        if saved is None:
            return draft_r if draft_r is not None else default
        return _merge_relationships(saved, draft_r) if draft_r is not None else saved

    def canvas_put(self, kind: str, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """Validate + persist one canvas. Returns (status, saved_or_error)."""
        from neonrp.core.storage import atomic_write_json

        if kind == "map":
            return self._map_canvas_put(payload)
        if kind == "story":
            ok, cleaned_or_err = _clean_flow_canvas(payload)
        else:
            ok, cleaned_or_err = _clean_relationships(payload)
        if not ok:
            return 400, {"error": str(cleaned_or_err)}
        f = self._studio_file(kind)
        f.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(f, cleaned_or_err)
        return 200, cleaned_or_err

    # 世界图:world_map.json ↔ 画布形状 双向投影。PUT 按 id 合并,保留
    # 投影没带的字段(state/region/…);payload 里缺席的 id = 删除。
    def _map_canvas_get(self) -> dict[str, Any]:
        wm = self._read_world_map()
        _known = {"id", "pos", "name", "summary", "type", "links", "state"}
        nodes = [
            {
                "id": str(n.get("id")),
                "pos": n.get("pos") or [0, 0],
                "data": {
                    "label": n.get("name") or str(n.get("id")),
                    "summary": n.get("summary") or "",
                    "node_kind": n.get("type") or "town",
                    # agent 写的丰富字段(altitude/tags/discovered…)只读透传,
                    # 弹窗可见(关联信息没反映在 map 上)。PUT 合并按 id
                    # 保留原字段,extra 不回写。
                    "extra": {k: v for k, v in n.items() if k not in _known},
                },
            }
            for n in wm.get("nodes") or []
            if n.get("id")
        ]
        # 悬空 route(端点不在 nodes 里,如模板裁剪残留)不投影 —— 否则
        # 画布原样送回会被 PUT 校验拒收,永远保存失败(E2E 抓到的实坑)。
        node_ids = {n["id"] for n in nodes}
        edges = [
            {
                "id": str(r.get("id")),
                "source": str(r.get("from")),
                "target": str(r.get("to")),
                "data": {
                    "kind": r.get("kind") or "road",
                    "distance": r.get("distance"),
                },
            }
            for r in wm.get("routes") or []
            if r.get("id")
            and str(r.get("from")) in node_ids
            and str(r.get("to")) in node_ids
        ]
        # 实际存在的地点实体(game/locations/*.json 等)若没进 world_map,
        # 也要出现在画布上(世界图没反映真实地点)——自动网格
        # 落位在底部,拖动/保存后会写回 world_map 成为正式节点。
        known = {n["id"] for n in nodes}
        extras = [
            loc for loc in self.entities().get("locations", [])
            if loc["id"] not in known
        ]
        for i, loc in enumerate(extras):
            nodes.append({
                "id": loc["id"],
                "pos": [4 + (i % 6) * 6, 40 + (i // 6) * 6],
                "data": {"label": loc["name"], "summary": "", "node_kind": "place"},
            })
        # 地图的 viewport 也是编辑副产物 → studio,不进世界文件
        viewport: dict[str, Any] = {}
        try:
            vf = self._studio_file("story").parent / "map-view.json"
            viewport = json.loads(vf.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
        return {"nodes": nodes, "edges": edges, "viewport": viewport}

    def _map_canvas_put(self, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        from neonrp.core.storage import atomic_write_json

        wm_path = self._data_dir() / "world" / "world_map.json"
        wm = self._read_world_map()
        in_nodes = [n for n in payload.get("nodes") or [] if isinstance(n, dict) and n.get("id")]
        in_edges = [e for e in payload.get("edges") or [] if isinstance(e, dict) and e.get("id")]
        node_ids = {str(n["id"]) for n in in_nodes}
        if len(node_ids) != len(in_nodes):
            return 400, {"error": "duplicate node ids"}
        for e in in_edges:
            if str(e.get("source")) == str(e.get("target")):
                return 400, {"error": f"self-loop route {e.get('id')}"}
            if str(e.get("source")) not in node_ids or str(e.get("target")) not in node_ids:
                return 400, {"error": f"route {e.get('id')} endpoint missing"}
        by_id = {str(n.get("id")): n for n in wm.get("nodes") or []}
        merged_nodes = []
        for n in in_nodes:
            base = dict(by_id.get(str(n["id"])) or {"id": n["id"], "type": "town"})
            data = n.get("data") or {}
            base["pos"] = [round(float(x), 2) for x in (n.get("pos") or base.get("pos") or [0, 0])[:2]]
            if data.get("label"):
                base["name"] = str(data["label"])[:60]
            if "summary" in data:
                base["summary"] = str(data.get("summary") or "")[:500]
            merged_nodes.append(base)
        routes_by_id = {str(r.get("id")): r for r in wm.get("routes") or []}
        merged_routes = []
        for e in in_edges:
            base = dict(routes_by_id.get(str(e["id"])) or {"id": e["id"], "kind": "road"})
            base["from"] = str(e["source"])
            base["to"] = str(e["target"])
            data = e.get("data") or {}
            if data.get("kind"):
                base["kind"] = str(data["kind"])[:30]
            if data.get("distance") is not None:
                try:
                    base["distance"] = float(data["distance"])
                except (TypeError, ValueError):
                    pass
            merged_routes.append(base)
        wm["nodes"] = merged_nodes
        wm["routes"] = merged_routes
        from neonrp.core.place_tree import WORLD, is_tree, save_level_doc

        if is_tree(self.world_dir):  # tree form: each node into its place folder; world_map.json keeps routes, never nodes
            save_level_doc(self.world_dir, WORLD, wm)
        else:
            wm_path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_json(wm_path, wm)
        if isinstance(payload.get("viewport"), dict):
            vf = self._studio_file("story").parent / "map-view.json"
            vf.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_json(vf, payload["viewport"])
        return 200, self._map_canvas_get()

    def _read_world_map(self) -> dict[str, Any]:
        from neonrp.core.place_tree import WORLD, is_tree, level_doc

        if is_tree(self.world_dir):
            return level_doc(self.world_dir, WORLD) or {}
        try:
            data = json.loads(
                (self._data_dir() / "world" / "world_map.json").read_text(encoding="utf-8")
            )
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def entities(self) -> dict[str, Any]:
        """引用选择器 + 条件绑定的数据源:npc/地点/任务/flag/souls 目录。"""
        data_dir = self._data_dir()
        npcs: list[dict[str, Any]] = []
        locations: list[dict[str, Any]] = []
        quests: list[dict[str, Any]] = []
        flags: list[dict[str, Any]] = []
        souls: list[dict[str, Any]] = []
        seen: set[str] = set()

        def _add(bucket: list, item_id: Any, name: Any) -> None:
            iid = str(item_id or "").strip()
            if not iid or iid in seen:
                return
            seen.add(iid)
            bucket.append({"id": iid, "name": str(name or iid)})

        for town_npcs in sorted(data_dir.glob("towns/*/npcs.json")):
            try:
                d = json.loads(town_npcs.read_text(encoding="utf-8"))
                for n in d if isinstance(d, list) else d.get("npcs") or []:
                    _add(npcs, n.get("id"), n.get("name"))
            except (OSError, ValueError):
                continue
        for f in sorted(data_dir.glob("npc/*.json")) + sorted(data_dir.glob("character/*.json")):
            try:
                d = json.loads(f.read_text(encoding="utf-8"))
                _add(npcs, d.get("id") or f.stem, d.get("name"))
            except (OSError, ValueError):
                continue
        wm = self._read_world_map()
        for n in wm.get("nodes") or []:
            _add(locations, n.get("id"), n.get("name"))
        for f in sorted(data_dir.glob("locations/*.json")):
            try:
                d = json.loads(f.read_text(encoding="utf-8"))
                _add(locations, d.get("id") or f.stem, d.get("name"))
            except (OSError, ValueError):
                continue
        for qf in sorted(data_dir.glob("towns/*/quests.json")):
            try:
                d = json.loads(qf.read_text(encoding="utf-8"))
                for q in d.get("quests") or []:
                    _add(quests, q.get("qid") or q.get("id"), q.get("title"))
            except (OSError, ValueError):
                continue
        try:
            fl = json.loads((data_dir / "player" / "flags.json").read_text(encoding="utf-8"))
            src = fl.get("flags") if isinstance(fl.get("flags"), dict) else fl
            if isinstance(src, dict):
                for k, v in src.items():
                    kind = (
                        "boolean"
                        if isinstance(v, bool)
                        else "number" if isinstance(v, (int, float)) else "enum"
                    )
                    flags.append({"key": str(k), "type": kind})
        except (OSError, ValueError):
            pass
        try:
            from neonrp.core.playthrough import read_playthrough

            pt = read_playthrough(self.world_dir)
            for ref in getattr(pt, "souls", None) or []:
                _add(souls, getattr(ref, "iid", None) or getattr(ref, "sid", None),
                     getattr(ref, "sid", None))
        except Exception:  # noqa: BLE001 — souls are optional
            pass
        return {"npcs": npcs, "locations": locations, "quests": quests,
                "flags": flags, "souls": souls}


def _merge_story_canvas(saved: dict[str, Any], draft: dict[str, Any]) -> dict[str, Any]:
    """增量合并(世界更新了但蓝图不动):draft 新节点追加
    (data.drafted=true,排在已有节点下方避免重叠);已有节点 pos/data 全保留;
    新边(端点齐、(source,target) 未有)追加;**绝不自动删**用户节点。
    结果不落盘——用户保存时才写(走 canvas_put)。"""
    nodes = [dict(n) for n in (saved.get("nodes") or []) if isinstance(n, dict)]
    have = {str(n.get("id")) for n in nodes}
    try:
        maxy = max(float((n.get("pos") or [0, 0])[1]) for n in nodes)
    except ValueError:
        maxy = 0.0
    added = 0
    for n in draft.get("nodes") or []:
        nid = str(n.get("id") or "")
        if not nid or nid in have:
            continue
        nn = dict(n)
        data = dict(nn.get("data") or {})
        data["drafted"] = True
        nn["data"] = data
        nn["pos"] = [(added % 4) * 260, maxy + 200 + (added // 4) * 150]
        nodes.append(nn)
        have.add(nid)
        added += 1
    edges = [dict(e) for e in (saved.get("edges") or []) if isinstance(e, dict)]
    ekeys = {(str(e.get("source")), str(e.get("target"))) for e in edges}
    for e in draft.get("edges") or []:
        k = (str(e.get("source") or ""), str(e.get("target") or ""))
        if not k[0] or not k[1] or k in ekeys or k[0] not in have or k[1] not in have:
            continue
        edges.append(dict(e))
        ekeys.add(k)
    out = dict(saved)
    out["nodes"] = nodes
    out["edges"] = edges
    if added:
        out["drafted_added"] = added
    return out


def _draft_relationships(world_dir: Path) -> dict[str, Any] | None:
    """关系画布草拟:souls/* 的角色名 → 「角色↔玩家」占位关系(过
    _clean_relationships 校验的形状)。无 souls → None。"""
    rels: list[dict[str, Any]] = []
    souls_dir = world_dir / "souls"
    if souls_dir.is_dir():
        for sd in sorted(souls_dir.iterdir()):
            sj = sd / "soul.json"
            if not sj.is_file():
                continue
            try:
                data = json.loads(sj.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            name = str(data.get("name_local") or data.get("name") or "").strip()
            if not name:
                continue
            rels.append(
                {
                    "id": f"rel-{len(rels) + 1}",
                    "source": name,
                    "target": "玩家",
                    "relation_type": "认识",
                    "description": "(草拟占位——按剧情修订)",
                    "direction": "bidirectional",
                    "strength": 3,
                }
            )
    if not rels:
        return None
    return {"relationships": rels, "layout": {"positions": {}, "viewport": {}}, "drafted": True}


def _merge_relationships(saved: dict[str, Any], draft: dict[str, Any]) -> dict[str, Any]:
    """关系增量:draft 里 source 尚未出现的角色补进去;已有条目不动不删。"""
    rels = [dict(r) for r in (saved.get("relationships") or []) if isinstance(r, dict)]
    have_src = {str(r.get("source")) for r in rels}
    added = 0
    for r in draft.get("relationships") or []:
        if str(r.get("source")) in have_src:
            continue
        nr = dict(r)
        nr["id"] = f"rel-{len(rels) + 1}"
        rels.append(nr)
        have_src.add(str(r.get("source")))
        added += 1
    out = dict(saved)
    out["relationships"] = rels
    if added:
        out["drafted_added"] = added
    return out


_es_logger = logging.getLogger("neonrp.edit_session")

_LAST_EDIT_SESSION_FILE = Path.home() / ".neonrp" / "last_edit_session.json"


def _persist_edit_session(world_dir: Path) -> None:
    """创作会话韧性(实测 409):记住最后编辑的世界,进程重启后可懒重建。"""
    try:
        _LAST_EDIT_SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
        _LAST_EDIT_SESSION_FILE.write_text(
            json.dumps({"world_dir": str(world_dir), "ts": time.time()}),
            encoding="utf-8",
        )
    except OSError:
        _es_logger.debug("persist edit session failed", exc_info=True)


def _bump_edit_world_output_cap(world_dir: Path) -> None:
    """老档吃新上限:deepseek 系世界 config 的 max_output_tokens<8192 → 16384
    (创作长输出截断修的存量档补丁;非 deepseek 不动)。"""
    cfg_path = world_dir / ".neonrp" / "config.json"
    try:
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    llm = cfg.get("llm") if isinstance(cfg.get("llm"), dict) else None
    if not llm:
        return
    blob = (str(llm.get("base_url") or "") + " " + str(llm.get("model") or "")).lower()
    if "deepseek" not in blob:
        return
    try:
        cur = int(llm.get("max_output_tokens") or 0)
    except (TypeError, ValueError):
        cur = 0
    if 0 < cur < 8192:
        llm["max_output_tokens"] = 16384
        try:
            cfg_path.write_text(
                json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            _es_logger.info("edit world %s: max_output_tokens %s→16384", world_dir.name, cur)
        except OSError:
            _es_logger.debug("cap bump write failed", exc_info=True)


def _make_edit_runtime(world_dir: Path) -> "EditRuntime":
    """统一建 EditRuntime:cap 补丁 + 持久化(重启可懒重建)。"""
    _bump_edit_world_output_cap(world_dir)
    _persist_edit_session(world_dir)
    return EditRuntime(world_dir)


def _try_rebind_edit_runtime(server: Any) -> "EditRuntime | None":
    """409 自愈:进程重启丢了内存态时,从 last_edit_session.json 懒重建。
    路径不存在/不含 .neonrp → None(调用方继续走 409)。"""
    existing = getattr(server, "edit_runtime", None)
    if existing is not None:
        return existing
    try:
        payload = json.loads(_LAST_EDIT_SESSION_FILE.read_text(encoding="utf-8"))
        wd = Path(str(payload.get("world_dir") or ""))
    except (OSError, ValueError):
        return None
    if not wd.is_dir() or not (wd / ".neonrp").is_dir():
        return None
    ert = _make_edit_runtime(wd)
    try:
        server.edit_runtime = ert
    except Exception:  # noqa: BLE001 — 挂回失败也返回实例供本次请求用
        _es_logger.debug("rebind attach failed", exc_info=True)
    _es_logger.info("edit session lazily rebound: %s", wd.name)
    return ert


def _draft_story_canvas(world_dir: Path) -> dict[str, Any] | None:
    """从世界数据草拟剧情蓝图(issue #14 方案 B;纯读,不写任何文件)。

    数据源:game/meta/timeline.json 的 events(id/what/time/is_cause_of/
    depends_on)+ game/towns/*/quests.json(best-effort)。返回画布形状
    (nodes[{id,pos,data}], edges)+ drafted 标记;无可草拟数据 → None。
    """
    from neonrp.core.paths import get_data_dir_name

    data_dir = world_dir / get_data_dir_name(world_dir)
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    ids: set[str] = set()

    try:
        tl = json.loads((data_dir / "meta" / "timeline.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        tl = {}
    events = tl.get("events") if isinstance(tl, dict) else None
    for i, ev in enumerate(events or []):
        if not isinstance(ev, dict):
            continue
        eid = str(ev.get("id") or "").strip()
        if not eid or eid in ids:
            continue
        ids.add(eid)
        label = str(ev.get("name") or ev.get("what") or eid)[:60]
        when = str(ev.get("time") or "").strip()
        nodes.append(
            {
                "id": eid,
                "pos": [(i % 4) * 260, (i // 4) * 150],
                "data": {"label": label, "kind": "event", "time": when},
            }
        )
    for ev in events or []:
        if not isinstance(ev, dict):
            continue
        eid = str(ev.get("id") or "").strip()
        for tgt in ev.get("is_cause_of") or []:
            tgt = str(tgt or "").strip()
            if eid in ids and tgt in ids and eid != tgt:
                edges.append(
                    {"id": f"se-{len(edges) + 1}", "source": eid, "target": tgt, "data": {"label": "导致"}}
                )
        for dep in ev.get("depends_on") or []:
            dep = str(dep or "").strip()
            if dep in ids and eid in ids and dep != eid:
                edges.append(
                    {"id": f"se-{len(edges) + 1}", "source": dep, "target": eid, "data": {"label": "前置"}}
                )

    qy = len(nodes) // 4 * 150 + 320
    qi = 0
    for qf in sorted(data_dir.glob("towns/*/quests.json")):
        try:
            qd = json.loads(qf.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        quests = qd.get("quests") if isinstance(qd, dict) else (qd if isinstance(qd, list) else [])
        for q in quests or []:
            if not isinstance(q, dict):
                continue
            qid = str(q.get("id") or q.get("name") or "").strip()
            if not qid or qid in ids:
                continue
            ids.add(qid)
            nodes.append(
                {
                    "id": qid,
                    "pos": [(qi % 4) * 260, qy + (qi // 4) * 150],
                    "data": {"label": str(q.get("name") or qid)[:60], "kind": "quest"},
                }
            )
            qi += 1

    if not nodes:
        return None
    return {"nodes": nodes, "edges": edges, "viewport": {}, "drafted": True}


def _clean_flow_canvas(payload: dict[str, Any]) -> tuple[bool, Any]:
    """剧情画布归一 + 校验(trpgmaster _draft_to_canvas_state 的文件版):
    节点按 id 去重、label 截断;边要求端点存在、拒自环、(source,target,label)
    去重。返回 (ok, cleaned|error_str)。"""
    nodes_in = payload.get("nodes") or []
    edges_in = payload.get("edges") or []
    if not isinstance(nodes_in, list) or not isinstance(edges_in, list):
        return False, "nodes/edges must be lists"
    nodes: list[dict[str, Any]] = []
    node_ids: set[str] = set()
    for n in nodes_in:
        if not isinstance(n, dict):
            continue
        nid = str(n.get("id") or "").strip()
        if not nid or nid in node_ids:
            continue
        node_ids.add(nid)
        data = n.get("data") if isinstance(n.get("data"), dict) else {}
        data = dict(data)
        data["label"] = str(data.get("label") or "")[:60]
        pos = n.get("pos") or [0, 0]
        try:
            pos = [round(float(pos[0]), 2), round(float(pos[1]), 2)]
        except (TypeError, ValueError, IndexError):
            pos = [0, 0]
        nodes.append({"id": nid, "pos": pos, "data": data})
    edges: list[dict[str, Any]] = []
    edge_keys: set[tuple] = set()
    for e in edges_in:
        if not isinstance(e, dict):
            continue
        src, tgt = str(e.get("source") or ""), str(e.get("target") or "")
        if not src or not tgt or src == tgt:
            continue
        if src not in node_ids or tgt not in node_ids:
            return False, f"edge {e.get('id')} endpoint missing"
        data = e.get("data") if isinstance(e.get("data"), dict) else {}
        key = (src, tgt, str(data.get("label") or ""))
        if key in edge_keys:
            continue
        edge_keys.add(key)
        edges.append({
            "id": str(e.get("id") or f"se-{len(edges) + 1}"),
            "source": src,
            "target": tgt,
            "data": dict(data),
        })
    viewport = payload.get("viewport") if isinstance(payload.get("viewport"), dict) else {}
    return True, {"nodes": nodes, "edges": edges, "viewport": viewport}


def _clean_relationships(payload: dict[str, Any]) -> tuple[bool, Any]:
    """关系画布归一 + 校验:(source,target,relation_type) 去重、拒自环。"""
    rels_in = payload.get("relationships") or []
    if not isinstance(rels_in, list):
        return False, "relationships must be a list"
    rels: list[dict[str, Any]] = []
    keys: set[tuple] = set()
    for r in rels_in:
        if not isinstance(r, dict):
            continue
        src, tgt = str(r.get("source") or ""), str(r.get("target") or "")
        rtype = str(r.get("relation_type") or "")[:40]
        if not src or not tgt or src == tgt:
            continue
        key = (src, tgt, rtype)
        if key in keys:
            continue
        keys.add(key)
        rels.append({
            "id": str(r.get("id") or f"rel-{len(rels) + 1}"),
            "source": src,
            "target": tgt,
            "relation_type": rtype,
            "description": str(r.get("description") or "")[:300],
            "direction": "bidirectional" if r.get("direction") == "bidirectional" else "directed",
            "strength": max(1, min(5, int(r.get("strength") or 3))),
        })
    layout = payload.get("layout") if isinstance(payload.get("layout"), dict) else {}
    return True, {"relationships": rels, "layout": layout}



def _portrait_prompt_from(dir_: Path) -> str:
    """从内容提图像 prompt:世界→风景封面,soul→人物立绘。"""
    if (dir_ / "game").is_dir():
        bits: list[str] = []
        for rel in ("game/meta/game-start.json", "game/lore/story.md", "game/world/world_map.json"):
            f = dir_ / rel
            if f.is_file():
                try:
                    bits.append(f.read_text(encoding="utf-8")[:400])
                except (OSError, UnicodeDecodeError):
                    continue
        hint = "\n".join(bits)[:600]
        return (
            "scenic key visual, wide establishing shot, atmospheric, "
            "no text, no characters in focus\n" + hint
        )
    bits = []
    for rel in ("soul.md", "persona/appearance.md", "persona/core.json"):
        f = dir_ / rel
        if f.is_file():
            try:
                bits.append(f.read_text(encoding="utf-8")[:400])
            except (OSError, UnicodeDecodeError):
                continue
    hint = "\n".join(bits)[:600]
    return (
        "character portrait, upper body, detailed face, soft light, "
        "clean background\n" + hint
    )


def _scaffold_soul_blank(name: str, seed: str) -> Path:
    """角色白模(=艾琳娜)scaffold 进 SOUL_HOME —— 与世界工坊
    同构:立即入库,工作台(EditRuntime)直接编辑库内目录。"""
    import re as _re
    import shutil
    from datetime import datetime as _dt
    from importlib import resources as _res

    from neonrp.core.souls import SOUL_HOME

    base = _re.sub(r"[^a-z0-9-]+", "-", name.lower()).strip("-") or "soul"
    dest = SOUL_HOME / f"{base}-{_dt.now().strftime('%Y%m%d-%H%M%S')}"
    src = _res.files("neonrp.templates").joinpath("soul-blank")
    with _res.as_file(src) as real:
        shutil.copytree(real, dest)
    # 身份改写:soul.json / run_state.json 用新名字
    for fn in ("soul.json", "run_state.json"):
        f = dest / fn
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            data["name"] = name
            data["sid"] = base
            f.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except (OSError, ValueError):
            continue
    # 概念种子给 agent 迁移分析用
    if seed:
        (dest / "trajectory" / "seed.md").write_text(
            f"# 创作种子\n\n{name} — {seed}\n", encoding="utf-8"
        )
    # 工作台基建:.neonrp(manifest+creation LLM config)—— EditRuntime 需要
    from neonrp.core.manifest import Manifest
    from neonrp.core.storage import atomic_write_json, ensure_dirs

    ensure_dirs(dest)
    atomic_write_json(dest / ".neonrp" / "manifest.json", Manifest().model_dump())
    preset = _resolve_creation_preset("")
    if preset:
        _apply_run_preset(dest, preset)
    return dest


def _new_world_slug(name: str) -> str:
    """Slug for a fresh created world under WORLDS_HOME (deduped).

    去重不仅避开已存在的 owned 目录,**也避开内置世界 id**(曾有
    bug:新建/编辑世界 slug 撞上内置 id 如 `stoneford-elena` → owned 同 id 顶替
    并从列表挤掉内置那份,导致"内置角色立绘没了")。撞任一侧都加 -N 后缀。
    """
    import re as _re
    from datetime import datetime as _dt

    from neonrp.worlds import WORLDS, WORLDS_HOME

    base = _re.sub(r"[^a-z0-9-]+", "-", name.lower()).strip("-") if name else ""
    if not base:
        base = "world-" + _dt.now().strftime("%Y%m%d-%H%M%S")
    slug, n = base, 2
    while (WORLDS_HOME / slug).exists() or slug in WORLDS:
        slug = f"{base}-{n}"
        n += 1
    return slug


# ── launcher API helpers (docs/WEBUI-UNIFICATION.md T0.2) ────────────────────
# The local library endpoints the shared LauncherShell's LocalProvider reads:
# list saves (gateway /api/v1/play/saves shape), list worlds, delete, and
# switching the wrapped session to another run — which is what turns this
# single-world server into a launcher-capable one.

_RUN_SUFFIX_RE = None  # compiled lazily (module import stays light)


def _path_seg(raw: str) -> str:
    """Decode one URL path segment (world ids / run slugs can be 中文)."""
    from urllib.parse import unquote

    return unquote(raw)


def _safe_name(name: str) -> bool:
    """Plain path-component names only (no traversal, no hidden dirs)."""
    return bool(name) and not name.startswith(".") and all(
        c.isalnum() or c in "-_." for c in name
    )


def _run_progress(d: Path) -> dict[str, Any]:
    """{template: the template id a run was built from | None, turns: turns played} — read from the run's files."""
    from neonrp.core.paths import get_data_dir_name

    meta = d / get_data_dir_name(d) / "meta"
    out: dict[str, Any] = {"template": None, "turns": 0}
    for name, key, field in (("template.json", "template", "id"), ("run_state.json", "turns", "turn_count")):
        try:
            v = json.loads((meta / name).read_text(encoding="utf-8")).get(field)
        except (OSError, ValueError, AttributeError):
            continue
        if v:
            out[key] = int(v) if key == "turns" and str(v).isdigit() else (str(v) if key == "template" else out[key])
    return out


def _library_saves(current_root: Path | None) -> dict[str, Any]:
    """PLAYS_HOME runs in the hosted gateway's /api/v1/play/saves shape.

    ``current_root=None`` = launcher mode (no wrapped session yet)."""
    import re as _re

    from neonrp.worlds import PLAYS_HOME, read_local_world_name, read_session_meta

    global _RUN_SUFFIX_RE
    if _RUN_SUFFIX_RE is None:
        _RUN_SUFFIX_RE = _re.compile(r"-\d{8}-\d{6}$")

    saves: list[dict[str, Any]] = []
    if PLAYS_HOME.is_dir():
        try:
            runs = sorted(
                (p for p in PLAYS_HOME.iterdir() if p.is_dir()),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
        except OSError:
            runs = []
        for d in runs:
            meta = read_session_meta(d) or {}
            # Run dirs are "<world_id>-<YYYYMMDD-HHMMSS>" (worlds.create_run_dir).
            slug = meta.get("slug") or _RUN_SUFFIX_RE.sub("", d.name)
            try:
                mtime = int(d.stat().st_mtime)
            except OSError:
                mtime = 0
            saves.append(
                {
                    "session_id": d.name,
                    "kind": meta.get("kind", "worlds"),
                    "slug": slug,
                    "name": meta.get("name") or read_local_world_name(d) or slug,
                    "started": meta.get("started"),
                    "last_modified": mtime,
                    # Hub「我的」继续世界(10-15):这一局来自哪个模板(没有 = 旧世界)、走了几回合
                    **_run_progress(d),
                    # 这一局建局时的语言(10-16):续玩照它,前端把它标在存档上(None = 没按语言建 / 旧世界)
                    "lang": _built_lang(d),
                    # 今日动态 tease (player-artifacts V0): the run's latest
                    # feed entry + who is waiting — the launcher's continue
                    # strip reads these. Absent artifacts → empty fields.
                    **_feed_tease(d),
                    # Local analogue of the gateway's "warm in pool": the run
                    # this server currently wraps.
                    "in_memory": (
                        current_root is not None
                        and d.resolve() == current_root.resolve()
                    ),
                }
            )
    return {"uid": "local", "saves": saves}


def _built_lang(d: Path) -> str | None:
    from neonrp.core.output_lang import built_lang

    try:
        return built_lang(d)
    except Exception:  # noqa: BLE001 — a broken run still lists
        return None


def _local_plays(current_root: Path | None, lang: str, *, every: bool = False) -> dict[str, Any]:
    """Hub「我的」继续世界: the runs played (a turn or more; ``every`` = all of them), newest first —
    {plays: [{session_id, template, world, turns, last_modified, cover_url, in_memory}]}. Continue one by binding its
    session_id (POST /api/v1/play/session {slug: session_id})."""
    from urllib.parse import quote

    from neonrp import template as TP
    from neonrp.template import i18n

    found = TP.discover()
    out = []
    for s in _library_saves(current_root)["saves"]:
        if not every and not s.get("turns"):
            continue
        tid = s.get("template")
        world, cover = s.get("name") or s.get("slug"), f"/api/v1/local/worlds/{quote(str(s.get('slug') or ''))}/cover"
        if tid and tid in found:
            try:
                t = TP.load(found[tid])
                world = i18n.card(t, lang).get("title") or t.card.get("title") or tid
                cover = f"/api/v1/local/templates/{quote(tid)}/assets/file?slot=card:cover" if t.card.get("cover") else None
            except TP.TemplateError:
                pass
        out.append({"session_id": s["session_id"], "template": tid, "world": world, "turns": s.get("turns", 0), "lang": s.get("lang"),
                    "last_modified": s.get("last_modified"), "cover_url": cover, "in_memory": s.get("in_memory", False)})
    return {"plays": out}


def _world_cover_bytes(world_id: str) -> bytes | None:
    """cover.png for an owned world or a built-in template (best-effort)."""
    from neonrp.worlds import WORLDS, WORLDS_HOME, resolve_template

    owned = WORLDS_HOME / world_id
    for rel in ("assets/cover.png", "cover.png"):
        f = owned / rel
        if f.is_file():
            try:
                return f.read_bytes()
            except OSError:
                return None
    if world_id in WORLDS:
        try:
            tpl = resolve_template(world_id, "en")
            res = resources.files("neonrp.templates").joinpath(f"{tpl}/assets/cover.png")
            return res.read_bytes()
        except Exception:  # noqa: BLE001 — no cover is fine
            return None
    return None


def _feed_tease(run_dir: Path) -> dict[str, Any]:
    """Latest feed line + waiting souls for a run (best-effort, never raises)."""
    import re as _re

    tease, world_time, waiting = "", "", []
    try:
        lines = (run_dir / "feed.jsonl").read_text(encoding="utf-8").splitlines()
        for ln in reversed(lines):
            ln = ln.strip()
            if not ln:
                continue
            entry = json.loads(ln)
            tease = str(entry.get("summary") or "")[:120]
            world_time = str(entry.get("world_time") or "")
            break
    except (OSError, ValueError):
        pass
    try:
        md = (run_dir / "feed.md").read_text(encoding="utf-8")
        m = _re.search(r"\*\*正在等你回应：\*\* (.+)", md)
        if m:
            waiting = [w.strip() for w in _re.split(r"[、,]", m.group(1)) if w.strip()]
    except OSError:
        pass
    return {"feed_tease": tease, "feed_time": world_time, "waiting": waiting}


def _library_worlds(locale: str) -> dict[str, Any]:
    """Owned worlds (WORLDS_HOME) + built-in templates for the launcher."""
    from neonrp.worlds import list_owned_worlds, list_worlds

    owned: list[dict[str, Any]] = []
    for w in list_owned_worlds():
        w = dict(w)
        w["source_dir"] = str(w.get("source_dir") or "")
        owned.append(w)
    try:
        builtin = list_worlds(locale)
    except Exception:  # noqa: BLE001 — templates listing must never 500 the API
        builtin = []
    # 去重(test-play bug#1):owned 世界(用户导入/创建)也可能进了
    # 世界注册表 → list_worlds 把它们当 builtin 一并返回,前端 [...worlds,...builtin]
    # 每个世界卡显示两次。builtin 排除已在 owned 的 id。
    owned_ids = {str(w.get("id")) for w in owned}
    builtin = [w for w in builtin if str(w.get("id")) not in owned_ids]
    return {"worlds": owned, "builtin": builtin}


def _switch_runtime(server: Any, slug: str, locale: str | None = None, player: dict[str, Any] | None = None,
                    replace: str | None = None) -> tuple[int, str]:
    """Point the server at another run (existing play, an owned world, or a
    built-in world scaffolded into a fresh run). Returns (http_status, detail).
    ``player`` = the character made on the builder screen (a template slug only; template/builder.py).
    A template slug is a NEW run: over the player's save limit (core/save_limits) → 409 {"error": "save_limit", …} and
    nothing is built; ``replace`` = one of this world's runs to delete once the new one is up (the player chose it).

    Single-active-session semantics — the local mirror of the gateway pool is
    one wrapped session at a time; switching swaps it. Refused mid-turn.
    Works in launcher mode too (server.runtime is None until the first pick)."""
    from neonrp.worlds import (
        WORLDS,
        PLAYS_HOME,
        get_owned_world_dir,
        instantiate_run,
        scaffold_builtin_run,
    )

    rt: WebRuntime | None = server.runtime
    if slug in ("", WebRuntime._LOCAL_SID) or (rt is not None and slug == rt.root.name):
        return (200, "already active") if rt is not None else (
            409, "no active session — pass a save or world slug"
        )
    if not _safe_name(slug):
        return 400, "bad slug"

    fresh = False  # instantiate/scaffold 路径置 True — bind 时才允许开局投放
    old: Path | None = None  # the run the player chose to give up for this new one (save limit, 10-21)
    run_dir = PLAYS_HOME / slug
    if run_dir.is_dir():
        target = run_dir
    elif get_owned_world_dir(slug) is not None:
        # A world id → start a NEW run of that owned world.
        try:
            target = instantiate_run(slug)
            fresh = True
        except (KeyError, OSError) as exc:
            return 500, f"instantiate failed: {exc}"
    elif slug.startswith("tpl--"):
        # A template id → build a fresh run from it (neonrp/template: world × souls × pack × prompts × plots)
        from neonrp.core import save_limits as _sl

        tid = slug[len("tpl--"):]
        if replace:
            old = PLAYS_HOME / replace
            if not _safe_name(replace) or not old.is_dir() or _sl.template_of(old) != tid:
                return 400, json.dumps({"ok": False, "error": "bad_replace", "message": "not a run of this world"})
        else:
            try:
                _sl.check_new_run(tid, PLAYS_HOME)
            except _sl.SaveLimit as lim:
                return 409, json.dumps(lim.to_dict(), ensure_ascii=False)
        try:
            from neonrp import template as _tpl
            from neonrp.template.builder import BuilderError

            # 本地化(10-14):按玩家选的语言用模板的 i18n/<lang>/ 层建这一局(没有该语言的层 → 模板主语言)
            target = _tpl.new_run(slug[len("tpl--"):], player=player, lang=locale or None)
            fresh = True
        except BuilderError as exc:  # the character made on the builder screen does not pass: nothing was built
            return 400, json.dumps({"ok": False, "errors": exc.errors}, ensure_ascii=False)
        except _tpl.TemplateError as exc:
            return 404, str(exc)
        except Exception as exc:  # noqa: BLE001 — surface as a clean HTTP error
            return 500, f"template build failed: {exc}"
    elif slug in WORLDS:
        # A built-in world id → scaffold a fresh run from its packaged
        # template (the TUI-free "new game" path).
        try:
            from neonrp.tui.i18n import resolve_locale

            # 语言隔离:按玩家选的语言 scaffold 对应平行世界文件夹
            # (kagura-island-ja / stoneford-elena-en …;resolve_template 处理回退)。
            # bind 未带语言时退回 UI locale(config/env)。
            target = scaffold_builtin_run(slug, locale or resolve_locale())
            fresh = True
        except Exception as exc:  # noqa: BLE001 — surface as a clean HTTP error
            return 500, f"scaffold failed: {exc}"
    elif rt is not None:
        # Unknown slug: keep the hosted client's semantics forgiving locally —
        # a shared PlayPage may POST whatever slug its URL carries (the P1
        # zero-change recipe). Attach to the currently wrapped session instead
        # of failing; only a slug that RESOLVES switches runs.
        return 200, "unknown slug — attached to the active session"
    else:
        return 404, "unknown save or world"

    if not get_manifest_path(target).exists():
        return 409, "target is not an initialized world"
    # Mid-turn switching: leaving a game while its turn is still generating
    # must NOT wedge the launcher (the old 409 did — the lock is held for the
    # whole LLM turn, minutes on multi-agent). Switching to a DIFFERENT run
    # simply abandons the busy runtime: its in-flight turn keeps writing to
    # its own run dir and finishes quietly off to the side. Only re-entering
    # the SAME busy run is refused (two engines on one dir).
    acquired = False
    if rt is not None:
        acquired = rt._busy.acquire(blocking=False)
        if not acquired and target.resolve() == rt.root.resolve():
            return 409, "a turn is in progress on this run"
    try:
        fallback_agent = rt.agent_id if rt is not None else "world-agent"
        agent = get_startup_entry_agent(target) or fallback_agent
        # 新开的 run 注入本地化开场指令(与 TUI 启动链同一份 handoff)——
        # gateway_start 的 kickoff 会把它发给 world-agent,进页即开演。
        # 不注入的话玩家落在空屏幕上等着(实测的「不立即开始」bug)。
        # 接着的这一局一个回合都没有(开场那一拍当时没跑完)= 同样给开场指令,用这一局建的语言(kickoff 再看一眼回合记录)
        startup: list[str] | None = None
        if fresh or not read_turn_traces(target, _run_branch(target), last=1):
            try:
                from neonrp.cli import _build_startup_handoff

                from neonrp.core.output_lang import built_lang, prompt_lang

                # the run's language, not the machine's (10-15: a zh run on a ja Mac opened with a ja cue)
                lg = (locale or prompt_lang(target)) if fresh else (built_lang(target) or prompt_lang(target))
                startup = _build_startup_handoff(None, locale=lg)
            except Exception:  # noqa: BLE001 — opening is best-effort
                startup = None
        server.runtime = WebRuntime(target, agent, startup_commands=startup, reopen=not fresh)
    finally:
        if acquired:
            rt._busy.release()
    if old is not None and old.resolve() != target.resolve():  # the new run is up: now let the old one go
        import shutil

        shutil.rmtree(old, ignore_errors=True)
    return 200, "switched-fresh" if fresh else "switched"


def _set_world_display_name(world_dir: Path, name: str) -> None:
    """Write the human-readable world name into game-start.json (best-effort)."""
    try:
        from neonrp.core.paths import get_game_dir

        gs = get_game_dir(world_dir) / "meta" / "game-start.json"
        data = json.loads(gs.read_text(encoding="utf-8")) if gs.exists() else {}
        data["name"] = name
        gs.parent.mkdir(parents=True, exist_ok=True)
        from neonrp.core.storage import atomic_write_json

        atomic_write_json(gs, data)
    except Exception:  # noqa: BLE001 — display name is cosmetic
        pass


def _resolve_creation_preset(explicit: str) -> str:
    """Which preset the web creation flows use, mirror of TUI's resolution:
    explicit(请求带的)→ create_provider(书房设置)→ 第一个可用 preset。
    没配任何 key 才返回 ''(前端引导去书房设置)。"""
    if explicit:
        return explicit
    try:
        from neonrp.presets import get_create_provider, list_presets

        cp = get_create_provider()
        if cp:
            return cp
        for p in list_presets():
            if p.get("available"):
                return str(p["id"])
    except Exception:  # noqa: BLE001
        pass
    return ""


def _apply_run_preset(run_dir: Path, preset_id: str) -> bool:
    """Write the chosen provider preset into a run's .neonrp/config.json.

    The PrePlay intake (visionrp-style 模型接入) lets the player pick which
    provider this run talks to — same persistence the TUI launcher uses
    (presets.build_config_dict). Returns False on unknown preset."""
    try:
        from neonrp.core.paths import get_neonrp_dir
        from neonrp.core.storage import atomic_write_json
        from neonrp.presets import build_config_dict

        cfg = build_config_dict(preset_id)
        atomic_write_json(get_neonrp_dir(run_dir) / "config.json", cfg)
        return True
    except Exception:  # noqa: BLE001 — surfaced as a clean HTTP error
        import logging

        logging.getLogger("neonrp").debug(
            "apply preset %s failed", preset_id, exc_info=True
        )
        return False


def _import_status_payload(root: Path) -> dict[str, Any]:
    """已导入文件夹的转换状态 —— 工坊三选项面板的数据源。

    对文件夹做确定性读取:已持久化源卡 + 尺寸估计 + 计划进度,以及工坊
    对话直接发送的三条开场指令(①计划-分批 / 续跑 / ②一次性)。指令在
    服务端组装,前端保持哑终端。无源卡 → {"has_source": False}。
    """
    from neonrp.core.import_plan import (
        estimate_source,
        load_plan,
        plan_path,
        resume_startup_command,
        start_planned_conversion,
    )

    imp_dir = plan_path(root).parent
    found = sorted(imp_dir.glob("source.*")) if imp_dir.is_dir() else []
    if not found:
        return {"has_source": False}
    src = found[0]
    rel = src.relative_to(root).as_posix()
    est = estimate_source(src)
    kind = "soul" if (root / "soul.json").exists() else "world"
    plan = load_plan(root)
    plan_info = None
    if plan is not None:
        nxt = plan.next_pending()
        plan_info = {
            "done": plan.done,
            "total": plan.total,
            "next_title": str((nxt or {}).get("title", "")),
            "complete": nxt is None,
        }
    if kind == "soul":
        oneshot = (
            f"读取已持久化的角色卡 {rel}(PNG 卡内嵌 JSON,用 `import_sillytavern_card` "
            "提取,不要当图片读),把这个角色补齐成完整 soul 结构:soul.md、persona/、"
            "character/、background/。忠实于卡片人设;面向玩家的文本用简体中文,id 保持 ASCII。"
        )
    else:
        oneshot = (
            "使用内置 skill `tavern-game-import`(一次性完成,不使用计划-分批协议)。\n"
            f"源文件路径:{rel}\n"
            "先读取卡片内容,对内容分类,就不明确的设计点问用户,再产出最小可玩切片。"
            "所有面向玩家的字段翻译成简体中文,id 保持 ASCII。"
        )
    return {
        "has_source": True,
        "source_rel": rel,
        "kind": kind,
        "format": est.get("format"),
        "bytes": est.get("bytes"),
        "entries": est.get("entries"),
        "recommend_plan": bool(est.get("recommend_plan")),
        "plan": plan_info,
        "start_command": start_planned_conversion(root, source_rel=rel),
        "resume_command": resume_startup_command(root),
        "oneshot_command": oneshot,
    }


class _Handler(NetRoutes, EngineRoutes, LauncherRoutes, HttpMixin, BaseHTTPRequestHandler):
    """引擎面 + launcher 面合体的 handler(`neonrp web` / `worldlines web`)。

    物理拆分后这里只剩分发:每个 do_* 先问引擎面(webui/
    engine_routes.py),再问 launcher 面(webui/launcher_routes.py),两边
    都不认领就落回原来的 404 兜底 —— if 链的相对顺序与拆分前一致。
    """

    server: Any  # ThreadingHTTPServer with .runtime attached

    def do_OPTIONS(self) -> None:  # noqa: N802 — http.server API
        if self._engine_route_options() or self._launcher_route_options():
            return
        self.send_error(404)

    def do_PUT(self) -> None:  # noqa: N802 — http.server API
        if self._engine_route_put() or self._launcher_route_put():
            return
        self.send_error(404)

    def do_DELETE(self) -> None:  # noqa: N802 — http.server API
        rt: WebRuntime | None = self.server.runtime
        if self._engine_route_delete(rt) or self._launcher_route_delete():
            return
        self.send_error(404)

    def do_GET(self) -> None:  # noqa: N802 — http.server API
        rt: WebRuntime | None = self.server.runtime
        if self._net_route_get() or self._engine_route_get(rt) or self._launcher_route_get(rt):
            return
        self.send_error(404)

    def do_POST(self) -> None:  # noqa: N802 — http.server API
        rt: WebRuntime | None = self.server.runtime
        if self._net_route_post() or self._engine_route_post(rt) or self._launcher_route_post(rt):
            return
        self.send_error(404)


def _bind_server(
    host: str,
    port: int,
    attempts: int = 20,
    handler: type[BaseHTTPRequestHandler] = _Handler,
) -> ThreadingHTTPServer:
    """Bind the HTTP server, falling back to the next free port.

    A stale server (an earlier `neonrp web`/launch still running) holds the
    requested port and makes a fresh bind raise OSError(EADDRINUSE), which
    used to crash the whole launch. Instead we walk a handful of sequential
    ports and, failing those, hand 0 to the OS so it picks any free port —
    so a launch never dies just because the default port is taken. The
    caller reads the real port back off ``server.server_address[1]``.

    ``NEONRP_STRICT_PORT=1`` (the e2e launchers, 10-18): only the requested port — a taken port is an error, not a
    quiet move to the next one (a test run that still talks to the requested port would play on someone else's engine)."""
    import errno
    import os

    last_err: OSError | None = None
    strict = os.environ.get("NEONRP_STRICT_PORT", "").strip().lower() in ("1", "true", "yes")
    for candidate in [port] if strict else [*range(port, port + attempts), 0]:
        try:
            return ThreadingHTTPServer((host, candidate), handler)
        except OSError as exc:
            if exc.errno in (errno.EADDRINUSE, errno.EADDRNOTAVAIL, errno.EACCES):
                last_err = exc
                continue
            raise
    # Exhausted every candidate including the OS-assigned port 0.
    raise last_err if last_err else OSError("could not bind web server")


def make_server(
    root: Path | None,
    agent_id: str,
    host: str,
    port: int,
    startup_commands: list[str] | None = None,
) -> ThreadingHTTPServer:
    """Build the HTTP server with a WebRuntime attached (testable seam).

    `root=None` starts in LAUNCHER MODE: no wrapped session yet — /launcher
    lists the local library and the first resolvable POST /api/v1/play/session
    {slug} binds one. `startup_commands` (the localized opening from
    _build_startup_handoff) is forwarded to the runtime and played once on
    first /start — so a fresh web launch streams the same kickoff the TUI
    does. If `port` is taken, binds the next free one (read it back from
    ``server.server_address[1]``)."""
    server = _bind_server(host, port)
    server.daemon_threads = True
    server.runtime = (  # type: ignore[attr-defined]
        WebRuntime(root, agent_id, startup_commands=startup_commands)
        if root is not None
        else None
    )
    server.edit_runtime = None  # type: ignore[attr-defined]  # CREATE contract (L0.1)
    return server


def _parent_alive(parent_pid: int) -> bool:
    """跨平台"父进程还活着吗"。

    POSIX:os.kill(pid, 0) 只探活。Windows 上这个写法是灾难——signal 0
    就是 CTRL_C_EVENT,GenerateConsoleCtrlEvent 对别的 pid 基本必失败,
    看门狗把 OSError 当"父进程没了",引擎启动 2 秒后自杀(桌面壳跳进
    Welcome 后 API 全灭的根因)。Windows 走 OpenProcess 探活。
    """
    if sys.platform == "win32":
        import ctypes

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        k32 = ctypes.windll.kernel32
        handle = k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, parent_pid)
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            if not k32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return False
            return code.value == STILL_ACTIVE
        finally:
            k32.CloseHandle(handle)
    try:
        os.kill(parent_pid, 0)  # 只探活,不发信号
        return True
    except OSError:
        return False


def start_parent_watchdog(parent_pid: int, interval: float = 2.0) -> threading.Thread:
    """Kill this process when parent_pid disappears.

    桌面壳(desktop/electron·tauri)把自己的 pid 传进来;壳被 SIGKILL 等
    任何方式带走时,引擎也跟着退,不留孤儿进程占端口。
    """

    def _watch() -> None:
        while True:
            time.sleep(interval)
            if not _parent_alive(parent_pid):
                os._exit(0)
                return  # 正常情况到不了这里;测试 stub 掉 _exit 后靠它停线程

    t = threading.Thread(target=_watch, daemon=True, name="parent-watchdog")
    t.start()
    return t


@click.command()
@click.option(
    "--project", "-p",
    type=click.Path(exists=True, file_okay=False),
    default=None,
    help="Project directory (default: current directory).",
)
@click.option("--host", default="127.0.0.1", help="Bind host (default 127.0.0.1).")
@click.option("--port", default=8787, type=int, help="Port (default 8787).")
@click.option(
    "--parent-pid",
    default=None,
    type=int,
    help="Exit when this process dies (desktop shells pass their own pid).",
)
@click.option("--no-browser", is_flag=True, help="Don't auto-open a browser window.")
def web(
    project: str | None,
    host: str,
    port: int,
    parent_pid: int | None,
    no_browser: bool,
) -> None:
    """[internal] Serve the web runtime — players: use `worldlines web`.

    Kept for the desktop shell and for development. For the engine API of
    one world without the web UI, see `neonrp serve`; to play in the
    browser, run `worldlines web`.

    \b
        neonrp web --project playground/stoneford-elena   # play one world
        neonrp web                                         # web launcher
        → open http://127.0.0.1:8787

    With no --project and no initialized world in the cwd, starts in
    LAUNCHER MODE: opens /launcher (your local library — continue a save,
    start a new run of an owned or built-in world) with no TUI involved.
    """
    root: Path | None
    if project:
        root = Path(project).resolve()
        if not get_manifest_path(root).exists():
            click.echo("Error: Not initialized. Run 'neonrp init' first.", err=True)
            raise SystemExit(1)
    else:
        cwd_root = get_project_root()
        root = cwd_root if get_manifest_path(cwd_root).exists() else None

    # /debug-grade recording for the lanes, no NEONRP_DEBUG needed.
    from neonrp.core.debug_flag import force_enable

    force_enable()

    # 桌面壳兜底:壳进程没了(哪怕 SIGKILL)引擎也自杀,不留孤儿占端口。
    if parent_pid is not None:
        start_parent_watchdog(parent_pid)

    agent_id = (get_startup_entry_agent(root) if root else None) or "world-agent"
    server = make_server(root, agent_id, host, port)
    bound_port = server.server_address[1]
    url = f"http://{host}:{bound_port}"
    if root is not None:
        click.echo(f"neonrp web · {root.name} · agent={agent_id}")
    else:
        click.echo("neonrp web · launcher mode(未绑定世界 — 用 LocalShell /local 选)")
    if bound_port != port:
        click.echo(f"  (port {port} was busy — using {bound_port})")
    # Launcher mode with the SPA packaged → land straight in the LocalShell.
    open_url = f"{url}/local" if (root is None and _spa_root() is not None) else url
    click.echo(f"→ {open_url}")
    if root is not None:  # 10-10: the same process is the host for networked clients (TUI --connect / --join)
        from neonrp.net.host import describe

        click.echo(f"  clients (TUI --connect): {describe(server, host, bound_port)}")
    if not no_browser:
        try:
            import webbrowser
            webbrowser.open(open_url)
        except Exception:
            pass
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        click.echo("\nbye")
    finally:
        server.shutdown()
