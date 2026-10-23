---
title: "WorldLines Launcher"
description: "Double-click launcher guide — the friendliest way to start a session."
---

<!-- section: intro -->
## What the launcher does

The launcher is a self-contained file you double-click to start WorldLines. No terminal required for the first run.

Three flavors:

- `WorldLines.command` (macOS)
- `WorldLines.bat` (Windows)
- `WorldLines.sh` (Linux — run `chmod +x` first)

Download from [worldlines.gg](https://worldlines.gg) → **Quick Install**.

<!-- section: screenshots -->
## Walkthrough

📸 **Screenshots coming** — this page is a placeholder. The walkthrough will show:

1. Launch the file from Finder / Explorer / Files
2. First-run bootstrap (Python detect + install if needed)
3. Provider picker (GLM / OpenAI / LM Studio / Ollama)
4. First world selector (Stoneford by default)
5. TUI opens automatically

Screenshots are being captured on macOS / Windows / Linux and will land here shortly.

<!-- section: troubleshooting -->
## Common issues

- **macOS "unidentified developer"** — Right-click → Open instead of double-click the first time.
- **Windows SmartScreen** — Click "More info" → "Run anyway". The script is unsigned for v0.1.
- **Linux permission denied** — Run `chmod +x WorldLines.sh` once, then `./WorldLines.sh`.
- **Python not found** — The launcher auto-installs 3.12 via `uv`. If `uv` install fails, install it manually: `curl -LsSf https://astral.sh/uv/install.sh | sh`.
