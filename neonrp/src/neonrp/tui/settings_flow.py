"""Shared settings flow used by both WorldLines launcher and NeonRP TUI.

Instead of duplicating the "pick a model / add a new one / test it" wizard in
two places, both the launcher and the main TUI push screens built from here.

The flow is a stateless collection of helpers; it does not own any
long-lived widgets. Each entry point receives the host App so it can call
`push_screen` / `call_later` with correct context.
"""

from __future__ import annotations

import json
import re
from typing import Any, Callable

from neonrp.presets import (
    PRESETS,
    PROVIDER_TYPES,
    _USER_CONFIG_PATH,
    _load_user_config_models,
    _save_key_to_user_config,
    fetch_openrouter_models,
    get_create_provider,
    get_provider_type,
    resolve_creation_provider,
    set_create_provider,
    test_preset,
)
from neonrp.tui.i18n import get_message

ENTRY_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

def _worldlines_signed_in() -> bool:
    try:
        from neonrp.core import worldlines_auth

        return bool(worldlines_auth.status()["signed_in"])
    except Exception:  # noqa: BLE001
        return False


def list_configured_entries() -> list[dict[str, Any]]:
    """Return every configured model entry the user has set up.

    Sources, in this order:
    - Built-in PRESETS where a real API key resolves (env or user config)
    - User-config `~/.neonrp/config.json.models.*` custom entries
    """
    import os

    result: list[dict[str, Any]] = []

    user_models = _load_user_config_models()

    for preset_id, info in PRESETS.items():
        env_key = os.environ.get(info.get("api_key_env", "") or "", "").strip()
        user_key = str((user_models.get(preset_id) or {}).get("api_key", "") or "").strip()
        has_key = bool(env_key or user_key) or (preset_id == "worldlines" and _worldlines_signed_in())
        if not has_key:
            continue
        entry = {
            "id": preset_id,
            "provider": info.get("provider", ""),
            "model": (user_models.get(preset_id) or {}).get("model", info.get("model", "")),
            "source": "builtin",
            "has_key": True,
        }
        result.append(entry)

    for mid, data in user_models.items():
        if mid in PRESETS or mid == "stub":
            continue
        result.append({
            "id": mid,
            "provider": data.get("provider", "openai"),
            "model": data.get("model", ""),
            "source": "custom",
            "has_key": bool(data.get("api_key")),
        })

    # De-dup by id, preserving order.
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for item in result:
        if item["id"] in seen:
            continue
        seen.add(item["id"])
        deduped.append(item)
    return deduped


def save_custom_entry(entry_id: str, data: dict[str, Any]) -> None:
    """Overwrite `~/.neonrp/config.json.models.<entry_id>` with `data`."""
    if _USER_CONFIG_PATH.exists():
        cfg = json.loads(_USER_CONFIG_PATH.read_text(encoding="utf-8"))
    else:
        cfg = {}
    models = cfg.setdefault("models", {})
    models[entry_id] = data
    _USER_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    _USER_CONFIG_PATH.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")


def set_entry_model(entry_id: str, model: str) -> None:
    """Set/override the model name for a config entry (built-in or custom),
    without touching its key. Shared by the TUI entry-detail「edit model」and
    the web settings API. Raises ValueError on empty input."""
    entry_id = (entry_id or "").strip()
    model = (model or "").strip()
    if not entry_id:
        raise ValueError("entry id is required")
    if not model:
        raise ValueError("model is required")
    cfg = json.loads(_USER_CONFIG_PATH.read_text(encoding="utf-8")) if _USER_CONFIG_PATH.exists() else {}
    models = cfg.setdefault("models", {})
    entry = models.setdefault(entry_id, {})
    entry["model"] = model
    _USER_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    _USER_CONFIG_PATH.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")


def delete_entry(entry_id: str) -> None:
    if not _USER_CONFIG_PATH.exists():
        return
    cfg = json.loads(_USER_CONFIG_PATH.read_text(encoding="utf-8"))
    if "models" in cfg and entry_id in cfg["models"]:
        del cfg["models"][entry_id]
        _USER_CONFIG_PATH.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------------------
# Flow controller — attached to either WorldLinesLauncherApp or NeonRPApp.
# The host must provide:
#   push_screen(screen, callback)
#   _step_prompt_text(title, default, on_submit)  (for TextInputScreen prompts)
#   ui_locale  (str)   — optional, defaults to "en"
# ---------------------------------------------------------------------------

class SettingsFlow:
    """State-less helpers for the shared settings flow."""

    def __init__(
        self,
        host: Any,
        *,
        on_exit: Callable[[], None] | None = None,
    ):
        self.host = host
        self.on_exit = on_exit

    @property
    def locale(self) -> str:
        return getattr(self.host, "ui_locale", None) or getattr(self.host, "locale", "en") or "en"

    def _t(self, key: str) -> str:
        return get_message(self.locale, key)

    # ------------------------------------------------------------------
    # Top-level menu: Configured (N) + Add new + System — each a section.
    # ------------------------------------------------------------------
    def open_root(self) -> None:
        from neonrp.tui.app import ChoicePickerScreen, section, spacer
        from neonrp.core.discord_config import get_discord_inline_status
        from neonrp.core.user_config import get_user_locale

        configured = list_configured_entries()

        options: list[tuple[str, str]] = []
        current = self._current_model_ref()

        # ─── Section 0: Worldlines account (optional; 10-02) ──────────
        signed = _worldlines_signed_in()
        options.append(section(f"── {self._t('account.title')} · {self._t('account.signed_in') if signed else self._t('account.signed_out')} ──"))
        options.append(spacer())
        options.append((self._t("account.settings_logout") if signed else f"→  {self._t('account.settings_login')}", "account_logout" if signed else "account_login"))
        options.append(spacer())

        # ─── Section 1: Configured ────────────────────────────────────
        options.append(section(f"── {self._t('settings.configured')} ({len(configured)}) ──"))
        options.append(spacer())
        if configured:
            options.append((f"▶▶ {self._t('settings.test')} all ({len(configured)})", "test_all"))
        for entry in configured:
            prov = entry["provider"] or "?"
            model = entry["model"] or "?"
            mark = "★ " if entry["id"] == current else "  "
            options.append((f"{mark}{entry['id']:<14}  [{prov:<9}]  {model}", f"view::{entry['id']}"))
        if not configured:
            options.append(("(none — add one below)", "__noop__"))

        options.append(spacer())

        # ─── Section 2: Add new ───────────────────────────────────────
        options.append(section(f"── {self._t('settings.add_new')} ──"))
        options.append(spacer())
        for ptype in PROVIDER_TYPES:
            tkey = f"settings.provider.{ptype['id']}"
            label = self._t(tkey) if tkey in self._all_translation_keys() else ptype["label"]
            options.append((f"+  {label}", f"add::{ptype['id']}"))

        options.append(spacer())

        # ─── Section 3: System ────────────────────────────────────────
        options.append(section("── system ──"))
        options.append(spacer())
        options.append((f"{self._t('settings.language')}  ({get_user_locale()})", "locale"))
        options.append((f"creation LLM  ({self._create_provider_inline_status()})", "create_provider"))
        options.append((f"{self._t('settings.discord')}  ({get_discord_inline_status()})", "discord"))
        options.append((f"{self._t('settings.image')}  ({self._image_inline_status()})", "image"))
        options.append((f"{self._t('settings.judge')}  ({self._judge_inline_status()})", "judge"))
        options.append((self._t('settings.config_path'), "show_path"))
        options.append(spacer())
        options.append((self._t('settings.back'), "back"))

        def on_selected(value: str | None) -> None:
            if value is None or value == "back":
                if self.on_exit:
                    self.on_exit()
                return
            if value == "__noop__":
                self.open_root()
                return
            if value == "test_all":
                self._run_test_all(configured)
                return
            if value in ("account_login", "account_logout"):
                cmd = getattr(self.host, "_cmd_login" if value == "account_login" else "_cmd_logout", None)
                if cmd is not None:
                    if self.on_exit:
                        self.on_exit()
                    cmd([]) if value == "account_login" else cmd()
                else:  # a host without the conversation view (the launcher): sign in from the shell
                    from neonrp.core import worldlines_auth

                    worldlines_auth.disconnect() if value == "account_logout" else worldlines_auth.connect()
                    self.open_root()
                return
            if value == "locale":
                self._open_language_picker()
                return
            if value == "create_provider":
                self._open_create_provider_picker()
                return
            if value == "discord":
                self._open_discord()
                return
            if value == "show_path":
                self._open_config_path()
                return
            if value == "image":
                self._open_image_settings()
                return
            if value == "judge":
                self._open_judge_settings()
                return
            if value.startswith("view::"):
                self._open_entry_detail(value.split("::", 1)[1])
                return
            if value.startswith("add::"):
                self._open_add_flow(value.split("::", 1)[1])
                return

        self.host.push_screen(
            ChoicePickerScreen(self._t("settings.title"), options),
            on_selected,
        )

    def _all_translation_keys(self) -> set[str]:
        from neonrp.tui.i18n import _MESSAGES

        return set(_MESSAGES.get(self.locale, _MESSAGES["en"]).keys())

    # ------------------------------------------------------------------
    # Per-entry detail: edit key / edit model / test / delete / back
    # ------------------------------------------------------------------
    def _current_model_ref(self) -> str | None:
        """The model this world/project is on (None from the launcher)."""
        getter = getattr(self.host, "_current_model_ref", None)
        if callable(getter):
            try:
                return getter()
            except Exception:  # noqa: BLE001
                return None
        return None

    def _can_switch(self) -> bool:
        return callable(getattr(self.host, "_cmd_auth_set_model", None))

    def _open_entry_detail(self, entry_id: str) -> None:
        from neonrp.tui.app import ChoicePickerScreen, section, spacer

        user_models = _load_user_config_models()
        preset_info = PRESETS.get(entry_id, {})
        merged = {**preset_info, **(user_models.get(entry_id) or {})}
        masked = _mask_key(merged.get("api_key", ""))
        model = merged.get("model", "") or "(unset)"
        prov = merged.get("provider", "?")
        is_current = self._current_model_ref() == entry_id

        options = [
            section(f"── {entry_id} ──"),
            spacer(),
            (f"id:        {entry_id}", "__noop__"),
            (f"provider:  {prov}", "__noop__"),
            (f"model:     {model}", "__noop__"),
            (f"api key:   {masked}", "__noop__"),
            spacer(),
            section("── actions ──"),
            spacer(),
        ]
        # 「点击已经设置好的模型并不会切换 —— 复用了只管测试
        # 的逻辑」. The list used to offer test / edit / delete only; using
        # the model is the one thing people come here for.
        if self._can_switch():
            options.append((f"★  {self._t('settings.use_model')}" + ("  (当前)" if is_current else ""), "use"))
        options += [
            (f"▶  {self._t('settings.test')}", "test"),
            (f"✎  {self._t('settings.edit')} API key", "edit_key"),
            (f"✎  {self._t('settings.edit')} model", "edit_model"),
            (f"✗  {self._t('settings.delete')}", "delete"),
            spacer(),
            (self._t("settings.back"), "back"),
        ]

        def on_selected(value: str | None) -> None:
            if value is None or value == "back":
                self.open_root()
                return
            if value == "__noop__":
                self._open_entry_detail(entry_id)
                return
            if value == "use":
                try:
                    self.host._cmd_auth_set_model(["model", entry_id])
                except Exception:  # noqa: BLE001 — the host reports its own errors
                    pass
                self.open_root()
                return
            if value == "test":
                self._run_test(entry_id)
                return
            if value == "edit_key":
                self.host._step_prompt_text(
                    f"{self._t('prompt.api_key')} · {entry_id}",
                    default="",
                    on_submit=lambda v: self._apply_key_edit(entry_id, v),
                )
                return
            if value == "edit_model":
                self.host._step_prompt_text(
                    f"{self._t('prompt.model_id')} · {entry_id}",
                    default=model if model != "(unset)" else "",
                    on_submit=lambda v: self._apply_model_edit(entry_id, v),
                )
                return
            if value == "delete":
                delete_entry(entry_id)
                self.open_root()

        self.host.push_screen(
            ChoicePickerScreen(f"{self._t('settings.title')} · {entry_id}", options),
            on_selected,
        )

    def _apply_key_edit(self, entry_id: str, raw: str) -> None:
        raw = (raw or "").strip()
        if raw:
            _save_key_to_user_config(entry_id, raw)
        self._open_entry_detail(entry_id)

    def _apply_model_edit(self, entry_id: str, raw: str) -> None:
        raw = (raw or "").strip()
        if not raw:
            self._open_entry_detail(entry_id)
            return
        set_entry_model(entry_id, raw)
        self._open_entry_detail(entry_id)

    def _run_test(self, entry_id: str) -> None:
        from neonrp.tui.app import ChoicePickerScreen, section, spacer

        result = test_preset(entry_id)
        if result.get("ok"):
            status = f"✓ {self._t('settings.test_ok')}  ({result.get('latency_ms', 0)}ms)"
        else:
            status = f"✗ {self._t('settings.test_fail')}  {result.get('error', '')[:200]}"
        options = [
            section(f"── test · {entry_id} ──"),
            spacer(),
            (status, "__noop__"),
            (f"provider:  {result.get('provider', '?')}", "__noop__"),
            (f"model:     {result.get('model', '?')}", "__noop__"),
            spacer(),
            (self._t("settings.back"), "back"),
        ]

        def on_selected(value: str | None) -> None:
            self._open_entry_detail(entry_id)

        self.host.push_screen(
            ChoicePickerScreen(f"Test · {entry_id}", options),
            on_selected,
        )

    def _run_test_all(self, entries: list[dict[str, Any]]) -> None:
        """Test every configured entry in parallel, then show a summary screen."""
        from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FutTimeout
        from neonrp.tui.app import ChoicePickerScreen, section, spacer

        if not entries:
            self.open_root()
            return

        results: list[tuple[str, dict[str, Any]]] = []
        ids = [e["id"] for e in entries]

        # Run pings in parallel. Per-preset timeout is enforced inside
        # `test_preset` (6s). We give the outer `as_completed` a hard
        # 10s wall-clock cap so a single hung request can't block the whole
        # Test-all screen from rendering.
        with ThreadPoolExecutor(max_workers=min(8, len(ids) or 1)) as pool:
            futures = {pool.submit(test_preset, pid): pid for pid in ids}
            try:
                for fut in as_completed(futures, timeout=12.0):
                    pid = futures[fut]
                    try:
                        results.append((pid, fut.result(timeout=0)))
                    except Exception as exc:
                        results.append((pid, {"ok": False, "error": str(exc)[:160]}))
            except FutTimeout:
                # Collect whatever finished; mark the rest as timed out.
                done_ids = {futures[f] for f in futures if f.done()}
                for fut, pid in futures.items():
                    if pid in [r[0] for r in results]:
                        continue
                    if pid in done_ids:
                        try:
                            results.append((pid, fut.result(timeout=0)))
                        except Exception as exc:
                            results.append((pid, {"ok": False, "error": str(exc)[:160]}))
                    else:
                        fut.cancel()
                        results.append((pid, {"ok": False, "error": "timeout"}))

        # Preserve original configured order for stable UX.
        order_index = {pid: i for i, pid in enumerate(ids)}
        results.sort(key=lambda r: order_index.get(r[0], 1_000_000))

        ok_count = sum(1 for _, r in results if r.get("ok"))
        fail_count = len(results) - ok_count

        options: list[tuple[str, str]] = [
            section(f"── {self._t('settings.test')} all  ·  ✓ {ok_count} / ✗ {fail_count} ──"),
            spacer(),
        ]
        for pid, res in results:
            if res.get("ok"):
                line = (
                    f"✓  {pid:<16} [{res.get('provider', ''):<9}] "
                    f"{res.get('model', ''):<28} {res.get('latency_ms', 0)}ms"
                )
            else:
                err = str(res.get("error", ""))[:110]
                line = f"✗  {pid:<16} [{res.get('provider', ''):<9}] {err}"
            options.append((line, f"view::{pid}"))

        options.append(spacer())
        options.append((self._t("settings.back"), "back"))

        def on_selected(value: str | None) -> None:
            if value is None or value == "back" or value == "__noop__":
                self.open_root()
                return
            if value.startswith("view::"):
                self._open_entry_detail(value.split("::", 1)[1])

        self.host.push_screen(
            ChoicePickerScreen(f"Test all · {self._t('settings.title')}", options),
            on_selected,
        )

    # ------------------------------------------------------------------
    # Add-new flow — 6 provider types
    # ------------------------------------------------------------------
    def _open_add_flow(
        self,
        type_id: str,
        *,
        on_done: Callable[[str], None] | None = None,
    ) -> None:
        ptype = get_provider_type(type_id)
        if ptype is None:
            self.open_root()
            return
        if type_id == "custom":
            self._open_add_custom(ptype, on_done=on_done)
            return
        self._open_add_standard(ptype, on_done=on_done)

    def _open_add_standard(
        self,
        ptype: dict[str, Any],
        *,
        on_done: Callable[[str], None] | None = None,
    ) -> None:
        """anthropic / openai / deepseek / openrouter flow."""
        # Use the canonical id (anthropic/openai/deepseek/openrouter) unless
        # user wants a variant name. Phase 1: simple, reuse the built-in id.
        entry_id = ptype["id"]

        def after_model(model: str) -> None:
            model = (model or "").strip() or ptype["default_model"]
            self.host._step_prompt_text(
                f"{self._t('prompt.api_key')} · {ptype['label']}",
                default="",
                on_submit=lambda k: self._finalize_standard(
                    ptype, entry_id, model, k, on_done=on_done
                ),
            )

        if ptype["id"] == "openrouter" and ptype.get("fetch_catalog"):
            self.host._step_prompt_text(
                f"{self._t('prompt.api_key')} · OpenRouter (for model catalog)",
                default="",
                on_submit=lambda k: self._openrouter_after_key(
                    ptype, entry_id, k, on_done=on_done
                ),
            )
            return

        # Standard path: offer model choice from ptype["models"], then API key.
        models = list(ptype.get("models") or [])
        if not models:
            after_model(ptype["default_model"])
            return
        self._pick_model(
            title=f"{ptype['label']} — {self._t('prompt.model_id')}",
            models=models,
            allow_manual=True,
            on_selected=after_model,
        )

    def _openrouter_after_key(
        self,
        ptype: dict[str, Any],
        entry_id: str,
        key: str,
        *,
        on_done: Callable[[str], None] | None = None,
    ) -> None:
        key = (key or "").strip()
        if not key:
            self.open_root()
            return
        catalog = fetch_openrouter_models(key)
        models = [m["id"] for m in catalog[:120]] if catalog else list(ptype.get("models") or [])

        def after(model: str) -> None:
            self._finalize_standard(ptype, entry_id, model, key, on_done=on_done)

        self._pick_model(
            title=f"OpenRouter — {self._t('prompt.model_id')} ({len(models)})",
            models=models,
            allow_manual=True,
            on_selected=after,
        )

    def _finalize_standard(
        self,
        ptype: dict[str, Any],
        entry_id: str,
        model: str,
        key: str,
        *,
        on_done: Callable[[str], None] | None = None,
    ) -> None:
        key = (key or "").strip()
        if not key:
            self.open_root()
            return
        entry: dict[str, Any] = {
            "provider": ptype["provider"],
            "model": model,
            "api_key": key,
        }
        if ptype.get("base_url"):
            entry["base_url"] = ptype["base_url"]
        save_custom_entry(entry_id, entry)
        if on_done is not None:
            on_done(entry_id)
            return
        # No callback — go to detail screen as before.
        self._open_entry_detail(entry_id)

    def _open_add_custom(
        self,
        ptype: dict[str, Any],
        *,
        on_done: Callable[[str], None] | None = None,
    ) -> None:
        from neonrp.presets import first_custom_entry_example

        example = first_custom_entry_example()
        prompt_title = self._t("prompt.entry_id").format(example=example)

        def after_id(entry_id: str) -> None:
            entry_id = (entry_id or "").strip().lower()
            if not ENTRY_ID_RE.match(entry_id or ""):
                self.open_root()
                return
            self.host._step_prompt_text(
                self._t("prompt.base_url"),
                default="http://localhost:11434/v1",
                on_submit=lambda url: after_url(entry_id, url),
            )

        def after_url(entry_id: str, base_url: str) -> None:
            base_url = (base_url or "").strip()
            self.host._step_prompt_text(
                self._t("prompt.model_id"),
                default=entry_id,
                on_submit=lambda m: after_model(entry_id, base_url, m),
            )

        def after_model(entry_id: str, base_url: str, model: str) -> None:
            model = (model or "").strip()
            self.host._step_prompt_text(
                self._t("prompt.api_key"),
                default="",
                on_submit=lambda k: self._finalize_custom(entry_id, base_url, model, k, on_done=on_done),
            )

        self.host._step_prompt_text(
            prompt_title,
            default="",
            on_submit=after_id,
        )

    def _finalize_custom(
        self,
        entry_id: str,
        base_url: str,
        model: str,
        key: str,
        *,
        on_done: Callable[[str], None] | None = None,
    ) -> None:
        entry: dict[str, Any] = {
            "provider": "openai",
            "model": model or entry_id,
            "base_url": base_url,
        }
        if key.strip():
            entry["api_key"] = key.strip()
        save_custom_entry(entry_id, entry)
        if on_done is not None:
            on_done(entry_id)
            return
        self._open_entry_detail(entry_id)

    def _pick_model(
        self,
        *,
        title: str,
        models: list[str],
        allow_manual: bool,
        on_selected: Callable[[str], None],
    ) -> None:
        from neonrp.tui.app import ChoicePickerScreen

        options: list[tuple[str, str]] = []
        for m in models:
            options.append((m, f"m::{m}"))
        if allow_manual:
            options.append(("…manual entry", "__manual__"))

        def handler(value: str | None) -> None:
            if value is None:
                self.open_root()
                return
            if value == "__manual__":
                self.host._step_prompt_text(
                    self._t("prompt.model_id"),
                    default="",
                    on_submit=lambda m: on_selected((m or "").strip()),
                )
                return
            if value.startswith("m::"):
                on_selected(value.split("::", 1)[1])
                return

        self.host.push_screen(ChoicePickerScreen(title, options), handler)

    # ------------------------------------------------------------------
    # Shortcuts to existing flows (language / discord / config path)
    # ------------------------------------------------------------------
    # ------------------------------------------------------------------
    # Creation-LLM provider selection.
    #
    # The world/soul creation flow uses an OpenAI-compatible provider,
    # resolved independently of the per-game model. This lets the user pin
    # which configured provider creation uses (DeepSeek, OpenRouter, …).
    # ------------------------------------------------------------------
    def _create_provider_inline_status(self) -> str:
        chosen = get_create_provider()
        resolved = resolve_creation_provider()
        if resolved is not None:
            _, model, _ = resolved
            model = model or "?"
        else:
            model = "deepseek-v4-pro (default)"
        if chosen:
            return f"{chosen} · {model}"
        return f"auto · {model}"

    def _create_provider_eligible(self) -> list[dict[str, Any]]:
        """Configured entries that creation can actually use (OpenAI-compatible + key)."""
        eligible: list[dict[str, Any]] = []
        for entry in list_configured_entries():
            if str(entry.get("provider", "")).lower() != "openai":
                continue
            if not entry.get("has_key"):
                continue
            eligible.append(entry)
        return eligible

    def _open_create_provider_picker(self) -> None:
        from neonrp.tui.app import ChoicePickerScreen, section, spacer

        chosen = get_create_provider()
        eligible = self._create_provider_eligible()

        options: list[tuple[str, str]] = [
            section("── creation LLM provider ──"),
            spacer(),
            (
                ("● " if not chosen else "  ") + "Auto (first configured w/ key)",
                "cp::__auto__",
            ),
        ]
        for entry in eligible:
            mark = "● " if entry["id"] == chosen else "  "
            options.append(
                (f"{mark}{entry['id']:<14} [{entry['provider']:<9}] {entry['model']}",
                 f"cp::{entry['id']}")
            )
        if not eligible:
            options.append(
                ("(no OpenAI-compatible provider with a key — add one above)", "__noop__")
            )
        options.append(spacer())
        options.append(("Note: Anthropic-only entries can't drive creation yet.", "__noop__"))
        options.append(spacer())
        options.append((self._t("settings.back"), "back"))

        def on_selected(value: str | None) -> None:
            if value is None or value == "back" or value == "__noop__":
                self.open_root()
                return
            if value.startswith("cp::"):
                target = value.split("::", 1)[1]
                set_create_provider(None if target == "__auto__" else target)
                self.open_root()

        self.host.push_screen(
            ChoicePickerScreen(f"{self._t('settings.title')} · creation LLM", options),
            on_selected,
        )

    def _open_language_picker(self) -> None:
        # We deliberately DON'T delegate to the launcher's
        # `_prompt_first_run_locale`: that relabels the launcher menu but
        # leaves the open Settings screen (and `ui_locale`) untouched, so the
        # picked language wouldn't take effect here. Drive it ourselves and
        # keep BOTH locale fields in sync, then re-render the settings root.
        from neonrp.tui.app import ChoicePickerScreen
        from neonrp.core.user_config import set_user_locale
        from neonrp.tui.i18n import resolve_locale

        options = [
            ("English", "en"),
            ("简体中文", "zh"),
            ("日本語", "ja"),
            ("한국어", "ko"),
            ("Auto", "auto"),
        ]

        def on_selected(value: str | None) -> None:
            if value:
                set_user_locale(value)
                resolved = resolve_locale()
                # `ui_locale` wins in `self.locale`; the launcher reads
                # `self.locale`. Update both so every surface re-renders in
                # the new language — Settings here AND the launcher behind it.
                self.host.ui_locale = resolved
                if hasattr(self.host, "locale"):
                    self.host.locale = resolved
                relabel = getattr(self.host, "_relabel_launcher", None)
                if callable(relabel):
                    relabel()
            self.open_root()

        self.host.push_screen(ChoicePickerScreen(self._t("settings.language"), options), on_selected)

    def _open_discord(self) -> None:
        fn = getattr(self.host, "_step_configure_discord", None)
        if callable(fn):
            fn()
            return
        self.open_root()

    # ------------------------------------------------------------------
    # Image generation (text → image) backend config.
    # ------------------------------------------------------------------
    def _image_inline_status(self) -> str:
        from neonrp.core.imagegen import load_image_config

        cfg = load_image_config()
        if cfg.backend == "comfyui" and cfg.comfyui_url:
            host = cfg.comfyui_url.replace("http://", "").replace("https://", "")
            return f"comfyui · {host}"
        if cfg.backend == "openai" and (cfg.openai_key or "OPENAI_API_KEY" in __import__("os").environ):
            return f"openai · {cfg.openai_model}"
        return self._t("settings.image.none").strip("()（）")

    def _open_image_settings(self) -> None:
        from neonrp.tui.app import ChoicePickerScreen, section, spacer
        from neonrp.core.imagegen import load_image_config

        cfg = load_image_config()
        backend_label = cfg.backend or "(none)"
        masked_key = _mask_key(cfg.openai_key)

        options = [
            section(f"── {self._t('settings.image')} ──"),
            spacer(),
            (f"{self._t('settings.image.backend')}:  {backend_label}", "switch_backend"),
            spacer(),
            section("── comfyui ──"),
            (f"  url:        {cfg.comfyui_url or '(unset)'}", "edit_url"),
            (f"  ckpt:       {cfg.comfyui_ckpt}", "edit_ckpt"),
            spacer(),
            section(f"── comfyui · {self._t('settings.image.custom')} ──"),
            (f"  workflow:   {_shorten(cfg.comfyui_workflow) or '(built-in)'}", "edit_workflow"),
            (f"  input node: {cfg.comfyui_input_node or '(unset)'}", "edit_input_node"),
            (f"  neg node:   {cfg.comfyui_neg_node or '(unset)'}", "edit_neg_node"),
            (f"  out node:   {cfg.comfyui_output_node or '(unset)'}", "edit_output_node"),
            (f"  seed node:  {cfg.comfyui_seed_node or '(unset)'}", "edit_seed_node"),
            spacer(),
            section("── openai ──"),
            (f"  api key:    {masked_key}", "edit_openai_key"),
            (f"  model:      {cfg.openai_model}", "edit_openai_model"),
            spacer(),
            (f"▶  {self._t('settings.test')}", "test"),
            spacer(),
            (self._t("settings.back"), "back"),
        ]

        def on_selected(value: str | None) -> None:
            if value is None or value == "back":
                self.open_root()
                return
            if value == "switch_backend":
                self._pick_image_backend()
                return
            if value == "edit_url":
                self.host._step_prompt_text(
                    self._t("settings.image.url"),
                    default=cfg.comfyui_url or "http://127.0.0.1:8188",
                    on_submit=lambda v: self._apply_image_field("comfyui_url", v),
                )
                return
            if value == "edit_ckpt":
                self.host._step_prompt_text(
                    self._t("settings.image.ckpt"),
                    default=cfg.comfyui_ckpt,
                    on_submit=lambda v: self._apply_image_field("comfyui_ckpt", v),
                )
                return
            # Custom-workflow fields: an API-format workflow + the node ids the
            # prompt/neg/output/seed get injected into. Empty = built-in graph.
            _custom = {
                "edit_workflow": ("comfyui_workflow", "settings.image.workflow", cfg.comfyui_workflow),
                "edit_input_node": ("comfyui_input_node", "settings.image.input_node", cfg.comfyui_input_node),
                "edit_neg_node": ("comfyui_neg_node", "settings.image.neg_node", cfg.comfyui_neg_node),
                "edit_output_node": ("comfyui_output_node", "settings.image.output_node", cfg.comfyui_output_node),
                "edit_seed_node": ("comfyui_seed_node", "settings.image.seed_node", cfg.comfyui_seed_node),
            }
            if value in _custom:
                _field, _label, _cur = _custom[value]
                self.host._step_prompt_text(
                    f"{self._t(_label)}  {self._t('settings.image.clear')}",
                    default=_cur,
                    on_submit=lambda v, f=_field: self._apply_image_field(f, v),
                )
                return
            if value == "edit_openai_key":
                self.host._step_prompt_text(
                    self._t("settings.image.openai_key"),
                    default="",
                    on_submit=lambda v: self._apply_image_field("openai_key", v),
                )
                return
            if value == "edit_openai_model":
                self.host._step_prompt_text(
                    self._t("settings.image.openai_model"),
                    default=cfg.openai_model,
                    on_submit=lambda v: self._apply_image_field("openai_model", v),
                )
                return
            if value == "test":
                self._run_image_test()
                return

        self.host.push_screen(
            ChoicePickerScreen(self._t("settings.title"), options),
            on_selected,
        )

    def _pick_image_backend(self) -> None:
        from neonrp.tui.app import ChoicePickerScreen, section, spacer

        options = [
            section(f"── {self._t('settings.image.backend')} ──"),
            spacer(),
            ("comfyui  (local, no billing)", "b::comfyui"),
            ("openai   (gpt-image-1 / billed)", "b::openai"),
            (self._t("settings.image.none"), "b::"),
            spacer(),
            (self._t("settings.back"), "back"),
        ]

        def on_selected(value: str | None) -> None:
            if value is None or value == "back":
                self._open_image_settings()
                return
            if value.startswith("b::"):
                self._apply_image_field("backend", value.split("::", 1)[1])

        self.host.push_screen(
            ChoicePickerScreen(self._t("settings.image.backend"), options),
            on_selected,
        )

    def _apply_image_field(self, field: str, raw: str) -> None:
        from neonrp.core.imagegen import update_image_field

        update_image_field(field, (raw or "").strip())
        self._open_image_settings()

    def _run_image_test(self) -> None:
        from neonrp.tui.app import ChoicePickerScreen, section, spacer
        from neonrp.core.imagegen import test_backend

        result = test_backend()
        status = (
            f"✓ {self._t('settings.test_ok')}"
            if result.get("ok")
            else f"✗ {self._t('settings.test_fail')}"
        )
        options = [
            section(f"── test · {self._t('settings.image')} ──"),
            spacer(),
            (f"{status}  ·  {result.get('backend', '?')}", "__noop__"),
            (f"{result.get('detail', '')}", "__noop__"),
            spacer(),
            (self._t("settings.back"), "back"),
        ]

        def on_selected(_: str | None) -> None:
            self._open_image_settings()

        self.host.push_screen(
            ChoicePickerScreen(f"Test · {self._t('settings.image')}", options),
            on_selected,
        )

    # ------------------------------------------------------------------
    # Judge (Jev) — 10-25: mode · own key · judge model preset · test.
    # Reads / writes through core.judge_settings (the web drawer shares it).
    # ------------------------------------------------------------------
    def _judge_inline_status(self) -> str:
        from neonrp.core import judge_settings

        try:
            st = judge_settings.read()
        except Exception:  # noqa: BLE001
            return "?"
        return f"{st['mode']} · {st['effective']}"

    def _open_judge_settings(self) -> None:
        from neonrp.tui.app import ChoicePickerScreen, section, spacer
        from neonrp.core import judge_settings

        st = judge_settings.read()
        key_label = st["key_masked"] or self._t("settings.judge.key_unset")
        if st["key_source"] == "env":
            key_label += f"  ({self._t('settings.judge.env').format(name=judge_settings.KEY_ENV)})"
        mode_label = self._t(f"settings.judge.mode.{st['mode']}") if st["mode"] in judge_settings.MODES else st["mode"]
        if st["mode_source"] == "env":
            mode_label += f"  ({self._t('settings.judge.env').format(name=judge_settings.MODE_ENV)})"
        preset_label = st["llm_preset"] or self._t("settings.judge.preset_none")
        if st["llm_preset_source"] == "env":
            preset_label += f"  ({self._t('settings.judge.env').format(name=judge_settings.PRESET_ENV)})"
        now = self._t(f"judge.{st['effective']}")
        if st.get("pinned_unusable"):
            now = f"{self._t('judge.pinned.' + st['pinned_unusable'])} → {self._t('judge.actual')}: {now}"
        if st["effective"] in ("off", "quota", "llm") and not st["signed_in"]:
            now += f"  ·  {self._t('judge.login')}"

        options: list[tuple[str, str]] = [
            section(f"── {self._t('settings.judge')} ──"),
            spacer(),
            (f"{self._t('settings.judge.now')}:  {now}", "__noop__"),
            (self._t("settings.judge.hint"), "__noop__"),
            spacer(),
            (f"{self._t('settings.judge.mode')}:    {mode_label}", "mode"),
            (f"{self._t('settings.judge.key')}:  {key_label}", "key"),
        ]
        if st["key_source"] == "config":
            options.append((f"  ✕ {self._t('settings.judge.key_clear')}", "key_clear"))
        options += [
            (f"{self._t('settings.judge.preset')}:  {preset_label}", "preset"),
            spacer(),
            (f"▶  {self._t('settings.test')}", "test"),
            spacer(),
            (self._t("settings.back"), "back"),
        ]

        def on_selected(value: str | None) -> None:
            if value is None or value == "back":
                self.open_root()
                return
            if value == "__noop__":
                self._open_judge_settings()
                return
            if value == "mode":
                self._pick_judge_mode()
                return
            if value == "key":
                self.host._step_prompt_text(
                    self._t("settings.judge.key_prompt"),
                    default="",
                    on_submit=lambda v: self._apply_judge(api_key=v),
                )
                return
            if value == "key_clear":
                self._apply_judge(clear_key=True)
                return
            if value == "preset":
                self._pick_judge_preset(st["presets"])
                return
            if value == "test":
                self._run_judge_test()
                return

        self.host.push_screen(ChoicePickerScreen(self._t("settings.judge"), options), on_selected)

    def _pick_judge_mode(self) -> None:
        from neonrp.tui.app import ChoicePickerScreen, section, spacer
        from neonrp.core import judge_settings

        options: list[tuple[str, str]] = [section(f"── {self._t('settings.judge.mode')} ──"), spacer()]
        options += [(self._t(f"settings.judge.mode.{m}"), f"m::{m}") for m in judge_settings.MODES]
        options += [spacer(), (self._t("settings.back"), "back")]

        def on_selected(value: str | None) -> None:
            if value is None or value == "back":
                self._open_judge_settings()
                return
            if value.startswith("m::"):
                self._apply_judge(mode=value.split("::", 1)[1])

        self.host.push_screen(ChoicePickerScreen(self._t("settings.judge.mode"), options), on_selected)

    def _pick_judge_preset(self, presets: list[str]) -> None:
        from neonrp.tui.app import ChoicePickerScreen, section, spacer

        options: list[tuple[str, str]] = [section(f"── {self._t('settings.judge.preset')} ──"), spacer()]
        options += [(f"  {pid}", f"p::{pid}") for pid in presets]
        options += [(self._t("settings.judge.preset_none"), "p::"), spacer(), (self._t("settings.back"), "back")]

        def on_selected(value: str | None) -> None:
            if value is None or value == "back":
                self._open_judge_settings()
                return
            if value.startswith("p::"):
                self._apply_judge(llm_preset=value.split("::", 1)[1])

        self.host.push_screen(ChoicePickerScreen(self._t("settings.judge.preset"), options), on_selected)

    def _apply_judge(self, **fields: Any) -> None:
        from neonrp.core import judge_settings

        if "api_key" in fields and not (fields["api_key"] or "").strip():  # blank = cancelled
            self._open_judge_settings()
            return
        judge_settings.save(**fields)
        self._open_judge_settings()

    def _run_judge_test(self) -> None:
        from neonrp.tui.app import ChoicePickerScreen, section, spacer
        from neonrp.core import judge_settings

        result = judge_settings.probe()
        status = f"✓ {self._t('settings.test_ok')}" if result.get("ok") else f"✗ {self._t('settings.test_fail')}"
        detail = f"{result.get('ms', 0)} ms · yes={result.get('yes')}" if result.get("ok") else str(result.get("error", ""))
        options = [
            section(f"── test · {self._t('settings.judge')} ──"),
            spacer(),
            (f"{status}  ·  {result.get('backend', '?')}", "__noop__"),
            (detail, "__noop__"),
            spacer(),
            (self._t("settings.back"), "back"),
        ]

        def on_selected(_: str | None) -> None:
            self._open_judge_settings()

        self.host.push_screen(ChoicePickerScreen(f"Test · {self._t('settings.judge')}", options), on_selected)

    def _open_config_path(self) -> None:
        from neonrp.tui.app import ChoicePickerScreen

        options = [
            (str(_USER_CONFIG_PATH), "__noop__"),
            (f"exists: {_USER_CONFIG_PATH.exists()}", "__noop__"),
            (self._t("settings.back"), "back"),
        ]

        def on_selected(value: str | None) -> None:
            self.open_root()

        self.host.push_screen(ChoicePickerScreen("Config file", options), on_selected)


def _mask_key(key: str) -> str:
    key = (key or "").strip()
    if not key:
        return "(not set)"
    if len(key) <= 10:
        return "…" + key[-4:]
    return key[:4] + "…" + key[-4:]


def _shorten(value: str, width: int = 40) -> str:
    """Compact a workflow spec (long path / inline JSON) for one menu row."""
    v = (value or "").strip().replace("\n", " ")
    if not v:
        return ""
    if v.startswith("{"):
        return f"(inline JSON · {len(v)}B)"
    return v if len(v) <= width else "…" + v[-(width - 1):]
