"""A stand-in external map SDK for tests: refuses the inn, clamps the guild to main street,
and records what it was asked to land. Referenced from actions.json as ``fake_map_sdk:judge``."""
from __future__ import annotations

from typing import Any

from neonrp.core.handlers import Verdict

landed: list[tuple[str, str]] = []


def judge(root: Any, reg: Any, who: str, cur: str, to: str) -> Verdict:
    if to.endswith("inn"):
        return Verdict(False, None, reason="the SDK says the inn is closed today", allowed=["T001/main_street(主街)"])
    if to.endswith("guild"):
        return Verdict(True, "T001/main_street", clamped=True, reason="SDK: the guild is a two-beat walk")
    return Verdict(True, to)


def move(root: Any, reg: Any, who: str, to: str) -> bool:
    landed.append((who, to))
    return True


def contract(root: Any, reg: Any, structured: str = "together") -> str:
    """A template's own world-side prompt (a werewolf judge, say) — the engine just uses it."""
    return "你是狼人杀的法官。只输出一个 JSON 对象 {\"narration\": \"<播报>\", \"ops\": []}"


def observe(root: Any, iid: str) -> str:
    return f"[桌面] 你是 {iid},天亮了。"


def everyone(root: Any, reg: Any, iid: str) -> bool:
    """Werewolf-style participation: every soul is at the table, wherever the map says it is."""
    return True


# ── a template op for the JSON-pack test: `inspect {who, target}` ─────────────
inspected: list[tuple[str, str]] = []


def judge_inspect(root: Any, reg: Any, op: dict[str, Any]) -> Verdict:
    tid = reg.resolve(str(op.get("target") or ""))
    if tid is None:
        return Verdict(False, reason=f"nothing called {op.get('target')!r} here", allowed=["T001/inn(河灯旅店)"])
    return Verdict(True, data={"target": tid})


def inspect(root: Any, reg: Any, op: dict[str, Any], res: Any) -> dict[str, Any]:
    inspected.append((str(op.get("who")), str(op.get("target"))))
    return {"found": "一枚旧铜币"}
