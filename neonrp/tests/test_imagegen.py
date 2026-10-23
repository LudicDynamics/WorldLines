"""Tests for the ComfyUI image backend, focused on custom-workflow support."""

import json
from pathlib import Path

import pytest

from neonrp.core import imagegen
from neonrp.core.imagegen import (
    ImageConfig,
    QUALITY_PREFIX,
    NEGATIVE,
    _build_custom_workflow,
    _generate_comfyui,
    load_image_config,
    save_image_config,
)


# A minimal valid ComfyUI API-format workflow with distinct node ids so we
# can assert injections land on the right nodes.
def _sample_workflow() -> dict:
    return {
        "ckpt": {"class_type": "CheckpointLoaderSimple",
                 "inputs": {"ckpt_name": "model.safetensors"}},
        "pos": {"class_type": "CLIPTextEncode",
                "inputs": {"text": "PLACEHOLDER", "clip": ["ckpt", 1]}},
        "neg": {"class_type": "CLIPTextEncode",
                "inputs": {"text": "PLACEHOLDER", "clip": ["ckpt", 1]}},
        "sampler": {"class_type": "KSampler",
                    "inputs": {"seed": 0, "steps": 20, "model": ["ckpt", 0]}},
        "save": {"class_type": "SaveImage",
                 "inputs": {"filename_prefix": "x", "images": ["sampler", 0]}},
    }


class TestBuildCustomWorkflow:
    """_build_custom_workflow injection + graceful fallback."""

    def test_injects_prompt_neg_and_seed_from_inline_json(self):
        wf_json = json.dumps(_sample_workflow())
        cfg = ImageConfig(
            backend="comfyui",
            comfyui_url="http://x:8188",
            comfyui_workflow=wf_json,
            comfyui_input_node="pos",
            comfyui_neg_node="neg",
            comfyui_seed_node="sampler",
        )
        wf = _build_custom_workflow("a cat", cfg, seed=12345)

        assert wf is not None
        # Positive prompt gets the quality prefix prepended.
        assert wf["pos"]["inputs"]["text"] == QUALITY_PREFIX + "a cat"
        # Negative prompt injected.
        assert wf["neg"]["inputs"]["text"] == NEGATIVE
        # Seed injected into the "seed" key (present in sampler).
        assert wf["sampler"]["inputs"]["seed"] == 12345

    def test_seed_uses_noise_seed_when_present(self):
        base = _sample_workflow()
        del base["sampler"]["inputs"]["seed"]
        base["sampler"]["inputs"]["noise_seed"] = 0
        cfg = ImageConfig(
            comfyui_workflow=json.dumps(base),
            comfyui_input_node="pos",
            comfyui_seed_node="sampler",
        )
        wf = _build_custom_workflow("x", cfg, seed=99)
        assert wf["sampler"]["inputs"]["noise_seed"] == 99
        assert "seed" not in wf["sampler"]["inputs"]

    def test_does_not_mutate_source_file(self, tmp_path: Path):
        wf_path = tmp_path / "wf.json"
        wf_path.write_text(json.dumps(_sample_workflow()), encoding="utf-8")
        cfg = ImageConfig(
            comfyui_workflow=str(wf_path),
            comfyui_input_node="pos",
        )
        _build_custom_workflow("x", cfg, seed=1)
        # File untouched; deep copy means injection did not bleed through.
        reloaded = json.loads(wf_path.read_text(encoding="utf-8"))
        assert reloaded["pos"]["inputs"]["text"] == "PLACEHOLDER"

    def test_loads_from_file_path_with_tilde_expansion(self, tmp_path: Path, monkeypatch):
        home = tmp_path / "home"
        home.mkdir()
        # ``Path.expanduser`` reads HOME on POSIX but USERPROFILE on Windows —
        # set both so the test home drives ``~`` on either platform (the Windows
        # CI runner fails with only HOME set).
        monkeypatch.setenv("HOME", str(home))
        monkeypatch.setenv("USERPROFILE", str(home))
        wf_path = home / "wf.json"
        wf_path.write_text(json.dumps(_sample_workflow()), encoding="utf-8")
        cfg = ImageConfig(comfyui_workflow="~/wf.json", comfyui_input_node="pos")
        wf = _build_custom_workflow("dog", cfg, seed=1)
        assert wf is not None
        assert wf["pos"]["inputs"]["text"] == QUALITY_PREFIX + "dog"

    def test_missing_input_node_falls_back(self):
        cfg = ImageConfig(
            comfyui_workflow=json.dumps(_sample_workflow()),
            comfyui_input_node="nonexistent",
        )
        assert _build_custom_workflow("x", cfg, seed=1) is None

    def test_empty_input_node_falls_back(self):
        cfg = ImageConfig(
            comfyui_workflow=json.dumps(_sample_workflow()),
            comfyui_input_node="",
        )
        assert _build_custom_workflow("x", cfg, seed=1) is None

    def test_invalid_json_falls_back(self):
        cfg = ImageConfig(comfyui_workflow="{not json", comfyui_input_node="pos")
        assert _build_custom_workflow("x", cfg, seed=1) is None

    def test_missing_neg_and_seed_nodes_are_skipped_not_fatal(self):
        cfg = ImageConfig(
            comfyui_workflow=json.dumps(_sample_workflow()),
            comfyui_input_node="pos",
            comfyui_neg_node="missing-neg",
            comfyui_seed_node="missing-seed",
        )
        wf = _build_custom_workflow("x", cfg, seed=1)
        # Input still injected; missing optional nodes just warn.
        assert wf is not None
        assert wf["pos"]["inputs"]["text"] == QUALITY_PREFIX + "x"


class _FakeComfy:
    """Captures the posted workflow + serves a canned history reply."""

    def __init__(self, *, output_node: str = "save"):
        self.posted_workflow = None
        self._output_node = output_node

    def post(self, url, path, payload, *, timeout=90.0):
        assert path == "/prompt"
        self.posted_workflow = payload["prompt"]
        return {"prompt_id": "pid-1"}

    def get(self, url, path, *, timeout=90.0):
        if path.startswith("/history/"):
            return json.dumps({
                "pid-1": {"outputs": {
                    self._output_node: {"images": [
                        {"filename": "out.png", "subfolder": "", "type": "output"}
                    ]},
                }},
            }).encode()
        if path.startswith("/view"):
            return b"PNGDATA"
        raise AssertionError(f"unexpected GET {path}")


def _patch_http(monkeypatch, fake: _FakeComfy):
    monkeypatch.setattr(imagegen, "_comfy_post", fake.post)
    monkeypatch.setattr(imagegen, "_comfy_get", fake.get)


class TestGenerateComfyuiWiring:
    """End-to-end of _generate_comfyui with HTTP mocked (no real ComfyUI)."""

    def test_custom_workflow_posted_and_output_node_read(self, tmp_path: Path, monkeypatch):
        fake = _FakeComfy(output_node="save")
        _patch_http(monkeypatch, fake)
        cfg = ImageConfig(
            backend="comfyui",
            comfyui_url="http://x:8188",
            comfyui_workflow=json.dumps(_sample_workflow()),
            comfyui_input_node="pos",
            comfyui_neg_node="neg",
            comfyui_output_node="save",
            comfyui_seed_node="sampler",
        )
        out = _generate_comfyui(
            "hero", tmp_path, cfg,
            width=512, height=512, seed=7,
            steps=20, guidance=6.0,
            poll_interval=0.0, timeout=5.0,
        )
        # The custom graph was posted (has our node ids), not the built-in one.
        assert "pos" in fake.posted_workflow
        assert "4" not in fake.posted_workflow  # built-in node id absent
        assert fake.posted_workflow["pos"]["inputs"]["text"] == QUALITY_PREFIX + "hero"
        assert fake.posted_workflow["sampler"]["inputs"]["seed"] == 7
        assert out.read_bytes() == b"PNGDATA"

    def test_missing_input_node_falls_back_to_builtin(self, tmp_path: Path, monkeypatch):
        # Built-in workflow writes to SaveImage node "9".
        fake = _FakeComfy(output_node="9")
        _patch_http(monkeypatch, fake)
        cfg = ImageConfig(
            backend="comfyui",
            comfyui_url="http://x:8188",
            comfyui_workflow=json.dumps(_sample_workflow()),
            comfyui_input_node="does-not-exist",
        )
        out = _generate_comfyui(
            "hero", tmp_path, cfg,
            width=512, height=512, seed=7,
            steps=20, guidance=6.0,
            poll_interval=0.0, timeout=5.0,
        )
        # Built-in graph posted: classic node ids present.
        assert set(fake.posted_workflow) == {"3", "4", "5", "6", "7", "8", "9"}
        assert fake.posted_workflow["6"]["inputs"]["text"] == QUALITY_PREFIX + "hero"
        assert out.read_bytes() == b"PNGDATA"

    def test_empty_config_uses_builtin_unchanged(self, tmp_path: Path, monkeypatch):
        fake = _FakeComfy(output_node="9")
        _patch_http(monkeypatch, fake)
        cfg = ImageConfig(backend="comfyui", comfyui_url="http://x:8188")
        _generate_comfyui(
            "hero", tmp_path, cfg,
            width=640, height=480, seed=42,
            steps=24, guidance=6.0,
            poll_interval=0.0, timeout=5.0,
        )
        wf = fake.posted_workflow
        assert set(wf) == {"3", "4", "5", "6", "7", "8", "9"}
        assert wf["5"]["inputs"] == {"width": 640, "height": 480, "batch_size": 1}
        assert wf["3"]["inputs"]["seed"] == 42
        assert wf["6"]["inputs"]["text"] == QUALITY_PREFIX + "hero"
        assert wf["7"]["inputs"]["text"] == NEGATIVE


class TestImageConfigRoundTrip:
    """load/save_image_config round-trips the new comfyui_* keys."""

    @pytest.fixture
    def isolated_config(self, tmp_path: Path, monkeypatch):
        path = tmp_path / "config.json"
        # Patch the path the user_config helpers actually read/write.
        import neonrp.core.user_config as uc
        monkeypatch.setattr(uc, "USER_CONFIG_PATH", path)
        return path

    def test_round_trip_new_keys(self, isolated_config):
        cfg = ImageConfig(
            backend="comfyui",
            comfyui_url="http://x:8188",
            comfyui_workflow="~/wf.json",
            comfyui_input_node="6",
            comfyui_neg_node="7",
            comfyui_output_node="9",
            comfyui_seed_node="3",
        )
        save_image_config(cfg)
        loaded = load_image_config()
        assert loaded.comfyui_workflow == "~/wf.json"
        assert loaded.comfyui_input_node == "6"
        assert loaded.comfyui_neg_node == "7"
        assert loaded.comfyui_output_node == "9"
        assert loaded.comfyui_seed_node == "3"

    def test_defaults_when_keys_absent(self, isolated_config):
        save_image_config(ImageConfig(backend="comfyui", comfyui_url="http://x:8188"))
        loaded = load_image_config()
        assert loaded.comfyui_workflow == ""
        assert loaded.comfyui_input_node == ""
        assert loaded.comfyui_neg_node == ""
        assert loaded.comfyui_output_node == ""
        assert loaded.comfyui_seed_node == ""
