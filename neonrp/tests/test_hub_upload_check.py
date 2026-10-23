"""Pre-upload validation + upload form (「上传的时候记得做
检验 —— hub 的文件、图片;远端两个世界都没图片而且重复」)。"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from neonrp.core import worldhub as H

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


def _world(root: Path, *, cover: bool = True, start: bool = True, world_map: bool = True, premise: str = "雾里有船来") -> Path:
    (root / "game" / "meta").mkdir(parents=True, exist_ok=True)
    (root / "game" / "world").mkdir(parents=True, exist_ok=True)
    if start:
        (root / "game" / "meta" / "game-start.json").write_text(
            json.dumps({"name": "猫岛", "world_info": {"world_name": "猫岛", "premise": premise, "genre": "奇幻", "tone": "温暖"}}),
            encoding="utf-8",
        )
    if world_map:
        (root / "game" / "world" / "world_map.json").write_text("{}", encoding="utf-8")
    if cover:
        (root / "assets").mkdir(exist_ok=True)
        (root / "assets" / "cover.png").write_bytes(PNG)
    return root


def test_good_world_passes_with_prefilled_form(tmp_path):
    c = H.validate_for_upload(_world(tmp_path / "cat-isle"))
    assert c.ok and not c.warnings
    assert c.title == "猫岛" and c.description == "雾里有船来"
    assert c.cover == tmp_path / "cat-isle" / "assets" / "cover.png"


def test_world_without_cover_is_blocked(tmp_path):
    c = H.validate_for_upload(_world(tmp_path / "w", cover=False))
    assert "check.no_cover" in c.errors and not c.ok


def test_world_without_start_card_is_blocked(tmp_path):
    c = H.validate_for_upload(_world(tmp_path / "w", start=False))
    assert "check.no_start_card" in c.errors


def test_missing_map_only_warns(tmp_path):
    c = H.validate_for_upload(_world(tmp_path / "w", world_map=False))
    assert c.ok and "check.no_map" in c.warnings


def test_run_directory_is_flagged_and_title_drops_the_timestamp(tmp_path):
    root = _world(tmp_path / "kusofuka-yabu-20260902-102819", start=False, cover=True)
    c = H.validate_for_upload(root)
    assert "check.is_run_dir" in c.warnings
    assert c.title == "kusofuka-yabu"


def test_description_falls_back_to_genre_and_tone(tmp_path):
    c = H.validate_for_upload(_world(tmp_path / "w", premise=""))
    assert c.description == "奇幻 · 温暖"


def test_oversized_world_is_blocked(tmp_path, monkeypatch):
    monkeypatch.setattr(H, "UPLOAD_SIZE_LIMIT", 10)
    c = H.validate_for_upload(_world(tmp_path / "w"))
    assert "check.too_big" in c.errors


def test_missing_folder(tmp_path):
    c = H.validate_for_upload(tmp_path / "nope")
    assert c.errors == ["check.missing_dir"]


def _soul(root: Path, *, portrait: bool = True) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "soul.json").write_text(json.dumps({"sid": "rowan", "name": "Rowan", "name_local": "罗文", "intro_i18n": {"zh": "沉默的铁匠", "en": "a quiet smith"}}), encoding="utf-8")
    if portrait:
        (root / "assets").mkdir(exist_ok=True)
        (root / "assets" / "portrait.png").write_bytes(PNG)
    return root


def test_good_soul(tmp_path):
    c = H.validate_for_upload(_soul(tmp_path / "rowan"), kind="souls")
    assert c.ok and c.title == "罗文" and c.description == "沉默的铁匠"
    assert c.cover and c.cover.name == "portrait.png"


def test_soul_without_portrait_is_blocked(tmp_path):
    c = H.validate_for_upload(_soul(tmp_path / "rowan", portrait=False), kind="souls")
    assert "check.no_portrait" in c.errors


def test_soul_without_json_is_blocked(tmp_path):
    d = tmp_path / "x"
    d.mkdir()
    c = H.validate_for_upload(d, kind="souls")
    assert "check.no_soul_json" in c.errors


# ── owner API wrappers ────────────────────────────────────────────────


class _Resp:
    def __init__(self, body: bytes = b"{}") -> None:
        self._b = body

    def read(self) -> bytes:
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _capture(monkeypatch):
    calls = []

    def fake_urlopen(req, timeout=0):
        calls.append((req.get_method(), req.full_url, req.data, dict(req.header_items())))
        return _Resp(b'{"ok": true}')

    monkeypatch.setattr(H.urllib.request, "urlopen", fake_urlopen)
    return calls


def test_update_meta_posts_json_to_the_owner_route(monkeypatch):
    calls = _capture(monkeypatch)
    H.update_meta_via_api("worlds", "cat-isle", api_token="t", name="猫岛", description="雾里有船来")
    method, url, body, headers = calls[0]
    assert method == "POST" and url.endswith("/api/v1/me/published/world/cat-isle/meta")
    assert json.loads(body) == {"name": "猫岛", "description": "雾里有船来"}
    assert headers.get("Authorization") == "Bearer t"


def test_visibility_and_delete_routes(monkeypatch):
    calls = _capture(monkeypatch)
    H.set_visibility_via_api("souls", "rowan", unlisted=True, api_token="t")
    H.delete_published_via_api("worlds", "cat-isle", api_token="t")
    assert calls[0][0] == "POST" and calls[0][1].endswith("/soul/rowan/visibility") and json.loads(calls[0][2]) == {"unlisted": True}
    assert calls[1][0] == "DELETE" and calls[1][1].endswith("/world/cat-isle") and calls[1][2] is None


def test_owner_call_without_token_is_refused():
    with pytest.raises(H.WorldHubError):
        H.delete_published_via_api("worlds", "x", api_token="")


# ── TUI: list ordering + upload flow ──────────────────────────────────


def test_upload_list_puts_sources_before_saves(tmp_path):
    from neonrp.tui.app import HubUploadScreen

    scr = HubUploadScreen(kind="worlds", locale="zh")
    with patch("neonrp.worlds.list_owned_worlds", return_value=[{"id": "cat-isle", "name": "猫岛", "template": str(tmp_path / "cat-isle")}]), patch(
        "neonrp.worlds.list_saved_games", return_value=[{"path": tmp_path / "cat-isle-20260901-000000", "display_name": "猫岛", "dir_name": "cat-isle-20260901-000000"}]
    ):
        options, items = scr._build_item_options()
    assert [o[0] for o in options] == ["🌍 猫岛", "💾 猫岛  (存档)"]
    assert items[0]["is_source"] and not items[1]["is_source"]


def test_upload_validates_then_opens_the_form(tmp_path):
    from neonrp.tui.app import HubUploadFormScreen, HubUploadScreen

    scr = HubUploadScreen(kind="worlds", locale="zh")
    scr._token = "t"
    scr._items = [{"path": _world(tmp_path / "w", cover=False)}]
    sel = MagicMock()
    sel.selected = [0]
    scr.query_one = MagicMock(return_value=sel)
    app = MagicMock()
    with patch.object(type(scr), "app", new_callable=lambda: property(lambda self: app)):
        scr._do_upload()
    app.push_screen.assert_called_once()
    form = app.push_screen.call_args.args[0]
    assert isinstance(form, HubUploadFormScreen)
    assert "check.no_cover" in form._check.errors, "错误进了表单,而不是直接上传"


def test_form_result_drives_upload_meta_and_cover(tmp_path):
    from neonrp.tui.app import HubUploadScreen

    scr = HubUploadScreen(kind="worlds", locale="zh")
    scr._token = "t"
    scr._set_feedback = MagicMock()
    new_cover = tmp_path / "new.png"
    new_cover.write_bytes(PNG)
    with patch("neonrp.core.worldhub.upload_via_api", return_value={"slug": "cat-isle"}) as up, patch(
        "neonrp.core.worldhub.update_meta_via_api"
    ) as meta, patch("neonrp.core.worldhub.replace_cover_via_api") as cov:
        scr._on_form_done({"source": tmp_path / "w", "title": "猫岛", "description": "雾里有船来", "cover": new_cover, "cover_changed": True})
    up.assert_called_once_with(tmp_path / "w", kind="worlds", name="猫岛", api_token="t", unlisted=True)
    meta.assert_called_once_with("worlds", "cat-isle", api_token="t", description="雾里有船来", name_i18n=None, description_i18n=None)
    cov.assert_called_once_with("worlds", "cat-isle", new_cover, api_token="t")
    assert "cat-isle" in scr._set_feedback.call_args.args[0]


def test_form_cancel_uploads_nothing():
    from neonrp.tui.app import HubUploadScreen

    scr = HubUploadScreen(kind="worlds", locale="zh")
    with patch("neonrp.core.worldhub.upload_via_api") as up:
        scr._on_form_done(None)
    up.assert_not_called()


def test_form_screen_blocks_upload_on_errors_and_returns_edits(tmp_path):
    import asyncio

    from textual.app import App

    from neonrp.tui.app import HubUploadFormScreen

    good = H.validate_for_upload(_world(tmp_path / "w"))
    bad = H.validate_for_upload(_world(tmp_path / "b", cover=False))

    class T(App):
        result = "unset"

        def __init__(self, check):
            super().__init__()
            self._c = check

        def on_mount(self):
            self.push_screen(HubUploadFormScreen(self._c, locale="zh"), lambda v: setattr(self, "result", v))

    async def run(check, edit_title: bool):
        app = T(check)
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            await pilot.pause()
            btn = app.screen.query_one("#hub-form-upload")
            disabled = btn.disabled
            if edit_title:
                app.screen.query_one("#hub-form-name-zh").value = "猫岛 · 重制"
            await pilot.click("#hub-form-upload")
            await pilot.pause()
            return disabled, app.result

    disabled, result = asyncio.run(run(bad, False))
    assert disabled and result == "unset", "有错误时上传键不可用"
    disabled, result = asyncio.run(run(good, True))
    assert not disabled and result["title"] == "猫岛 · 重制" and result["cover_changed"] is False


def test_world_souls_without_portrait_are_named_in_a_warning(tmp_path):
    root = _world(tmp_path / "w")
    _soul(root / "souls" / "rowan-si-1", portrait=True)
    _soul(root / "souls" / "ghost-si-2", portrait=False)
    c = H.validate_for_upload(root)
    assert c.ok
    assert "check.souls_no_portrait" in c.warnings
    assert c.souls_without_portrait == ["罗文"]
