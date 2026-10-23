"""Secrets P2 (docs/SECRETS-DESIGN.md §c/§d) — keeper adjudication + guardrail.

The keeper judges fuzzy ``judgment`` reveal conditions in at most ONE batched
LLM call per turn, and only for secrets whose host is scene-relevant; verdicts
apply through the shared P1 reveal machinery marked ``adjudicated_by``. The
guardrail is deterministic: narration containing distinctive text of a
still-unrevealed secret queues a deliver-once correction line. Worlds without
secrets never construct an adapter and never write a file.
"""

import json
from pathlib import Path

from neonrp.core.secrets import (
    drain_guardrail_notices,
    drain_reveal_notices,
    guardrail_scan,
    keeper_adjudicate,
    read_ledger,
    secrets_p2_turn_pass,
    standing_gm_block,
)


def _write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _world(tmp_path: Path) -> Path:
    root = tmp_path / "world"
    _write(root / "game" / "npc" / "kagami.json", {
        "id": "kagami", "kind": "npc", "name": "鏡子", "location": "cafe", "trust": 30,
    })
    _write(root / "game" / "location" / "cafe.json", {
        "id": "cafe", "kind": "location", "name": "咖啡馆", "summary": "岛上唯一的咖啡馆。",
    })
    _write(root / "game" / "location" / "cellar.json", {
        "id": "cellar", "kind": "location", "name": "地下室", "summary": "堆满旧物。",
    })
    _write(root / "game" / "meta" / "run_state.json", {"turn_count": 3, "location": "cafe"})
    return root


def _add_secret(root: Path, name: str, data: dict) -> None:
    _write(root / "game" / "secrets" / f"{name}.json", data)


def _judgment_secret(about: str, sid: str, hidden: str, condition: str) -> dict:
    return {
        "id": sid,
        "about": about,
        "audience": ["gm"],
        "content": {"summary_hidden": hidden},
        "revealed_when": [{"judgment": condition}],
    }


class _StubKeeper:
    """Counting stub adapter; returns a canned reply from .generate()."""

    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.calls = 0
        self.last_user = ""

    def generate(self, system_prompt, user_prompt, tools=None):
        self.calls += 1
        self.last_user = user_prompt
        return self.reply


class _CountingFactory:
    def __init__(self, adapter) -> None:
        self.adapter = adapter
        self.constructions = 0

    def __call__(self):
        self.constructions += 1
        return self.adapter


def test_no_secrets_world_is_total_noop(tmp_path):
    root = _world(tmp_path)  # no game/secrets/
    factory = _CountingFactory(_StubKeeper("{}"))
    secrets_p2_turn_pass(
        root, player_text="我侦查地下室", narration_text="你搜了一圈。", adapter_factory=factory
    )
    assert factory.constructions == 0
    assert not (root / "game" / "meta" / "secret_guardrail.json").exists()
    assert standing_gm_block(root) == ""


def test_keeper_gated_when_host_out_of_scene(tmp_path):
    root = _world(tmp_path)
    _add_secret(root, "location--cellar", _judgment_secret(
        "location/cellar", "s-cellar", "有一条通向海底的隐藏通道。", "玩家认真侦查地下室"
    ))
    factory = _CountingFactory(_StubKeeper("{}"))
    # Player is at cafe; texts never mention the cellar → zero LLM activity.
    revealed = keeper_adjudicate(
        root, player_text="我和镜子聊天", narration_text="镜子笑着递来咖啡。", adapter_factory=factory
    )
    assert revealed == []
    assert factory.constructions == 0


def test_keeper_batches_relevant_secrets_into_one_call(tmp_path):
    root = _world(tmp_path)
    _add_secret(root, "location--cafe", _judgment_secret(
        "location/cafe", "s-cafe", "柜台下压着一把旧钥匙,鏡子从不提起。", "玩家仔细搜查咖啡馆(侦查成功)"
    ))
    _add_secret(root, "npc--kagami", _judgment_secret(
        "npc/kagami", "s-kagami", "她整夜守着孤儿院的名单。", "镜子主动吐露心事"
    ))
    reply = json.dumps({"verdicts": [
        {"id": "s-cafe", "reveal": True, "reason": "玩家翻查柜台,叙事确认找到暗格"},
        {"id": "s-kagami", "reveal": False, "reason": "未发生"},
    ]}, ensure_ascii=False)
    stub = _StubKeeper(reply)
    factory = _CountingFactory(stub)
    revealed = keeper_adjudicate(
        root,
        player_text="我仔细搜查咖啡馆的柜台",
        narration_text="你在柜台下摸到一个暗格,指尖碰到了冰凉的金属。",
        adapter_factory=factory,
    )
    assert revealed == ["s-cafe"]
    assert stub.calls == 1  # BOTH candidates batched into one call
    assert "s-cafe" in stub.last_user and "s-kagami" in stub.last_user
    ledger = read_ledger(root)
    assert ledger["s-cafe"]["adjudicated_by"] == "keeper"
    assert ledger["s-cafe"]["reason"]
    assert "s-kagami" not in ledger  # reveal:false not applied
    host = json.loads((root / "game" / "location" / "cafe.json").read_text(encoding="utf-8"))
    assert "旧钥匙" in host["summary"]  # merged back
    notices = drain_reveal_notices(root)
    assert any("s-cafe" in n for n in notices)


def test_keeper_unparseable_reply_reveals_nothing(tmp_path):
    root = _world(tmp_path)
    _add_secret(root, "location--cafe", _judgment_secret(
        "location/cafe", "s-cafe", "柜台下压着一把旧钥匙。", "侦查成功"
    ))
    factory = _CountingFactory(_StubKeeper("我觉得应该可以揭示了吧!"))
    revealed = keeper_adjudicate(
        root, player_text="搜查咖啡馆", narration_text="你搜查了咖啡馆。", adapter_factory=factory
    )
    assert revealed == []
    assert read_ledger(root) == {}


def test_keeper_confines_verdicts_to_candidates(tmp_path):
    root = _world(tmp_path)
    _add_secret(root, "location--cafe", _judgment_secret(
        "location/cafe", "s-cafe", "柜台下压着一把旧钥匙。", "侦查成功"
    ))
    _add_secret(root, "location--cellar", _judgment_secret(
        "location/cellar", "s-cellar", "有一条通向海底的隐藏通道。", "侦查地下室成功"
    ))
    # Keeper tries to reveal the OUT-OF-SCENE cellar secret it was never asked about.
    reply = json.dumps({"verdicts": [
        {"id": "s-cellar", "reveal": True, "reason": "越权"},
        {"id": "s-cafe", "reveal": False, "reason": "未成功"},
    ]}, ensure_ascii=False)
    factory = _CountingFactory(_StubKeeper(reply))
    revealed = keeper_adjudicate(
        root, player_text="搜查咖啡馆", narration_text="你在咖啡馆里转了一圈。", adapter_factory=factory
    )
    assert revealed == []
    assert read_ledger(root) == {}


def test_keeper_skips_without_narration(tmp_path):
    root = _world(tmp_path)
    _add_secret(root, "location--cafe", _judgment_secret(
        "location/cafe", "s-cafe", "柜台下压着一把旧钥匙。", "侦查成功"
    ))
    factory = _CountingFactory(_StubKeeper("{}"))
    assert keeper_adjudicate(
        root, player_text="", narration_text="", adapter_factory=factory
    ) == []
    assert factory.constructions == 0


def test_guardrail_flags_leaked_fragment_once(tmp_path):
    root = _world(tmp_path)
    _add_secret(root, "location--cellar", _judgment_secret(
        "location/cellar", "s-cellar", "有一条通向海底的隐藏通道。", "侦查地下室成功"
    ))
    narration = "老板娘压低声音:据说这下面有一条通向海底的隐藏通道。"
    flagged = guardrail_scan(root, narration)
    assert flagged == ["s-cellar"]
    lines = drain_guardrail_notices(root)
    assert len(lines) == 1 and "s-cellar" in lines[0]
    assert drain_guardrail_notices(root) == []  # deliver-once


def test_guardrail_ignores_revealed_and_clean_narration(tmp_path):
    root = _world(tmp_path)
    _add_secret(root, "location--cellar", _judgment_secret(
        "location/cellar", "s-cellar", "有一条通向海底的隐藏通道。", "侦查地下室成功"
    ))
    # Clean narration → nothing flagged.
    assert guardrail_scan(root, "你们聊起了天气与祭典。") == []
    # Mark revealed → leaking it is no longer a violation.
    _write(root / "game" / "meta" / "secret_ledger.json", {"s-cellar": {"about": "location/cellar"}})
    assert guardrail_scan(root, "据说这下面有一条通向海底的隐藏通道。") == []


def test_standing_gm_block_lists_unrevealed_then_empties(tmp_path):
    root = _world(tmp_path)
    _add_secret(root, "location--cafe", _judgment_secret(
        "location/cafe", "s-cafe", "柜台下压着一把旧钥匙。", "侦查成功"
    ))
    block = standing_gm_block(root)
    assert "未揭示秘密" in block and "s-cafe" in block
    _write(root / "game" / "meta" / "secret_ledger.json", {"s-cafe": {"about": "location/cafe"}})
    assert standing_gm_block(root) == ""


def test_turn_pass_adjudicates_then_guardrails_remainder(tmp_path):
    root = _world(tmp_path)
    _add_secret(root, "location--cafe", _judgment_secret(
        "location/cafe", "s-cafe", "柜台下压着一把旧钥匙,鏡子从不提起。", "侦查成功"
    ))
    reply = json.dumps(
        {"verdicts": [{"id": "s-cafe", "reveal": True, "reason": "确凿"}]}, ensure_ascii=False
    )
    factory = _CountingFactory(_StubKeeper(reply))
    # Narration BOTH satisfies the condition and quotes the hidden text: the
    # keeper reveals first, so the guardrail must NOT flag it afterwards.
    secrets_p2_turn_pass(
        root,
        player_text="我彻底搜查柜台",
        narration_text="你找到了暗格:柜台下压着一把旧钥匙,鏡子从不提起。",
        adapter_factory=factory,
    )
    assert "s-cafe" in read_ledger(root)
    assert drain_guardrail_notices(root) == []
