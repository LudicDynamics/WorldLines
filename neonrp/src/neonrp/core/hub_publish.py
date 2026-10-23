"""Publish gate for the Hub.

Before a world or character may go *public* on the hub three things must be
true, and the client checks them so nothing embarrassing has to be caught
after the fact:

1. **No secrets ship** — the kusofuka-yabu leak was a config file with a live
   key inside a published bundle. Every text file that would enter the zip is
   scanned for key-shaped strings and credential files; a hit blocks even a
   draft upload.
2. **Every picture is there** — the cover, and a portrait for each of the
   world's own characters.
3. **Title and description in zh / en / ja / ko** — kept with the source as
   ``hub.json`` so they survive re-uploads; the missing languages can be
   filled by the configured model (:func:`translate_missing`).

Drafts (unlisted uploads) only need (1); a public listing needs all three.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

HUB_LANGS: tuple[str, ...] = ("zh", "en", "ja", "ko")
HUB_META_FILE = "hub.json"

_TEXT_SUFFIXES = {".json", ".md", ".txt", ".yaml", ".yml", ".toml", ".env", ".ini", ".cfg", ".py", ".js", ".ts", ".csv", ".jsonl"}
_MAX_SCAN_BYTES = 2 * 1024 * 1024

# Key shapes we know: OpenAI/Kimi/SiliconFlow/DeepSeek `sk-…`, AWS access
# keys, GitHub tokens, HuggingFace, Anthropic, Google API keys, Slack, and
# generic `"api_key": "<long>"` / `token=<long>` pairs.
_KEY_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("sk-key", re.compile(r"\bsk-[A-Za-z0-9_\-]{16,}")),
    ("aws-access-key", re.compile(r"\b(AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("github-token", re.compile(r"\b(ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}")),
    ("huggingface-token", re.compile(r"\bhf_[A-Za-z0-9]{20,}")),
    ("anthropic-key", re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{20,}")),
    ("google-api-key", re.compile(r"\bAIza[0-9A-Za-z_\-]{30,}")),
    ("slack-token", re.compile(r"\bxox[abpr]-[A-Za-z0-9\-]{10,}")),
    ("bearer", re.compile(r"Bearer\s+[A-Za-z0-9._\-]{24,}")),
    (
        "key-field",
        re.compile(
            r"[\"']?(api[_\-]?key|apikey|secret[_\-]?key|access[_\-]?token|auth[_\-]?token|client[_\-]?secret|password)[\"']?\s*[:=]\s*[\"']?([A-Za-z0-9._\-]{16,})",
            re.IGNORECASE,
        ),
    ),
)
_PLACEHOLDER = re.compile(r"^(\$\{?[A-Z_]+\}?|<[^>]+>|your[_\-]|xxx+|\*+|changeme|example|placeholder|none|null)", re.IGNORECASE)
_CREDENTIAL_FILES = re.compile(r"(^|/)(\.env(\..*)?|.*\.pem|.*\.key|id_rsa.*|credentials(\.json)?|secrets?\.json|\.netrc)$")


@dataclass
class SecretHit:
    path: str
    kind: str
    line: int

    def to_dict(self) -> dict[str, Any]:
        return {"path": self.path, "kind": self.kind, "line": self.line}


def _would_ship(rel: Path) -> bool:
    """Mirror world_export's filter: excluded dirs out, `.neonrp/` only the allowlist."""
    from neonrp.core.world_export import _EXCLUDE_DIR_NAMES, _NEONRP_EXPORT_ALLOW

    if any(part in _EXCLUDE_DIR_NAMES for part in rel.parts):
        return False
    rel_posix = rel.as_posix()
    if rel_posix == ".neonrp" or rel_posix.startswith(".neonrp/"):
        return rel_posix in _NEONRP_EXPORT_ALLOW
    return True


def scan_for_secrets(source: Path) -> list[SecretHit]:
    """Every key-shaped string / credential file that would enter the bundle."""
    source = Path(source)
    hits: list[SecretHit] = []
    if not source.is_dir():
        return hits
    for p in sorted(source.rglob("*")):
        try:
            if not p.is_file() or p.is_symlink():
                continue
            rel = p.relative_to(source)
        except (OSError, ValueError):
            continue
        if not _would_ship(rel):
            continue
        rel_s = rel.as_posix()
        if _CREDENTIAL_FILES.search(rel_s):
            hits.append(SecretHit(rel_s, "credential-file", 0))
            continue
        if p.suffix.lower() not in _TEXT_SUFFIXES:
            continue
        try:
            if p.stat().st_size > _MAX_SCAN_BYTES:
                continue
            text = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            for kind, pat in _KEY_PATTERNS:
                m = pat.search(line)
                if not m:
                    continue
                value = m.group(m.lastindex or 0)
                if kind == "key-field" and _PLACEHOLDER.match(value):
                    continue
                hits.append(SecretHit(rel_s, kind, lineno))
                break
    return hits


# ── hub.json: title / description per language ─────────────────────────


def hub_meta_path(source: Path, kind: str = "worlds") -> Path:
    source = Path(source)
    if kind == "souls":
        return source / HUB_META_FILE
    try:
        from neonrp.core.paths import get_game_dir

        return get_game_dir(source) / "meta" / HUB_META_FILE
    except Exception:
        return source / "game" / "meta" / HUB_META_FILE


def _clean_map(raw: Any) -> dict[str, str]:
    out: dict[str, str] = {}
    if isinstance(raw, dict):
        for lang in HUB_LANGS:
            v = raw.get(lang)
            if isinstance(v, str) and v.strip():
                out[lang] = v.strip()
    return out


def load_hub_meta(source: Path, kind: str = "worlds") -> dict[str, Any]:
    path = hub_meta_path(source, kind)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"title": {}, "description": {}}
    if not isinstance(data, dict):
        return {"title": {}, "description": {}}
    return {"title": _clean_map(data.get("title")), "description": _clean_map(data.get("description"))}


def save_hub_meta(source: Path, kind: str, *, title: dict[str, str], description: dict[str, str]) -> Path:
    from datetime import datetime, timezone

    path = hub_meta_path(source, kind)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "title": _clean_map(title),
        "description": _clean_map(description),
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def guess_lang(text: str) -> str:
    """Which of the four hub languages a string is written in (script based)."""
    if re.search(r"[぀-ヿ]", text):
        return "ja"
    if re.search(r"[가-힯]", text):
        return "ko"
    if re.search(r"[一-鿿]", text):
        return "zh"
    return "en"


def missing_langs(values: dict[str, str]) -> list[str]:
    return [lang for lang in HUB_LANGS if not values.get(lang)]


@dataclass
class HubMeta:
    title: dict[str, str] = field(default_factory=dict)
    description: dict[str, str] = field(default_factory=dict)

    @property
    def missing(self) -> list[str]:
        seen: list[str] = []
        for lang in missing_langs(self.title) + missing_langs(self.description):
            if lang not in seen:
                seen.append(lang)
        return seen

    @property
    def complete(self) -> bool:
        return not self.missing

    def pick(self, lang: str, which: str = "title") -> str:
        values = self.title if which == "title" else self.description
        if values.get(lang):
            return values[lang]
        for k in HUB_LANGS:
            if values.get(k):
                return values[k]
        return ""


def seed_hub_meta(source: Path, kind: str, *, title: str, description: str) -> HubMeta:
    """hub.json first; the source's own name/premise fill the language they
    are written in when the file has nothing for it."""
    stored = load_hub_meta(source, kind)
    meta = HubMeta(title=dict(stored["title"]), description=dict(stored["description"]))
    if title.strip():
        lang = guess_lang(title)
        meta.title.setdefault(lang, title.strip())
    if description.strip():
        lang = guess_lang(description)
        meta.description.setdefault(lang, description.strip())
    return meta


# ── auto-translation ───────────────────────────────────────────────────

_LANG_NAMES = {"zh": "Simplified Chinese", "en": "English", "ja": "Japanese", "ko": "Korean"}


def _extract_json(raw: str) -> dict[str, Any] | None:
    raw = raw.strip()
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def translate_missing(meta: HubMeta, *, llm: Any) -> HubMeta:
    """Fill every missing language of ``meta`` with one model call.

    ``llm`` is any :class:`neonrp.core.llm.LLMAdapter`. Existing values are
    never overwritten. Raises ``RuntimeError`` when the model gives nothing
    usable, so the caller can show the error instead of silently uploading
    half-translated metadata.
    """
    from neonrp.core.llm import Message

    want = meta.missing
    if not want:
        return meta
    src_title = meta.pick("zh", "title") or meta.pick("en", "title")
    src_desc = meta.pick("zh", "description") or meta.pick("en", "description")
    have = {
        "title": {k: v for k, v in meta.title.items() if v},
        "description": {k: v for k, v in meta.description.items() if v},
    }
    prompt = (
        "You localize catalogue metadata for a story-world hub. Translate the title and the "
        "one-line description into the requested languages. Keep proper nouns recognisable, "
        "keep the description to one sentence, no quotes, no explanations.\n\n"
        f"Existing values (JSON): {json.dumps(have, ensure_ascii=False)}\n"
        f"Source title: {src_title}\nSource description: {src_desc}\n"
        f"Languages needed: {', '.join(f'{lang} ({_LANG_NAMES[lang]})' for lang in want)}\n\n"
        'Reply with JSON only: {"title": {"<lang>": "..."}, "description": {"<lang>": "..."}} '
        "covering exactly the languages needed."
    )
    result = llm.chat([
        Message(role="system", content="You are a precise localization assistant. Output JSON only."),
        Message(role="user", content=prompt),
    ])
    if not getattr(result, "success", False) or result.message is None:
        raise RuntimeError(getattr(result, "error", None) or "translation failed")
    data = _extract_json(result.message.content or "")
    if data is None:
        raise RuntimeError("translation returned no JSON")
    got_title = _clean_map(data.get("title"))
    got_desc = _clean_map(data.get("description"))
    for lang in want:
        if not meta.title.get(lang) and got_title.get(lang):
            meta.title[lang] = got_title[lang]
        if not meta.description.get(lang) and got_desc.get(lang):
            meta.description[lang] = got_desc[lang]
    return meta


def adapter_for_preset(preset_id: str | None = None) -> Any:
    """The configured model as an LLM adapter: the given preset, else the
    user's creation provider (what build mode already uses)."""
    from neonrp.core.config import _parse_config, resolve_provider
    from neonrp.core.llm import get_adapter, get_adapter_from_config
    from neonrp.presets import build_config_dict, get_create_provider, resolve_creation_provider

    pid = preset_id or get_create_provider()
    if pid:
        try:
            cfg = _parse_config(build_config_dict(pid))
            return get_adapter_from_config(resolve_provider(cfg))
        except Exception:
            if preset_id:
                raise
    resolved = resolve_creation_provider()
    if not resolved:
        raise RuntimeError("no model configured — pick one in settings (/auth) first")
    base_url, model, api_key = resolved
    return get_adapter("openai", api_key=api_key, model=model, base_url=base_url)
