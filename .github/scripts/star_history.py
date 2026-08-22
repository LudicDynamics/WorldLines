#!/usr/bin/env python3
"""Self-hosted star-history chart for this repo.

GitHub has restricted third-party access to this repo's starred-at data, so
services like star-history.com return 403 and the README image breaks. This
script fetches stargazers with the repo's own credentials (which ARE allowed),
and renders the cumulative curve as light/dark SVGs committed to the repo.

Run locally (uses `gh` auth) or in Actions (uses GITHUB_TOKEN):
    python3 .github/scripts/star_history.py
Outputs: .github/assets/star-history-light.svg / star-history-dark.svg
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO = os.environ.get("STAR_REPO", "LudicDynamics/WorldLines")
OUT_DIR = Path(__file__).resolve().parents[1] / "assets"

# chart geometry
W, H = 800, 420
ML, MR, MT, MB = 62, 30, 64, 48   # margins: left/right/top/bottom
PW, PH = W - ML - MR, H - MT - MB

THEMES = {
    "light": {"ink": "#1f2328", "muted": "#57606a", "grid": "#d0d7de",
              "line": "#d97706", "fill": "#d97706", "fill_op": "0.08"},
    "dark":  {"ink": "#e6edf3", "muted": "#8b949e", "grid": "#30363d",
              "line": "#fbbf24", "fill": "#fbbf24", "fill_op": "0.10"},
}


def fetch_stars() -> list[datetime]:
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    dates: list[datetime] = []
    page = 1
    while True:
        url = (f"https://api.github.com/repos/{REPO}/stargazers"
               f"?per_page=100&page={page}")
        if token:
            req = urllib.request.Request(url, headers={
                "Accept": "application/vnd.github.star+json",
                "Authorization": f"Bearer {token}",
                "X-GitHub-Api-Version": "2022-11-28",
            })
            with urllib.request.urlopen(req, timeout=30) as r:
                batch = json.loads(r.read().decode())
        else:   # local convenience: piggyback on `gh` auth
            out = subprocess.run(
                ["gh", "api", f"repos/{REPO}/stargazers?per_page=100&page={page}",
                 "-H", "Accept: application/vnd.github.star+json"],
                capture_output=True, text=True, check=True).stdout
            batch = json.loads(out)
        if not batch:
            break
        for it in batch:
            ts = it.get("starred_at")
            if ts:
                dates.append(datetime.fromisoformat(ts.replace("Z", "+00:00")))
        if len(batch) < 100:
            break
        page += 1
    dates.sort()
    return dates


def render(dates: list[datetime], theme: dict) -> str:
    now = datetime.now(timezone.utc)
    if not dates:
        dates = [now]
    x0, x1 = dates[0].timestamp(), max(now.timestamp(), dates[-1].timestamp())
    span = max(1.0, x1 - x0)
    n = len(dates)

    def X(t): return ML + (t - x0) / span * PW
    ymax = max(5, n)
    # round y-max up to a friendly step so gridlines land on integers
    step = max(1, int(round(ymax / 4)))
    ymax = step * 4 if step * 4 >= ymax else step * 5
    def Y(c): return MT + PH - (c / ymax) * PH

    # cumulative step points (staircase reads truthfully for counts)
    pts = [(X(x0), Y(0))]
    for i, d in enumerate(dates, 1):
        px = X(d.timestamp())
        pts.append((px, Y(i - 1)))
        pts.append((px, Y(i)))
    pts.append((X(x1), Y(n)))
    path = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    area = (path + f" L{X(x1):.1f},{Y(0):.1f} L{ML},{Y(0):.1f} Z")

    # x ticks: ~5 evenly spaced dates
    xticks = []
    for k in range(5):
        t = x0 + span * k / 4
        xticks.append((X(t), datetime.fromtimestamp(t, timezone.utc)
                       .strftime("%b %d")))
    yticks = [step * k for k in range(0, 5) if step * k <= ymax]

    g = theme
    s = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
         f'font-family="-apple-system,Segoe UI,Helvetica,Arial,sans-serif">']
    # title + subtitle (text tokens, not series color)
    s.append(f'<text x="{ML}" y="26" font-size="16" font-weight="600" '
             f'fill="{g["ink"]}">Star History — {REPO}</text>')
    s.append(f'<text x="{ML}" y="46" font-size="12" fill="{g["muted"]}">'
             f'{n} stars · updated {now.strftime("%Y-%m-%d")} · '
             f'self-hosted (third-party star APIs are blocked for this repo)'
             f'</text>')
    # grid + y labels (recessive)
    for c in yticks:
        y = Y(c)
        s.append(f'<line x1="{ML}" y1="{y:.1f}" x2="{W-MR}" y2="{y:.1f}" '
                 f'stroke="{g["grid"]}" stroke-width="1" opacity="0.6"/>')
        s.append(f'<text x="{ML-8}" y="{y+4:.1f}" font-size="11" '
                 f'text-anchor="end" fill="{g["muted"]}">{c}</text>')
    # x labels
    for x, lab in xticks:
        s.append(f'<text x="{x:.1f}" y="{H-16}" font-size="11" '
                 f'text-anchor="middle" fill="{g["muted"]}">{lab}</text>')
    # area + line (thin marks)
    s.append(f'<path d="{area}" fill="{g["fill"]}" fill-opacity="{g["fill_op"]}"/>')
    s.append(f'<path d="{path}" fill="none" stroke="{g["line"]}" '
             f'stroke-width="2" stroke-linejoin="round"/>')
    # selective direct label at the end of the line
    ex, ey = X(x1), Y(n)
    s.append(f'<circle cx="{ex:.1f}" cy="{ey:.1f}" r="4" fill="{g["line"]}"/>')
    s.append(f'<text x="{ex-8:.1f}" y="{ey-10:.1f}" font-size="13" '
             f'font-weight="600" text-anchor="end" fill="{g["ink"]}">'
             f'★ {n}</text>')
    s.append('</svg>')
    return "\n".join(s)


def main():
    dates = fetch_stars()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for mode, theme in THEMES.items():
        (OUT_DIR / f"star-history-{mode}.svg").write_text(render(dates, theme))
    print(f"[star-history] {len(dates)} stars -> {OUT_DIR}/star-history-*.svg")


if __name__ == "__main__":
    main()
