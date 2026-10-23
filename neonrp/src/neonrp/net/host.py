"""The host side of the network layer, mounted on the engine's HTTP server (``neonrp serve``; 10-10).

    POST /rpc          one JSON-RPC request from a client → its response (``turn.send`` holds until the turn is done)
    GET  /rpc/events   SSE: the session bus as ``bus.message`` notifications (``?since=<seq>`` replays what a reconnecting
                       client missed) + the host's own requests to that client (``ask_user``), answered with ``reply``

Auth: ``Authorization: Bearer <token>`` — the host's own token (printed when the host starts) or a seat credential (from
an invite the host approved; net.seats). A seat sees only its share of the bus and may call only what its kind may.
The host is the only authority: clients send intents, the engine verifies and lands them.
"""
from __future__ import annotations

import collections
import dataclasses
import json
import queue
import secrets
import threading
from typing import Any
from urllib.parse import parse_qs, urlparse

from neonrp.net import protocol as P

_STREAM_TOPICS = ("engine/#", "world/#", "soul/#", "player/#")
_REPLAY = 2000  # bus notifications kept for clients that reconnect


class NetHub:
    """Per-server state: the token, the connected event streams, the host's open requests to clients."""

    def __init__(self, token: str | None = None, root: Any = None) -> None:
        from neonrp.net.seats import Room

        self.token = token or secrets.token_urlsafe(18)
        self.room = Room(root, self.token)
        self._lock = threading.Lock()
        self._streams: dict[str, queue.Queue] = {}  # client id → its SSE queue
        self._who: dict[str, Any] = {}  # client id → its Principal (what it may see)
        self._recent: collections.deque = collections.deque(maxlen=_REPLAY)
        self._bridged: Any = None
        self._pending: dict[str, tuple[threading.Event, list[Any]]] = {}
        self._req_ids = (f"h{i}" for i in range(1, 10**12))

    # -- bus → clients -----------------------------------------------------------------------------------------------
    def bridge(self, session: Any) -> None:
        """Forward the session bus to every connected client (once per session)."""
        if self._bridged is session:
            return
        self._bridged = session
        bus = session.bus()

        def _fwd(msg: Any) -> None:
            note = P.notification("bus.message", {"topic": msg.topic, "seq": msg.seq, "payload": msg.payload})
            with self._lock:
                self._recent.append(note)
                qs = [(q, self._who.get(c)) for c, q in self._streams.items()]
            for q, who in qs:
                if who is None or who.sees(msg.topic):  # a seat sees only its share (three-party isolation)
                    q.put(note)

        for t in _STREAM_TOPICS:
            bus.subscribe(t, _fwd)

    def open_stream(self, client: str, since: int | None, who: Any = None) -> queue.Queue:
        q: queue.Queue = queue.Queue()
        with self._lock:
            if since is not None:
                for note in self._recent:
                    if int(note["params"].get("seq") or 0) > since and (who is None or who.sees(str(note["params"].get("topic")))):
                        q.put(note)
            self._streams[client] = q
            self._who[client] = who
        return q

    def end_stream(self, client: str) -> None:
        """A client said goodbye: end its event stream now (not on the next heartbeat)."""
        with self._lock:
            q = self._streams.get(client)
        if q is not None:
            q.put(None)

    def tell_owner(self, method: str, params: dict[str, Any]) -> None:
        """A notification for the host's own clients (a join request …)."""
        note = P.notification(method, params)
        with self._lock:
            qs = [q for c, q in self._streams.items() if getattr(self._who.get(c), "owner", False)]
        for q in qs:
            q.put(note)

    def connected(self) -> dict[str, list[str]]:
        """seat → its connected client ids."""
        with self._lock:
            out: dict[str, list[str]] = {}
            for c, w in self._who.items():
                if c in self._streams and w is not None:
                    out.setdefault(w.seat, []).append(c)
        return out

    def close_stream(self, client: str, q: queue.Queue) -> None:
        with self._lock:
            if self._streams.get(client) is q:
                self._streams.pop(client, None)
                self._who.pop(client, None)

    # -- host → one client: a request that waits for its reply ---------------------------------------------------------
    def ask(self, client: str, method: str, params: dict[str, Any], timeout: float) -> Any:
        """Send ``method`` to ``client`` and wait for its ``reply``; None on timeout or when the client has no stream."""
        with self._lock:
            q = self._streams.get(client)
        if q is None:
            return None
        rid = next(self._req_ids)
        ev, box = threading.Event(), []
        with self._lock:
            self._pending[rid] = (ev, box)
        q.put(P.request(method, params, id=rid))
        ev.wait(timeout)
        with self._lock:
            self._pending.pop(rid, None)
        return box[0] if box else None

    def reply(self, rid: str, value: Any) -> bool:
        with self._lock:
            p = self._pending.get(rid)
        if p is None:
            return False  # late or unknown: dropped (a late answer never rewrites a landed turn)
        p[1].append(value)
        p[0].set()
        return True


def hub_of(server: Any) -> NetHub:
    hub = getattr(server, "net_hub", None)
    if hub is None:
        rt = getattr(server, "runtime", None)
        hub = server.net_hub = NetHub(root=getattr(rt, "root", None))
    return hub


def _result_dict(res: Any) -> dict[str, Any]:
    if dataclasses.is_dataclass(res):
        return {k: v for k, v in dataclasses.asdict(res).items() if k != "proposal"}
    return dict(res) if isinstance(res, dict) else {"success": False, "error": "no result"}


def _message_dict(m: Any) -> dict[str, Any]:
    return {"role": getattr(m, "role", ""), "content": getattr(m, "content", None), "name": getattr(m, "name", None)}


class NetRoutes:
    """Mixin for the engine handler (EngineRoutes + HttpMixin + BaseHTTPRequestHandler)."""

    server: Any
    headers: Any
    path: str
    rfile: Any
    wfile: Any

    def _net_principal(self) -> Any:
        """Who is calling (the host or a seat), from ``Authorization: Bearer …``; None = nobody."""
        tok = str(self.headers.get("Authorization") or "")
        return hub_of(self.server).room.principal(tok[7:] if tok.startswith("Bearer ") else "")

    def _net_route_get(self) -> bool:
        u = urlparse(self.path)
        if u.path != "/rpc/events":
            return False
        who = self._net_principal()
        if who is None:
            self.send_error(401, "bad token")
            return True
        q_ = parse_qs(u.query)
        client = str((q_.get("client") or [""])[0]) or secrets.token_hex(4)
        since = int(q_["since"][0]) if q_.get("since") and q_["since"][0].lstrip("-").isdigit() else None
        hub = hub_of(self.server)
        rt = getattr(self.server, "runtime", None)
        if rt is not None:
            hub.bridge(rt.session())
        q = hub.open_stream(client, since, who)
        soul_route = None
        if getattr(who, "kind", "") in ("soul", "character") and who.target:  # her seat is connected: questions to her go here
            from neonrp.core import soul_remote

            def soul_route(*, question: str, beat: Any = None, timeout: float = 10.0) -> Any:
                return hub.ask(client, "soul.ask", {"iid": who.target, "question": question, "beat": beat or None}, timeout)

            soul_remote.register(who.target, soul_route, human=who.kind == "character")
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        try:
            self.wfile.write(f": {P.PROTOCOL} client={client}\n\n".encode())
            self.wfile.flush()
            while True:
                try:
                    msg = q.get(timeout=15)
                    if msg is None:  # goodbye
                        break
                    data = P.dumps(msg)
                except queue.Empty:
                    data = None
                self.wfile.write((f"data: {data}\n\n" if data else ": ping\n\n").encode())  # heartbeat
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            hub.close_stream(client, q)
            if soul_route is not None:
                from neonrp.core import soul_remote

                soul_remote.unregister(who.target, soul_route)
        return True

    def _net_route_post(self) -> bool:
        if urlparse(self.path).path != "/rpc":
            return False
        n = int(self.headers.get("Content-Length") or 0)
        try:
            req = P.parse(self.rfile.read(n) if n else b"")
        except ValueError as e:
            self._net_send(P.error(None, P.PARSE_ERROR, str(e)))
            return True
        rid, method, params = req.get("id"), str(req.get("method") or ""), req.get("params") or {}
        who = self._net_principal()
        if who is None and method not in ("session.join", "session.join_status"):  # joining needs only the invite
            self._net_send(P.error(rid, P.UNAUTHORIZED, "bad token"), status=401)
            return True
        if who is not None and not who.may_call(method):
            self._net_send(P.error(rid, P.FORBIDDEN, f"seat {who.seat} may not call {method}"))
            return True
        try:
            self._net_send(P.result(rid, self._net_call(method, params, who)))
        except P.RpcError as e:
            self._net_send(P.error(rid, e.code, e.message, e.data))
        except Exception as e:  # noqa: BLE001 — a crashed call answers, it never kills the host
            self._net_send(P.error(rid, P.INTERNAL_ERROR, f"{type(e).__name__}: {e}"))
        return True

    def _net_send(self, msg: dict[str, Any], status: int = 200) -> None:
        body = P.dumps(msg).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _net_call(self, method: str, params: dict[str, Any], who: Any = None) -> Any:
        hub = hub_of(self.server)
        room = hub.room
        if method == "session.join":  # an invite → a pending request (or the credential, when the room auto-approves)
            try:
                out = room.request_join(str(params.get("invite") or ""), str(params.get("who") or ""))
            except PermissionError as e:
                raise P.RpcError(P.UNAUTHORIZED, str(e)) from e
            if out.get("pending"):
                hub.tell_owner("room.join_request", {"request": out["pending"], "seat": out["seat"], "who": params.get("who")})
            return out
        if method == "session.join_status":
            return room.join_status(str(params.get("request") or ""))
        if method == "room.invite":
            host = str(self.headers.get("Host") or "")
            try:
                return room.invite(str(params.get("kind") or ""), str(params.get("target") or ""), str(params.get("label") or ""), host)
            except ValueError as e:
                raise P.RpcError(P.INVALID_PARAMS, str(e)) from e
        if method == "room.seats":
            on = hub.connected()
            return {"room": room.id, "auto_approve": room.auto_approve,
                    "seats": [{"seat": k, **v, "connected": len(on.get(k, []))} for k, v in room.seats.items()]}
        if method == "room.pending":
            return room.pending()
        if method == "room.approve":
            try:
                room.approve(str(params.get("request") or ""))
            except KeyError as e:
                raise P.RpcError(P.INVALID_PARAMS, str(e)) from e
            return {"ok": True}
        if method == "room.deny":
            return {"ok": room.deny(str(params.get("request") or ""))}
        if method == "room.revoke":
            return {"revoked": room.revoke(str(params.get("seat") or ""))}
        if method == "room.auto_approve":
            room.auto_approve = bool(params.get("on"))
            room._save()
            return {"auto_approve": room.auto_approve}
        if method == "session.bye":
            hub.end_stream(str(params.get("client") or ""))
            return {"ok": True}
        if method == "session.whoami":
            return {"seat": getattr(who, "seat", None), "kind": getattr(who, "kind", None), "target": getattr(who, "target", None)}
        if method == "session.hello":
            if str(params.get("protocol") or "") != P.PROTOCOL:
                raise P.RpcError(P.VERSION_MISMATCH, f"host speaks {P.PROTOCOL}, client {params.get('protocol')!r}")
            rt = getattr(self.server, "runtime", None)
            return {"protocol": P.PROTOCOL, "world": getattr(getattr(rt, "root", None), "name", None),
                    "agent_id": getattr(rt, "agent_id", None)}
        if method == "reply":
            return {"accepted": hub.reply(str(params.get("id") or ""), params.get("result"))}
        rt = getattr(self.server, "runtime", None)
        if rt is None:
            raise P.RpcError(P.NO_SESSION, "no play session")
        session = rt.session()
        hub.bridge(session)
        if method == "turn.send":
            text, client = str(params.get("text") or ""), str(params.get("client") or "")
            if not rt._busy.acquire(blocking=False):
                raise P.RpcError(P.BUSY, "a turn is already running")
            try:
                def _ask(question: str, options: list[str]) -> str | None:  # the turn asks the human: route to this client
                    ans = hub.ask(client, "ask_user", {"question": question, "options": list(options or [])}, timeout=300)
                    return None if ans is None else str(ans)

                return _result_dict(session.send(text, on_ask_user=_ask if client else None))
            finally:
                rt._busy.release()
        if method == "turn.cancel":
            session.cancel()
            return {"ok": True}
        if method == "session.state":
            return {"branch": session.branch, "mode": session.mode, "agent_id": session.agent_id,
                    "total_turns": getattr(session, "total_turns", 0), "total_usage": dict(getattr(session, "total_usage", {}) or {}),
                    "recent_files": list(getattr(session, "recent_files", []) or []), "messages": len(session.messages),
                    "bus_seq": session.bus().seq}
        if method == "session.messages":
            if params.get("resume"):
                session.resume()
            return [_message_dict(m) for m in session.get_messages()]
        if method == "session.clear":
            session.clear()
            return {"ok": True}
        if method == "session.set_mode":
            session.set_mode(str(params.get("mode") or "play"))
            return {"ok": True, "mode": session.mode}
        raise P.RpcError(P.METHOD_NOT_FOUND, f"no method {method!r}")


def describe(server: Any, host: str, port: int) -> str:
    """What a client needs to connect (printed by ``neonrp serve``)."""
    return json.dumps({"url": f"http://{host}:{port}", "token": hub_of(server).token, "protocol": P.PROTOCOL})
