"""The workbench's 「捏角色」 switch (10-25): any world can open with the builder. On = the sheet the template had (set
aside when it was turned off) or a generic one; off = set aside; the field editor writes labels / random names / required
in the workbench's language. Only a copy in the write store is written; a built-in is read-only (template/author.py)."""
from __future__ import annotations

import json
import shutil
import threading
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

import pytest

from neonrp import template as TP
from neonrp.template import author
from neonrp.template import builder as B
from neonrp.template import i18n as I
from _paths import PRODUCT

PCT = PRODUCT / "templates" / "pct-house.template"
NEON = PRODUCT / "templates" / "neon-rebirth.template"
PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 32
WORLD_WORDS = ("读者", "转生", "穹顶", "九条", "Reader", "Reborn")


def _j(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


@pytest.fixture
def store(tmp_path: Path, monkeypatch):
    w = tmp_path / "store"
    w.mkdir()
    monkeypatch.setenv("NEONRP_TEMPLATE_WRITE_DIR", str(w))
    monkeypatch.setenv("NEONRP_TEMPLATE_PATH", str(w))
    return w


def _copy(src: Path, store: Path, tid: str) -> TP.Template:
    td = store / f"{tid}.template"
    shutil.copytree(src, td, symlinks=True)
    d = _j(td / "template.json")
    d["id"] = tid
    (td / "template.json").write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    return TP.load(td)


def test_generic_sheet_knows_no_world(store):
    t = _copy(PCT, store, "pc")
    b = B.default_decl(t)
    assert [f["id"] for f in b["fields"]] == ["name", "gender", "look"], "no pictures in assets/player/ → no portrait field"
    assert set(b["title"]) == {"zh", "en", "ja", "ko"} and all(set(f["label"]) == {"zh", "en", "ja", "ko"} for f in b["fields"])
    assert not any(w in json.dumps(b, ensure_ascii=False) for w in WORLD_WORDS)
    (t.dir / "assets" / "player").mkdir(parents=True, exist_ok=True)
    (t.dir / "assets" / "player" / "a-f.png").write_bytes(PNG)
    face = B.default_decl(t)["fields"][-1]
    assert face["kind"] == "portrait" and face["options"] == [{"id": "a-f", "src": "assets/player/a-f.png"}]


def test_on_off_on_round_trip_and_the_run(store, tmp_path, monkeypatch):
    import neonrp.worlds as W

    made: list[Path] = []

    def fake_dir(prefix: str) -> Path:
        made.append(tmp_path / "plays" / f"{prefix}-{len(made)}")
        made[-1].mkdir(parents=True)
        return made[-1]

    monkeypatch.setattr(W, "create_run_dir", fake_dir)
    monkeypatch.setattr(W, "seed_run_model", lambda *a, **k: None)
    t = _copy(PCT, store, "pc")
    assert not B.declared(t) and t.meta()["pc"]["builder"] is False
    t = author.set_builder(t, True)
    assert B.declared(t) and t.meta()["pc"]["builder"] is True and B.problems(t) == []
    errs, _ = B.check(t, {"fields": {}})
    assert errs == ["name: required"]
    run = TP.new_run(t, player={"fields": {"name": "阿澄", "gender": "female", "look": "灰色风衣"}})
    prof = _j(run / "game" / "player" / "profile.json")
    assert prof["name"] == "阿澄" and prof["gender"] == "女" and prof["pronouns"] == "她" and prof["appearance"] == "灰色风衣"
    t = author.set_builder(t, False)
    d = _j(t.dir / "template.json")
    assert "builder" not in d["player"] and d["player"][B.STASH]["fields"][0]["id"] == "name"
    assert not B.declared(t) and B.editor(t)["kept"] is True
    plain = TP.new_run(t)
    assert not (plain / "game" / "player" / "card.json").exists(), "off = the run opens as before"


def test_neon_rebirth_sheet_is_never_replaced(store):
    t = _copy(NEON, store, "nr")
    before = json.dumps(B.raw(t), sort_keys=True)
    en_before = (_j(t.dir / "i18n" / "en" / "template.json")["player"]["builder"])
    assert json.dumps(B.raw(author.set_builder(t, True)), sort_keys=True) == before, "on over a sheet = nothing changes"
    t = author.set_builder(t, False)
    en = _j(t.dir / "i18n" / "en" / "template.json")["player"]
    assert "builder" not in en and en[B.STASH] == en_before, "the layer's sheet is set aside too"
    with I.localized(t, "en") as lt:
        assert not B.declared(lt), "a run in English opens without a builder too"
    t = author.set_builder(t, True)
    assert json.dumps(B.raw(t), sort_keys=True) == before, "back on = the author's sheet, not the generic one"
    assert _j(t.dir / "i18n" / "en" / "template.json")["player"]["builder"] == en_before


def test_field_editor_writes_in_the_language(store):
    t = author.set_builder(_copy(PCT, store, "pc"), True)
    t = author.edit_builder(t, [{"id": "name", "label": "代号", "random": ["甲", "乙", ""], "required": False}], lang="zh")
    f = B.raw(t)["fields"][0]
    assert f["label"]["zh"] == "代号" and f["label"]["en"] == "Name" and f["random"] == ["甲", "乙"] and f["required"] is False
    assert B.editor(t, "zh")["fields"][0] == {"id": "name", "kind": "text", "label": "代号", "required": False, "random": ["甲", "乙"]}
    with pytest.raises(TP.TemplateError):
        author.edit_builder(t, [{"id": "gender", "random": ["x"]}])
    with pytest.raises(TP.TemplateError):
        author.edit_builder(t, [{"id": "nope", "label": "x"}])
    # a language with its own layer: the layer's text is what that language reads, so the edit lands there
    n = _copy(NEON, store, "nr")
    n = author.edit_builder(n, [{"id": "name", "label": "Alias", "random": ["Kai"]}], lang="en")
    assert B.raw(n)["fields"][0]["label"] == {"zh": "名字"}, "the template's own text is untouched"
    assert _j(n.dir / "i18n" / "en" / "template.json")["player"]["builder"]["fields"][0]["label"] == "Alias"
    assert B.editor(n, "en")["fields"][0]["label"] == "Alias" and B.editor(n, "en")["fields"][0]["random"] == ["Kai"]


def test_portrait_upload_grows_the_sheet_and_keeps_the_layers_in_shape(store):
    t = author.set_builder(_copy(PCT, store, "pc"), True)
    t = author.add_portrait(t, PNG, ext=".png")
    face = B.raw(t)["fields"][-1]
    assert face["kind"] == "portrait" and face["options"] == [{"id": "face-1", "src": "assets/player/face-1.png"}]
    assert B.problems(t) == [] and B.option_image(t, face["id"], "face-1").read_bytes() == PNG
    with pytest.raises(TP.TemplateError):
        author.add_portrait(t, b"not an image")
    n = _copy(NEON, store, "nr")
    n = author.add_portrait(n, PNG, ext=".png")
    with I.localized(n, "en") as lt:
        assert not [p for p in B.problems(lt) if p[0] == "block"], "the English run still has every picture"
        faces = next(f for f in B.raw(lt)["fields"] if f["kind"] == "portrait")["options"]
        assert faces[-1]["id"] == "face-1" and faces[0]["label"] == "Female · default"


def test_builtin_is_read_only(store):
    with pytest.raises(TP.TemplateError):
        author.set_builder(TP.load(PCT), True)
    assert not B.declared(TP.load(PCT))


def test_http_switch(store, tmp_path, monkeypatch):
    from neonrp.commands.web import make_server

    _copy(PCT, store, "pc")
    monkeypatch.setenv("NEONRP_TEMPLATE_PATH", f"{store}:{PCT.parent}")
    monkeypatch.setenv("NEONRP_DISABLE_CLAUDE_CODE", "1")
    with (
        patch("neonrp.worlds.WORLDS_HOME", tmp_path / "worlds"),
        patch("neonrp.worlds.PLAYS_HOME", tmp_path / "plays"),
        patch("neonrp.worlds.STUDIO_HOME", tmp_path / "studio"),
        patch("neonrp.commands.web.WebRuntime.gateway_start", lambda self: {"sid": "local", "root": self.root.name}),
    ):
        server = make_server(None, "world-agent", "127.0.0.1", 0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{server.server_address[1]}"

        def call(path, body=None, raw=None):
            data = raw if raw is not None else None if body is None else json.dumps(body).encode()
            req = urllib.request.Request(base + path, data=data, method="GET" if data is None else "POST",
                                         headers={"Content-Type": "application/octet-stream" if raw is not None else "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=120) as r:
                    return r.status, json.loads(r.read())
            except urllib.error.HTTPError as e:
                return e.code, json.loads(e.read() or b"{}")

        try:
            st, v = call("/api/v1/local/templates/pc/builder/edit?lang=en")
            assert st == 200 and v["on"] is False and v["writable"] is True
            st, v = call("/api/v1/local/templates/pc/builder/edit", {"on": True, "lang": "en"})
            assert st == 200 and v["on"] and [f["label"] for f in v["fields"]] == ["Name", "Gender & pronouns", "Appearance"]
            st, v = call("/api/v1/local/templates/pc/builder/edit", {"fields": [{"id": "look", "required": True}], "lang": "en"})
            assert st == 200 and v["fields"][2]["required"] is True
            st, v = call("/api/v1/local/templates/pc/builder/portrait?ext=.png", raw=PNG)
            assert st == 200 and v["fields"][-1]["kind"] == "portrait" and v["fields"][-1]["options"] == 1
            st, v = call("/api/v1/local/templates/pc/builder")
            assert st == 200 and v["declared"] is True, "the builder screen sees it at once"
            st, v = call("/api/v1/local/templates/pc/builder/edit", {"on": False})
            assert st == 200 and v["on"] is False and v["kept"] is True
            assert call("/api/v1/local/templates/pc/builder")[1] == {"declared": False}
            st, v = call("/api/v1/local/templates/pct-house/builder/edit", {"on": True})
            assert st == 403 and v["ok"] is False, "a built-in is read-only: fork first"
            st, v = call("/api/v1/local/templates/pc/builder/edit", {"fields": [{"id": "name", "label": ""}]})
            assert st == 400
        finally:
            server.shutdown()


# ── our development engine edits the official worlds in place (10-25) ─────────


@pytest.fixture
def dev_repo(store, tmp_path: Path, monkeypatch):
    """A stand-in source checkout (``.git`` + ``worldlines/templates``) so the test never writes the real official worlds."""
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    tpls = repo / "worldlines" / "templates"
    shutil.copytree(PCT, tpls / "pct-house.template", symlinks=True)
    monkeypatch.setattr(author, "_REPO", repo)
    monkeypatch.setenv("NEONRP_TEMPLATE_PATH", f"{store}:{tpls}")
    monkeypatch.delenv(author.DEV_OFFICIAL_ENV, raising=False)
    return tpls


def test_official_world_is_read_only_without_the_dev_switch(dev_repo):
    t = TP.load(dev_repo / "pct-house.template")
    assert author.dev_official_root() is None and not author.writable(t)
    assert B.editor(t, "zh")["writable"] is False
    with pytest.raises(TP.TemplateError):
        author.set_builder(t, True)


def test_dev_switch_makes_the_source_official_world_writable(dev_repo, store, monkeypatch):
    monkeypatch.setenv(author.DEV_OFFICIAL_ENV, "1")
    src = dev_repo / "pct-house.template"
    t = TP.load(src)
    assert author.dev_official_root() == dev_repo.resolve() and author.writable(t) and B.editor(t, "zh")["writable"] is True
    t = author.set_builder(t, True)
    assert isinstance(_j(src / "template.json")["player"]["builder"], dict), "the change lands in the source file (git sees it)"
    author.set_builder(t, False)
    assert "builder" not in _j(src / "template.json")["player"] and B.STASH in _j(src / "template.json")["player"]
    assert author.write_root() == store.resolve(), "not a write store: new / forked templates still go to the store"
    assert author.delete("pct-house") is False, "an official world is never removable"


def test_dev_switch_needs_a_source_checkout(dev_repo, monkeypatch):
    monkeypatch.setenv(author.DEV_OFFICIAL_ENV, "1")
    shutil.rmtree(dev_repo.parents[1] / ".git")   # an installed wheel: no checkout around it
    assert author.dev_official_root() is None and not author.writable(TP.load(dev_repo / "pct-house.template"))
