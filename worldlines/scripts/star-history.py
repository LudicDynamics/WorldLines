#!/usr/bin/env python3
"""Generate the Star History chart as self-hosted SVGs.

Fetches stargazer timestamps via the GitHub CLI (needs `gh auth login`)
and renders assets/star-history-{light,dark}.svg — no third-party chart
service involved. Re-run any time to refresh:

    python3 scripts/star-history.py
"""

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

REPO = "LudicDynamics/WorldLines"
OUT = Path(__file__).resolve().parent.parent / "assets"
W, H = 760, 380
ML, MR, MT, MB = 56, 24, 46, 44  # margins
PURPLE = "#8b5cf6"

THEMES = {
    "light": {"bg": "#ffffff", "fg": "#111111", "grid": "#e6e6ef", "dim": "#8a8aa0"},
    "dark": {"bg": "#0d1117", "fg": "#e6e6ef", "grid": "#23262f", "dim": "#8a8aa0"},
}


def fetch_starred_at():
    out = subprocess.run(
        ["gh", "api", "--paginate", f"repos/{REPO}/stargazers?per_page=100",
         "-H", "Accept: application/vnd.github.star+json", "--jq", ".[].starred_at"],
        capture_output=True, text=True, check=True).stdout.split()
    times = sorted(datetime.fromisoformat(t.replace("Z", "+00:00")) for t in out)
    return times


def render(times, theme_name):
    t = THEMES[theme_name]
    n = len(times)
    t0, t1 = times[0], datetime.now(timezone.utc)
    span = max((t1 - t0).total_seconds(), 1)
    y_max = max(n, 1) * 1.15

    def x(dt):
        return ML + (W - ML - MR) * (dt - t0).total_seconds() / span

    def y(count):
        return H - MB - (H - MT - MB) * count / y_max

    # step polyline through (time_i, i+1)
    pts = [(ML, y(0))]
    for i, dt in enumerate(times):
        px = x(dt)
        pts.append((px, pts[-1][1]))
        pts.append((px, y(i + 1)))
    pts.append((W - MR, y(n)))
    line = " ".join(f"{px:.1f},{py:.1f}" for px, py in pts)
    area = f"{ML:.1f},{y(0):.1f} " + line + f" {W - MR:.1f},{y(0):.1f}"

    # y grid: ~5 lines at nice ints
    step = max(1, round(y_max / 5))
    grid, labels = [], []
    c = 0
    while c <= y_max:
        gy = y(c)
        grid.append(f'<line x1="{ML}" y1="{gy:.1f}" x2="{W-MR}" y2="{gy:.1f}" stroke="{t["grid"]}" stroke-width="1"/>')
        labels.append(f'<text x="{ML-8}" y="{gy+4:.1f}" text-anchor="end" font-size="11" fill="{t["dim"]}">{c}</text>')
        c += step

    # x labels: first, middle, today
    xticks = []
    for dt in [t0, t0 + (t1 - t0) / 2, t1]:
        xticks.append(f'<text x="{x(dt):.1f}" y="{H-MB+18}" text-anchor="middle" font-size="11" fill="{t["dim"]}">{dt.strftime("%b %d, %Y")}</text>')

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-family="-apple-system,'Segoe UI',Helvetica,Arial,sans-serif">
  <rect width="{W}" height="{H}" rx="10" fill="{t["bg"]}"/>
  <text x="{ML}" y="26" font-size="14" font-weight="600" fill="{t["fg"]}">{REPO} — GitHub stars</text>
  <text x="{W-MR}" y="26" text-anchor="end" font-size="12" fill="{t["dim"]}">updated {t1.strftime("%Y-%m-%d")}</text>
  {"".join(grid)}
  {"".join(labels)}
  {"".join(xticks)}
  <polygon points="{area}" fill="{PURPLE}" opacity="0.12"/>
  <polyline points="{line}" fill="none" stroke="{PURPLE}" stroke-width="2.5" stroke-linejoin="round"/>
  <circle cx="{x(times[-1]):.1f}" cy="{y(n):.1f}" r="4.5" fill="{PURPLE}"/>
  <text x="{x(times[-1])-10:.1f}" y="{y(n)-10:.1f}" text-anchor="end" font-size="13" font-weight="700" fill="{t["fg"]}">{n} ★</text>
</svg>'''
    OUT.mkdir(exist_ok=True)
    path = OUT / f"star-history-{theme_name}.svg"
    path.write_text(svg)
    print(f"wrote {path} ({n} stars)")


if __name__ == "__main__":
    times = fetch_starred_at()
    for name in THEMES:
        render(times, name)
