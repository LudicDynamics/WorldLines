"""Skills for coding agents ship with the engine (10-26): one source — the workbench folder
(``worldlines/workbench/.claude/skills/<name>``; the open repo's root ``.claude/skills/<name>``) — copied into the sdist as
``_skills/<name>`` and into the wheel as ``neonrp/_skills/<name>`` by hatch_build.py. These keep the build hook, the
engine's lookup and the Codex copy pointing at that one source, byte for byte."""
from __future__ import annotations

import importlib.util
import shutil
import sys
import types

from neonrp import spec

from _paths import ENGINE_ROOT


def _hook():
    """hatch_build.py without hatchling installed (only its BuildHookInterface base is needed to import it)."""
    stub = types.ModuleType("hatchling.builders.hooks.plugin.interface")
    stub.BuildHookInterface = type("BuildHookInterface", (), {})
    names = ["hatchling", "hatchling.builders", "hatchling.builders.hooks", "hatchling.builders.hooks.plugin"]
    saved = {n: sys.modules.get(n) for n in [*names, stub.__name__]}
    for n in names:
        sys.modules.setdefault(n, types.ModuleType(n))
    sys.modules[stub.__name__] = stub
    try:
        s = importlib.util.spec_from_file_location("_hatch_build_under_test", ENGINE_ROOT / "hatch_build.py")
        mod = importlib.util.module_from_spec(s)
        s.loader.exec_module(mod)
        return mod
    finally:
        for n, m in saved.items():
            if m is None:
                sys.modules.pop(n, None)
            else:
                sys.modules[n] = m


def _tree(d):
    return {p.relative_to(d).as_posix(): p.read_bytes() for p in sorted(d.rglob("*")) if p.is_file()}


def test_build_hook_and_engine_agree_on_the_one_source():
    hook = _hook()
    assert tuple(hook.SKILLS) == tuple(spec.SKILLS)
    src = hook.skill_sources(ENGINE_ROOT)
    for name in spec.SKILLS:
        d = spec.skill_dir(name)
        assert d is not None and d.resolve() == src[name]
        assert (d / "SKILL.md").read_text(encoding="utf-8").startswith(f"---\nname: {name}\n")


def test_a_wheel_built_from_the_sdist_carries_the_same_files(tmp_path):
    hook = _hook()
    for name, d in hook.skill_sources(ENGINE_ROOT).items():
        sdist = tmp_path / "sdist"
        shutil.copytree(d, sdist / "_skills" / name)              # what the sdist step force-includes
        again = hook.skill_sources(sdist)[name]                    # what the wheel step (run inside the sdist) finds
        assert again == (sdist / "_skills" / name).resolve()
        assert _tree(again) == _tree(d)


def test_codex_copy_matches_the_claude_copy():
    """worldlines/workbench/sync.sh writes .agents/skills from .claude/skills; both reach the open repo's root."""
    for name in spec.SKILLS:
        claude = spec.skill_dir(name)
        agents = claude.parents[2] / ".agents" / "skills" / name
        assert agents.is_dir(), "run: bash worldlines/workbench/sync.sh"
        assert _tree(agents) == _tree(claude), "run: bash worldlines/workbench/sync.sh"


def test_spec_skill_command_lists_and_prints():
    from click.testing import CliRunner

    from neonrp.commands.spec_cmd import spec_cmd

    listed = CliRunner().invoke(spec_cmd, ["skill"])
    assert listed.exit_code == 0 and str(spec.skill_dir("world-creation")) in listed.output
    shown = CliRunner().invoke(spec_cmd, ["skill", "world-creation"])
    assert shown.exit_code == 0 and shown.output.startswith("---\nname: world-creation\n")
    assert CliRunner().invoke(spec_cmd, ["skill", "nope"]).exit_code != 0
