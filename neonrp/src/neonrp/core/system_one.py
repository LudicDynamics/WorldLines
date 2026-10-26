"""System One adapter — typed fast judgments (TypeSafe AI "Jev") for the turn.

Experiment branch ``exp/jev-system-one`` (先在隔离环境做实验,
大幅提速再迁移). The engine asks *judgments* here — yes/no, pick one, score —
and keeps the LLM for *generation*. Everything is behind flags and every
caller has a no-System-One fallback, so an outage equals today's behaviour.

    from neonrp.core.system_one import ask, noul, choice, score
    answers = ask({"text": ...}, {"urgent": noul("Does this express urgency?")})
    answers["urgent"].value  # 0.0–1.0

Backends (``NEONRP_S1_BACKEND``):
- ``jev``  — https://api.typesafe.ai/v1/systemone, ``TYPESAFE_API_KEY`` (env
  or ``~/.neonrp/config.json`` → ``models.typesafe.api_key``). Never logged.
- ``stub`` — deterministic, offline: a caller-installed function (tests /
  experiments without a key) or, by default, "unsure" answers.
- ``off``  — :func:`ask` returns ``None`` immediately.

Unset ⇒ ``jev`` when a key is present, else ``off``.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger("neonrp")

JEV_URL = "https://api.typesafe.ai/v1/systemone"
DEFAULT_MODEL = "jev-latest"
DEFAULT_TIMEOUT = 3.0
CACHE_TTL_S = 300.0


@dataclass(frozen=True)
class Q:
    """One typed question. ``criteria``: None/str (noul), dict (choice), list (score)."""

    type: str
    instructions: str
    criteria: Any = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"type": self.type, "instructions": self.instructions}
        if self.criteria is None:
            return d
        if self.type == "noul" and not isinstance(self.criteria, dict):
            # Jev's noul takes no free-text criteria (422); fold the hint into the question
            d["instructions"] = f"{self.instructions}(判据:{self.criteria})"
            return d
        d["criteria"] = self.criteria
        return d

def noul(instructions: str, criteria: str | None = None) -> Q:
    return Q("noul", instructions, criteria)


def choice(instructions: str, criteria: dict[str, str]) -> Q:
    if len(criteria) < 2:
        raise ValueError("choice needs at least two options")
    return Q("choice", instructions, dict(criteria))


def score(instructions: str, criteria: list[str]) -> Q:
    if len(criteria) < 2:
        raise ValueError("score needs at least two levels")
    return Q("score", instructions, list(criteria))


@dataclass
class Answer:
    type: str
    value: Any  # float for noul/score, str for choice
    probabilities: dict[str, float] = field(default_factory=dict)
    confidence: float = 1.0

    @property
    def yes(self) -> float:
        """noul convenience: probability of yes."""
        try:
            return float(self.value)
        except (TypeError, ValueError):
            return 0.0

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type, "value": self.value, "probabilities": dict(self.probabilities), "confidence": self.confidence}


# ── key / backend selection ─────────────────────────────────────────────


def _user_cfg() -> dict[str, Any]:
    """The user config, through the one resolver every reader uses (``core.user_config``; tests point it at a tmp dir)."""
    from neonrp.core import user_config

    cfg = user_config.load_user_config()
    return cfg if isinstance(cfg, dict) else {}


def api_key() -> str | None:
    key = os.environ.get("TYPESAFE_API_KEY", "").strip()
    if key:
        return key
    models = _user_cfg().get("models") or {}
    ts = models.get("typesafe") if isinstance(models, dict) else None
    if isinstance(ts, dict) and isinstance(ts.get("api_key"), str) and ts["api_key"].strip():
        return ts["api_key"].strip()
    return None


PROXY_URL_DEFAULT = "https://ai.worldlines.gg/v1/systemone"  # 10-01 (identity reply): the new service; the old Hub keeps api.worldlines.gg/api/v1/systemone via NEONRP_S1_PROXY_URL
QUOTA_COOLDOWN_S = float(os.environ.get("NEONRP_S1_QUOTA_COOLDOWN", "300"))  # after a 429 kind=systemone, skip Jev this long
_QUOTA: dict[str, float] = {"until": 0.0}


def proxy_url() -> str:
    return os.environ.get("NEONRP_S1_PROXY_URL", "").strip() or PROXY_URL_DEFAULT


def proxy_token() -> str | None:
    """The worldlines session token (Supabase auth) — the online default: users never hold a Jev key."""
    tok = os.environ.get("HUB_API_TOKEN", "").strip()
    if tok:
        return tok
    from neonrp.core import worldlines_auth

    wl = worldlines_auth.access_token()  # a PAT (WORLDLINES_API_KEY) or the connect session
    if wl:
        return wl
    hub = _user_cfg().get("hub") or {}
    if isinstance(hub, dict) and isinstance(hub.get("api_token"), str) and hub["api_token"].strip():
        return hub["api_token"].strip()
    return None


LLM_ADAPTER_FACTORY: Callable[[], Any] | None = None  # test seam / custom judge model


def llm_judge_preset() -> str | None:
    """A configured judging LLM (a small local model via an OpenAI-compatible
    preset, or the play provider): ``NEONRP_S1_LLM_PRESET`` or
    ``~/.neonrp/config.json models.judge.preset``. Present ⇒ backend ``llm``
    is in the auto chain after proxy and before ``off``."""
    raw = os.environ.get("NEONRP_S1_LLM_PRESET", "").strip()
    if raw:
        return raw
    cfg = _user_cfg()
    j = cfg["models"].get("judge") if isinstance(cfg.get("models"), dict) else None
    if isinstance(j, dict) and isinstance(j.get("preset"), str) and j["preset"].strip():
        return j["preset"].strip()
    return None


def config_mode() -> str | None:
    """``judge.mode`` in the user config (the settings page's pick, 10-25): jev · proxy · llm · off, or None
    for auto / unset. ``NEONRP_S1_BACKEND`` still wins (see :func:`backend_name`)."""
    j = _user_cfg().get("judge")
    m = str(j.get("mode") or "").strip().lower() if isinstance(j, dict) else ""
    return m if m in ("jev", "proxy", "llm", "off") else None


def _pinned() -> str | None:
    raw = os.environ.get("NEONRP_S1_BACKEND", "").strip().lower()
    if raw in ("jev", "proxy", "llm", "stub", "off"):
        return raw
    return config_mode()


def pinned_unusable() -> str | None:
    """Why the pinned backend (``NEONRP_S1_BACKEND`` / ``judge.mode``) cannot answer: ``no_key`` (Jev without a key) ·
    ``signed_out`` (the proxy without a Worldlines session) · None (usable, or nothing pinned)."""
    pinned = _pinned()
    if pinned == "jev" and not api_key():
        return "no_key"
    if pinned == "proxy" and not proxy_token():
        return "signed_out"
    return None


def backend_name() -> str:
    """``jev`` (own key, direct) · ``proxy`` (our API, Supabase token) · ``stub`` · ``off``.

    Priority when unset: own key → proxy token → off. ``off`` must always be a
    complete engine (every Jev site has a deterministic fallback) — the local
    no-Jev build is this mode, not a different code path. ``NEONRP_S1_BACKEND``
    pins it; else the settings page's ``judge.mode`` (:func:`config_mode`). A pin that cannot answer
    (:func:`pinned_unusable`) is not tried: the LLM judge when one is set, else ``off``.
    """
    pinned = _pinned()
    if pinned:
        if not pinned_unusable():
            return pinned
        # pinned to Jev with no key / the proxy signed out: no doomed call — the path a failed Jev call takes
        return "llm" if LLM_ADAPTER_FACTORY is not None or fallback_judge_preset() else "off"
    if api_key():
        return "jev"
    if proxy_token():
        return "proxy"
    if llm_judge_preset() or LLM_ADAPTER_FACTORY is not None:
        return "llm"
    return "off"


def available() -> bool:
    return backend_name() != "off"


def fast_judge_available() -> bool:
    """A sub-second judge will answer (Jev direct or the proxy, quota not spent) — or a test stub. Anything else
    (llm / off) is slow or absent, and the engine keeps judgments off the critical path (10-01)."""
    b = backend_name()
    return b == "stub" or (b in ("jev", "proxy") and not quota_blocked())


# ── stub backend (offline) ───────────────────────────────────────────────

StubFn = Callable[[Any, dict[str, Q]], dict[str, Answer]]
_STUB: dict[str, StubFn | None] = {"fn": None}


def install_stub(fn: StubFn | None) -> None:
    """Tests / offline experiments: answer questions with ``fn``."""
    _STUB["fn"] = fn


def _unsure(questions: dict[str, Q]) -> dict[str, Answer]:
    out: dict[str, Answer] = {}
    for qid, q in questions.items():
        if q.type == "noul":
            out[qid] = Answer("noul", 0.5, {}, 0.0)
        elif q.type == "choice":
            opts = list(q.criteria.keys())
            out[qid] = Answer("choice", opts[0], {o: 1.0 / len(opts) for o in opts}, 0.0)
        else:
            n = len(q.criteria)
            out[qid] = Answer("score", (n - 1) / 2.0, {str(i): 1.0 / n for i in range(n)}, 0.0)
    return out


# ── Jev backend ─────────────────────────────────────────────────────────


def _parse_answer(qid: str, q: Q, raw: Any) -> Answer:
    if not isinstance(raw, dict):
        raise ValueError(f"answer {qid}: not an object")
    probs = raw.get("probabilities") if isinstance(raw.get("probabilities"), dict) else {}
    conf = raw.get("confidence")
    try:
        conf_f = float(conf) if conf is not None else 1.0
    except (TypeError, ValueError):
        conf_f = 1.0
    if q.type == "noul":
        p = raw.get("noul")
        if p is None:
            p = raw.get("value", raw.get("probability"))
        val = float(p)
        # A noul carries no confidence field: how far from 0.5 it sits is one.
        return Answer("noul", val, {"yes": val, "no": 1.0 - val}, conf_f if conf is not None else abs(val - 0.5) * 2.0)
    if q.type == "choice":
        chosen = raw.get("choice") or raw.get("value")
        if chosen is None and probs:
            chosen = max(probs.items(), key=lambda kv: kv[1])[0]
        return Answer("choice", str(chosen), {str(k): float(v) for k, v in probs.items()}, conf_f)
    val = raw.get("score")
    if val is None:
        val = raw.get("value")
    return Answer("score", float(val), {str(k): float(v) for k, v in probs.items()}, conf_f)


_LLM_SYSTEM = (
    "你是判断器。对给定 state 回答每一道题,只输出一个 JSON 对象,键 = 题号。"
    "noul 题答 {\"noul\": 0..1(是的概率), \"confidence\": 0..1};choice 题答 {\"choice\": <选项键>, \"probabilities\": {选项: 0..1}, \"confidence\": 0..1};"
    "score 题答 {\"score\": <数>, \"confidence\": 0..1}。不要解释。"
)


def fallback_judge_preset() -> str | None:
    """The judge a failed Jev call falls back to (「Jev 不行就用 LLM 小模型做判断」):
    ``NEONRP_S1_LLM_PRESET`` / ``models.judge.preset`` (put the small model here), else the first of
    ``NEONRP_S1_FALLBACK_PRESETS`` (default ``deepseek``) that exists in ``~/.neonrp/config.json`` models.
    ``NEONRP_S1_LLM_FALLBACK=0`` turns the middle step off (Jev → deterministic, the old chain)."""
    if os.environ.get("NEONRP_S1_LLM_FALLBACK", "1").strip() in ("0", "false", "off"):
        return None
    p = llm_judge_preset()
    if p:
        return p
    models = _user_cfg().get("models") or {}
    for cand in (x.strip() for x in os.environ.get("NEONRP_S1_FALLBACK_PRESETS", "deepseek").split(",")):
        if cand and isinstance(models, dict) and cand in models:
            return cand
    return None


def _llm_adapter() -> Any:
    if LLM_ADAPTER_FACTORY is not None:
        return LLM_ADAPTER_FACTORY()
    from neonrp.core.hub_publish import adapter_for_preset

    # a preset id from ~/.neonrp/config.json models.* (deepseek / qwen / a local
    # OpenAI-compatible endpoint) — the same resolver build mode uses.
    return adapter_for_preset(llm_judge_preset() or fallback_judge_preset())


def own_model_judge(root: Path | None) -> bool:
    """No Jev, no proxy, no judging preset — but the run has its own model: the planning beat asks that model its one
    question (10-24: deepseek alone, not signed in, the host kept handing the choice back because nothing could
    say the talk was settled). ``turn.plan_loop_own_judge`` (default on). Only the planning beat passes its root here: the
    roster plan's hundreds of questions stay off (fast_judge_available), as before."""
    if root is None or backend_name() != "off":
        return False
    try:
        from neonrp.core import engine_config

        return bool(engine_config.get(Path(root), "turn.plan_loop_own_judge", True))
    except Exception:  # noqa: BLE001
        return False


def _run_adapter(root: Path) -> Any:
    from neonrp.core.turn_v3 import _adapter

    return _adapter(Path(root), None)


def _ask_llm(state: Any, questions: dict[str, Q], adapter: Any = None) -> dict[str, Any]:
    """The judging-LLM fallback: same questions, same answer shape, any model — a small local one included."""
    from neonrp.core.llm import Message

    body = json.dumps({"state": state, "questions": {k: q.to_dict() for k, q in questions.items()}}, ensure_ascii=False)
    res = (adapter if adapter is not None else _llm_adapter()).chat([Message(role="system", content=_LLM_SYSTEM), Message(role="user", content=body)])
    text = (getattr(getattr(res, "message", None), "content", None) or "").strip()
    i, j = text.find("{"), text.rfind("}")
    if i < 0 or j <= i:
        raise RuntimeError("judge llm returned no JSON")
    parsed = json.loads(text[i : j + 1])
    answers = parsed.get("answers") if isinstance(parsed.get("answers"), dict) else parsed
    for raw in answers.values():  # tolerate "yes" / "p" spellings for a noul
        if isinstance(raw, dict) and "noul" not in raw and "probability" not in raw and "value" not in raw:
            for k in ("yes", "p", "prob"):
                if k in raw:
                    raw["noul"] = raw[k]
                    break
    return {"answers": answers}


def endpoint() -> tuple[str, str | None]:
    """(url, bearer) for the active backend: direct Jev or the worldlines proxy."""
    if backend_name() == "proxy":
        return proxy_url(), proxy_token()
    return JEV_URL, api_key()


def _post_jev(state: Any, questions: dict[str, Q], *, model: str, timeout: float) -> dict[str, Any]:
    url, key = endpoint()
    if not key:
        raise RuntimeError("no TYPESAFE_API_KEY / HUB_API_TOKEN")
    body = json.dumps({"state": state, "model": model, "questions": {k: q.to_dict() for k, q in questions.items()}}, ensure_ascii=False).encode("utf-8")
    from neonrp.core import request_ids, worldlines_auth

    hdrs = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    if worldlines_auth.is_worldlines(url):
        hdrs.update({**worldlines_auth.headers(), **worldlines_auth.client_header(), **worldlines_auth.world_header()})
    req = urllib.request.Request(url, data=body, headers=hdrs, method="POST")
    release = None
    if worldlines_auth.is_worldlines(url):
        # one of the account's open-request slots, shared with chat (core/wl_slots): System One waits in line for at most
        # one of them, no longer than its own timeout — then this question takes the no-Jev path instead of a 429
        from neonrp.core import wl_slots

        t_wait = time.monotonic()
        release = wl_slots.acquire("s1", timeout)
        if release is None:
            raise SlotBusy("no free Worldlines slot")
        timeout = max(0.5, timeout - (time.monotonic() - t_wait))
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            request_ids.add(resp.headers.get("x-request-id"), kind="systemone", model=model)
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        # keep the server's explanation (422 = a malformed question) for the log
        raw = ""
        try:
            raw = exc.read().decode("utf-8", "replace")[:8192]
        except Exception:  # noqa: BLE001
            pass
        body = raw[:300]
        try:
            request_ids.add(exc.headers.get("x-request-id") if exc.headers else None, kind="systemone", status=exc.code)
        except Exception:  # noqa: BLE001
            pass
        if exc.code == 429 and '"systemone"' in body:  # System One's own quota is spent: not a transient 429
            raise QuotaExceeded(body) from None
        from neonrp.core import billing_stop

        stop = billing_stop.remember(billing_stop.from_body(exc.code, raw))
        if stop:  # the wallet is empty / today's claim pending: same no-Jev path (after one claim + resend, _ask_one)
            raise QuotaExceeded(body, stop=stop) from None
        raise urllib.error.HTTPError(exc.url, exc.code, f"{exc.reason}: {body}", exc.hdrs, None) from None
    finally:
        if release is not None:
            release()


class SlotBusy(RuntimeError):
    """Every Worldlines slot stayed taken (core/wl_slots) for this question's whole timeout."""


def _retry_after(exc: Any, default: float) -> float:
    try:
        v = exc.headers.get("Retry-After") if exc.headers else None
        return min(10.0, max(0.0, float(v))) if v is not None else default
    except (AttributeError, TypeError, ValueError):
        return default


class QuotaExceeded(RuntimeError):
    """429 quota_exceeded, kind=systemone — the account's Jev allowance is used up — or a wallet refusal (402
    insufficient_credits / claim_required, core/billing_stop.py); callers take the no-Jev path."""

    def __init__(self, *args: Any, stop: Any = None) -> None:
        super().__init__(*args)
        self.stop = stop


def quota_blocked() -> bool:
    return time.monotonic() < _QUOTA["until"]


# ── cache + log ─────────────────────────────────────────────────────────

_CACHE: dict[str, tuple[float, dict[str, Answer]]] = {}
_CACHE_LOCK = threading.Lock()
_LAST_CALL: dict[str, Any] = {}


def _cache_key(state: Any, questions: dict[str, Q], model: str) -> str:
    h = hashlib.sha256()
    h.update(json.dumps(state, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8"))
    h.update(json.dumps({k: q.to_dict() for k, q in sorted(questions.items())}, ensure_ascii=False, sort_keys=True).encode("utf-8"))
    h.update(model.encode("utf-8"))
    return h.hexdigest()


def _brief_answers(answers: Any) -> dict[str, Any]:
    """Each answer as its value (a noul's yes-probability, a choice's pick) — enough to read back why a gate did or did
    not open (10-15: the planning judges' scores were nowhere to be found)."""
    out: dict[str, Any] = {}
    for k, a in (answers or {}).items():
        v = getattr(a, "value", a)
        out[k] = round(v, 3) if isinstance(v, float) else v
    return out


def _log(log_dir: Path | None, record: dict[str, Any]) -> None:
    if log_dir is None:
        return
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        with (log_dir / "system_one.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        pass


def last_call() -> dict[str, Any]:
    """Telemetry of the most recent :func:`ask` (backend, ms, usage, cached, error)."""
    return dict(_LAST_CALL)


def ask(
    state: Any,
    questions: dict[str, Q],
    *,
    timeout: float = DEFAULT_TIMEOUT,
    model: str = DEFAULT_MODEL,
    log_dir: Path | None = None,
    retries: int = 1,
    own_model_root: Path | None = None,
) -> dict[str, Answer] | None:
    """Ask every question about ``state`` in one call. Three steps: Jev / proxy → an LLM judge with the
    same questions and answer shape (``fallback_judge_preset``, a small model) → ``None``, and the caller's
    deterministic fallback. ``last_call()["fallback"] == "llm"`` when the middle step answered.
    ``own_model_root``: with no judge at all (backend ``off``) the run's own model answers instead
    (:func:`own_model_judge`; ``last_call()["fallback"] == "own-model"``)."""
    backend = backend_name()
    answers = _ask_one(backend, state, questions, timeout=timeout, model=model, log_dir=log_dir, retries=retries)
    if answers is None and backend == "off" and questions and own_model_judge(own_model_root):
        try:
            ad = _run_adapter(own_model_root)  # type: ignore[arg-type]
        except Exception as exc:  # noqa: BLE001 — no model for this run: the caller's deterministic path
            _LAST_CALL.update({"fallback": "none", "own_error": str(exc)[:200]})
            return None
        answers = _ask_one("llm", state, questions, timeout=timeout, model=model, log_dir=log_dir, retries=0, adapter=ad)
        _LAST_CALL["fallback"] = "own-model" if answers is not None else "none"
        return answers
    if answers is not None or backend not in ("jev", "proxy") or not questions:
        return answers
    if LLM_ADAPTER_FACTORY is None and not fallback_judge_preset():
        return None
    first = dict(_LAST_CALL)
    answers = _ask_one("llm", state, questions, timeout=timeout, model=model, log_dir=log_dir, retries=0)
    _LAST_CALL.update({"fallback": "llm" if answers is not None else (first.get("fallback") or "none"),
                       "primary_error": first.get("error"), "primary_ms": first.get("ms")})
    if answers is None and first.get("fallback") == "quota":
        _LAST_CALL["fallback"] = "quota"  # nothing answered: the caller's deterministic path, as before
    return answers


def _ask_one(
    backend: str,
    state: Any,
    questions: dict[str, Q],
    *,
    timeout: float = DEFAULT_TIMEOUT,
    model: str = DEFAULT_MODEL,
    log_dir: Path | None = None,
    retries: int = 1,
    adapter: Any = None,
) -> dict[str, Answer] | None:
    if not questions:
        return {}
    t0 = time.monotonic()
    rec: dict[str, Any] = {"ts": time.time(), "backend": backend, "questions": sorted(questions), "n": len(questions)}
    if backend == "off":
        _LAST_CALL.clear()
        _LAST_CALL.update({**rec, "ms": 0, "ok": False, "error": "off"})
        return None
    if backend == "stub":
        fn = _STUB["fn"]
        try:
            answers = fn(state, questions) if fn is not None else _unsure(questions)
        except Exception as exc:  # noqa: BLE001
            _LAST_CALL.clear()
            _LAST_CALL.update({**rec, "ms": 0, "ok": False, "error": str(exc)[:200]})
            return None
        for qid in questions:
            answers.setdefault(qid, _unsure({qid: questions[qid]})[qid])
        _LAST_CALL.clear()
        _LAST_CALL.update({**rec, "ms": round((time.monotonic() - t0) * 1000, 1), "ok": True, "cached": False})
        _log(log_dir, {**rec, "ms": round((time.monotonic() - t0) * 1000, 1), "ok": True, "answers": _brief_answers(answers)})
        return answers

    from neonrp.core import beat_budget

    if backend in ("jev", "proxy", "llm") and beat_budget.expired():  # the beat is over: the caller's no-Jev path, no call
        beat_budget.note("system_one")
        _LAST_CALL.clear()
        _LAST_CALL.update({**rec, "ms": 0, "ok": False, "error": "beat timeout"})
        return None
    _left = beat_budget.remaining()
    if _left is not None:
        timeout = max(0.5, min(timeout, _left))
    if backend in ("jev", "proxy") and quota_blocked():  # quota spent: the no-Jev judgment path, no network call
        _LAST_CALL.clear()
        _LAST_CALL.update({**rec, "ms": 0, "ok": False, "error": "quota", "fallback": "quota"})
        return None
    key = _cache_key(state, questions, model)
    with _CACHE_LOCK:
        hit = _CACHE.get(key)
        if hit and time.monotonic() - hit[0] < CACHE_TTL_S:
            _LAST_CALL.clear()
            _LAST_CALL.update({**rec, "ms": 0, "ok": True, "cached": True})
            cached = dict(hit[1])
    if hit and time.monotonic() - hit[0] < CACHE_TTL_S:
        _log(log_dir, {**rec, "ms": 0, "ok": True, "cached": True, "answers": _brief_answers(cached)})
        return cached
    attempt = 0
    while True:
        try:
            data = _ask_llm(state, questions, adapter) if backend == "llm" else _post_jev(state, questions, model=model, timeout=timeout)
            answers: dict[str, Answer] = {}
            raw_answers = data.get("answers") if isinstance(data.get("answers"), dict) else data
            for qid, q in questions.items():
                if qid in raw_answers:
                    answers[qid] = _parse_answer(qid, q, raw_answers[qid])
            usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
            ms = round((time.monotonic() - t0) * 1000, 1)
            with _CACHE_LOCK:
                _CACHE[key] = (time.monotonic(), dict(answers))
            _LAST_CALL.clear()
            _LAST_CALL.update({**rec, "ms": ms, "ok": True, "cached": False, "usage": usage, "model": data.get("model", model)})
            _log(log_dir, {**rec, "ms": ms, "ok": True, "usage": usage, "answers": _brief_answers(answers)})
            return answers
        except QuotaExceeded as qe:
            from neonrp.core import wl_claims

            if attempt == 0 and backend == "proxy" and wl_claims.claimable(qe.stop) and wl_claims.recover(qe.stop):
                # 10-25: a new account's first Jev call is 402 claim_required — claim, wait out ai's 2 s refusal cache,
                # ask once more when the beat has the time; otherwise only a short pause before the next question tries
                _left = beat_budget.remaining()
                if _left is None or _left > wl_claims.RESEND_AFTER_S + timeout:
                    attempt += 1
                    time.sleep(wl_claims.RESEND_AFTER_S)
                    continue
                _QUOTA["until"] = time.monotonic() + wl_claims.RESEND_AFTER_S
                _LAST_CALL.clear()
                _LAST_CALL.update({**rec, "ms": round((time.monotonic() - t0) * 1000, 1), "ok": False, "error": "claimed", "fallback": "quota"})
                return None
            _QUOTA["until"] = time.monotonic() + QUOTA_COOLDOWN_S
            ms = round((time.monotonic() - t0) * 1000, 1)
            _LAST_CALL.clear()
            _LAST_CALL.update({**rec, "ms": ms, "ok": False, "error": "quota", "fallback": "quota"})
            _log(log_dir, {**rec, "ms": ms, "ok": False, "error": "quota"})
            logger.info("system one quota spent: no-Jev judgments for %.0fs", QUOTA_COOLDOWN_S)
            return None
        except urllib.error.HTTPError as exc:
            status = exc.code
            if status in (429, 529) and attempt < retries:
                wait = _retry_after(exc, 0.5 * (attempt + 1))  # 429 concurrency_limit: as long as the server asks
                _left = beat_budget.remaining()
                if _left is None or _left > wait + 0.5:
                    attempt += 1
                    time.sleep(wait)
                    continue
            err = f"http {status}: {str(getattr(exc, 'reason', ''))[:200]}"
        except Exception as exc:  # noqa: BLE001 — never let a judgment break a turn
            err = str(exc)[:200]
        ms = round((time.monotonic() - t0) * 1000, 1)
        _LAST_CALL.clear()
        _LAST_CALL.update({**rec, "ms": ms, "ok": False, "error": err})
        _log(log_dir, {**rec, "ms": ms, "ok": False, "error": err})
        logger.debug("system one ask failed: %s", err)
        return None


def confidence_ok(ans: Answer | None, threshold: float | None = None) -> bool:
    if ans is None:
        return False
    thr = threshold if threshold is not None else float(os.environ.get("NEONRP_S1_CONFIDENCE", "0.7") or 0.7)
    return float(ans.confidence) >= thr
