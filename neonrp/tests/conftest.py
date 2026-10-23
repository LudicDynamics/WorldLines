"""测试全局密封护栏。

心跳(M30 lifecycle)在真实游玩默认开启;测试环境默认**关闭**——
未 mock adapter 的测试工程没配 llm,adapter 会落到开发者的用户配置
(真 deepseek key!),导致测试静默烧真 API(2026-08-14 实测:
multiagent 文件 1s→123s)。需要心跳的测试用
`monkeypatch.setenv("NEONRP_HEARTBEAT", "1")` 显式开启。
"""

import pytest

# 10-10 R1: the planning beat lives in the private layer now (NeonRP-private → worldlines/private). Load it before test
# modules are collected, so the tests that drive it can still say ``from neonrp.core import plan_loop``; without the
# private layer those tests are skipped (tests/private/), the rest run on the open engine.
from neonrp.core import node_kinds as _node_kinds

PLAN_PLUGIN = _node_kinds.get("plan") is not None
_REQ_FILE = __import__("pathlib").Path(__file__).parent / "requires_private.txt"  # not exported: the open repo has none
_REQUIRES_PRIVATE = {
    ln.strip() for ln in (_REQ_FILE.read_text(encoding="utf-8").splitlines() if _REQ_FILE.is_file() else [])
    if ln.strip() and not ln.startswith("#")
}


# niko 10-17: the open-source repo carries only the templates the local edition ships (worldlines/templates/shipped.json);
# the other official worlds' sources stay in the development repo. A test that names one of them is skipped where it
# is not there (the whole module when its fixtures / constants name it, else just that test).
OFFICIAL_UNSHIPPED = ("guixiang", "kagura-island", "last-train", "neon-rebirth", "spice-witch", "stoneford-elena",
                      "stoneford-market", "stoneford-three-towns", "werewolf-night-village", "wuwu")


def _missing_templates() -> set[str]:
    from _paths import PRODUCT_TEMPLATES

    return {t for t in OFFICIAL_UNSHIPPED if not (PRODUCT_TEMPLATES / f"{t}.template" / "template.json").is_file()}


def _skip_missing_templates(items) -> None:
    import ast
    import re

    missing = _missing_templates()
    if not missing:
        return
    pat = re.compile(r"""["'/](%s)(?:\.template)?["'/]""" % "|".join(re.escape(m) for m in sorted(missing)))
    mods: dict[str, tuple[str | None, dict[str, str]]] = {}
    for it in items:
        path = str(getattr(it, "fspath", "") or "")
        if path not in mods:
            try:
                src = open(path, encoding="utf-8").read()
                tree = ast.parse(src)
            except (OSError, SyntaxError, ValueError):
                mods[path] = (None, {})
                continue
            top = [n for n in tree.body if not (isinstance(n, ast.FunctionDef) and n.name.startswith("test"))]
            hit = next((m.group(1) for n in top for m in [pat.search(ast.get_source_segment(src, n) or "")] if m), None)
            fns = {n.name: ast.get_source_segment(src, n) or "" for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
            decs = {n.name: " ".join(ast.get_source_segment(src, d) or "" for d in n.decorator_list)
                    for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
            mods[path] = (hit, fns, decs)
        hit, fns, decs = mods[path]
        name = getattr(getattr(it, "function", None), "__name__", "")
        cs = getattr(it, "callspec", None)
        if cs is not None:   # parametrized: only the cases on a missing template (the decorator lists every case)
            m = hit or next((x for x in missing if re.search(r"(^|[-\[])%s($|[-\]])" % re.escape(x), cs.id)), None) \
                or (pat.search(fns.get(name, "")) or [None, None])[1]
        else:
            m = hit or (pat.search(fns.get(name, "") + decs.get(name, "")) or [None, None])[1]
        if m:
            it.add_marker(pytest.mark.skip(reason=f"template {m} is not in this repo (only the shipped ones are open source)"))


def pytest_collection_modifyitems(config, items):
    """Without the private layer the planning beat's own tests are skipped (the open engine has no planning beat);
    tests on official templates this repo does not carry are skipped too (_skip_missing_templates)."""
    import os

    _skip_missing_templates(items)
    if PLAN_PLUGIN and os.environ.get("NEONRP_PRIVATE", "").strip().lower() not in ("off", "0", "false", "no"):
        return
    skip = pytest.mark.skip(reason="needs the private layer (the planning beat)")
    for it in items:
        if it.nodeid.split("[", 1)[0] in _REQUIRES_PRIVATE:
            it.add_marker(skip)


@pytest.fixture(autouse=True)
def _hermetic_official_cache(monkeypatch, tmp_path_factory):
    """Official worlds fetched with an account (~/.worldlines/official, 10-17) never reach a test, and the shipped-only
    view / the official-publish switch are off unless a test sets them."""
    monkeypatch.setenv("NEONRP_OFFICIAL_DIR", str(tmp_path_factory.mktemp("official")))
    for k in ("NEONRP_TEMPLATES", "NEONRP_OFFICIAL_PUBLISH"):
        monkeypatch.delenv(k, raising=False)


@pytest.fixture(autouse=True)
def _hermetic_heartbeat(monkeypatch):
    monkeypatch.setenv("NEONRP_HEARTBEAT", "0")


@pytest.fixture(autouse=True)
def _restore_cwd():
    """The CLI's launch paths chdir into the save (cli.py); a test that drives them must not leave the next test there
    (10-23: test_worldlines_cli left every later relative path pointing into a tmp save)."""
    import os

    cwd = os.getcwd()
    yield
    try:
        os.chdir(cwd)
    except OSError:
        pass


@pytest.fixture(autouse=True)
def _hermetic_judge_fallback(monkeypatch):
    """A failed Jev call now falls back to an LLM judge from the user's config (10-01). Tests must never reach a
    real model that way: off by default; a test that wants the middle step sets it and installs LLM_ADAPTER_FACTORY."""
    monkeypatch.setenv("NEONRP_S1_LLM_FALLBACK", "0")
    # and no real Jev either (the user's config may hold a key): a test that wants a judge sets the backend itself
    import os

    if not os.environ.get("NEONRP_S1_BACKEND"):
        monkeypatch.setenv("NEONRP_S1_BACKEND", "off")


@pytest.fixture(autouse=True)
def _hermetic_worldlines_account(monkeypatch, tmp_path_factory):
    """The developer's real Worldlines session (~/.worldlines/identity.json) and PAT never reach a test (10-02: a real
    session flipped the judge backend to the proxy). A test that wants a session writes its own file."""
    monkeypatch.setenv("WORLDLINES_IDENTITY_FILE", str(tmp_path_factory.mktemp("wl-identity") / "identity.json"))
    for k in ("WORLDLINES_API_KEY", "HUB_API_TOKEN"):
        monkeypatch.delenv(k, raising=False)


@pytest.fixture(autouse=True)
def _hermetic_soul_library(monkeypatch, tmp_path_factory):
    """cast_soul now archives into ``~/.worldlines/souls/`` (任务 B1). A test
    that casts must never touch the user's real library — one did, on
    2026-09-10, before this guard existed."""
    import neonrp.core.souls as _souls

    lib = tmp_path_factory.mktemp("souls-lib")
    monkeypatch.setattr(_souls, "SOUL_HOME", lib)
    # placement.py binds its own name at import time; keep the two in step.
    try:
        import neonrp.core.placement as _placement

        monkeypatch.setattr(_placement, "SOUL_HOME", lib, raising=False)
    except Exception:
        pass


@pytest.fixture(autouse=True)
def _hermetic_player_data(monkeypatch, tmp_path_factory):
    """The player's record (core/player_data: gained characters, endings, achievements) lives in ~/.worldlines — a test
    that reaches an ending or chats with a standalone soul must not write into the developer's real one (10-15)."""
    import neonrp.core.player_data as _pd

    monkeypatch.setattr(_pd, "HOME", tmp_path_factory.mktemp("player-data"))
    monkeypatch.delenv("WORLDLINES_PLAYER_ID", raising=False)
    import neonrp.core.chronicle as _chron  # chronicle's spool too (10-15): never the developer's, never the network

    monkeypatch.setattr(_chron, "SPOOL", tmp_path_factory.mktemp("chronicle") / "spool.jsonl")
    monkeypatch.setattr(_chron, "BASE", "http://127.0.0.1:9")
    import neonrp.core.replay_library as _rl  # a run that ends keeps a replay (10-18): never in the developer's library

    monkeypatch.setattr(_rl, "HOME", tmp_path_factory.mktemp("replays"))
