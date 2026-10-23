"""Publish gate:「在发布之前,warning alert config 的 json 是否
有清楚,是否所有配了图片,是否有中英日韩的 title(提供自动翻译)和介绍,然后才
能公开发布」。"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from neonrp.core import hub_publish as HP
from neonrp.core import worldhub as H

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
FAKE_KEY = "sk-" + "a1b2c3d4" * 4


def _world(root: Path, *, cover: bool = True) -> Path:
    (root / "game" / "meta").mkdir(parents=True, exist_ok=True)
    (root / "game" / "world").mkdir(parents=True, exist_ok=True)
    (root / ".neonrp").mkdir(exist_ok=True)
    (root / "game" / "meta" / "game-start.json").write_text(
        json.dumps({"name": "猫岛", "world_info": {"world_name": "猫岛", "premise": "雾里有船来"}}, ensure_ascii=False), encoding="utf-8"
    )
    (root / "game" / "world" / "world_map.json").write_text("{}", encoding="utf-8")
    if cover:
        (root / "assets").mkdir(exist_ok=True)
        (root / "assets" / "cover.png").write_bytes(PNG)
    return root


def _full_meta(root: Path, kind: str = "worlds") -> None:
    HP.save_hub_meta(
        root, kind,
        title={"zh": "猫岛", "en": "Cat Isle", "ja": "猫島", "ko": "고양이 섬"},
        description={"zh": "雾里有船来", "en": "A ship comes through the fog", "ja": "霧の中から船が来る", "ko": "안개 속에서 배가 온다"},
    )


# ── secrets ───────────────────────────────────────────────────────────


def test_key_in_a_shipping_json_blocks_the_upload(tmp_path):
    root = _world(tmp_path / "w")
    (root / "game" / "meta" / "agent.json").write_text(json.dumps({"api_key": FAKE_KEY}), encoding="utf-8")
    hits = HP.scan_for_secrets(root)
    assert [h.path for h in hits] == ["game/meta/agent.json"] and hits[0].kind == "sk-key"
    check = H.validate_for_upload(root)
    assert "check.secret_found" in check.errors and not check.ok
    assert check.secrets[0]["path"] == "game/meta/agent.json"


def test_neonrp_config_is_not_scanned_because_it_never_ships(tmp_path):
    root = _world(tmp_path / "w")
    (root / ".neonrp" / "config.json").write_text(json.dumps({"providers": {"kimi": {"api_key": FAKE_KEY}}}), encoding="utf-8")
    assert HP.scan_for_secrets(root) == []
    assert H.validate_for_upload(root).ok


def test_credential_files_and_placeholders(tmp_path):
    root = _world(tmp_path / "w")
    (root / ".env").write_text("OPENAI_API_KEY=whatever\n", encoding="utf-8")
    (root / "game" / "meta" / "ok.json").write_text(json.dumps({"api_key": "${KIMI_API_KEY}", "token": "<your-token>"}), encoding="utf-8")
    hits = HP.scan_for_secrets(root)
    assert [(h.path, h.kind) for h in hits] == [(".env", "credential-file")], "占位符不算泄露"


def test_story_secrets_are_not_keys(tmp_path):
    root = _world(tmp_path / "w")
    (root / "game" / "secrets").mkdir()
    (root / "game" / "secrets" / "root-cradle.json").write_text(json.dumps({"secret": "the cradle remembers", "unlock": "ask the gardener"}, ensure_ascii=False), encoding="utf-8")
    assert HP.scan_for_secrets(root) == []


# ── four languages ────────────────────────────────────────────────────


def test_guess_lang():
    assert HP.guess_lang("猫岛") == "zh" and HP.guess_lang("猫島の夜") == "ja"
    assert HP.guess_lang("고양이 섬") == "ko" and HP.guess_lang("Cat Isle") == "en"


def test_missing_languages_block_public_but_not_a_draft(tmp_path):
    root = _world(tmp_path / "w")
    check = H.validate_for_upload(root)
    assert check.ok, "草稿可以传"
    assert "check.i18n_missing" in check.publish_blockers and not check.public_ready
    assert check.title_i18n == {"zh": "猫岛"} and check.description_i18n == {"zh": "雾里有船来"}
    assert check.missing_langs == ["en", "ja", "ko"]


def test_hub_json_makes_it_public_ready(tmp_path):
    root = _world(tmp_path / "w")
    _full_meta(root)
    check = H.validate_for_upload(root)
    assert check.public_ready and check.missing_langs == []
    assert check.title_i18n["ko"] == "고양이 섬"
    assert HP.hub_meta_path(root) == root / "game" / "meta" / "hub.json"


def test_souls_without_portrait_block_public(tmp_path):
    root = _world(tmp_path / "w")
    _full_meta(root)
    (root / "souls" / "luowen").mkdir(parents=True)
    (root / "souls" / "luowen" / "soul.json").write_text(json.dumps({"name": "罗文"}, ensure_ascii=False), encoding="utf-8")
    check = H.validate_for_upload(root)
    assert check.ok and not check.public_ready
    assert "check.souls_no_portrait" in check.publish_blockers and check.souls_without_portrait == ["罗文"]


def test_translate_missing_fills_only_the_gaps():
    meta = HP.HubMeta(title={"zh": "猫岛"}, description={"zh": "雾里有船来"})
    llm = MagicMock()
    llm.chat.return_value = MagicMock(
        success=True,
        message=MagicMock(content='here you go:\n{"title": {"en": "Cat Isle", "ja": "猫島", "ko": "고양이 섬", "zh": "别改我"}, "description": {"en": "A ship in the fog", "ja": "霧の船", "ko": "안개 속 배"}}'),
    )
    out = HP.translate_missing(meta, llm=llm)
    assert out.complete and out.title["zh"] == "猫岛" and out.title["en"] == "Cat Isle"
    prompt = llm.chat.call_args.args[0][1].content
    assert "en (English)" in prompt and "ko (Korean)" in prompt and "zh" not in prompt.split("Languages needed:")[1].split("\n")[0]


def test_translate_failure_is_loud():
    import pytest

    llm = MagicMock()
    llm.chat.return_value = MagicMock(success=False, error="boom", message=None)
    with pytest.raises(RuntimeError):
        HP.translate_missing(HP.HubMeta(title={"zh": "猫岛"}), llm=llm)


# ── the form ──────────────────────────────────────────────────────────


def test_form_has_four_language_rows_translate_and_the_public_checklist(tmp_path):
    import asyncio

    from textual.app import App

    from neonrp.tui.app import HubUploadFormScreen

    check = H.validate_for_upload(_world(tmp_path / "w"))
    translated = HP.HubMeta(
        title={"zh": "猫岛", "en": "Cat Isle", "ja": "猫島", "ko": "고양이 섬"},
        description={"zh": "雾里有船来", "en": "Fog ship", "ja": "霧の船", "ko": "안개 배"},
    )

    class T(App):
        result = "unset"

        def on_mount(self):
            self.push_screen(HubUploadFormScreen(check, locale="zh"), lambda v: setattr(self, "result", v))

    async def run():
        app = T()
        async with app.run_test(size=(120, 50)) as pilot:
            await pilot.pause()
            await pilot.pause()
            scr = app.screen
            before = str(scr.query_one("#hub-form-public").render())
            with patch("neonrp.core.hub_publish.adapter_for_preset", return_value=MagicMock()), patch(
                "neonrp.core.hub_publish.translate_missing", return_value=translated
            ):
                await pilot.click("#hub-form-translate")
                for _ in range(10):
                    await pilot.pause()
                    if scr.query_one("#hub-form-name-ko").value:
                        break
            after = str(scr.query_one("#hub-form-public").render())
            await pilot.click("#hub-form-upload")
            await pilot.pause()
            return before, after, app.result

    before, after, result = asyncio.run(run())
    assert "en / ja / ko" in before, "一开始告诉你缺哪些语言"
    assert "可以申请上架" in after
    assert result["title_i18n"]["ko"] == "고양이 섬" and result["description_i18n"]["en"] == "Fog ship"
    assert result["title"] == "猫岛"


def test_form_done_saves_hub_json_and_sends_i18n_meta(tmp_path):
    from neonrp.tui.app import HubUploadScreen

    root = _world(tmp_path / "w")
    scr = HubUploadScreen(kind="worlds", locale="zh")
    scr._token = "t"
    scr._set_feedback = MagicMock()
    form = {
        "source": root, "title": "猫岛", "description": "雾里有船来",
        "title_i18n": {"zh": "猫岛", "en": "Cat Isle"}, "description_i18n": {"zh": "雾里有船来"},
        "cover": None, "cover_changed": False,
    }
    with patch("neonrp.core.worldhub.upload_via_api", return_value={"slug": "cat-isle"}) as up, patch(
        "neonrp.core.worldhub.update_meta_via_api"
    ) as meta:
        scr._on_form_done(form)
    up.assert_called_once_with(root, kind="worlds", name="猫岛", api_token="t", unlisted=True)
    meta.assert_called_once_with(
        "worlds", "cat-isle", api_token="t", description="雾里有船来",
        name_i18n={"zh": "猫岛", "en": "Cat Isle"}, description_i18n={"zh": "雾里有船来"},
    )
    saved = json.loads((root / "game" / "meta" / "hub.json").read_text(encoding="utf-8"))
    assert saved["title"]["en"] == "Cat Isle"
    assert H.validate_for_upload(root).title_i18n["en"] == "Cat Isle", "下次上传从 hub.json 起步"


def test_meta_api_carries_the_four_languages(monkeypatch):
    seen = {}

    def fake(path, *, api_token, payload=None, method="POST", api_url=None):
        seen.update(path=path, payload=payload)
        return {}

    monkeypatch.setattr(H, "_owner_api_call", fake)
    H.update_meta_via_api("worlds", "cat-isle", api_token="t", name_i18n={"zh": "猫岛", "en": " "}, description_i18n={"ja": "霧"})
    assert seen["payload"] == {"name_i18n": {"zh": "猫岛"}, "description_i18n": {"ja": "霧"}}


# ── the CLI ───────────────────────────────────────────────────────────


def test_cli_refuses_a_bundle_with_a_key_even_when_forced(tmp_path, monkeypatch):
    from neonrp.commands.world_hub import world_group

    root = _world(tmp_path / "w")
    (root / "game" / "meta" / "agent.json").write_text(json.dumps({"api_key": FAKE_KEY}), encoding="utf-8")
    up = MagicMock()
    monkeypatch.setattr("neonrp.commands.world_hub.upload_via_api", up)
    res = CliRunner().invoke(world_group, ["upload", str(root), "--force", "--unlisted"])
    assert res.exit_code != 0 and "agent.json" in res.output
    up.assert_not_called()


def test_cli_public_upload_needs_the_gate_but_a_draft_does_not(tmp_path, monkeypatch):
    from neonrp.commands.world_hub import world_group

    root = _world(tmp_path / "w")
    up = MagicMock(return_value={"name": "猫岛", "slug": "cat-isle", "version": "1.0", "hash": "h", "size_bytes": 1, "url": "u"})
    monkeypatch.setattr("neonrp.commands.world_hub.upload_via_api", up)
    res = CliRunner().invoke(world_group, ["upload", str(root)])
    assert res.exit_code != 0 and "missing in: en, ja, ko" in res.output
    up.assert_not_called()
    res = CliRunner().invoke(world_group, ["upload", str(root), "--unlisted"])
    assert res.exit_code == 0, res.output
    _full_meta(root)
    res = CliRunner().invoke(world_group, ["upload", str(root)])
    assert res.exit_code == 0, res.output
    assert up.call_count == 2
