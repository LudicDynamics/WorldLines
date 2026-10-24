"""Per-run output language for LLM prompts (中/英/日).

语言隔离(統合検証帖·語言隔離):世界的 prompt 与**隐藏/系统提示词**要能按
输出语切换,不再把创作语言(多为中文)硬塞进每个 soul。骨架做**中/英/日三份**
("canonical 骨架是中英日 i18n,或者做 3 份"),运行时按本局的
``output_lang`` 选用。

output_lang 的落地位置 = 本局 game meta 的 ``run_state.json['output_lang']``,
在 bind 一局时由前端选择的语言写入(见 webui 的 play/session 处理)。读取处
(soul-agent 模板选择、world/keeper 语言指令)一律经 :func:`resolve_output_lang`,
精度=不穿参数过几十个调用点,就近读 run_state。

只做 zh/en/ja 三种 prompt 语言:UI 有 ko,但 prompt 骨架先覆盖中英日,ko 回退
到 en(避免混入未翻译的第四语)。
"""

from __future__ import annotations

import json
from pathlib import Path

from neonrp.core.paths import get_data_dir_name

# prompt 骨架实际提供的语言(与 UI 四语区分:ko 暂回退 en)。
PROMPT_LANGS: tuple[str, ...] = ("zh", "en", "ja", "ko")
DEFAULT_PROMPT_LANG = "zh"


def normalize_prompt_lang(value: str | None) -> str:
    """把任意 locale 串规约到 {zh,en,ja,ko} 之一;未知 → en,空 → 默认(10-05 四语:ko 不再回退 en)。"""
    s = str(value or "").strip().lower()
    if not s:
        return DEFAULT_PROMPT_LANG
    if s.startswith("zh"):
        return "zh"
    if s.startswith("ja"):
        return "ja"
    if s.startswith("en"):
        return "en"
    if s.startswith("ko"):
        return "ko"
    # 其它:回退英文(不回退中文——避免非中文世界串味)。
    return "en"


def _run_state_path(root: Path) -> Path:
    return root / get_data_dir_name(root) / "meta" / "run_state.json"


def _read_run_state(root: Path) -> dict:
    try:
        data = json.loads(_run_state_path(root).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def resolve_output_lang(root: Path) -> str:
    """本局 prompt 输出语言。优先级:

    1. ``run_state.json['output_lang']``(bind 时按玩家选的语言写入) —— 权威;
    2. ``run_state.json['source_lang']``(世界创作语言,若曾落盘);
    3. 默认 ``zh``(引擎内置世界均为中文创作)。

    结果规约到 {zh,en,ja}。就近读盘、不抛错(缺文件 → 默认)。
    """
    rs = _read_run_state(root)
    explicit = rs.get("output_lang")
    if isinstance(explicit, str) and explicit.strip():
        return normalize_prompt_lang(explicit)
    src = rs.get("source_lang")
    if isinstance(src, str) and src.strip():
        return normalize_prompt_lang(src)
    return prompt_lang(root)  # 10-05: the world's own language (manifest / suffix / script), not a fixed zh


def write_output_lang(root: Path, lang: str) -> str:
    """把本局输出语写进 ``run_state.json``(bind 时调用)。返回规约后的值。

    合并写(保留 turn_count 等既有字段)。run_state 缺失时创建 meta 目录 + 文件。
    best-effort:写失败不抛(读取侧有默认回退)。
    """
    norm = normalize_prompt_lang(lang)
    path = _run_state_path(root)
    rs = _read_run_state(root)
    rs["output_lang"] = norm
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(rs, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass
    return norm


def built_lang(root: Path) -> str | None:
    """The language a template run was BUILT in (its ``i18n/<lang>/`` layer: ``game/meta/template.json`` →
    ``i18n.lang``), or None (a run built without a language, or not from a template). The world files of such a run
    are in that language and stay so; a later ``output_lang`` cannot re-localize them (10-16, iOS: an English save
    resumed from a Japanese Hub played English world text under Japanese narration)."""
    try:
        rec = json.loads((root / get_data_dir_name(root) / "meta" / "template.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    lg = str(((rec.get("i18n") or {}) if isinstance(rec, dict) else {}).get("lang") or "").strip().lower()[:2]
    return lg if lg in ALL_LANGS else None


# ── one language source for prompts (10-05: 四语;玩家选的语言优先) ─────────────────────────────────────────────
ALL_LANGS: tuple[str, ...] = ("zh", "en", "ja", "ko")


def prompt_lang(root: Path) -> str:
    """zh | en | ja | ko — the language this run's prompts and authored text are picked in: the language the player chose
    (``run_state.output_lang``) wins, else the world's own (``adv.world_lang``: manifest lang → folder suffix → script).
    Unlike :func:`normalize_prompt_lang` it keeps ko; callers pick text with :func:`pick_lang` (ko → en → zh)."""
    v = str(_read_run_state(root).get("output_lang") or "").strip().lower()[:2]
    if v in ALL_LANGS:
        return v
    try:
        from neonrp.core.adv import world_lang_raw

        w = world_lang_raw(root)
    except Exception:  # noqa: BLE001
        w = DEFAULT_PROMPT_LANG
    return w if w in ALL_LANGS else DEFAULT_PROMPT_LANG


def pick_lang(texts: dict | str | None, lang: str, default: str = "") -> str:
    """One text out of ``{lang: text}`` (or a plain string): lang → en → zh → any. A missing language never raises."""
    if isinstance(texts, str):
        return texts
    if not isinstance(texts, dict) or not texts:
        return default
    for k in (lang, "en", "zh"):
        v = texts.get(k)
        if isinstance(v, str) and v.strip():
            return v
    return next((v for v in texts.values() if isinstance(v, str) and v.strip()), default)


def pick_opening(startup: dict | None, lang: str) -> tuple[str, list[str]]:
    """game-start.json ``startup`` → (opening scene, opening choices) in ``lang`` (开场旁白四语).

    Either field may be plain (one language) or ``{zh,en,ja,ko}``; choices may also be ``{lang: [...]}`` or a list
    of ``{lang: text}``. A missing language falls back lang → en → zh → any."""
    st = startup if isinstance(startup, dict) else {}
    scene = pick_lang(st.get("opening_scene"), lang).strip()
    raw = st.get("opening_choices") or []
    if isinstance(raw, dict):
        lists = {k: v for k, v in raw.items() if isinstance(v, list) and v}
        raw = next((lists[k] for k in (lang, "en", "zh") if k in lists), next(iter(lists.values()), []))
    if not isinstance(raw, list):
        raw = []
    items = [pick_lang(c, lang) if isinstance(c, dict) else c for c in raw if isinstance(c, (str, dict))]
    return scene, [c.strip() for c in items if c and c.strip()]
