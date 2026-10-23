"""CLI surface tests for the `neonrp soul` group.

These exercise click wiring only — every `neonrp.core.worldhub` call is
monkeypatched so nothing touches S3 / the network. The contract under
test is purely: the subcommands exist, they delegate to the shared
worldhub functions with `kind="souls"`, and the `--unlisted` flag is
wired through.
"""

from __future__ import annotations

from typing import Any

import pytest
from click.testing import CliRunner

from neonrp.commands.soul_hub import soul_group


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def test_group_lists_all_subcommands(runner: CliRunner) -> None:
    result = runner.invoke(soul_group, ["--help"])
    assert result.exit_code == 0
    for sub in ("upload", "download", "list", "unlist", "relist"):
        assert sub in result.output
    # Group help text present.
    assert "SoulHub" in result.output


@pytest.mark.parametrize("sub", ["upload", "download", "list", "unlist", "relist"])
def test_subcommand_has_help(runner: CliRunner, sub: str) -> None:
    result = runner.invoke(soul_group, [sub, "--help"])
    assert result.exit_code == 0
    assert result.output.strip()


def test_upload_passes_souls_kind_and_unlisted(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    captured: dict[str, Any] = {}

    def fake_upload(path: Any, **kwargs: Any) -> dict[str, Any]:
        captured["path"] = path
        captured.update(kwargs)
        return {
            "name": "Elena",
            "slug": "elena",
            "version": "1.0",
            "hash": "deadbeef",
            "size_bytes": 1234,
            "url": "s3://hub/souls/deadbeef.zip",
            "unlisted": kwargs.get("unlisted", False),
            "changelog": "",
        }

    monkeypatch.setattr("neonrp.commands.soul_hub.upload_via_api", fake_upload)

    soul_dir = tmp_path / "elena"
    soul_dir.mkdir()
    result = runner.invoke(
        soul_group,
        ["upload", str(soul_dir), "--slug", "elena", "--version", "1.0", "--unlisted"],
    )

    assert result.exit_code == 0, result.output
    assert captured["kind"] == "souls"
    assert captured["unlisted"] is True
    assert captured["slug"] == "elena"
    assert "Uploaded" in result.output


def test_upload_unlisted_defaults_false(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    captured: dict[str, Any] = {}

    def fake_upload(path: Any, **kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {
            "name": "Elena",
            "slug": "elena",
            "version": "1.0",
            "hash": "deadbeef",
            "size_bytes": 1,
            "url": "u",
        }

    monkeypatch.setattr("neonrp.commands.soul_hub.upload_via_api", fake_upload)

    soul_dir = tmp_path / "elena"
    soul_dir.mkdir()
    # 2026-09-13 publish gate: a PUBLIC upload of a folder with no portrait /
    # no four-language intro is refused; --force skips the gate, --unlisted
    # makes it a draft.
    refused = runner.invoke(soul_group, ["upload", str(soul_dir)])
    assert refused.exit_code != 0 and "PUBLIC" in refused.output and "captured" not in captured
    result = runner.invoke(soul_group, ["upload", str(soul_dir), "--force"])

    assert result.exit_code == 0, result.output
    assert captured["unlisted"] is False


def test_download_passes_souls_kind(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    captured: dict[str, Any] = {}

    def fake_download(query: str, **kwargs: Any) -> Any:
        captured["query"] = query
        captured.update(kwargs)
        return tmp_path / "elena-20260515"

    monkeypatch.setattr("neonrp.commands.soul_hub.download", fake_download)

    result = runner.invoke(soul_group, ["download", "elena@1.0"])

    assert result.exit_code == 0, result.output
    assert captured["query"] == "elena@1.0"
    assert captured["kind"] == "souls"


def test_list_passes_souls_kind_and_all_flag(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, Any] = {}

    def fake_list_stories(**kwargs: Any) -> list[dict[str, Any]]:
        captured.update(kwargs)
        return [
            {
                "slug": "elena",
                "display_name": "Elena Voss",
                "latest_version": "2.0",
                "latest_hash": "abc123",
                "versions": [
                    {"version": "2.0", "size_bytes": 2048, "hash": "abc123"},
                    {"version": "1.0", "size_bytes": 1024, "hash": "def456",
                     "changelog": "first cut"},
                ],
            }
        ]

    monkeypatch.setattr("neonrp.commands.soul_hub.list_stories", fake_list_stories)

    result = runner.invoke(soul_group, ["list", "--all"])

    assert result.exit_code == 0, result.output
    assert captured["kind"] == "souls"
    assert "elena" in result.output
    # --all surfaces the older version line.
    assert "first cut" in result.output


def test_list_empty_uses_souls_registry_url(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict[str, Any] = {}

    monkeypatch.setattr(
        "neonrp.commands.soul_hub.list_stories", lambda **kw: seen.update(kw) or []
    )
    monkeypatch.setattr(
        "neonrp.commands.soul_hub.registry_url",
        lambda kind="worlds": f"s3://hub/{kind}/index.json",
    )

    result = runner.invoke(soul_group, ["list"])

    assert result.exit_code == 0, result.output
    assert seen["kind"] == "souls"
    assert "souls/index.json" in result.output


def test_unlist_passes_souls_kind_true(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, Any] = {}

    def fake_set_unlisted(query: str, **kwargs: Any) -> list[dict[str, Any]]:
        captured["query"] = query
        captured.update(kwargs)
        return [{"slug": "elena", "version": "1.0", "hash": "abc"}]

    monkeypatch.setattr("neonrp.commands.soul_hub.set_unlisted", fake_set_unlisted)

    result = runner.invoke(soul_group, ["unlist", "elena"])

    assert result.exit_code == 0, result.output
    assert captured["kind"] == "souls"
    assert captured["unlisted"] is True
    assert "Unlisted" in result.output


def test_relist_passes_souls_kind_false(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, Any] = {}

    def fake_set_unlisted(query: str, **kwargs: Any) -> list[dict[str, Any]]:
        captured.update(kwargs)
        return [{"slug": "elena", "version": "1.0", "hash": "abc"}]

    monkeypatch.setattr("neonrp.commands.soul_hub.set_unlisted", fake_set_unlisted)

    result = runner.invoke(soul_group, ["relist", "elena"])

    assert result.exit_code == 0, result.output
    assert captured["kind"] == "souls"
    assert captured["unlisted"] is False
    assert "Relisted" in result.output


def test_no_kind_flag_on_subcommands(runner: CliRunner) -> None:
    # The soul group hard-wires kind; exposing --kind would be a bug.
    for sub in ("upload", "download", "list", "unlist", "relist"):
        result = runner.invoke(soul_group, [sub, "--help"])
        assert "--kind" not in result.output, sub
