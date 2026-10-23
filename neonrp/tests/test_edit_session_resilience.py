"""创作会话韧性(实测 409)— 重启后懒重建 + 老档 cap 补丁 回归。"""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from neonrp.commands import web as web_mod


@pytest.fixture(autouse=True)
def _isolate_session_file(tmp_path, monkeypatch):
    monkeypatch.setattr(
        web_mod, "_LAST_EDIT_SESSION_FILE", tmp_path / "last_edit_session.json"
    )


def _world(tmp_path: Path, name: str = "w-edit") -> Path:
    w = tmp_path / name
    (w / ".neonrp").mkdir(parents=True)
    return w


def test_persist_on_create(tmp_path: Path) -> None:
    w = _world(tmp_path)
    web_mod._make_edit_runtime(w)
    payload = json.loads(web_mod._LAST_EDIT_SESSION_FILE.read_text(encoding="utf-8"))
    assert payload["world_dir"] == str(w)


def test_lazy_rebind_after_restart(tmp_path: Path) -> None:
    w = _world(tmp_path)
    web_mod._make_edit_runtime(w)
    server = SimpleNamespace(edit_runtime=None)  # 模拟进程重启:内存态没了
    ert = web_mod._try_rebind_edit_runtime(server)
    assert ert is not None and ert.world_dir == w
    assert server.edit_runtime is ert  # 挂回,后续请求直用


def test_rebind_invalid_path_returns_none(tmp_path: Path) -> None:
    web_mod._LAST_EDIT_SESSION_FILE.write_text(
        json.dumps({"world_dir": str(tmp_path / "gone")}), encoding="utf-8"
    )
    assert web_mod._try_rebind_edit_runtime(SimpleNamespace(edit_runtime=None)) is None
    # 无记录文件同样 None
    web_mod._LAST_EDIT_SESSION_FILE.unlink()
    assert web_mod._try_rebind_edit_runtime(SimpleNamespace(edit_runtime=None)) is None


def test_cap_bump_deepseek_only(tmp_path: Path) -> None:
    w = _world(tmp_path, "w-cap")
    cfg = w / ".neonrp" / "config.json"
    cfg.write_text(
        json.dumps({"llm": {"provider": "openai", "model": "deepseek-v4-pro", "base_url": "https://api.deepseek.com/v1", "max_output_tokens": 4096}}),
        encoding="utf-8",
    )
    web_mod._bump_edit_world_output_cap(w)
    assert json.loads(cfg.read_text(encoding="utf-8"))["llm"]["max_output_tokens"] == 16384
    # 非 deepseek 不动
    w2 = _world(tmp_path, "w-cap2")
    cfg2 = w2 / ".neonrp" / "config.json"
    cfg2.write_text(
        json.dumps({"llm": {"provider": "openai", "model": "gpt-4o", "max_output_tokens": 4096}}),
        encoding="utf-8",
    )
    web_mod._bump_edit_world_output_cap(w2)
    assert json.loads(cfg2.read_text(encoding="utf-8"))["llm"]["max_output_tokens"] == 4096
