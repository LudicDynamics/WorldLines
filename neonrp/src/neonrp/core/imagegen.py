"""Text→image backends for NeonRP.

Two backends, both optional; whichever is configured wins:

  - ComfyUI (local, no API billing). Config:
        image.backend = "comfyui"
        image.comfyui_url = "http://192.168.x.x:8188"
        image.comfyui_ckpt = "animagineXL31.safetensors"  (optional)

    A user-supplied custom workflow can override the built-in graph
    (all optional; empty = built-in default, current behavior):
        image.comfyui_workflow = "~/wf.json"   path to a ComfyUI
            **API-format** workflow JSON (``~`` is expanded), OR an inline
            JSON string. On any load/validation failure the code logs a
            warning and falls back to the built-in workflow, so generation
            never hard-crashes.
        image.comfyui_input_node = "6"   node id whose inputs.text gets the
            (QUALITY_PREFIX-prefixed) positive prompt. Required when a
            custom workflow is set; if missing from the graph the code
            falls back to the built-in workflow.
        image.comfyui_neg_node = "7"     (optional) node id whose
            inputs.text gets the negative prompt.
        image.comfyui_output_node = "9"  (optional) node id to read the
            image from; empty = auto-detect first node that produced images
            (current behavior).
        image.comfyui_seed_node = "3"    (optional) node id to inject the
            seed into (uses "seed" if present, else "noise_seed").

  - OpenAI Images API. Config:
        image.backend = "openai"
        image.openai_key = "sk-..."
        image.openai_model = "gpt-image-2"  (optional)

  - Codex CLI (uses the local ``codex`` login's built-in image generation,
    no API key in NeonRP). Config:
        image.backend = "codex"
        image.codex_bin = "codex"          (optional; path to the binary)

``generate_image`` is text→image. ``edit_image`` takes reference images too
(a layout guide for maps, style references for portraits) — that is what keeps
a generated map aligned with the world's file coordinates (see worldmap.py).

Configuration lives under the ``image`` key of ``~/.neonrp/config.json``
and is managed from the settings TUI (see settings_flow.py). Settings the
user has never touched return defaults from the helpers below — there is
no separate "factory" file.

The ComfyUI client is intentionally stdlib-only (urllib) so the base
NeonRP install stays light. OpenAI image-gen uses the existing ``openai``
SDK that is already a dep.
"""

from __future__ import annotations

import copy
import json
import logging
import os
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from neonrp.core.user_config import load_user_config, save_user_config

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

@dataclass
class ImageConfig:
    backend: str = ""              # "" | "comfyui" | "openai" | "codex"
    comfyui_url: str = ""
    comfyui_ckpt: str = "animagineXL31.safetensors"
    # Optional user-supplied custom workflow (empty = built-in default).
    comfyui_workflow: str = ""     # path to API-format JSON, or inline JSON
    comfyui_input_node: str = ""   # node id receiving the positive prompt
    comfyui_neg_node: str = ""     # node id receiving the negative prompt
    comfyui_output_node: str = ""  # node id to read the image from
    comfyui_seed_node: str = ""    # node id to inject the seed into
    openai_key: str = ""
    openai_model: str = "gpt-image-2"
    codex_bin: str = "codex"

    @property
    def is_configured(self) -> bool:
        if self.backend == "comfyui":
            return bool(self.comfyui_url)
        if self.backend == "openai":
            return bool(self.openai_key or os.environ.get("OPENAI_API_KEY"))
        if self.backend == "codex":
            import shutil

            return shutil.which(self.codex_bin or "codex") is not None
        return False


def load_image_config() -> ImageConfig:
    data = load_user_config()
    img = data.get("image") if isinstance(data.get("image"), dict) else {}
    return ImageConfig(
        backend=str(img.get("backend") or "").strip().lower(),
        comfyui_url=str(img.get("comfyui_url") or "").strip(),
        comfyui_ckpt=str(img.get("comfyui_ckpt") or "animagineXL31.safetensors").strip(),
        comfyui_workflow=str(img.get("comfyui_workflow") or "").strip(),
        comfyui_input_node=str(img.get("comfyui_input_node") or "").strip(),
        comfyui_neg_node=str(img.get("comfyui_neg_node") or "").strip(),
        comfyui_output_node=str(img.get("comfyui_output_node") or "").strip(),
        comfyui_seed_node=str(img.get("comfyui_seed_node") or "").strip(),
        openai_key=str(img.get("openai_key") or "").strip(),
        openai_model=str(img.get("openai_model") or "gpt-image-2").strip(),
        codex_bin=str(img.get("codex_bin") or "codex").strip(),
    )


def save_image_config(cfg: ImageConfig) -> None:
    data = load_user_config()
    image = data.get("image") if isinstance(data.get("image"), dict) else {}
    image["backend"] = cfg.backend
    if cfg.comfyui_url:
        image["comfyui_url"] = cfg.comfyui_url
    if cfg.comfyui_ckpt:
        image["comfyui_ckpt"] = cfg.comfyui_ckpt
    # Custom-workflow fields are optional: write when set, REMOVE when cleared
    # so emptying a field in Settings actually reverts to the built-in graph
    # (otherwise a stale value would linger in the config).
    for _field in (
        "comfyui_workflow", "comfyui_input_node", "comfyui_neg_node",
        "comfyui_output_node", "comfyui_seed_node",
    ):
        _val = getattr(cfg, _field)
        if _val:
            image[_field] = _val
        else:
            image.pop(_field, None)
    if cfg.openai_key:
        image["openai_key"] = cfg.openai_key
    if cfg.openai_model:
        image["openai_model"] = cfg.openai_model
    if cfg.codex_bin and cfg.codex_bin != "codex":
        image["codex_bin"] = cfg.codex_bin
    else:
        image.pop("codex_bin", None)
    data["image"] = image
    save_user_config(data)


def update_image_field(field: str, value: str) -> ImageConfig:
    cfg = load_image_config()
    if hasattr(cfg, field):
        setattr(cfg, field, value)
        save_image_config(cfg)
    return cfg


# ---------------------------------------------------------------------------
# ComfyUI client (stdlib only)
# ---------------------------------------------------------------------------

QUALITY_PREFIX = "masterpiece, best quality, very aesthetic, absurdres, "
NEGATIVE = (
    "lowres, (bad), text, error, fewer, extra, missing, worst quality, "
    "jpeg artifacts, low quality, watermark, unfinished, displeasing"
)


def _comfy_post(url: str, path: str, payload: dict, *, timeout: float = 90.0) -> dict:
    req = urllib.request.Request(
        f"{url}{path}",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def _comfy_get(url: str, path: str, *, timeout: float = 90.0) -> bytes:
    with urllib.request.urlopen(f"{url}{path}", timeout=timeout) as r:
        return r.read()


def _build_workflow(prompt: str, *, ckpt: str, width: int, height: int,
                    seed: int, steps: int, cfg: float) -> dict:
    pos = QUALITY_PREFIX + prompt.strip().replace("\n", " ")
    return {
        "4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": ckpt}},
        "5": {"class_type": "EmptyLatentImage",
              "inputs": {"width": width, "height": height, "batch_size": 1}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": pos, "clip": ["4", 1]}},
        "7": {"class_type": "CLIPTextEncode", "inputs": {"text": NEGATIVE, "clip": ["4", 1]}},
        "3": {"class_type": "KSampler", "inputs": {
            "seed": seed, "steps": steps, "cfg": cfg,
            "sampler_name": "euler_ancestral", "scheduler": "normal",
            "denoise": 1.0, "model": ["4", 0],
            "positive": ["6", 0], "negative": ["7", 0],
            "latent_image": ["5", 0],
        }},
        "8": {"class_type": "VAEDecode", "inputs": {"samples": ["3", 0], "vae": ["4", 2]}},
        "9": {"class_type": "SaveImage",
              "inputs": {"filename_prefix": "neonrp", "images": ["8", 0]}},
    }


def _load_custom_workflow(spec: str) -> dict | None:
    """Load a user-supplied ComfyUI API-format workflow.

    ``spec`` is either a path to a JSON file (``~`` expanded) or an inline
    JSON string. Returns the parsed dict, or ``None`` on any failure (the
    caller then falls back to the built-in workflow).
    """
    spec = spec.strip()
    if not spec:
        return None
    raw: str | None = None
    try:
        is_file = False
        if "\n" not in spec and len(spec) < 4096:
            # Only treat short, single-line specs as candidate paths; an
            # inline JSON blob can exceed the OS filename length limit and
            # make is_file() raise, so we never stat() those.
            try:
                is_file = Path(spec).expanduser().is_file()
            except OSError:
                is_file = False
        if is_file:
            raw = Path(spec).expanduser().read_text(encoding="utf-8")
        else:
            raw = spec
        data = json.loads(raw)
    except (OSError, ValueError) as exc:
        logger.warning("comfyui_workflow could not be loaded (%s); "
                       "falling back to built-in workflow", exc)
        return None
    if not isinstance(data, dict):
        logger.warning("comfyui_workflow is not a JSON object; "
                       "falling back to built-in workflow")
        return None
    return data


def _inject_seed(node: dict, seed: int) -> None:
    inputs = node.setdefault("inputs", {})
    if "seed" in inputs:
        inputs["seed"] = seed
    elif "noise_seed" in inputs:
        inputs["noise_seed"] = seed
    else:
        inputs["seed"] = seed


def _build_custom_workflow(prompt: str, cfg: ImageConfig, *, seed: int) -> dict | None:
    """Build a posted workflow dict from a user-supplied custom workflow.

    Returns ``None`` to signal a graceful fall-back to the built-in graph
    (unloadable workflow, or the configured input node is absent).
    """
    base_wf = _load_custom_workflow(cfg.comfyui_workflow)
    if base_wf is None:
        return None

    input_node = cfg.comfyui_input_node.strip()
    if not input_node or input_node not in base_wf:
        logger.warning("comfyui_input_node %r not found in custom workflow; "
                       "falling back to built-in workflow", input_node)
        return None

    wf = copy.deepcopy(base_wf)
    pos = QUALITY_PREFIX + prompt.strip().replace("\n", " ")
    wf[input_node].setdefault("inputs", {})["text"] = pos

    neg_node = cfg.comfyui_neg_node.strip()
    if neg_node:
        if neg_node in wf:
            wf[neg_node].setdefault("inputs", {})["text"] = NEGATIVE
        else:
            logger.warning("comfyui_neg_node %r not found in custom workflow; "
                           "skipping negative prompt injection", neg_node)

    seed_node = cfg.comfyui_seed_node.strip()
    if seed_node:
        if seed_node in wf:
            _inject_seed(wf[seed_node], seed)
        else:
            logger.warning("comfyui_seed_node %r not found in custom workflow; "
                           "skipping seed injection", seed_node)

    return wf


def _read_image_info(outputs: dict, output_node: str) -> dict:
    """Find the image descriptor in a ComfyUI history ``outputs`` block.

    If ``output_node`` is set, read its ``images``; otherwise auto-detect
    the first node that produced images.
    """
    images: list = []
    if output_node:
        images = outputs.get(output_node, {}).get("images", [])
    else:
        for node_out in outputs.values():
            if isinstance(node_out, dict) and node_out.get("images"):
                images = node_out["images"]
                break
    if not images:
        raise RuntimeError("ComfyUI finished but produced no image")
    return images[0]


def _generate_comfyui(prompt: str, out_dir: Path, cfg: ImageConfig, *,
                      width: int, height: int, seed: int | None,
                      steps: int, guidance: float,
                      poll_interval: float, timeout: float) -> Path:
    base = cfg.comfyui_url.rstrip("/")
    if not base:
        raise RuntimeError("comfyui_url not configured")
    if seed is None:
        seed = uuid.uuid4().int % (2**31)

    client_id = uuid.uuid4().hex
    workflow = None
    output_node = ""
    if cfg.comfyui_workflow.strip():
        workflow = _build_custom_workflow(prompt, cfg, seed=seed)
        if workflow is not None:
            output_node = cfg.comfyui_output_node.strip()
    if workflow is None:
        workflow = _build_workflow(
            prompt, ckpt=cfg.comfyui_ckpt or "animagineXL31.safetensors",
            width=width, height=height, seed=seed, steps=steps, cfg=guidance,
        )
        output_node = "9"
    resp = _comfy_post(base, "/prompt", {"prompt": workflow, "client_id": client_id})
    prompt_id = resp["prompt_id"]

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            hist = json.loads(_comfy_get(base, f"/history/{prompt_id}"))
        except urllib.error.URLError:
            time.sleep(poll_interval)
            continue
        if prompt_id in hist:
            outputs = hist[prompt_id]["outputs"]
            info = _read_image_info(outputs, output_node)
            qs = (
                f"/view?filename={info['filename']}"
                f"&subfolder={info.get('subfolder', '')}"
                f"&type={info.get('type', 'output')}"
            )
            data = _comfy_get(base, qs)
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = out_dir / f"{stamp}-comfy.png"
            out_path.write_bytes(data)
            return out_path
        time.sleep(poll_interval)
    raise TimeoutError(f"ComfyUI job {prompt_id} did not finish in {timeout}s")


# ---------------------------------------------------------------------------
# OpenAI Images
# ---------------------------------------------------------------------------

def _generate_openai(prompt: str, out_dir: Path, cfg: ImageConfig, *,
                     size: str) -> Path:
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("openai package not installed") from exc
    import base64

    key = cfg.openai_key or os.environ.get("OPENAI_API_KEY", "")
    if not key:
        raise RuntimeError("openai_key not configured and OPENAI_API_KEY not set")

    client = OpenAI(api_key=key)
    resp = client.images.generate(
        model=cfg.openai_model or "gpt-image-2",
        prompt=prompt,
        size=size,
        quality="high",
        n=1,
    )
    data = resp.data[0]
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{stamp}-openai.png"
    if getattr(data, "b64_json", None):
        out_path.write_bytes(base64.b64decode(data.b64_json))
    elif getattr(data, "url", None):
        with urllib.request.urlopen(data.url) as r:
            out_path.write_bytes(r.read())
    else:
        raise RuntimeError("OpenAI image response had neither b64_json nor url")
    return out_path


# ---------------------------------------------------------------------------
# Reference-guided generation (maps from layout guides, style-matched portraits)
# ---------------------------------------------------------------------------

def _edit_openai(prompt: str, images: list[Path], out_path: Path, cfg: ImageConfig, *,
                 size: str, background: str) -> Path:
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("openai package not installed") from exc
    import base64

    key = cfg.openai_key or os.environ.get("OPENAI_API_KEY", "")
    if not key:
        raise RuntimeError("openai_key not configured and OPENAI_API_KEY not set")
    client = OpenAI(api_key=key)
    handles = [open(p, "rb") for p in images]
    try:
        kwargs: dict[str, Any] = dict(
            model=cfg.openai_model or "gpt-image-2", image=handles, prompt=prompt,
            size=size, quality="high", n=1,
        )
        if background == "transparent":
            kwargs["background"] = "transparent"
        resp = client.images.edit(**kwargs)
    finally:
        for h in handles:
            h.close()
    data = resp.data[0]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if getattr(data, "b64_json", None):
        out_path.write_bytes(base64.b64decode(data.b64_json))
    elif getattr(data, "url", None):
        with urllib.request.urlopen(data.url) as r:
            out_path.write_bytes(r.read())
    else:
        raise RuntimeError("OpenAI image response had neither b64_json nor url")
    return out_path


def _codex_generated_dir() -> Path:
    return Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")) / "generated_images"


def _edit_codex(prompt: str, images: list[Path], out_path: Path, cfg: ImageConfig, *,
                size: str, background: str, timeout: float) -> Path:
    """Drive the Codex CLI's built-in image generation non-interactively.

    Codex keeps what it generates under ``~/.codex/generated_images``; we ask it
    to copy the result to ``out_path`` and, if it forgets, pick up the newest
    image it produced during this call.
    """
    import shutil
    import subprocess

    exe = shutil.which(cfg.codex_bin or "codex")
    if not exe:
        raise RuntimeError("codex CLI not found (install Codex or set image.codex_bin)")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    started = time.time()
    instr = (
        "Use your image generation tool (do not write code to draw it). "
        + prompt
        + f"\nTarget size {size}"
        + (", fully transparent background (PNG with alpha)" if background == "transparent" else "")
        + f". When done, copy the generated image file to {out_path} and reply only with that path."
    )
    cmd = [exe, "exec", "--skip-git-repo-check", "--sandbox", "workspace-write",
           "-C", str(out_path.parent)]
    for img in images:
        cmd += ["-i", str(img)]
    proc = subprocess.run(cmd, input=instr, text=True, capture_output=True, timeout=timeout)
    if out_path.is_file() and out_path.stat().st_mtime >= started - 1:
        return out_path
    gen = _codex_generated_dir()
    fresh = sorted(
        (p for p in gen.rglob("*.png") if p.stat().st_mtime >= started),
        key=lambda p: p.stat().st_mtime,
    ) if gen.is_dir() else []
    if fresh:
        shutil.copyfile(fresh[-1], out_path)
        return out_path
    tail = (proc.stdout or proc.stderr or "")[-300:]
    raise RuntimeError(f"codex produced no image (exit {proc.returncode}): {tail}")


def edit_image(
    prompt: str,
    images: list[Path],
    out_path: Path,
    *,
    cfg: ImageConfig | None = None,
    width: int = 1536,
    height: int = 1024,
    background: str = "auto",
    timeout: float = 600.0,
) -> Path:
    """Reference-guided generation → ``out_path`` (PNG).

    ``images`` are references the model must follow: a layout guide (maps) or
    style references (portraits). Supported by the ``openai`` and ``codex``
    backends; ComfyUI falls back to plain text→image (references ignored).
    """
    cfg = cfg or load_image_config()
    size = f"{width}x{height}"
    if cfg.backend == "openai":
        return _edit_openai(prompt, images, out_path, cfg, size=size, background=background)
    if cfg.backend == "codex":
        return _edit_codex(prompt, images, out_path, cfg, size=size,
                           background=background, timeout=timeout)
    if cfg.backend == "comfyui":
        import shutil
        tmp = generate_image(prompt, out_path.parent / ".tmp-imagegen", cfg=cfg,
                             width=width, height=height)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(tmp), out_path)
        return out_path
    raise RuntimeError("No image backend configured. Open settings → Image generation.")


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def generate_image(
    prompt: str,
    out_dir: Path,
    *,
    cfg: ImageConfig | None = None,
    width: int = 1024,
    height: int = 1024,
    seed: int | None = None,
    steps: int = 24,
    guidance: float = 6.0,
    poll_interval: float = 1.0,
    timeout: float = 240.0,
) -> Path:
    """Run text→image with the configured backend; return the saved PNG path.

    Raises RuntimeError if no backend is configured. Callers should
    surface the error to the user with a "go configure it in settings"
    hint (the settings flow is the only way to wire it up).
    """
    cfg = cfg or load_image_config()
    if cfg.backend == "comfyui":
        return _generate_comfyui(
            prompt, out_dir, cfg,
            width=width, height=height, seed=seed,
            steps=steps, guidance=guidance,
            poll_interval=poll_interval, timeout=timeout,
        )
    if cfg.backend == "openai":
        return _generate_openai(prompt, out_dir, cfg, size=f"{width}x{height}")
    if cfg.backend == "codex":
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        return _edit_codex(prompt, [], out_dir / f"{stamp}-codex.png", cfg,
                           size=f"{width}x{height}", background="auto", timeout=timeout * 2.5)
    raise RuntimeError(
        "No image backend configured. Open settings → Image generation."
    )


def test_backend(cfg: ImageConfig | None = None) -> dict[str, Any]:
    """Cheap ping that proves the backend is reachable.

    For ComfyUI: HTTP GET /system_stats. For OpenAI: client constructor
    plus a key-shape sanity check (no actual generation — that costs $$).
    Returns ``{"ok": bool, "backend": str, "detail": str}``.
    """
    cfg = cfg or load_image_config()
    if cfg.backend == "comfyui":
        if not cfg.comfyui_url:
            return {"ok": False, "backend": "comfyui", "detail": "url not set"}
        try:
            data = _comfy_get(cfg.comfyui_url.rstrip("/"), "/system_stats", timeout=5.0)
            return {"ok": True, "backend": "comfyui", "detail": f"{len(data)}B reply"}
        except Exception as exc:
            return {"ok": False, "backend": "comfyui", "detail": str(exc)[:160]}
    if cfg.backend == "openai":
        key = cfg.openai_key or os.environ.get("OPENAI_API_KEY", "")
        if not key:
            return {"ok": False, "backend": "openai", "detail": "key not set"}
        if not key.startswith("sk-"):
            return {"ok": False, "backend": "openai",
                    "detail": "key does not look like an OpenAI key"}
        return {"ok": True, "backend": "openai", "detail": "key present"}
    if cfg.backend == "codex":
        import shutil
        exe = shutil.which(cfg.codex_bin or "codex")
        return {"ok": bool(exe), "backend": "codex",
                "detail": exe or "codex CLI not found"}
    return {"ok": False, "backend": cfg.backend or "(none)",
            "detail": "no backend configured"}
