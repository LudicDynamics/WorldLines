"""The collection on the Worldlines account (10-18, core/collection_sync; docs/planning/COLLECTION-SYNC-1018.md): cards,
runs, characters (with their template version), achievements and endings go up to data ``hub/collection`` and come back
on another device; only adds, the newer ``updated`` wins, duplicates from two devices fold into one, pictures come from
the template. Plus the Free Zone: nobody comes home from a Free-Zone run (10-18)."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from neonrp import template
from neonrp.core import collection_sync as CS
from neonrp.core import player_data, rewards, sdk, truth_quiz
from neonrp.core.registry import load_registry
from _paths import PRODUCT

TEMPLATES = PRODUCT / "templates"


class FakeData:
    """data's hub/collection as the sync uses it: list mine (paged), batch create / put / delete (rev checked)."""

    def __init__(self, page: int = 3):
        self.rows: dict[str, dict] = {}
        self.n, self.page, self.calls = 0, page, []

    def __call__(self, method, path, token, body=None):
        self.calls.append((method, path.split("?")[0]))
        if token != "tok":
            raise CS.SyncError("relogin", "401")
        if method == "GET":
            cur = int(path.split("cursor=")[1]) if "cursor=" in path else 0
            ids = sorted(self.rows)
            chunk = [self.rows[i] for i in ids[cur:cur + self.page]]
            nxt = str(cur + self.page) if cur + self.page < len(ids) else None
            return 200, {"records": chunk, "next_cursor": nxt}
        assert method == "POST" and path == "/v1/records:batch" and body["product"] == "hub" and body["kind"] == "collection"
        res = []
        for op in body["ops"]:
            if op["op"] == "create":
                self.n += 1
                rid = f"r_{self.n:04d}"
                self.rows[rid] = {"id": rid, "rev": 1, "body": op["body"]}
                res.append({"status": 201})
            elif op["op"] == "put":
                r = self.rows[op["id"]]
                if r["rev"] != op["rev"]:
                    res.append({"status": 409})
                    continue
                r.update(rev=r["rev"] + 1, body=op["body"])
                res.append({"status": 200})
            elif op["op"] == "delete":
                self.rows.pop(op["id"], None)
                res.append({"status": 200})
        ok = sum(1 for r in res if r["status"] < 300)
        return 200, {"counts": {"ok": ok, "failed": len(res) - ok}, "results": res}

    def bodies(self, t: str) -> list[dict]:
        return [r["body"] for r in self.rows.values() if r["body"]["type"] == t]


@pytest.fixture
def cloud(monkeypatch):
    fake = FakeData()
    monkeypatch.setattr(CS, "_call", fake)
    monkeypatch.setattr(CS, "_token", lambda: "tok")
    return fake


def _device(tmp_path: Path, monkeypatch, name: str) -> Path:
    home = tmp_path / name
    monkeypatch.setattr(player_data, "HOME", home / "player-data")
    rewards._STORE.clear()
    return home


def _build(name: str, dest: Path, edit=None) -> Path:
    src = TEMPLATES / f"{name}.template"
    if edit is not None:
        cp = dest.parent / f"{name}-copy.template"
        shutil.copytree(src, cp)
        edit(cp)
        src = cp
    template.build(template.load(src), dest)
    return dest


def _beat(root: Path, turn: int, says: str = "", ops: list | None = None):
    return sdk.apply(root, list(ops or []), load_registry(root), turn=turn, player_says=says, narration=says)


def _play_pct(root: Path) -> None:
    _beat(root, 1, "", [{"op": "set", "var": "P01.stage", "value": 1}])
    r = _beat(root, 2, "我要离开这里,逃出去")
    assert r.ended and r.ended["id"] == "E02"


def test_one_device_up_another_down_with_pictures_from_the_template(tmp_path, monkeypatch, cloud):
    _device(tmp_path, monkeypatch, "a")
    root = _build("pct-house", tmp_path / "a-run")
    _play_pct(root)
    iid = next(i for i, s in player_data.run_souls(root).items() if s["sid"] == "chara")  # Winnie: pct-house's one who can come home (10-20)
    assert player_data.take(root, iid, "settlement", memory="fresh")
    st = CS.sync()
    assert st["state"] == "ok" and st["pushed"] > 0
    assert {b["key"] for b in cloud.bodies("card")} == {"half_burnt_diary", "way_out_in_fog"}
    card = next(b for b in cloud.bodies("card") if b["key"] == "half_burnt_diary")
    assert card["card"]["image_slot"] == "item.icon:I801" and card["version"] == "0.2" and "image" not in card["card"], "a slot, never the picture"
    assert card["card"]["title"]["en"] == "The Half-Burnt Diary"
    assert [b["key"] for b in cloud.bodies("run")] == ["a-run"] and cloud.bodies("run")[0]["run"]["ending"] == "E02"
    assert cloud.bodies("character")[0]["version"] == "0.2" and cloud.bodies("character")[0]["character"]["memory"] == "fresh"
    ach = {b["key"]: b["achievement"] for b in cloud.bodies("achievement")}
    assert ach["walked_out"]["title"]["ja"] == "もう一つの扉" and ach["walked_out"]["points"] == 10, "four-language face for the web"
    assert ach["first_ending"]["scope"] == "player"
    assert CS.sync()["pushed"] == 0, "nothing new: nothing sent"

    _device(tmp_path, monkeypatch, "b")
    st = CS.sync()
    assert st["state"] == "ok" and st["pulled"] >= 5 and st["pushed"] == 0
    pd = player_data.read()
    assert {c["id"] for c in pd["cards"]} == {"half_burnt_diary", "way_out_in_fog"}
    got = next(c for c in pd["cards"] if c["id"] == "half_burnt_diary")
    assert got["image"] and (rewards.card_dir("pct-house") / got["image"]).is_file(), "the picture from this machine's template"
    assert rewards.listing("en")["cards"][0]["image"].startswith("/api/v1/local/player-data/card?")
    assert [r["run"] for r in pd["runs"]] == ["a-run"] and pd["characters"][0]["version"] == "0.2"
    assert {"walked_out", "first_ending", "run_complete"} <= {a["id"] for a in pd["achievements"]}
    assert CS.sync()["pushed"] == 0, "what came down does not go back up"


def test_only_adds_newer_wins_and_duplicates_fold(tmp_path, monkeypatch, cloud):
    _device(tmp_path, monkeypatch, "a")
    _stage = lambda root, n: _beat(root, 1, "", [{"op": "set", "var": "P01.stage", "value": n}])  # noqa: E731
    _stage(_build("pct-house", tmp_path / "a-run"), 1)
    CS.sync()
    # the account lost nothing it had, and a thing only the account has comes down — this device keeps its own
    other = {**next(iter(cloud.rows.values()))["body"], "key": "fresh_plaster", "card": {"kind": "card", "rarity": "rare", "title": {"zh": "新抹的石灰"}}}
    cloud.rows["r_9000"] = {"id": "r_9000", "rev": 1, "body": other}
    for rid in [k for k, r in cloud.rows.items() if r["body"]["key"] == "half_burnt_diary"]:
        cloud.rows.pop(rid)  # gone from the account (not by us): this device puts it back, it never drops its own
    CS.sync()
    assert {c["id"] for c in player_data.read()["cards"]} == {"half_burnt_diary", "fresh_plaster"}
    assert {b["key"] for b in cloud.bodies("card")} == {"half_burnt_diary", "fresh_plaster"}, "put back"
    # newer wins: a pulled new face here (updated now) goes up; a newer one there comes down
    player_data.update("cards", {"id": "half_burnt_diary", "world": "pct-house"}, {"title": {"zh": "日记(新版)"}, "updated": "2030-10-18T09:00:00+0000"})
    CS.sync()
    up = next(r for r in cloud.rows.values() if r["body"]["key"] == "half_burnt_diary")
    assert up["body"]["card"]["title"] == {"zh": "日记(新版)"} and up["rev"] == 2
    up["body"] = {**up["body"], "updated": "2031-10-19T00:00:00Z", "card": {**up["body"]["card"], "title": {"zh": "日记(第三版)"}}}
    CS.sync()
    assert next(c for c in player_data.read()["cards"] if c["id"] == "half_burnt_diary")["title"] == {"zh": "日记(第三版)"}
    # two devices created the same thing at once: the newest stays, the other record goes
    dup = {**up["body"], "updated": "2026-10-01T00:00:00Z"}
    cloud.rows["r_9001"] = {"id": "r_9001", "rev": 1, "body": dup}
    CS.sync()
    assert [r["id"] for r in cloud.rows.values() if r["body"]["key"] == "half_burnt_diary"] == [up["id"]]


def test_signed_out_old_session_offline_leave_the_local_record_alone(tmp_path, monkeypatch, cloud):
    _device(tmp_path, monkeypatch, "a")
    monkeypatch.setattr(CS, "_token", lambda: None)
    assert CS.sync()["state"] == "signed_out" and not cloud.calls
    monkeypatch.setattr(CS, "_token", lambda: "old")
    assert CS.sync()["state"] == "relogin"
    assert CS.state()["state"] == "relogin"

    def down(*a, **k):
        raise CS.SyncError("offline", "no route")
    monkeypatch.setattr(CS, "_call", down)
    monkeypatch.setattr(CS, "_token", lambda: "tok")
    assert CS.sync()["state"] == "offline"
    monkeypatch.setenv("WORLDLINES_COLLECTION_SYNC", "0")
    assert CS.sync()["state"] == "off"


def test_schedule_never_runs_under_a_test_and_needs_a_session(monkeypatch):
    started = []
    monkeypatch.setattr(CS.threading, "Timer", lambda d, f: started.append(d) or type("T", (), {"start": lambda s: None, "daemon": True, "is_alive": lambda s: False})())
    CS.schedule()
    assert not started, "PYTEST_CURRENT_TEST"
    monkeypatch.delenv("PYTEST_CURRENT_TEST")
    CS.schedule()
    assert not started, "no session file, no PAT"
    monkeypatch.setenv("WORLDLINES_API_KEY", "pat")
    CS.schedule()
    assert started == [CS.DEBOUNCE_S]


def test_http_player_data_carries_the_sync_state_and_syncs_on_request(tmp_path, monkeypatch, cloud):
    import threading
    import urllib.request
    from unittest.mock import patch

    from neonrp.commands.web import make_server

    _device(tmp_path, monkeypatch, "a")
    _beat(_build("pct-house", tmp_path / "run"), 1, "", [{"op": "set", "var": "P01.stage", "value": 1}])
    monkeypatch.setenv("NEONRP_DISABLE_CLAUDE_CODE", "1")
    with patch("neonrp.worlds.PLAYS_HOME", tmp_path / "plays"):
        server = make_server(None, "world-agent", "127.0.0.1", 0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            req = urllib.request.Request(base + "/api/v1/local/player-data/sync", data=b"{}", method="POST", headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=60) as r:
                assert json.loads(r.read())["state"] == "ok"
            assert cloud.bodies("card")
            with urllib.request.urlopen(base + "/api/v1/local/player-data?lang=zh", timeout=60) as r:
                d = json.loads(r.read())
            assert d["sync"]["state"] == "ok" and "t" not in d["sync"]
        finally:
            server.shutdown()


# ── the Free Zone ────────────────────────────────────────────────────────────

def _open_zone(cp: Path) -> None:
    p = cp / "template.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    d["zone"] = "open"
    d.pop("forkable", None)
    p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")


def test_nobody_comes_home_from_a_free_zone_run(tmp_path, monkeypatch):
    _device(tmp_path, monkeypatch, "a")
    root = _build("pct-house", tmp_path / "run", _open_zone)
    assert player_data.free_zone(root)
    souls = player_data.run_souls(root)
    assert souls and not any(s["takeable"] for s in souls.values())
    iid = next(iter(souls))
    assert not player_data.take(root, iid, "settlement", memory="fresh")
    assert not player_data.gain(root, iid, "companion_at_ending")
    _play_pct(root)
    pd = player_data.read()
    assert pd["characters"] == [] and pd["cards"] == [], "no cards, nobody taken"
    assert pd["runs"] and pd["endings"], "the run itself is still the player's"
    assert truth_quiz.takeable(root) == [] and truth_quiz.reward_soul(root) is None, "the settlement offers nobody"
    # a default-zone run of the same world still lets them go
    other = _build("pct-house", tmp_path / "run2")
    assert not player_data.free_zone(other) and any(s["takeable"] for s in player_data.run_souls(other).values())
