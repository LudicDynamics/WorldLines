"""Regenerate tests/data/prompt_zh_snapshot.json (only when a zh prompt change is deliberate).

    PYTHONPATH=src:tests python tests/gen_prompt_snapshot.py [--show KEY] [--lang xx]
"""
import sys
import tempfile
from pathlib import Path

import prompt_harness as H

if __name__ == "__main__":
    lang = sys.argv[sys.argv.index("--lang") + 1] if "--lang" in sys.argv else None
    with tempfile.TemporaryDirectory() as t:
        out = H.render_all(Path(t), lang)
    if "--show" in sys.argv:
        print(out[sys.argv[sys.argv.index("--show") + 1]])
    elif lang:
        for k, v in sorted(out.items()):
            print(f"{k:28s} han={H.cjk_share(v):.2f} kana={H.script_share(v, 'kana'):.2f} hangul={H.script_share(v, 'hangul'):.2f} latin={H.script_share(v, 'latin'):.2f}")
    else:
        H.dump(Path(__file__).parent / "data" / "prompt_zh_snapshot.json", out)
        print({k: len(v) for k, v in out.items()})
