"""Seats and invites.

A **seat** is a place at the table: ``player`` (a person; ``target`` = pid), ``player-agent`` (an AI playing for a pid),
``soul`` (a character played by an agent elsewhere; ``target`` = its instance id) or ``character`` (a character played by
a person elsewhere — the way a second human joins the world: 10-10, each human plays a character in it). The host hands out a one-time **invite** for a seat; whoever
opens it asks to sit there; the host **approves once**; the client gets a long-lived **seat credential** and reconnects
with it by itself. Only hashes of tokens are kept, in ``<world>/.neonrp/room.json``.

What a seat sees (three-party isolation, 10-01): a player / player agent — the story (``engine/#``, ``world/narration``)
and its own ``player/<pid>/#``; a character — only ``soul/<iid>/#`` (its own perceptions and questions, never the
scene's narration). The host sees everything. What a seat may call is in ``may_call``.
"""
from __future__ import annotations

import hashlib
import json
import secrets
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from neonrp.core.message_bus import topic_matches

KINDS = ("player", "player-agent", "soul", "character")
OWNER = "@host"


def _h(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Principal:
    """Who is calling: the host (owner) or one seat."""

    seat: str  # OWNER or a seat id
    kind: str  # "owner" | a seat kind
    target: str = ""

    @property
    def owner(self) -> bool:
        return self.seat == OWNER

    def sees(self, topic: str) -> bool:
        if self.owner:
            return True
        if self.kind == "soul":
            return topic_matches(f"soul/{self.target}/#", topic)
        if self.kind == "character":  # a person playing a character: the story, and that character's own channel
            return topic_matches("engine/#", topic) or topic == "world/narration" or topic_matches(f"soul/{self.target}/#", topic)
        return (topic_matches("engine/#", topic) or topic == "world/narration"
                or topic_matches(f"player/{self.target}/#", topic))

    def may_call(self, method: str) -> bool:
        if self.owner:
            return True
        if method.startswith("room."):
            return False
        if method in ("turn.send", "turn.cancel"):
            return self.kind in ("player", "player-agent")
        return method.startswith(("session.", "soul.")) or method == "reply"


class Room:
    """The host's seats, invites and credentials (one per world, persisted next to it)."""

    def __init__(self, root: Path | None, host_token: str) -> None:
        self._lock = threading.Lock()
        self._file = (Path(root) / ".neonrp" / "room.json") if root is not None else None
        self._owner = _h(host_token)
        d: dict[str, Any] = {}
        if self._file is not None and self._file.is_file():
            try:
                d = json.loads(self._file.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                d = {}
        self.id: str = str(d.get("id") or secrets.token_hex(3))
        self.auto_approve: bool = bool(d.get("auto_approve", False))
        self.seats: dict[str, dict[str, Any]] = dict(d.get("seats") or {})
        self._invites: dict[str, dict[str, Any]] = dict(d.get("invites") or {})
        self._creds: dict[str, str] = dict(d.get("creds") or {})
        self._pending: dict[str, dict[str, Any]] = {}
        self._issued: dict[str, str] = {}  # request id → credential, handed out once on the next status poll

    def _save(self) -> None:
        if self._file is None:
            return
        self._file.parent.mkdir(parents=True, exist_ok=True)
        self._file.write_text(json.dumps({"id": self.id, "auto_approve": self.auto_approve, "seats": self.seats,
                                          "invites": self._invites, "creds": self._creds}, ensure_ascii=False, indent=1),
                              encoding="utf-8")

    # -- who is calling ------------------------------------------------------------------------------------------------
    def principal(self, bearer: str) -> Principal | None:
        if not bearer:
            return None
        h = _h(bearer)
        if secrets.compare_digest(h, self._owner):
            return Principal(OWNER, "owner")
        seat = self._creds.get(h)
        s = self.seats.get(seat or "")
        return Principal(seat, str(s["kind"]), str(s.get("target") or "")) if seat and s else None

    # -- host: seats and invites ---------------------------------------------------------------------------------------
    def seat_id(self, kind: str, target: str) -> str:
        if kind not in KINDS:
            raise ValueError(f"seat kind must be one of {KINDS}")
        if not target:
            raise ValueError("a seat needs a target (pid / soul instance id)")
        return f"{kind}:{target}"

    def invite(self, kind: str, target: str, label: str = "", host: str = "") -> dict[str, Any]:
        sid = self.seat_id(kind, target)
        tok = secrets.token_urlsafe(16)
        code = "-".join(secrets.token_hex(2).upper() for _ in range(2))
        with self._lock:
            self.seats.setdefault(sid, {"kind": kind, "target": target, "label": label or target})
            self._invites[_h(tok)] = {"seat": sid, "used": False, "at": time.time()}
            self._invites[_h(code)] = {"seat": sid, "used": False, "at": time.time(), "short": True}
            self._save()
        link = f"worldlines://join?h={host}&room={self.id}&seat={sid}&t={tok}"
        return {"seat": sid, "token": tok, "code": code, "link": link}

    def revoke(self, seat: str) -> int:
        """Remove a seat's credentials and open invites (the person is out; the seat stays, empty)."""
        with self._lock:
            n = len([h for h, s in self._creds.items() if s == seat])
            self._creds = {h: s for h, s in self._creds.items() if s != seat}
            self._invites = {h: i for h, i in self._invites.items() if i.get("seat") != seat}
            self._save()
        return n

    # -- a client: join ------------------------------------------------------------------------------------------------
    def request_join(self, invite: str, who: str = "") -> dict[str, Any]:
        """Use an invite (link token or short code). Auto-approve → the credential now; else a pending request."""
        h = _h(str(invite or "").strip())
        with self._lock:
            inv = self._invites.get(h)
            if inv is None or inv.get("used"):
                raise PermissionError("invite unknown or already used")
            inv["used"] = True
            rid = secrets.token_urlsafe(9)
            self._pending[rid] = {"seat": inv["seat"], "who": who, "at": time.time()}
            self._save()
        if self.auto_approve:
            return {"credential": self.approve(rid), "seat": inv["seat"]}
        return {"pending": rid, "seat": inv["seat"]}

    def approve(self, rid: str) -> str:
        with self._lock:
            req = self._pending.pop(rid, None)
            if req is None:
                raise KeyError("no such request")
            cred = secrets.token_urlsafe(24)
            self._creds[_h(cred)] = req["seat"]
            self._issued[rid] = cred
            self._save()
        return cred

    def deny(self, rid: str) -> bool:
        with self._lock:
            return self._pending.pop(rid, None) is not None

    def join_status(self, rid: str) -> dict[str, Any]:
        with self._lock:
            if rid in self._issued:
                cred = self._issued.pop(rid)
                seat = self._creds.get(_h(cred), "")
                return {"approved": True, "credential": cred, "seat": seat}
            if rid in self._pending:
                return {"approved": False, "pending": True}
        return {"approved": False, "pending": False}

    def pending(self) -> list[dict[str, Any]]:
        with self._lock:
            return [{"request": r, **v} for r, v in self._pending.items()]
