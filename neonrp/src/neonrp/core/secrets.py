"""Secrets overlay — deterministic "who may know what" (docs/SECRETS-DESIGN.md P1).

Secrets live OUTSIDE the entities they describe, in ``game/secrets/``, one file
per host entity. That turns field-level partitioning into PATH-level
partitioning, which the existing glob permission machinery can enforce:

- the indexer skips ``game/secrets/**`` (never retrievable by find/context),
- non-GM agents get per-file deny globs for every secret not addressed to them
  (deny-first semantics — a blanket deny could not be re-opened by audience),
- souls' scoped allow-lists never include the folder, plus an explicit deny.

Reveal is a deterministic state transition, not a prompt request: when a
machine-checkable ``revealed_when`` condition holds, the secret's ``content``
is merged back into the host entity file (``summary_hidden`` → ``summary``,
``connections_hidden`` → ``connections``, …), the event is recorded in
``game/meta/secret_ledger.json`` — inside game/, so the M17 commit DAG
versions it and rollback un-reveals — and a one-line notice is queued for the
next turn's world-agent preflight (same delivery pattern as the location
judge). Once revealed, the text is ordinary public knowledge with zero
runtime cost.

``judgment`` (free-text) conditions are the P2 keeper's job (below):
once per turn, fuzzy conditions whose HOST is relevant to the current scene
are batched into ONE LLM call; the keeper only VERDICTS — application goes
through the same merge-back + ledger machinery, marked ``adjudicated_by``.
P2 also adds the narration guardrail (§d): a standing GM prompt block listing
unrevealed secret labels, and a deterministic post-scan that flags narration
containing distinctive unrevealed-secret text via a deliver-once correction
queue (the location-judge feedback philosophy — said words can't be unsaid,
the rail keeps it from getting worse).

Worlds without a ``game/secrets/`` directory are untouched by every function
in this module (each one early-returns), so pre-secrets worlds keep
byte-for-byte behavior.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from neonrp.core.paths import get_data_dir_name, get_game_dir

SECRETS_DIRNAME = "secrets"
LEDGER_RELPATH = "meta/secret_ledger.json"
REVEALS_QUEUE_RELPATH = "meta/secret_reveals.json"

# Agents that keep full sight of game/secrets/** (the GM side of the table).
# The router/narrator id is world-specific and passed in by the caller.
GM_AGENT_IDS = {"world-agent", "game-master"}

_HIDDEN_SUFFIX = "_hidden"


@dataclass
class Secret:
    """One parsed ``game/secrets/*.json`` overlay file."""

    secret_id: str
    about: str  # host entity relpath under game/, no extension: "location/cafe-basement"
    audience: List[str]  # "gm" | "player" | "npc:<id>" | "soul:<sid>" | "agent:<id>"
    content: Dict[str, Any]
    revealed_when: List[Dict[str, Any]] = field(default_factory=list)
    rel_path: str = ""  # file path relative to root, e.g. "game/secrets/location--x.json"

    def machine_conditions(self) -> List[Dict[str, Any]]:
        return [c for c in self.revealed_when if isinstance(c, dict) and "judgment" not in c]

    def judgment_conditions(self) -> List[Dict[str, Any]]:
        return [c for c in self.revealed_when if isinstance(c, dict) and "judgment" in c]


def secrets_dir(root: Path) -> Path:
    return get_game_dir(root) / SECRETS_DIRNAME


def has_secrets(root: Path) -> bool:
    d = secrets_dir(root)
    try:
        return d.is_dir() and any(d.glob("*.json"))
    except OSError:
        return False


def load_secrets(root: Path) -> tuple[List[Secret], List[str]]:
    """Load every secret overlay file. Returns (secrets, issues).

    Malformed files are reported, never fatal — validate surfaces the issues;
    the runtime just treats a broken secret as GM-only and unrevealable
    (fail closed: a secret we can't parse is a secret nobody new learns)."""
    out: List[Secret] = []
    issues: List[str] = []
    d = secrets_dir(root)
    if not d.is_dir():
        return out, issues
    data_dir_name = get_data_dir_name(root)
    for path in sorted(d.glob("*.json")):
        rel = f"{data_dir_name}/{SECRETS_DIRNAME}/{path.name}"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            issues.append(f"{rel}: unreadable secret file ({exc})")
            continue
        if not isinstance(data, dict):
            issues.append(f"{rel}: secret file must be a JSON object")
            continue
        about = str(data.get("about") or "").strip().strip("/")
        audience = data.get("audience")
        content = data.get("content")
        if not about:
            issues.append(f"{rel}: missing 'about' (host entity relpath)")
        if not isinstance(audience, list) or not audience:
            issues.append(f"{rel}: missing/empty 'audience' list")
            audience = ["gm"]
        if not isinstance(content, dict) or not content:
            issues.append(f"{rel}: missing/empty 'content' object")
            content = {}
        bad_tokens = [
            t
            for t in audience
            if not (
                t in ("gm", "player")
                or (isinstance(t, str) and t.partition(":")[0] in ("npc", "soul", "agent") and t.partition(":")[2])
            )
        ]
        if bad_tokens:
            issues.append(f"{rel}: unknown audience token(s) {bad_tokens}")
        revealed_when = data.get("revealed_when") or []
        if not isinstance(revealed_when, list):
            issues.append(f"{rel}: 'revealed_when' must be a list")
            revealed_when = []
        out.append(
            Secret(
                secret_id=str(data.get("id") or path.stem),
                about=about,
                audience=[str(t) for t in audience],
                content=content,
                revealed_when=[c for c in revealed_when if isinstance(c, dict)],
                rel_path=rel,
            )
        )
    return out, issues


# ── Audience / permission surface ────────────────────────────────────────


def _audience_matches_agent(audience: Iterable[str], agent_id: str) -> bool:
    for token in audience:
        kind, _, ident = str(token).partition(":")
        if kind == "agent" and ident == agent_id:
            return True
        # npc:<id> matches both the bare id and the conventional npc-<id>
        # agent folder name (kagura's agents/npc-kagami ↔ game/npc/kagami).
        if kind == "npc" and ident and agent_id in (ident, f"npc-{ident}"):
            return True
    return False


def is_gm_agent(agent_id: str, *, router_agent_id: str | None = None) -> bool:
    if agent_id in GM_AGENT_IDS:
        return True
    return bool(router_agent_id) and agent_id == router_agent_id


def secrets_deny_paths(root: Path, agent_id: str, *, router_agent_id: str | None = None) -> List[str]:
    """Deny globs for this agent: every secret file whose audience does not
    include it. GM agents get none (full sight). Deny is per-FILE because the
    permission checker is deny-first — a blanket ``game/secrets/**`` deny
    could never be re-opened for an audience member.

    Worlds without secrets return [] — zero behavior change."""
    if is_gm_agent(agent_id, router_agent_id=router_agent_id):
        return []
    if not has_secrets(root):
        return []
    denied: List[str] = []
    all_secrets, _issues = load_secrets(root)
    listed = {s.rel_path for s in all_secrets}
    for s in all_secrets:
        if not _audience_matches_agent(s.audience, agent_id):
            denied.append(s.rel_path)
    # Files that failed to parse aren't in `all_secrets` — deny the whole
    # folder minus nothing in that case is impossible per-file, so fail closed
    # by denying any stray json not accounted for.
    data_dir_name = get_data_dir_name(root)
    d = secrets_dir(root)
    for path in d.glob("*.json"):
        rel = f"{data_dir_name}/{SECRETS_DIRNAME}/{path.name}"
        if rel not in listed and rel not in denied:
            denied.append(rel)
    return sorted(denied)


def is_secrets_path(rel_path: str, *, data_dir_name: str = "game") -> bool:
    rel = str(rel_path).replace("\\", "/").lstrip("./")
    return rel.startswith(f"{data_dir_name}/{SECRETS_DIRNAME}/")


# ── Machine-checkable reveal conditions ──────────────────────────────────


def _read_json(path: Path) -> Optional[Dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def _run_state(root: Path) -> Dict[str, Any]:
    return _read_json(get_game_dir(root) / "meta" / "run_state.json") or {}


def _dig(data: Dict[str, Any], dotted: str) -> Any:
    cur: Any = data
    for part in str(dotted).split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def _npc_trust(root: Path, npc_id: str) -> Optional[float]:
    game = get_game_dir(root)
    for folder in ("npc", "npcs", "character", "characters"):
        data = _read_json(game / folder / f"{npc_id}.json")
        if data is not None:
            for key in ("trust", "trust_current", "trust_initial"):
                val = data.get(key)
                if isinstance(val, (int, float)):
                    return float(val)
    return None


def _location_tokens(value: Any) -> set[str]:
    toks: set[str] = set()
    if isinstance(value, str) and value.strip():
        toks.add(value.strip())
        if "/" in value:
            toks.add(value.rsplit("/", 1)[-1])
    elif isinstance(value, dict):
        for k in ("node_id", "subnode_id", "node", "display", "id"):
            v = value.get(k)
            if isinstance(v, str) and v.strip():
                toks.add(v.strip())
    return toks


def condition_met(root: Path, cond: Dict[str, Any]) -> bool:
    """Evaluate ONE machine-checkable condition. Unknown/unevaluable → False
    (fail closed). ``judgment`` is always False here — the P2 keeper's call."""
    if "judgment" in cond:
        return False
    if "trust_gte" in cond:
        spec = cond["trust_gte"] or {}
        npc = str(spec.get("npc") or "").strip()
        try:
            value = float(spec.get("value"))
        except (TypeError, ValueError):
            return False
        if not npc:
            return False
        trust = _npc_trust(root, npc)
        return trust is not None and trust >= value
    if "flag" in cond:
        spec = cond["flag"] or {}
        key = str(spec.get("key") or "").strip()
        if not key:
            return False
        actual = _dig(_run_state(root), key)
        if "equals" in spec:
            return actual == spec["equals"]
        return bool(actual)
    if "visited" in cond:
        spec = cond["visited"] or {}
        target = str(spec.get("location") or "").strip()
        if not target:
            return False
        rs = _run_state(root)
        if target in _location_tokens(rs.get("location")):
            return True
        visited = rs.get("visited")
        if isinstance(visited, list):
            for entry in visited:
                if target in _location_tokens(entry):
                    return True
        return False
    if "item_owned" in cond:
        spec = cond["item_owned"] or {}
        item = str(spec.get("item") or "").strip()
        if not item:
            return False
        party = _run_state(root).get("party")
        blob = json.dumps(party, ensure_ascii=False) if party else ""
        return item in blob
    return False


# ── Reveal = deterministic text move + ledger + notice ──────────────────


def _ledger_path(root: Path) -> Path:
    return get_game_dir(root) / "meta" / "secret_ledger.json"


def read_ledger(root: Path) -> Dict[str, Any]:
    return _read_json(_ledger_path(root)) or {}


def _merge_content_into_host(root: Path, secret: Secret) -> bool:
    """Merge ``*_hidden`` fields into the host entity file. Returns True on
    success; False (and no ledger entry) if the host is missing/unreadable."""
    host_path = get_game_dir(root) / f"{secret.about}.json"
    host = _read_json(host_path)
    if host is None:
        return False
    for key, hidden in secret.content.items():
        base = key[: -len(_HIDDEN_SUFFIX)] if key.endswith(_HIDDEN_SUFFIX) else key
        existing = host.get(base)
        if isinstance(hidden, list):
            merged = list(existing) if isinstance(existing, list) else []
            merged.extend(v for v in hidden if v not in merged)
            host[base] = merged
        elif isinstance(hidden, dict):
            merged_d = dict(existing) if isinstance(existing, dict) else {}
            merged_d.update(hidden)
            host[base] = merged_d
        else:
            text = str(hidden)
            if isinstance(existing, str) and existing.strip():
                host[base] = f"{existing.rstrip()} {text}"
            else:
                host[base] = text
    host_path.write_text(
        json.dumps(host, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return True


def _queue_reveal_notice(root: Path, line: str) -> None:
    from neonrp.core.notes import post_note

    post_note(root, "reveal", line)


def drain_reveal_notices(root: Path) -> List[str]:
    """Deliver-once drain of queued 【秘密解锁】 lines(统一便签通道 V3)."""
    from neonrp.core.notes import drain_notes

    return drain_notes(root, "reveal", legacy_path=get_game_dir(root) / REVEALS_QUEUE_RELPATH)


def _write_ledger(root: Path, ledger: Dict[str, Any]) -> None:
    lp = _ledger_path(root)
    lp.parent.mkdir(parents=True, exist_ok=True)
    lp.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _apply_reveal(
    root: Path,
    secret: Secret,
    ledger: Dict[str, Any],
    *,
    how: Dict[str, Any],
    adjudicated_by: str | None = None,
    reason: str | None = None,
) -> bool:
    """Shared reveal application: merge-back + ledger entry + notice queue.
    Mutates ``ledger`` in place (caller persists). False if host missing."""
    if not _merge_content_into_host(root, secret):
        return False
    entry: Dict[str, Any] = {
        "about": secret.about,
        "revealed_to": ["player"],
        "turn": _run_state(root).get("turn_count"),
        "how": how,
    }
    if adjudicated_by:
        entry["adjudicated_by"] = adjudicated_by
    if reason:
        entry["reason"] = str(reason)[:200]
    ledger[secret.secret_id] = entry
    _queue_reveal_notice(
        root,
        f"[secret:{secret.secret_id}] {secret.about} 的隐藏信息已解锁"
        f"(条件 {json.dumps(how, ensure_ascii=False)});内容已并入实体,可在叙事中自然揭示",
    )
    return True


def check_and_apply_reveals(root: Path) -> List[str]:
    """Per-turn deterministic reveal pass. O(secrets); instant no-op for
    worlds without a secrets dir. Idempotent: the ledger is the source of
    truth for what has already been revealed. Returns newly revealed ids."""
    if not has_secrets(root):
        return []
    all_secrets, _issues = load_secrets(root)
    if not all_secrets:
        return []
    ledger = read_ledger(root)
    revealed_now: List[str] = []
    for secret in all_secrets:
        if secret.secret_id in ledger:
            continue
        hit = next((c for c in secret.machine_conditions() if condition_met(root, c)), None)
        if hit is None:
            continue
        if _apply_reveal(root, secret, ledger, how=hit):
            revealed_now.append(secret.secret_id)
    if revealed_now:
        _write_ledger(root, ledger)
    return revealed_now


# ── P2: keeper adjudication of fuzzy conditions (§c) ─────────────────────

logger = logging.getLogger("neonrp.secrets")

GUARDRAIL_QUEUE_RELPATH = "meta/secret_guardrail.json"
_KEEPER_BREADCRUMB = "[secrets:keeper]"
_KEEPER_SYSTEM_PROMPT = (
    "你是游戏的秘密守门人(keeper)。给你若干未揭示的秘密与其解锁条件,以及"
    "刚刚发生的回合(玩家的行动与叙事)。逐条判断:该回合是否满足了解锁条件?"
    "从严裁定——条件要求的行为必须确实发生且成立(例如「侦查成功」需要玩家确实"
    "认真侦查且叙事支持其成功),擦边、口头提及、未遂都不算。"
    '只输出 JSON,格式:{"verdicts":[{"id":"<secret id>","reveal":true|false,'
    '"reason":"一句话依据"}]}。不要输出任何其他文字。'
)

_STOP_FRAGMENT_CHARS = 8  # distinctive-substring floor for the guardrail scan


def unrevealed_secrets(root: Path) -> List[Secret]:
    if not has_secrets(root):
        return []
    all_secrets, _issues = load_secrets(root)
    if not all_secrets:
        return []
    ledger = read_ledger(root)
    return [s for s in all_secrets if s.secret_id not in ledger]


def _host_kind_id(secret: Secret) -> tuple[str, str]:
    kind, _, ident = secret.about.partition("/")
    return kind.strip(), ident.strip()


def _secret_label(secret: Secret) -> str:
    """Short one-line label: id + host + a truncated content fragment. Used in
    the GM standing block and guardrail lines — the label itself must not be a
    worse leak than the GM's existing full sight, so it is only ever shown to
    GM agents."""
    frag = ""
    for value in secret.content.values():
        if isinstance(value, str) and value.strip():
            frag = value.strip()
            break
        if isinstance(value, list):
            s = next((x for x in value if isinstance(x, str) and x.strip()), "")
            if s:
                frag = s.strip()
                break
    if len(frag) > 40:
        frag = frag[:40] + "…"
    return f"「{secret.secret_id}」({secret.about}){':' + frag if frag else ''}"


def _host_relevant(root: Path, secret: Secret, player_tokens: set[str], turn_text: str) -> bool:
    """Deterministic relevance gate: is the secret's HOST part of the current
    scene (player location / co-located npc) or explicitly touched by this
    turn's text? Conservative — irrelevant hosts never reach the keeper."""
    kind, ident = _host_kind_id(secret)
    if not ident:
        return False
    if kind in ("location", "locations", "town", "towns"):
        return ident in player_tokens or (bool(turn_text) and ident in turn_text)
    if kind in ("npc", "npcs", "character", "characters"):
        game = get_game_dir(root)
        data = _read_json(game / kind / f"{ident}.json") or {}
        loc_tokens = _location_tokens(data.get("location"))
        name = str(data.get("name") or "").strip()
        if loc_tokens & player_tokens:
            return True
        if turn_text and (ident in turn_text or (name and name in turn_text)):
            return True
        return False
    # lore / timeline / quest / anything else: only when this turn touches it.
    return bool(turn_text) and ident in turn_text


def pending_judgment_candidates(
    root: Path, *, player_tokens: set[str], turn_text: str
) -> List[Secret]:
    return [
        s
        for s in unrevealed_secrets(root)
        if s.judgment_conditions() and _host_relevant(root, s, player_tokens, turn_text)
    ]


def _reply_text(raw: Any) -> str:
    if isinstance(raw, str):
        return raw
    return str(getattr(raw, "proposal_text", None) or getattr(raw, "raw_output", None) or "")


def keeper_adjudicate(
    root: Path,
    *,
    player_text: str,
    narration_text: str,
    adapter_factory: Any,
) -> List[str]:
    """Adjudicate fuzzy ``judgment`` conditions for scene-relevant unrevealed
    secrets — at most ONE batched LLM call per turn, zero when nothing is
    relevant (or the world has no secrets / nothing happened yet). Verdicts
    apply through the shared reveal machinery, marked ``adjudicated_by``.
    Any failure (adapter, transport, unparseable reply) reveals nothing and
    never breaks the turn."""
    if not narration_text.strip():
        return []
    player_tokens = _location_tokens(_run_state(root).get("location"))
    turn_text = f"{player_text}\n{narration_text}"
    candidates = pending_judgment_candidates(root, player_tokens=player_tokens, turn_text=turn_text)
    if not candidates:
        return []
    lines: List[str] = []
    for s in candidates:
        conds = "; ".join(str(c.get("judgment") or "") for c in s.judgment_conditions())
        extra = ""
        kind, ident = _host_kind_id(s)
        if kind in ("npc", "npcs", "character", "characters"):
            trust = _npc_trust(root, ident)
            if trust is not None:
                extra = f"(当前信任值 {trust:g})"
        lines.append(f"- id: {s.secret_id} | 关于: {s.about}{extra} | 解锁条件: {conds}")
    user_prompt = (
        "本回合玩家行动:\n"
        f"{(player_text or '(无)')[:1200]}\n\n"
        "本回合叙事:\n"
        f"{narration_text[:2000]}\n\n"
        "待裁定的秘密:\n" + "\n".join(lines)
    )
    try:
        adapter = adapter_factory()
        raw = adapter.generate(_KEEPER_SYSTEM_PROMPT, user_prompt, None)
        from neonrp.core.json_repair import loads_repaired

        reply = _reply_text(raw).strip()
        if reply.startswith("```"):
            reply = reply.strip("`")
            reply = reply[reply.find("{") :] if "{" in reply else reply
        data = loads_repaired(reply)
    except Exception as exc:  # noqa: BLE001 — keeper must never break a turn
        logger.info("%s adjudication skipped: %s", _KEEPER_BREADCRUMB, exc)
        return []
    verdicts = data.get("verdicts") if isinstance(data, dict) else None
    if not isinstance(verdicts, list):
        logger.info("%s reply had no verdicts list — no reveals", _KEEPER_BREADCRUMB)
        return []
    by_id = {s.secret_id: s for s in candidates}
    ledger = read_ledger(root)
    revealed: List[str] = []
    for v in verdicts:
        if not isinstance(v, dict) or not v.get("reveal"):
            continue
        secret = by_id.get(str(v.get("id") or ""))
        if secret is None or secret.secret_id in ledger:
            continue
        how = {"judgment": "; ".join(str(c.get("judgment") or "") for c in secret.judgment_conditions())}
        if _apply_reveal(
            root, secret, ledger, how=how, adjudicated_by="keeper", reason=str(v.get("reason") or "")
        ):
            revealed.append(secret.secret_id)
    if revealed:
        _write_ledger(root, ledger)
        logger.info("%s revealed %s", _KEEPER_BREADCRUMB, revealed)
    return revealed


# ── P2: narration guardrail (§d, best-effort) ────────────────────────────


def standing_gm_block(root: Path, *, cap: int = 6) -> str:
    """Compact standing instruction for GM agents: labels of currently
    UNREVEALED secrets (in-scene hosts first). Empty string when the world has
    no secrets or everything is revealed — zero prompt cost then."""
    pending = unrevealed_secrets(root)
    if not pending:
        return ""
    player_tokens = _location_tokens(_run_state(root).get("location"))
    in_scene = [s for s in pending if _host_relevant(root, s, player_tokens, "")]
    rest = [s for s in pending if s not in in_scene]
    picked = (in_scene + rest)[:cap]
    lines = "\n".join(f"- {_secret_label(s)}" for s in picked)
    more = f"\n(另有 {len(pending) - len(picked)} 条未列出)" if len(pending) > len(picked) else ""
    return (
        "【未揭示秘密(GM 全知;不得直接叙述其内容,可铺垫暗示;"
        "等到【秘密解锁】出现后方可自然揭示)】\n" + lines + more
    )


def _guardrail_queue_path(root: Path) -> Path:
    return get_game_dir(root) / GUARDRAIL_QUEUE_RELPATH


def _distinctive_fragments(secret: Secret) -> List[str]:
    """Split content strings into punctuation-bounded fragments long enough to
    be distinctive (≥ 8 chars). Short/generic tokens never trigger the rail."""
    frags: List[str] = []

    def _collect(value: Any) -> None:
        if isinstance(value, str):
            for part in (
                value.replace("\n", "。")
                .replace(";", "。")
                .replace(";", "。")
                .replace(",", "。")
                .replace(",", "。")
                .replace("、", "。")
                .split("。")
            ):
                part = part.strip()
                if len(part) >= _STOP_FRAGMENT_CHARS:
                    frags.append(part)
        elif isinstance(value, list):
            for item in value:
                _collect(item)
        elif isinstance(value, dict):
            for item in value.values():
                _collect(item)

    for v in secret.content.values():
        _collect(v)
    return frags[:8]


def guardrail_scan(root: Path, narration_text: str) -> List[str]:
    """Deterministic post-scan: does the narration literally contain
    distinctive text of a still-unrevealed secret? On hit, queue a deliver-once
    correction line for the next GM preflight (feedback-only — narration is
    never rewritten; the location-judge philosophy). Returns flagged ids."""
    if not narration_text or not narration_text.strip():
        return []
    flagged: List[str] = []
    for secret in unrevealed_secrets(root):
        if any(frag in narration_text for frag in _distinctive_fragments(secret)):
            flagged.append(secret.secret_id)
            _queue_guardrail_notice(
                root,
                f"[secret:{secret.secret_id}] 叙述触碰了未揭示秘密 {_secret_label(secret)}"
                " —— 已出口的不再收回;后续回避展开,或引导玩家以行动正式解锁",
            )
    return flagged


def _queue_guardrail_notice(root: Path, line: str) -> None:
    from neonrp.core.notes import post_note

    post_note(root, "guardrail", line, dedupe=True)


def drain_guardrail_notices(root: Path) -> List[str]:
    """Deliver-once drain of queued 【秘密裁定】 correction lines(V3)."""
    from neonrp.core.notes import drain_notes

    return drain_notes(root, "guardrail", legacy_path=_guardrail_queue_path(root))


def secrets_p2_turn_pass(
    root: Path,
    *,
    player_text: str,
    narration_text: str,
    adapter_factory: Any,
) -> None:
    """P2 per-turn pass, run at the start of a turn against LAST turn's texts:
    keeper adjudication first (newly revealed secrets stop being 'unrevealed'),
    then the guardrail scan against what remains. Instant no-op without
    secrets; never turn-fatal."""
    if not has_secrets(root):
        return
    try:
        keeper_adjudicate(
            root,
            player_text=player_text,
            narration_text=narration_text,
            adapter_factory=adapter_factory,
        )
    except Exception:  # noqa: BLE001
        logger.info("%s pass error", _KEEPER_BREADCRUMB, exc_info=True)
    try:
        guardrail_scan(root, narration_text)
    except Exception:  # noqa: BLE001
        logger.info("[secrets:guardrail] scan error", exc_info=True)
