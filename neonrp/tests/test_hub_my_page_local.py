"""Hub「我的」页的本地引擎接口(10-15,hub2):
- 分身:GET/POST /api/v1/local/avatar · /avatar/current · /avatar/portrait;/api/v1/local/souls 的 avatars 带 current / portrait_url
- 开局用分身当主角:POST /api/v1/play/session {avatar: <file>|"current"}(只对新开的一局、没走捏人时)
- 继续世界:/api/v1/play/saves 每行带 template / turns。stub,不调模型。"""
from __future__ import annotations

import json
import shutil
import threading
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

from _paths import PRODUCT_TEMPLATES
from neonrp import players

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def test_avatar_store(tmp_path):
    with patch.object(players, "PLAYERS_HOME", tmp_path / "players"):
        assert players.current_avatar() is None
        a = players.save_avatar_fields({"name": "阿九", "summary": "爱看云", "appearance": "短发", "junk": "x"})
        assert players.current_avatar() == a.stem and "junk" not in json.loads(a.read_text(encoding="utf-8"))
        b = players.save_avatar_fields({"name": "Mio"})
        assert players.current_avatar() == b.stem
        assert players.set_current_avatar(a.stem) and not players.set_current_avatar("../etc")
        players.save_avatar_fields({"name": "阿九", "summary": "爱看海"}, a.stem)
        assert json.loads(a.read_text(encoding="utf-8"))["appearance"] == "短发", "editing keeps what the form left out"
        assert players.save_portrait(a.stem, b"not an image") is None and players.save_portrait("nobody", PNG) is None
        assert players.save_portrait(a.stem, PNG).name == f"{a.stem}.portrait.png"
        rows = {r["file"]: r for r in players.list_avatars()}
        assert rows[a.stem]["current"] and rows[a.stem]["portrait_url"] and not rows[b.stem]["current"] and rows[b.stem]["portrait_url"] is None


def test_http_avatar_bind_and_saves(tmp_path, monkeypatch):
    from neonrp.commands.web import make_server

    store = tmp_path / "store"
    for t in ("kagura-island", "neon-rebirth"):
        shutil.copytree(PRODUCT_TEMPLATES / f"{t}.template", store / f"{t}.template")
    monkeypatch.setenv("NEONRP_TEMPLATE_PATH", str(store))
    monkeypatch.setenv("NEONRP_DISABLE_CLAUDE_CODE", "1")
    with (
        patch.object(players, "PLAYERS_HOME", tmp_path / "players"),
        patch("neonrp.worlds.WORLDS_HOME", tmp_path / "worlds"),
        patch("neonrp.worlds.PLAYS_HOME", tmp_path / "plays"),
        patch("neonrp.worlds.STUDIO_HOME", tmp_path / "studio"),
        patch("neonrp.commands.web.WebRuntime.gateway_start", lambda self: {"sid": "local", "root": self.root.name}),
    ):
        server = make_server(None, "world-agent", "127.0.0.1", 0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{server.server_address[1]}"

        def call(path, body=None, raw=None):
            data = raw if raw is not None else (None if body is None else json.dumps(body).encode())
            req = urllib.request.Request(base + path, data=data, method="GET" if data is None else "POST",
                                         headers={"Content-Type": "application/octet-stream" if raw is not None else "application/json"})
            with urllib.request.urlopen(req, timeout=240) as r:
                out = r.read()
                return out if path.startswith("/api/v1/local/avatar/portrait") and data is None else json.loads(out)
        try:
            assert call("/api/v1/local/avatar") == {"current": None, "avatar": None, "avatars": []}
            with urllib.request.urlopen(urllib.request.Request(base + "/api/v1/local/avatar", data=b"{}", method="POST"), timeout=30) as r:
                raise AssertionError(r.status)
        except urllib.error.HTTPError as e:
            assert e.code == 400
        try:
            from urllib.parse import quote

            f = call("/api/v1/local/avatar", {"name": "阿九", "summary": "爱看云的旅人", "appearance": "短发,背着相机"})["file"]
            qf = quote(f)
            assert call(f"/api/v1/local/avatar/portrait?file={qf}", raw=PNG)["ok"]
            assert call(cur_url := call("/api/v1/local/avatar")["avatar"]["portrait_url"]) == PNG and qf in cur_url
            cur = call("/api/v1/local/avatar")
            assert cur["current"] == f and cur["avatar"]["name"] == "阿九" and cur["avatar"]["portrait_url"]
            assert any(a["current"] for a in call("/api/v1/local/souls")["avatars"])
            call("/api/v1/play/session", {"slug": "tpl--kagura-island", "output_lang": "zh", "avatar": "current"})
            run = next((tmp_path / "plays").iterdir())
            prof = json.loads((run / "game" / "player" / "profile.json").read_text(encoding="utf-8"))
            assert prof["name"] == "阿九" and prof["summary"] == "爱看云的旅人" and "name_i18n" not in prof and prof["pid"] == "player"
            assert (run / "game" / "player" / "assets" / "portrait.png").read_bytes() == PNG
            assert not (run / "game" / "player" / "assets" / "portrait.webp").exists()
            row = next(s for s in call("/api/v1/play/saves")["saves"] if s["session_id"] == run.name)
            assert row["template"] == "kagura-island" and row["turns"] == 0
            # 继续世界:/api/v1/local/plays 只列走过回合的局(all=1 全列),带世界标题 · 封面
            assert call("/api/v1/local/plays?lang=zh")["plays"] == []
            assert [p["session_id"] for p in call("/api/v1/local/plays?all=1")["plays"]] == [run.name]
            rs = run / "game" / "meta" / "run_state.json"
            rs.write_text(json.dumps({**json.loads(rs.read_text(encoding="utf-8")), "turn_count": 3}), encoding="utf-8")
            (p,) = call("/api/v1/local/plays?lang=zh")["plays"]
            card = json.loads((store / "kagura-island.template" / "template.json").read_text(encoding="utf-8"))["card"]
            assert p["template"] == "kagura-island" and p["turns"] == 3 and p["world"] == card["title"] and p["in_memory"]
            assert p["cover_url"] == "/api/v1/local/templates/kagura-island/assets/file?slot=card:cover"
            # PUT = POST;?tpl= 给捏人台预填(模板把文字字段写到 profile.json 的 name / summary / appearance …)
            put = urllib.request.Request(base + "/api/v1/local/avatar", data=json.dumps({"file": f, "appearance": "长发"}).encode(),
                                         method="PUT", headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(put, timeout=30) as r:
                assert json.loads(r.read())["file"] == f
            got = call("/api/v1/local/avatar?tpl=neon-rebirth")
            assert got["avatar"]["data"]["appearance"] == "长发" and [a["file"] for a in got["avatars"]] == [f]
            b = json.loads((store / "neon-rebirth.template" / "template.json").read_text(encoding="utf-8"))["player"]["builder"]
            want = {x["id"]: k for x in b["fields"] for k in ("name", "summary", "appearance")
                    if x.get("to") == f"player/profile.json:{k}" and x.get("kind", "text") == "text"}
            vals = {"name": "阿九", "summary": "爱看云的旅人", "appearance": "长发"}
            assert want and got["prefill"]["fields"] == {i: vals[k] for i, k in want.items()}
            # 成就带显示名(core/achievements.describe;四语)
            from neonrp.core import player_data

            player_data.unlock_achievement("first_ending", "kagura-island", once=True)
            player_data.unlock_achievement("nope", "kagura-island")
            rows = {a["id"]: a for a in call("/api/v1/local/player-data?lang=en")["achievements"]}
            assert rows["first_ending"]["title"] and rows["first_ending"]["title"] != "first_ending" and rows["first_ending"]["points"]
            assert "title" not in rows["nope"], "unknown ids stay as they are"
            assert call("/api/v1/local/player-data?lang=zh")["achievements"][0]["title"] != rows["first_ending"]["title"]
        finally:
            server.shutdown()


def test_template_meta_says_who_the_player_is(tmp_path, monkeypatch):
    """模板 meta 的 pc:{fixed, builder}(hub2 10-15:「用我的分身开局」开关在 builder 或非 fixed 时出现)。"""
    from neonrp import template as TP

    def pc(tid):
        return TP.load(PRODUCT_TEMPLATES / f"{tid}.template").meta()["pc"]

    assert pc("kagura-island") == {"fixed": True, "builder": False}, "卡卡尔: the world's own protagonist"
    assert pc("spice-witch") == {"fixed": True, "builder": False}
    assert pc("neon-rebirth") == {"fixed": False, "builder": True}, "the builder screen makes the player"
    assert pc("wuwu") == {"fixed": False, "builder": False}, "playthrough players[0] is the scaffold's Player"
    assert pc("stoneford-town") == {"fixed": False, "builder": False}
    t = tmp_path / "kagura-island.template"
    shutil.copytree(PRODUCT_TEMPLATES / "kagura-island.template", t)
    tj = json.loads((t / "template.json").read_text(encoding="utf-8"))
    (t / "template.json").write_text(json.dumps({**tj, "player": {**(tj.get("player") or {}), "fixed": False}}, ensure_ascii=False), encoding="utf-8")
    assert TP.load(t).meta()["pc"] == {"fixed": False, "builder": False}, "the template may say it outright"
    from neonrp.commands.web import make_server

    monkeypatch.setenv("NEONRP_TEMPLATE_PATH", str(tmp_path))
    monkeypatch.setenv("NEONRP_DISABLE_CLAUDE_CODE", "1")
    server = make_server(None, "world-agent", "127.0.0.1", 0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{server.server_address[1]}/api/v1/local/templates", timeout=120) as r:
            rows = json.loads(r.read())
    finally:
        server.shutdown()
    rows = rows.get("templates", rows) if isinstance(rows, dict) else rows
    row = next(x for x in rows if (x.get("id") or (x.get("meta") or {}).get("id")) == "kagura-island")
    assert (row.get("pc") or (row.get("meta") or {}).get("pc")) == {"fixed": False, "builder": False}
