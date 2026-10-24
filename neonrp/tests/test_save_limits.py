"""Save limits (10-15, PLATFORM-PLAY-RULES-1015 §4; core/save_limits.py): how many runs of one world a player may
keep — a NEW run over the limit is refused (409 save_limit + this world's runs), carrying on never is; the player may
give one run up for the new one (``replace``). Numbers: the platform's entitlements.limits > NEONRP_SAVE_LIMITS > the
packaged table by tier. A local player with their own key who is not signed in has no limit; billing out of reach =
no limit; a token billing refuses = free."""
from __future__ import annotations

import json
import shutil
import threading
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

import pytest

from _paths import PRODUCT_TEMPLATES
from neonrp.core import save_limits as SL


@pytest.fixture(autouse=True)
def _clear_cache():
    SL._CACHE.clear()
    yield
    SL._CACHE.clear()


@pytest.fixture
def store(tmp_path, monkeypatch):
    st = tmp_path / "store"
    for tid in ("pct-house", "stoneford-town"):
        shutil.copytree(PRODUCT_TEMPLATES / f"{tid}.template", st / f"{tid}.template")
    monkeypatch.setenv("NEONRP_TEMPLATE_PATH", str(st))
    monkeypatch.setenv("NEONRP_DISABLE_CLAUDE_CODE", "1")
    return st


def signed(monkeypatch, tier: str | None = "free", limits: dict | None = None, status: int = 200) -> list[str]:
    """A signed-in player whose billing answers ``tier`` (None: billing out of reach). Returns the URLs billing was asked."""
    asked: list[str] = []
    monkeypatch.setattr("neonrp.core.worldlines_auth.access_token", lambda: "tok-e2e")

    def call(method, url, token, body=None, timeout=30):
        asked.append(url)
        if tier is None:
            return 0, None
        if status != 200:
            return status, {"error": "unauthorized"}
        return 200, {"plan": tier, "tier": tier, "limits": limits or {}}

    monkeypatch.setattr("neonrp.core.scene_art._call", call)
    return asked


def fake_runs(plays: Path, tid: str, n: int) -> list[str]:
    out = []
    for k in range(n):
        d = plays / f"tpl-{tid}-2026101{k}-120000"
        (d / "game" / "meta").mkdir(parents=True)
        (d / "game" / "meta" / "template.json").write_text(json.dumps({"id": tid}), encoding="utf-8")
        (d / "game" / "meta" / "run_state.json").write_text(json.dumps({"turn_count": k + 1}), encoding="utf-8")
        out.append(d.name)
    return out


# ── the table / the kind of world ────────────────────────────────────────────

def test_packaged_table_follows_the_rules() -> None:
    t = SL.table()
    assert t["free"] == {"sandbox": 1, "adventure": 1}
    assert t["story"] == {"sandbox": 3, "adventure": 4}
    assert t["vivid"]["sandbox"] is None and t["vivid"]["adventure"] == 4


def test_env_table_wins(tmp_path, monkeypatch) -> None:
    f = tmp_path / "lim.json"
    f.write_text(json.dumps({"free": {"sandbox": 7, "adventure": 2}}), encoding="utf-8")
    monkeypatch.setenv("NEONRP_SAVE_LIMITS", str(f))
    assert SL.table()["free"]["sandbox"] == 7


def test_kind_of_world(store) -> None:
    assert SL.kind_of("pct-house") == "sandbox"            # mystery-trpg contract
    assert SL.kind_of("stoneford-town") == "adventure"     # open-adventure contract: exit on a segment (a day)
    assert SL.kind_of("no-such-world") == "sandbox"


def test_runs_of_counts_only_this_world(tmp_path) -> None:
    plays = tmp_path / "plays"
    fake_runs(plays, "pct-house", 2)
    fake_runs(plays, "stoneford-town", 1)
    rows = SL.runs_of("pct-house", plays)
    assert [r["turns"] for r in rows] and len(rows) == 2 and all(r["slug"].startswith("tpl-pct-house-") for r in rows)
    assert set(rows[0]) == {"slug", "turns", "updated", "ended"}


# ── who is limited, and by how much ─────────────────────────────────────────

def test_own_key_not_signed_in_has_no_limit(monkeypatch) -> None:
    monkeypatch.setattr("neonrp.core.worldlines_auth.access_token", lambda: None)
    assert SL.limit_for("sandbox") == (None, None)
    monkeypatch.setattr("neonrp.core.worldlines_auth.access_token", lambda: "-")   # the browser build without a token
    assert SL.limit_for("sandbox") == (None, None)


@pytest.mark.parametrize("tier,kind,want", [("free", "sandbox", 1), ("free", "adventure", 1), ("story", "sandbox", 3),
                                            ("story", "adventure", 4), ("vivid", "sandbox", None), ("vivid", "adventure", 4)])
def test_tiers(monkeypatch, tier, kind, want) -> None:
    signed(monkeypatch, tier)
    assert SL.limit_for(kind) == (tier, want)


def test_platform_limits_win(monkeypatch) -> None:
    signed(monkeypatch, "story", limits={"saves_sandbox": 5})
    assert SL.limit_for("sandbox") == ("story", 5)
    assert SL.limit_for("adventure") == ("story", 4)       # not given by the platform: the table


def test_billing_unreachable_does_not_limit(monkeypatch) -> None:
    signed(monkeypatch, None)
    assert SL.limit_for("sandbox") == (None, None)


def test_refused_token_is_free(monkeypatch) -> None:
    signed(monkeypatch, "story", status=401)
    assert SL.limit_for("sandbox") == ("free", 1)


def test_entitlements_are_cached(monkeypatch) -> None:
    asked = signed(monkeypatch, "story")
    SL.limit_for("sandbox")
    SL.limit_for("adventure")
    assert len(asked) == 1 and "/v1/me/entitlements?product=" in asked[0]


def test_check_new_run(store, tmp_path, monkeypatch) -> None:
    plays = tmp_path / "plays"
    signed(monkeypatch, "free")
    SL.check_new_run("pct-house", plays)                  # none yet: fine
    fake_runs(plays, "pct-house", 1)
    with pytest.raises(SL.SaveLimit) as e:
        SL.check_new_run("pct-house", plays)
    d = e.value.to_dict()
    assert d["error"] == "save_limit" and d["limit"] == 1 and d["kind"] == "sandbox" and d["tier"] == "free" and len(d["saves"]) == 1
    SL.check_new_run("stoneford-town", plays)             # another world: its own count


# ── over HTTP: POST /api/v1/play/session ─────────────────────────────────────

@pytest.fixture
def web(store, tmp_path):
    from neonrp.commands.web import make_server

    plays = tmp_path / "lib" / "plays"
    ps = [patch("neonrp.worlds.WORLDS_HOME", tmp_path / "lib" / "worlds"), patch("neonrp.worlds.PLAYS_HOME", plays),
          patch("neonrp.worlds.STUDIO_HOME", tmp_path / "lib" / "studio"),
          patch("neonrp.commands.web.WebRuntime.gateway_start", lambda self: {"sid": "local", "root": self.root.name})]
    for p in ps:
        p.start()
    server = make_server(None, "world-agent", "127.0.0.1", 0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"

    def call(path, body=None, method=None):
        req = urllib.request.Request(base + path, data=None if body is None else json.dumps(body).encode(),
                                     method=method or ("GET" if body is None else "POST"), headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                b = r.read()
                return r.status, (json.loads(b) if b else {})
        except urllib.error.HTTPError as e:
            b = e.read()
            try:
                return e.code, json.loads(b)
            except ValueError:
                return e.code, {"raw": b.decode("utf-8", "replace")}

    yield {"call": call, "plays": plays, "server": server}
    server.shutdown()
    server.server_close()
    for p in ps:
        p.stop()


def test_http_limit_then_replace(web, monkeypatch) -> None:
    signed(monkeypatch, "free")
    call, plays = web["call"], web["plays"]
    st, r1 = call("/api/v1/play/session", {"slug": "tpl--pct-house", "output_lang": "zh"})
    assert st == 200, r1
    first = web["server"].runtime.root.name
    # a second new run of the same world: refused, nothing built, the page gets this world's runs
    st, r = call("/api/v1/play/session", {"slug": "tpl--pct-house", "output_lang": "zh"})
    assert st == 409 and r["error"] == "save_limit" and r["limit"] == 1 and [s["slug"] for s in r["saves"]] == [first]
    assert len([d for d in plays.iterdir() if d.is_dir()]) == 1
    # carrying on with the run is never limited
    st, _ = call("/api/v1/play/session", {"slug": first})
    assert st == 200
    # replace with a run that is not this world's: refused
    st, r = call("/api/v1/play/session", {"slug": "tpl--pct-house", "replace": "../etc"})
    assert st == 400 and r["error"] == "bad_replace"
    # the player gives the first run up (even the one being played): the new run is up, the old one gone
    st, _ = call("/api/v1/play/session", {"slug": "tpl--pct-house", "output_lang": "zh", "replace": first})
    assert st == 200
    now = web["server"].runtime.root.name
    assert now != first and not (plays / first).exists() and (plays / now).is_dir()
    # another world has its own count
    st, _ = call("/api/v1/play/session", {"slug": "tpl--stoneford-town", "output_lang": "zh"})
    assert st == 200


def test_http_own_key_not_limited(web, monkeypatch) -> None:
    monkeypatch.setattr("neonrp.core.worldlines_auth.access_token", lambda: None)
    for _ in range(3):
        st, r = web["call"]("/api/v1/play/session", {"slug": "tpl--pct-house", "output_lang": "zh"})
        assert st == 200, r
    assert len([d for d in web["plays"].iterdir() if d.is_dir()]) == 3


def test_http_limit_probe(web, monkeypatch) -> None:
    signed(monkeypatch, "free")
    call = web["call"]
    assert call("/api/v1/play/session/limit?tpl=pct-house") == (200, {"ok": True})
    assert call("/api/v1/play/session", {"slug": "tpl--pct-house", "output_lang": "zh"})[0] == 200
    st, r = call("/api/v1/play/session/limit?tpl=pct-house")
    assert st == 200 and r["ok"] is False and r["error"] == "save_limit" and len(r["saves"]) == 1
