"""导出 / 导入(「我们在引擎里面修改好的文档可以有地方可以 extract,或者 import」)。
一种包:zip + pack.json(kind = template | soul)。模板包带上它 link 的角色库角色;导入时角色进角色库,行照旧 link。"""

from __future__ import annotations

import io
import json
import shutil
import zipfile

import pytest
from click.testing import CliRunner

from _paths import PRODUCT_TEMPLATES

SOUL_SRC = PRODUCT_TEMPLATES / "pct-house.template" / "world" / "souls" / "chara-si-chara0001"


@pytest.fixture
def env(tmp_path, monkeypatch):
    store = tmp_path / "mine"
    store.mkdir()
    shutil.copytree(PRODUCT_TEMPLATES / "pct-house.template", store / "pct-mine.template")
    p = store / "pct-mine.template" / "template.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    d["id"] = "pct-mine"
    d.pop("zone", None)   # my copy, not the default-zone original (10-16: only free-zone works export)
    p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setenv("NEONRP_TEMPLATE_PATH", str(store))
    monkeypatch.setenv("NEONRP_TEMPLATE_WRITE_DIR", str(store))
    lib = tmp_path / "souls"
    shutil.copytree(SOUL_SRC, lib / "mira")
    sj = json.loads((lib / "mira" / "soul.json").read_text(encoding="utf-8"))
    sj["sid"] = "mira"
    (lib / "mira" / "soul.json").write_text(json.dumps(sj, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr("neonrp.core.souls.SOUL_HOME", lib)
    from neonrp.template import author

    assert author.apply_ops(store / "pct-mine.template", [{"op": "set_cast", "souls": [{"sid": "chara"}, {"lib": "mira", "role": "companion"}]}])["ok"]
    return store, lib


def _names(data: bytes) -> list[str]:
    return zipfile.ZipFile(io.BytesIO(data)).namelist()


def test_template_round_trip_carries_linked_souls(env, tmp_path):
    from neonrp import template as TP
    from neonrp.template import package as P

    store, lib = env
    data = P.export_template("pct-mine")
    names = _names(data)
    assert "pack.json" in names and "pct-mine.template/template.json" in names
    assert any(n.startswith("souls-lib/mira/") for n in names)
    meta = json.loads(zipfile.ZipFile(io.BytesIO(data)).read("pack.json"))
    assert meta["kind"] == "template" and meta["links"] == ["mira"]

    r = P.import_package(data)                                   # 同一台机器再导一次:id 被占 → -2;角色一模一样 → 复用
    assert r["id"] == "pct-mine-2" and r["renamed_from"] == "pct-mine"
    assert r["souls"] == [{"name": "mira", "how": "same"}]
    t = TP.load(store / "pct-mine-2.template")
    assert t.id == "pct-mine-2"
    assert any(s.get("lib") == "mira" for s in t.souls)
    assert not [p for p in TP.lint(t).get("problems", []) if p.get("code") == "ref.soul"]


def test_import_on_a_fresh_machine_installs_the_souls(env, tmp_path, monkeypatch):
    from neonrp import template as TP
    from neonrp.template import package as P

    data = P.export_template("pct-mine")
    store2, lib2 = tmp_path / "other-store", tmp_path / "other-souls"
    monkeypatch.setenv("NEONRP_TEMPLATE_PATH", str(store2))
    monkeypatch.setenv("NEONRP_TEMPLATE_WRITE_DIR", str(store2))
    monkeypatch.setattr("neonrp.core.souls.SOUL_HOME", lib2)
    r = P.import_package(data)
    assert r["id"] == "pct-mine" and r["souls"] == [{"name": "mira", "how": "new"}]
    assert (lib2 / "mira" / "soul.json").is_file()
    TP.build(TP.load(store2 / "pct-mine.template"), tmp_path / "run")   # 开得了局


def test_a_different_soul_with_the_same_name_is_renamed_and_repointed(env, tmp_path):
    from neonrp import template as TP
    from neonrp.template import package as P

    store, lib = env
    data = P.export_template("pct-mine")
    (lib / "mira" / "soul.md").write_text("另一个 mira\n", encoding="utf-8")    # 本机的 mira 已经不是包里那个
    r = P.import_package(data, new_id="pct-copy")
    assert r["id"] == "pct-copy" and r["souls"] == [{"name": "mira-2", "how": "renamed"}]
    t = TP.load(store / "pct-copy.template")
    assert any(s.get("lib") == "mira-2" for s in t.souls)
    assert (lib / "mira" / "soul.md").read_text(encoding="utf-8") == "另一个 mira\n"   # 本机的不动


def test_soul_round_trip(env, tmp_path, monkeypatch):
    from neonrp.template import package as P

    data = P.export_soul("mira")
    lib2 = tmp_path / "lib2"
    monkeypatch.setattr("neonrp.core.souls.SOUL_HOME", lib2)
    r = P.import_package(data)
    assert r["kind"] == "soul" and r["id"] == "mira" and (lib2 / "mira" / "soul.json").is_file()


def _zip(files: dict[str, bytes], meta: dict | None = None) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        if meta is not False:
            z.writestr("pack.json", json.dumps(meta or {"schema": "worldlines.package/1", "kind": "template", "id": "evil"}))
        for k, v in files.items():
            z.writestr(k, v)
    return buf.getvalue()


@pytest.mark.parametrize("data,why", [
    (b"not a zip", "not a zip"),
    (_zip({"x.txt": b"1"}, meta=False), "no pack.json"),
    (_zip({}, meta={"schema": "x", "kind": "template"}), "unknown package"),
    (_zip({"../escape.json": b"{}"}), "unsafe path"),
    (_zip({"evil.template/hook.py": b"import os"}), "code files"),
    (_zip({"evil.template/x.json": b"{}"}), "without evil.template/template.json"),
])
def test_bad_packages_are_refused_and_nothing_lands(env, data, why):
    from neonrp.template import TemplateError
    from neonrp.template import package as P

    store, _ = env
    before = sorted(p.name for p in store.iterdir())
    with pytest.raises(TemplateError, match=why):
        P.import_package(data)
    assert sorted(p.name for p in store.iterdir()) == before


def test_cli_export_then_import(env, tmp_path):
    from neonrp.commands.template_cmd import template_group

    out = tmp_path / "p.zip"
    r = CliRunner().invoke(template_group, ["export", "pct-mine", "-o", str(out)])
    assert r.exit_code == 0, r.output
    r = CliRunner().invoke(template_group, ["import", str(out), "--id", "pct-cli"])
    assert r.exit_code == 0, r.output
    assert "imported template pct-cli" in r.output and "soul mira: same" in r.output


def test_http_export_and_import(env, tmp_path):
    import threading
    import urllib.request
    from unittest.mock import patch

    from neonrp.commands.web import make_server

    with (
        patch("neonrp.worlds.WORLDS_HOME", tmp_path / "worlds"),
        patch("neonrp.worlds.PLAYS_HOME", tmp_path / "plays"),
    ):
        server = make_server(None, "world-agent", "127.0.0.1", 0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            with urllib.request.urlopen(base + "/api/v1/local/templates/pct-mine/export", timeout=60) as r:
                assert r.headers["Content-Type"] == "application/zip"
                data = r.read()
            with urllib.request.urlopen(base + "/api/v1/local/souls/mira/export", timeout=60) as r:
                assert "pack.json" in _names(r.read())
            req = urllib.request.Request(base + "/api/v1/local/import/package?id=pct-web", data=data, method="POST",
                                         headers={"Content-Type": "application/zip"})
            with urllib.request.urlopen(req, timeout=60) as r:
                got = json.loads(r.read())
            assert got["ok"] and got["id"] == "pct-web" and got["kind"] == "template"
        finally:
            server.shutdown()


# ── 10-16:只有自由区的作品能导出;默认区(官方世界都在这)只能玩 ──────────────────

def test_default_zone_works_are_not_exported(env, tmp_path):
    from neonrp.commands.template_cmd import template_group
    from neonrp.template import author
    from neonrp.template import package as P

    with pytest.raises(P.ExportRefused):
        P.export_template("pct-house")
    assert "pack.json" in _names(P.export_template("pct-house", any_zone=True)), "the engine's own use (publishing) still packs it"
    r = CliRunner().invoke(template_group, ["export", "pct-house", "-o", str(tmp_path / "x.zip")])
    assert r.exit_code != 0 and not (tmp_path / "x.zip").exists()
    assert any(w in r.output for w in ("默认区", "Default Zone", "デフォルトエリア", "기본 구역")), r.output
    t = author.fork(PRODUCT_TEMPLATES / "pct-house.template", "pct-fork")
    assert t.zone is None, "a copy is the author's own work"
    assert "pack.json" in _names(P.export_template("pct-fork"))


def test_http_export_refuses_the_default_zone_in_the_players_language(env, tmp_path):
    import threading
    import urllib.error
    import urllib.request
    from unittest.mock import patch

    from neonrp.commands.web import make_server

    with (
        patch("neonrp.worlds.WORLDS_HOME", tmp_path / "worlds"),
        patch("neonrp.worlds.PLAYS_HOME", tmp_path / "plays"),
    ):
        server = make_server(None, "world-agent", "127.0.0.1", 0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            for lang, word in (("zh", "默认区"), ("en", "Default Zone"), ("ja", "デフォルトエリア"), ("ko", "기본 구역")):
                with pytest.raises(urllib.error.HTTPError) as e:
                    urllib.request.urlopen(f"{base}/api/v1/local/templates/pct-house/export?lang={lang}", timeout=60)
                body = json.loads(e.value.read())
                assert e.value.code == 403 and body["error"] == "default_zone" and word in body["message"]
        finally:
            server.shutdown()
