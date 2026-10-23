"""Paths the tests share. The product's templates live in ``worldlines/templates`` — inside the dev repo
(``<repo>/worldlines``) or next to the engine in the public repo (``<repo>/neonrp`` beside ``<repo>/worldlines``)."""

from pathlib import Path

ENGINE_ROOT = Path(__file__).resolve().parents[1]
PRODUCT_TEMPLATES = next(
    (d for d in (ENGINE_ROOT / "worldlines" / "templates", ENGINE_ROOT.parent / "worldlines" / "templates") if d.is_dir()),
    ENGINE_ROOT / "worldlines" / "templates",
)
PRODUCT = PRODUCT_TEMPLATES.parent  # <…>/worldlines: its templates/, contracts/, examples/
