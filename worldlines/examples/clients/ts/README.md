# 灰橡宅 · TypeScript client (a small game on a WorldLines host)

A web game for a WorldLines host (`neonrp serve`): title screen, the scene behind you changing as you move, the people in
the room, a dialogue panel with the prose as it is written, d100 checks rolled on screen, clues you pick up, a map of the
house, the ending with its CG. The demo world is 灰橡宅 (pct-house); any other world plays too, with placeholders.

```
src/client.ts   the protocol — JSON-RPC 2.0 over HTTP + SSE; copy this one file into your own front end
src/host.ts     plain reads: /state (who is where) · variables · template · settlement · conditions
src/art.ts      a world's art pack (../art/<world>/art.json): which picture goes with which place / person / ending / clue
src/dice.ts     checks the narrator writes ("[调查员 侦查(…): 16 ≤ 60] → 成功") lifted out and rolled on screen
src/game.ts     the screens
```

The game knows no particular beat: names, colours, the input hint, suggestions and dividers come from the host
(`GET /api/v1/play/engine/beat-kinds`, declared by the play pack) — the open engine shows one plain turn, a release
with our planning + resolve beats shows both, with the same code.

## Run it

```bash
neonrp serve --project <a run of pct-house> --port 8788         # prints a token
npm install
WL_HOST=http://127.0.0.1:8788 npm run dev                         # → http://localhost:5180 · paste the token · 进入
```

`?world=<template id>` picks the art pack before connecting (after connecting the host's template decides).
The dev server proxies `/rpc`, `/api`, `/state` to the host (same origin: no CORS, the token rides in a header).

One line from Node, no page: `WL_HOST=… WL_TOKEN=… npm run smoke -- "Look around."`

## Art

`../art/pull.sh` copies the pictures from the asset workshop and the template, resized. Pictures not drawn yet are
listed and skipped; the game shows the world's key art (dimmed) for a room without its own, a silhouette for a person,
an icon for a clue. The prompts for the missing ones: `worldlines-assets/worlds/pct-house/GAME-CLIENT-PROMPTS.md`.
