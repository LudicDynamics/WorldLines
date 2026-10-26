"""The judge (Jev) settings page: how the fast judge behind the planning beat is chosen, read from and written to
``~/.neonrp/config.json``. The TUI ``/settings`` page and the local web settings drawer both use this module, so the two
show and save the same thing (10-25: until now these keys were engine-only — the file or an environment variable).

Keys in the user config (an environment variable wins over each, as before):

- ``judge.mode``             ``auto`` · ``jev`` · ``proxy`` · ``llm`` · ``off``  (``NEONRP_S1_BACKEND``)
- ``models.typesafe.api_key`` the player's own Jev key, used directly        (``TYPESAFE_API_KEY``)
- ``models.judge.preset``    a model preset that judges when Jev is absent    (``NEONRP_S1_LLM_PRESET``)

``auto`` is the engine's chain: own key → Worldlines account → judge preset → none. The page never returns the key
itself, only whether one is set and a masked tail."""

from __future__ import annotations

import os
import time
from typing import Any

from neonrp.core import system_one as s1
from neonrp.core.user_config import load_user_config, save_user_config

MODES = ("auto", "jev", "proxy", "llm", "off")
MODE_ENV = "NEONRP_S1_BACKEND"
KEY_ENV = "TYPESAFE_API_KEY"
PRESET_ENV = "NEONRP_S1_LLM_PRESET"


def mask(key: str | None) -> str:
    key = (key or "").strip()
    if not key:
        return ""
    if len(key) <= 10:
        return "…" + key[-4:]
    return key[:4] + "…" + key[-4:]


def _config_key() -> str:
    models = load_user_config().get("models")
    ts = models.get("typesafe") if isinstance(models, dict) else None
    return str(ts.get("api_key") or "").strip() if isinstance(ts, dict) else ""


def _config_preset() -> str:
    models = load_user_config().get("models")
    j = models.get("judge") if isinstance(models, dict) else None
    return str(j.get("preset") or "").strip() if isinstance(j, dict) else ""


def _signed_in() -> bool:
    try:
        from neonrp.core import worldlines_auth

        return bool(worldlines_auth.status().get("signed_in"))
    except Exception:  # noqa: BLE001
        return False


def preset_choices() -> list[str]:
    """Preset ids a judge model can be picked from: every configured model entry (built-in with a key, or the user's own)."""
    try:
        from neonrp.tui.settings_flow import list_configured_entries

        return [str(e["id"]) for e in list_configured_entries()]
    except Exception:  # noqa: BLE001
        return []


def read() -> dict[str, Any]:
    """What the page shows. ``effective`` is the backend the engine would use right now (``quota`` when Jev's quota is spent);
    ``pinned_unusable`` says why a pinned mode is not the one answering (``no_key`` · ``signed_out``, else None)."""
    env_mode = os.environ.get(MODE_ENV, "").strip().lower()
    env_pinned = env_mode in MODES or env_mode == "stub"  # stub = the tests' backend; still an env pin
    mode = env_mode if env_pinned else (s1.config_mode() or "auto")
    env_key = os.environ.get(KEY_ENV, "").strip()
    cfg_key = _config_key()
    env_preset = os.environ.get(PRESET_ENV, "").strip()
    cfg_preset = _config_preset()
    try:
        unusable = s1.pinned_unusable()
    except Exception:  # noqa: BLE001
        unusable = None
    try:
        effective = s1.backend_name()
        if effective in ("jev", "proxy") and s1.quota_blocked():
            effective = "quota"
    except Exception:  # noqa: BLE001
        effective = "off"
    return {
        "mode": mode,
        "mode_source": "env" if env_pinned else ("config" if s1.config_mode() else "default"),
        "key_set": bool(env_key or cfg_key),
        "key_masked": mask(env_key or cfg_key),
        "key_source": "env" if env_key else ("config" if cfg_key else "none"),
        "llm_preset": env_preset or cfg_preset,
        "llm_preset_source": "env" if env_preset else ("config" if cfg_preset else "none"),
        "effective": effective,
        "pinned_unusable": unusable,
        "signed_in": _signed_in(),
        "presets": preset_choices(),
    }


def save(
    *,
    mode: str | None = None,
    api_key: str | None = None,
    clear_key: bool = False,
    llm_preset: str | None = None,
    clear_preset: bool = False,
) -> dict[str, Any]:
    """Write the given fields to the user config (only those passed) and return :func:`read`. A bad mode raises ValueError."""
    data = load_user_config()
    if mode is not None:
        m = str(mode).strip().lower()
        if m not in MODES:
            raise ValueError(f"mode must be one of {', '.join(MODES)}")
        judge = data.get("judge") if isinstance(data.get("judge"), dict) else {}
        if m == "auto":
            judge.pop("mode", None)
        else:
            judge["mode"] = m
        if judge:
            data["judge"] = judge
        else:
            data.pop("judge", None)
    models = data.get("models") if isinstance(data.get("models"), dict) else {}
    if clear_key:
        ts = models.get("typesafe") if isinstance(models.get("typesafe"), dict) else {}
        ts.pop("api_key", None)
        if ts:
            models["typesafe"] = ts
        else:
            models.pop("typesafe", None)
    elif api_key is not None and api_key.strip():
        ts = models.get("typesafe") if isinstance(models.get("typesafe"), dict) else {}
        ts["api_key"] = api_key.strip()
        models["typesafe"] = ts
    if clear_preset or (llm_preset is not None and not str(llm_preset).strip()):
        j = models.get("judge") if isinstance(models.get("judge"), dict) else {}
        j.pop("preset", None)
        if j:
            models["judge"] = j
        else:
            models.pop("judge", None)
    elif llm_preset is not None:
        j = models.get("judge") if isinstance(models.get("judge"), dict) else {}
        j["preset"] = str(llm_preset).strip()
        models["judge"] = j
    if models or "models" in data:
        data["models"] = models
    save_user_config(data)
    return read()


_PROBE_STATE = {"scene": "Two people haggle over a basket of apples at the market. Hearing the final price, the buyer says: fine, that price, deal."}


def probe(timeout: float = 8.0) -> dict[str, Any]:
    """Ask the active backend one yes/no question. ``{"ok", "backend", "ms", "error"?, "yes"?}`` — ``ok`` means the backend
    answered; ``yes`` is its probability that the buyer agreed (a sane judge says high)."""
    backend = s1.backend_name()
    if backend == "off":
        return {"ok": False, "backend": backend, "ms": 0, "error": "off"}
    q = {"agreed": s1.noul("Has the buyer agreed to the deal?")}
    t0 = time.monotonic()
    answers = s1._ask_one(backend, _PROBE_STATE, q, timeout=timeout, retries=0)  # noqa: SLF001 — the primary backend only, no fallback chain
    ms = round((time.monotonic() - t0) * 1000)
    last = s1.last_call()
    if answers is None or "agreed" not in answers:
        return {"ok": False, "backend": backend, "ms": ms, "error": str(last.get("error") or "no answer")[:200]}
    return {"ok": True, "backend": backend, "ms": ms, "yes": round(answers["agreed"].yes, 2), "model": last.get("model")}
