# ui/ — the WorldLines web shell

The web half of the WorldLines shell. It is the interface you see when
you run `worldlines web` and open `/local`.

**This repository contains no engine.** The shell is AGPL-3.0; the NeonRP
engine it drives is Apache-2.0 and lives in its own folder (`neonrp/`). The two talk over
HTTP and nothing else — there is no shared module, no import that reaches
outside `ui/`, and no engine source to build against. That boundary is the
point: you can develop, typecheck, and build this SPA with the engine
absent, and CI does exactly that.

## The engine boundary

Every call goes to one of the three surfaces named in the engine's
`ENGINE-API-CONTRACT` (that document lives in the engine repo and is the
authority; the summary here is orientation, not a spec):

| Surface | Routes | What it covers |
|---|---|---|
| `CONTRACT-PLAY` | `/api/v1/play/*`, `/api/v1/meta` | sessions, turns, the SSE event stream, traces, rollback, portraits |
| `CONTRACT-CREATE` | `/api/v1/create/*` | the authoring workshop |
| `CONTRACT-LOCAL` | `/api/v1/local/*` | local library, settings, import, hub bridge |

These surfaces are permanent and live in the engine repo. If you find
yourself wanting something the contract does not expose, that is an engine
change, not a shell workaround.

## Layout

```
app/
  src/        the 1.0 interface — index.html, styles, page logic, live.js (engine layer), img/
  real/       engine adapter (ext / engine / link / bench)
  hub/        the new Hub mock, built to hub.html
  build.mjs   inlines everything into dist-local/index.html (+ hub.html, assets/wl/*)
e2e/          Playwright specs run against the engine-served build
e2e-legacy/   specs of the retired React shell — not run; a checklist of behaviour to re-cover
```

There is no bundler and no framework: `app/` is plain browser scripts that
`build.mjs` syntax-checks and concatenates into one page.

## Build

```bash
npm run build         # = build:local → dist-local/
```

Point the engine at it with `NEONRP_SPA_DIR=$PWD/dist-local` and open `/local`.
The engine serves `/local/*` from `index.html` and top-level files (`/hub.html`)
and `/assets/*` as static files.

## Packaging for the engine

`../scripts/package-spa.sh` builds the LocalShell in same-origin mode and
produces `dist/worldlines-spa.zip`, with the built files at the archive
root so unzipping yields a directory the engine can serve directly:

```bash
../scripts/package-spa.sh
unzip -d /tmp/worldlines-spa ../dist/worldlines-spa.zip
NEONRP_SPA_DIR=/tmp/worldlines-spa worldlines web
```

The engine resolves its shell in this order: `NEONRP_SPA_DIR` first (an
unpacked dist directory — this is the seam, and it always wins), then a
build packaged inside the wheel at `neonrp/webui/spa` (transition compat
for pre-split installs), and finally nothing — in which case the engine
runs API-only and `/local/*` returns 404 with a pointer here. A directory
without an `index.html` is ignored rather than trusted, so a half-built
`NEONRP_SPA_DIR` falls through instead of serving a broken shell.

## Tests

`npm run lint` (TypeScript only — the Playwright specs and config) and
`npx tsc -b` are clean; CI gates on both plus the build.

The Playwright suite in `e2e/` boots a real engine through
`NEONRP_E2E_SERVER` (the engine's `scripts/e2e.sh` sets it), so it needs an
engine checkout to run.

## License

AGPL-3.0-or-later, like the rest of this repository. See `../LICENSE`.
