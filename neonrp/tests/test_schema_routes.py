"""Schema over HTTP (webui/schema_routes.py): workbench read / register / unregister / history / events / SSE."""
from __future__ import annotations

import json
import shutil
import threading
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

import neonrp
from neonrp.core import ledger

TEMPLATE = Path(neonrp.__file__).parent / "templates" / "stoneford-elena"
P = "/api/v1/create/session/edit-local/schema"


def _req(base: str, path: str, method="GET", body: dict | None = None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(f"{base}{path}", data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if r.headers.get_content_type() == "application/json" else raw.decode())
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except ValueError:
            return e.code, None


def test_workbench_schema_routes(tmp_path: Path) -> None:
    from neonrp.commands.web import make_server
    from neonrp.core.manifest import Manifest

    worlds = tmp_path / "lib" / "worlds"
    shutil.copytree(TEMPLATE, worlds / "stone")
    (worlds / "stone" / ".neonrp").mkdir(exist_ok=True)
    m = Manifest()
    m.branches["main"].head_event = -1
    (worlds / "stone" / ".neonrp" / "manifest.json").write_text(json.dumps(m.model_dump(), default=str))
    with (
        patch("neonrp.worlds.WORLDS_HOME", worlds),
        patch("neonrp.worlds.PLAYS_HOME", tmp_path / "lib" / "plays"),
        patch("neonrp.worlds.STUDIO_HOME", tmp_path / "lib" / "studio"),
    ):
        server = make_server(None, "world-agent", "127.0.0.1", 0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            # play side has no bound run → 409 (the edit side may rebind a persisted session, so not asserted)
            assert _req(base, "/api/v1/play/schema")[0] == 409
            assert _req(base, "/api/v1/create/session", "POST", {"world_id": "stone"})[0] == 200
            root = worlds / "stone"

            st, v = _req(base, P)
            assert st == 200 and v["template"] == "rpg" and v["schema_version"] == 1 and v["turn_mode"] in ("v2b", "v3")
            gold = next(x for x in v["variables"] if x["name"] == "player.gold")
            assert gold["type"] == "int" and "value" in gold
            assert "place" in [c["name"] for c in v["classes"]] and v["entries"]["place"]

            # closed schema: register a variable
            spec = {"type": "int", "path": "game/towns/T001/market.json", "key": "price.grain", "min": 1, "max": 99}
            st, r = _req(base, f"{P}/register", "POST", {"table": "variables", "id": "price.T001.grain", "spec": spec})
            assert st == 200 and r["ok"] and "price.T001.grain" in [x["name"] for x in r["schema"]["variables"]]
            # validation errors come back as 400 + message
            st, r = _req(base, f"{P}/register", "POST", {"table": "variables", "id": "bad", "spec": {"type": "money", "path": "a", "key": "b"}})
            assert st == 400 and "int|float|str|bool" in r["error"]
            st, r = _req(base, f"{P}/register", "POST", {"table": "entries", "id": "F1", "spec": {"class": "faction", "props": {"name": "x"}}})
            assert st == 400 and "register it in classes first" in r["error"]
            # open schema: class then instance
            cls = {"required": ["name"], "folder": "game/factions", "props": {"power": {"type": "int", "min": 0, "max": 100}}}
            assert _req(base, f"{P}/register", "POST", {"table": "classes", "id": "faction", "spec": cls})[0] == 200
            st, r = _req(base, f"{P}/register", "POST", {"table": "entries", "id": "F_bandits", "spec": {"class": "faction", "props": {"name": "独眼虎山贼", "power": 46}}})
            assert st == 200, r
            # unregister
            assert _req(base, f"{P}/unregister", "POST", {"table": "variables", "id": "price.T001.grain"})[0] == 200
            st, v = _req(base, P)
            assert "price.T001.grain" not in [x["name"] for x in v["variables"]]
            # players can't register
            assert _req(base, "/api/v1/play/schema/register", "POST", {"table": "variables", "id": "x", "spec": spec})[0] in (403, 409)

            # pull + push
            ledger.append(root, 2, [("var.changed", {"var": "player.gold", "from": 18, "to": 25, "by": "solve"}),
                                    ("entity.created", {"id": "N1", "class": "place"})])
            st, h = _req(base, f"{P}/history?var=player.gold")
            assert st == 200 and h[0]["to"] == 25
            assert _req(base, f"{P}/history")[0] == 400
            st, evs = _req(base, f"{P}/events?type=entity.created")
            assert st == 200 and evs[0]["payload"]["id"] == "N1"
            st, body = _req(base, f"{P}/stream?pattern=var.changed:player.gold&since=0&timeout=0.3")
            assert st == 200 and "event: hello" in body
            datas = [d for d in (json.loads(line[6:]) for line in body.splitlines() if line.startswith("data: ")) if "type" in d]
            assert len(datas) == 1 and datas[0]["payload"]["to"] == 25
        finally:
            server.shutdown()
