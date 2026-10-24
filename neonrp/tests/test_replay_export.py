"""TODO #2:存档上传 + Hub 回放馆。引擎侧:run 目录 →
Replay Bundle(白名单),CLI export/upload,launcher 里的存档走回放线。"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from neonrp.core import replay_export as RE

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


def _run(root: Path, *, turns: int = 3, feed: bool = True) -> Path:
    (root / ".neonrp" / "orchestration").mkdir(parents=True)
    (root / ".neonrp" / "sessions").mkdir()
    (root / ".neonrp" / "manifest.json").write_text(json.dumps({"wid": "stoneford-elena", "name": "石津镇·艾琳娜"}, ensure_ascii=False), encoding="utf-8")
    (root / ".neonrp" / "config.json").write_text(json.dumps({"api_key": "sk-" + "x" * 32}), encoding="utf-8")
    (root / ".neonrp" / "sessions" / "s1.json").write_text("{}", encoding="utf-8")
    (root / ".neonrp" / "playthrough.json").write_text("{}", encoding="utf-8")
    (root / "game" / "meta").mkdir(parents=True)
    (root / "souls" / "elena").mkdir(parents=True)
    story = ["# 世界线实录", ""]
    for i in range(turns):
        story += [f"## T{i} · 石津镇·北门 · Day1 0{8 + i}:00", "", f"**艾琳娜**：第 {i} 回合。", ""]
    (root / "story.md").write_text("\n".join(story), encoding="utf-8")
    if feed:
        (root / "feed.jsonl").write_text("\n".join(json.dumps({"turn_seq": i, "location": "北门"}) for i in range(turns)) + "\n", encoding="utf-8")
    (root / ".neonrp" / "orchestration" / "main.jsonl").write_text(json.dumps({"turn_seq": 0, "souls": []}) + "\n", encoding="utf-8")
    (root / "cover.png").write_bytes(PNG)
    return root


def test_bundle_is_a_whitelist_copy(tmp_path):
    run = _run(tmp_path / "stoneford-elena-20260911-101010")
    out = tmp_path / "r.zip"
    meta = RE.build_replay_bundle(run, out, uploader="mika")
    with zipfile.ZipFile(out) as zf:
        names = sorted(zf.namelist())
    assert names == sorted(
        ["stoneford-elena-replay/replay.json", "stoneford-elena-replay/timeline.json", "stoneford-elena-replay/story.md", "stoneford-elena-replay/feed.jsonl", "stoneford-elena-replay/cover.png"]
    ), "sessions / config / playthrough / game / souls / 原始回合轨迹(orchestration.jsonl)一律不进包"
    assert meta["world"] == {"slug": "stoneford-elena", "name": "石津镇·艾琳娜"} and meta["turns"] == 3
    assert meta["kind"] == "replay" and meta["uploader"] == "mika"


def test_turns_fall_back_to_story_headings_and_slug_to_the_folder(tmp_path):
    run = _run(tmp_path / "some-world-20260911-101010-mig0badcafe", turns=2, feed=False)
    (run / ".neonrp" / "manifest.json").unlink()
    assert RE.count_turns(run) == 2
    assert RE.derive_world_slug(run) == "some-world"
    check = RE.validate_replay_source(run)
    assert check.ok and check.world_slug == "some-world" and "check.replay_no_feed" in check.warnings


def test_a_run_without_story_cannot_be_replayed(tmp_path):
    run = _run(tmp_path / "w-20260911-101010")
    (run / "story.md").write_text("# nothing\n", encoding="utf-8")
    check = RE.validate_replay_source(run)
    assert "check.replay_no_story" in check.errors
    import pytest

    with pytest.raises(RE.ReplayExportError):
        RE.build_replay_bundle(run, tmp_path / "x.zip")


def test_cli_export_and_upload(tmp_path, monkeypatch):
    from neonrp.commands.replay import replay_group

    run = _run(tmp_path / "stoneford-elena-20260911-101010")
    out = tmp_path / "out.zip"
    res = CliRunner().invoke(replay_group, ["export", str(run), "--out", str(out)])
    assert res.exit_code == 0, res.output
    assert out.is_file() and "3 turns" in res.output

    posted = {}

    def fake_post(zip_path, fields, *, token, base_url):
        with zipfile.ZipFile(zip_path) as zf:
            posted["names"] = sorted(zf.namelist())
        posted["fields"] = dict(fields)
        posted["token"] = token
        return {"slug": fields["slug"], "name": fields["name"], "status": "draft"}

    monkeypatch.setattr("neonrp.core.worldhub._post_bundle", fake_post)
    res = CliRunner().invoke(replay_group, ["upload", str(run), "--token", "tok"])
    assert res.exit_code == 0, res.output
    assert posted["fields"]["kind"] == "replay" and posted["fields"]["unlisted"] == "true"
    assert posted["fields"]["slug"].startswith("stoneford-elena-replay-") and posted["token"] == "tok"
    assert "stoneford-elena-replay/story.md" in posted["names"] and not any("config" in n for n in posted["names"])
    assert "draft" in res.output


def test_launcher_saved_run_goes_up_as_a_replay(tmp_path):
    from neonrp.tui.app import HubUploadFormScreen, HubUploadScreen

    run = _run(tmp_path / "stoneford-elena-20260911-101010")
    scr = HubUploadScreen(kind="worlds", locale="zh")
    scr._token = "t"
    scr._items = [{"path": run, "is_source": False, "display_name": "石津镇·艾琳娜"}]
    sel = MagicMock()
    sel.selected = [0]
    scr.query_one = MagicMock(return_value=sel)
    app = MagicMock()
    with patch.object(type(scr), "app", new_callable=lambda: property(lambda self: app)):
        scr._do_upload()
    form = app.push_screen.call_args.args[0]
    assert isinstance(form, HubUploadFormScreen) and form._check.kind == "replays"
    assert form._check.ok and "回放" in form._check.title and form._check.cover == run / "cover.png"

    scr._set_feedback = MagicMock()
    with patch("neonrp.core.worldhub.upload_replay_via_api", return_value={"slug": "stoneford-elena-replay-1", "turns": 3}) as up, patch(
        "neonrp.core.worldhub.upload_via_api"
    ) as world_up:
        scr._on_form_done({"source": run, "kind": "replays", "title": "石津镇 · 回放", "description": "", "title_i18n": {}, "description_i18n": {}, "cover": None, "cover_changed": False})
    up.assert_called_once()
    world_up.assert_not_called()
    assert "stoneford-elena-replay-1" in scr._set_feedback.call_args.args[0]


def test_world_upload_still_uses_the_world_path(tmp_path):
    """The refactor must not change what `upload_via_api` sends."""
    from neonrp.core import worldhub as H

    src = tmp_path / "w"
    (src / ".neonrp").mkdir(parents=True)
    (src / ".neonrp" / "manifest.json").write_text("{}", encoding="utf-8")
    seen = {}

    def fake_post(zip_path, fields, *, token, base_url):
        seen.update(fields=fields, token=token, base_url=base_url)
        return {"slug": "w"}

    with patch("neonrp.core.worldhub._post_bundle", fake_post):
        H.upload_via_api(src, kind="worlds", name="Cat Isle", api_token="t", unlisted=True, api_url="https://x")
    assert seen["fields"] == {"kind": "world", "name": "Cat Isle", "version": "1.0", "changelog": "", "unlisted": "true", "slug": "cat-isle"}
    assert seen["token"] == "t" and seen["base_url"] == "https://x"


def test_world_ref_names_the_template_for_sns_zone(tmp_path, monkeypatch):
    """10-15 sns-platform:回放 meta 带 world_ref = hub/template/<id>(和 catalog id 一致),SNS 按它查世界的区。"""
    run = _run(tmp_path / "tpl-wuwu-20261015-101010")
    (run / "game" / "meta" / "template.json").write_text(json.dumps({"id": "wuwu"}), encoding="utf-8")
    meta = RE.build_replay_bundle(run, tmp_path / "r.zip")
    assert meta["world_ref"] == "hub/template/wuwu"
    with zipfile.ZipFile(tmp_path / "r.zip") as zf:
        assert json.loads(zf.read(next(n for n in zf.namelist() if n.endswith("replay.json"))))["world_ref"] == "hub/template/wuwu"
    posted = {}
    monkeypatch.setattr("neonrp.core.worldhub._post_bundle", lambda z, fields, **k: posted.update(fields) or {"slug": fields["slug"]})
    from neonrp.core.worldhub import upload_replay_via_api

    entry = upload_replay_via_api(run, api_token="tok")
    assert posted["world_ref"] == entry["world_ref"] == "hub/template/wuwu"
    old = _run(tmp_path / "stoneford-elena-20260911-101010")
    assert "world_ref" not in RE.build_replay_bundle(old, tmp_path / "o.zip"), "not from a template: no address, SNS treats it as open"
