"""``EngineClient`` — how a front end (the TUI first) plays a world, wherever the engine runs (10-10: the TUI is a client).

Two implementations of one surface:

- ``InProcessClient``  the engine in this process (today's behaviour, zero latency) — wraps ``ConversationSession``
- ``RemoteClient``     the engine in a host process, local or across the network — JSON-RPC over HTTP + SSE (net.host)

The surface is what the TUI's play path uses: ``send(text, on_ask_user)``, ``bus()`` (subscribe to engine/stream ·
engine/event · engine/beat …), ``cancel · clear · resume · get_messages · set_mode`` and the session's ``branch · mode ·
agent_id · messages · total_usage · total_turns · recent_files``. A remote client mirrors the host's bus into a local one,
so the TUI's subscriptions are the same whichever client it holds.
"""
from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

from neonrp.net import protocol as P


def connect(root: Path | None = None, *, agent_id: str = "world-agent", mode: str = "play", provider: str | None = None,
            url: str | None = None, token: str | None = None) -> Any:
    """The client for this front end: remote when ``url`` is given, else the engine in this process."""
    if url:
        return RemoteClient(url, token or "")
    from neonrp.core.conversation import ConversationSession

    return InProcessClient(ConversationSession(root=root, agent_id=agent_id, mode=mode, provider=provider))  # type: ignore[arg-type]


class InProcessClient:
    """The engine in this process. Every attribute not defined here is the session's own (behaviour unchanged)."""

    remote = False

    def __init__(self, session: Any) -> None:
        self._session = session

    def __getattr__(self, name: str) -> Any:
        return getattr(self._session, name)

    def __setattr__(self, name: str, value: Any) -> None:
        if name == "_session":
            object.__setattr__(self, name, value)
        else:
            setattr(self._session, name, value)

    @property
    def session(self) -> Any:
        return self._session


class RemoteClient:
    """The engine in a host process. ``send`` blocks until the turn is done (like the in-process one); the stream arrives
    meanwhile on the local mirror bus; the host's ``ask_user`` requests are answered with the callback ``send`` got."""

    remote = True

    def __init__(self, url: str, token: str, *, client_id: str | None = None, timeout: float = 600.0) -> None:
        import secrets

        from neonrp.core.message_bus import InProcessBus

        self.url, self.token, self.timeout = url.rstrip("/"), token, timeout
        self.client_id = client_id or secrets.token_hex(4)
        self._bus = InProcessBus()
        self._ask: Callable[[str, list[str]], str | None] | None = None
        self._handlers: dict[str, Callable[[dict[str, Any]], Any]] = {}
        self._host_seq: int | None = None
        self._stop = threading.Event()
        self._ready = threading.Event()
        self.hello = self.call("session.hello", {"protocol": P.PROTOCOL})
        self._sse = threading.Thread(target=self._listen, name=f"net-sse-{self.client_id}", daemon=True)
        self._sse.start()
        self._ready.wait(10)

    @classmethod
    def join(cls, url: str, invite: str, *, who: str = "", wait: float = 300.0, store: Path | None = None,
             on_pending: Callable[[str], None] | None = None) -> RemoteClient:
        """Take a seat with an invite (link token or short code): ask, wait for the host to approve (``on_pending`` hears
        the request id), then connect with the seat credential. With ``store`` the credential is kept for next time."""
        import time

        probe = cls.__new__(cls)
        probe.url, probe.token, probe.timeout = url.rstrip("/"), "", 30.0
        out = probe.call("session.join", {"invite": invite, "who": who})
        cred = out.get("credential")
        if not cred:
            rid = str(out.get("pending") or "")
            if on_pending:
                on_pending(rid)
            end = time.time() + wait
            while time.time() < end:
                st = probe.call("session.join_status", {"request": rid})
                if st.get("credential"):
                    cred = st["credential"]
                    break
                if not st.get("pending"):
                    raise P.RpcError(P.UNAUTHORIZED, "the host declined")
                time.sleep(0.5)
            else:
                raise P.RpcError(P.UNAUTHORIZED, "the host did not answer in time")
        if store is not None:
            save_credential(store, url, str(cred))
        return cls(url, str(cred))

    # -- transport -----------------------------------------------------------------------------------------------------
    def _post(self, msg: dict[str, Any], timeout: float | None = None) -> dict[str, Any]:
        req = urllib.request.Request(self.url + "/rpc", data=P.dumps(msg).encode("utf-8"), method="POST",
                                     headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.token}"})
        try:
            with urllib.request.urlopen(req, timeout=timeout or self.timeout) as r:
                return P.parse(r.read())
        except urllib.error.HTTPError as e:
            try:
                return P.parse(e.read())
            except ValueError:
                raise P.RpcError(P.UNAUTHORIZED if e.code == 401 else P.INTERNAL_ERROR, f"HTTP {e.code}") from e

    def call(self, method: str, params: dict[str, Any] | None = None, timeout: float | None = None) -> Any:
        # only a turn may take long; everything else answers fast or fails fast (a gone host never hangs the front end)
        resp = self._post(P.request(method, params), timeout or (self.timeout if method == "turn.send" else 10.0))
        if "error" in resp:
            err = resp["error"] or {}
            raise P.RpcError(int(err.get("code") or P.INTERNAL_ERROR), str(err.get("message") or ""), err.get("data"))
        return resp.get("result")

    def _listen(self) -> None:
        """The host's event stream; reconnects and asks for what it missed (``since``) until closed."""
        while not self._stop.is_set():
            q = f"?client={self.client_id}" + (f"&since={self._host_seq}" if self._host_seq is not None else "")
            req = urllib.request.Request(self.url + "/rpc/events" + q, headers={"Authorization": f"Bearer {self.token}"})
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    self._ready.set()
                    for raw in r:
                        if self._stop.is_set():
                            return
                        line = raw.decode("utf-8").rstrip("\n")
                        if line.startswith("data: "):
                            self._on_message(json.loads(line[6:]))
            except Exception:  # noqa: BLE001 — dropped: reconnect after a breath
                self._ready.set()
                self._stop.wait(1.0)

    def _on_message(self, msg: dict[str, Any]) -> None:
        if msg.get("method") == "bus.message":
            p = msg.get("params") or {}
            self._host_seq = int(p.get("seq") or 0)
            self._bus.publish(str(p.get("topic") or ""), dict(p.get("payload") or {}))
        elif msg.get("id") is None and msg.get("method"):  # the host's own notices (room.join_request …) → local net/<method>
            self._bus.publish(f"net/{msg['method']}", dict(msg.get("params") or {}))
        elif msg.get("id") is not None and msg.get("method"):  # the host asks this client something; answer with reply
            p = msg.get("params") or {}
            m = str(msg["method"])
            if m == "ask_user":
                ans = self._ask(str(p.get("question") or ""), list(p.get("options") or [])) if self._ask else None
            else:
                fn = self._handlers.get(m)
                ans = fn(p) if fn else None

            def _reply(rid: Any = msg["id"], value: Any = ans) -> None:
                try:
                    self.call("reply", {"id": rid, "result": value})
                except Exception:  # noqa: BLE001 — the host stopped waiting
                    pass

            threading.Thread(target=_reply, daemon=True).start()

    def on(self, method: str, fn: Callable[[dict[str, Any]], Any]) -> None:
        """Answer the host's ``method`` requests (a remote character: ``soul.ask`` → her own words)."""
        self._handlers[method] = fn

    def close(self) -> None:
        """Leave: tell the host (it drops this client's stream and routes at once), then stop listening."""
        self._stop.set()
        try:
            self.call("session.bye", {"client": self.client_id}, timeout=3)
        except Exception:  # noqa: BLE001 — the host is gone already
            pass

    # -- the session surface -------------------------------------------------------------------------------------------
    def bus(self) -> Any:
        return self._bus

    def send(self, text: str, *, on_ask_user: Callable[[str, list[str]], str | None] | None = None, **_: Any) -> Any:
        from neonrp.core.conversation import ConversationTurnResult

        self._ask = on_ask_user
        try:
            r = self.call("turn.send", {"text": text, "client": self.client_id})
        except P.RpcError as e:
            return ConversationTurnResult(success=False, run_id="", error=str(e))
        fields = set(ConversationTurnResult.__dataclass_fields__)
        return ConversationTurnResult(**{k: v for k, v in (r or {}).items() if k in fields})

    def cancel(self) -> None:
        self.call("turn.cancel", timeout=10)

    def clear(self) -> None:
        self.call("session.clear")

    def resume(self) -> bool:
        return bool(self.call("session.messages", {"resume": True}) is not None)

    def get_messages(self) -> list[Any]:
        from neonrp.core.llm import Message

        try:
            rows = self.call("session.messages") or []
        except Exception:  # noqa: BLE001 — host gone: nothing to show, never a hang
            rows = []
        return [Message(role=m.get("role") or "assistant", content=m.get("content")) for m in rows]

    def set_mode(self, mode: str) -> None:
        self.call("session.set_mode", {"mode": mode})

    def _state(self) -> dict[str, Any]:
        try:
            return dict(self.call("session.state", timeout=10) or {})
        except Exception:  # noqa: BLE001
            return {}

    @property
    def branch(self) -> str:
        return str(self._state().get("branch") or "main")

    @property
    def mode(self) -> str:
        return str(self._state().get("mode") or "play")

    @property
    def agent_id(self) -> str:
        return str(self._state().get("agent_id") or (self.hello or {}).get("agent_id") or "world-agent")

    @property
    def messages(self) -> list[Any]:
        return self.get_messages()

    @property
    def total_usage(self) -> dict[str, Any]:
        return dict(self._state().get("total_usage") or {})

    @property
    def total_turns(self) -> int:
        return int(self._state().get("total_turns") or 0)

    @property
    def recent_files(self) -> list[str]:
        return list(self._state().get("recent_files") or [])

    def _current_branch(self) -> str:
        return self.branch


def credentials_file() -> Path:
    """Where seat credentials are kept between runs (the launcher owns ~/.worldlines)."""
    return Path.home() / ".worldlines" / "net" / "credentials.json"


def save_credential(store: Path, url: str, cred: str) -> None:
    try:
        d = json.loads(store.read_text(encoding="utf-8")) if store.is_file() else {}
    except (OSError, ValueError):
        d = {}
    d[url.rstrip("/")] = cred
    store.parent.mkdir(parents=True, exist_ok=True)
    store.write_text(json.dumps(d, indent=1), encoding="utf-8")
    try:
        store.chmod(0o600)
    except OSError:
        pass


def saved_credential(store: Path, url: str) -> str | None:
    """A seat credential kept for this host (reconnect without the link)."""
    try:
        return json.loads(store.read_text(encoding="utf-8")).get(url.rstrip("/"))
    except (OSError, ValueError):
        return None


def as_session(client: Any) -> Any:
    """The in-process session behind a client (None for a remote one) — for the few TUI paths not yet on the client."""
    return getattr(client, "session", None) if not getattr(client, "remote", False) else None


__all__ = ["connect", "InProcessClient", "RemoteClient", "as_session", "credentials_file", "save_credential", "saved_credential"]
