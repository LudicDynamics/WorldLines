# ui/ — the WorldLines web shell

The React SPA half of the WorldLines shell. It is the interface you see when
you run `neonrp web` and open `/local`, and the same codebase builds the
hosted storefront.

**This repository contains no engine.** The shell is AGPL-3.0; the NeonRP
engine it drives is proprietary and ships separately. The two talk over
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
src/
  shared/   chrome and cross-cutting concerns (auth, i18n, identity,
            registry, analytics) used by both entry points
  play/     the play surface — playClient + stage/ (transcript, input,
            map, agent lanes, replay). Shared by local and hub.
  local/    the LocalShell product: library, studio, import, settings
  hub/      the hosted storefront: catalog, detail, account, pricing
  main-local.tsx / main-hub.tsx    the two entry points
e2e/        Playwright specs — see the caveat below
```

`index.html` is shared; a Vite plugin swaps the entry script per target so
each build tree-shakes the other product's pages out.

## Develop

```bash
npm install

# Point at a local engine and start the dev server.
VITE_PLAY_ENDPOINT=http://127.0.0.1:8787 npm run dev

# The hosted storefront entry instead:
npm run dev:hub
```

`8787` is the port `neonrp web` listens on by default, so start the engine
first and the SPA will find it. Every `VITE_*` variable is optional — the
source carries localhost defaults, so a bare `npm run dev` still comes up.
`.env.example` documents all ten; copy it to `.env.development` to persist
your own. Never put a secret in one: Vite inlines every `VITE_*` value into
the shipped bundle.

## Build

Two product lines out of one source tree:

```bash
npm run build:local   # → dist-local/   LocalShell (shared + play + local)
npm run build:hub     # → dist-hub/     storefront (shared + play + hub)
```

`npm run build` is an alias for `build:local`.

### The empty-string trap

`VITE_PLAY_ENDPOINT` is three-state, and the middle state is the one that
bites:

| Value | Meaning |
|---|---|
| unset | fall back to the localhost dev default |
| **empty string** | **same-origin — fetch by relative path** |
| a URL | use it as-is |

Empty is not "unset". The engine serves the SPA from its own origin, so an
engine-bound build must pass `VITE_PLAY_ENDPOINT=` explicitly. Merely
leaving it unset lets an `.env.production` bake hosted URLs into a bundle
that was supposed to talk to localhost.

## Packaging for the engine

`../scripts/package-spa.sh` builds the LocalShell in same-origin mode and
produces `dist/worldlines-spa.zip`, with the built files at the archive
root so unzipping yields a directory the engine can serve directly:

```bash
../scripts/package-spa.sh
unzip -d /tmp/worldlines-spa ../dist/worldlines-spa.zip
NEONRP_SPA_DIR=/tmp/worldlines-spa neonrp web
```

The engine resolves its shell in this order: `NEONRP_SPA_DIR` first (an
unpacked dist directory — this is the seam, and it always wins), then a
build packaged inside the wheel at `neonrp/webui/spa` (transition compat
for pre-split installs), and finally nothing — in which case the engine
runs API-only and `/local/*` returns 404 with a pointer here. A directory
without an `index.html` is ignored rather than trusted, so a half-built
`NEONRP_SPA_DIR` falls through instead of serving a broken shell.

## Tests

`npx tsc -b` is clean and is what CI gates on, together with the build.

`npm run lint` currently exits non-zero: 16 errors and 26 warnings, carried
over verbatim from the engine repo (mostly `setState` inside effects and
refs touched during render, plus two unused bindings). They are pre-existing
rather than anything the repo split introduced, so CI does not gate on lint
yet. Don't let a green typecheck fool you into thinking lint is clean; if
you clear them, do it as its own change rather than inside a feature PR.

The Playwright suite in `e2e/` **cannot run from this repository**. Its
`webServer` boots a real engine via a script in the engine repo, so the
specs need a NeonRP checkout that this repo deliberately does not have.
They are kept here because they test shell behaviour and should move with
the shell; CI runs typecheck and build only. To run them you need an engine
checkout and its `scripts/e2e-server.sh`.

## License

AGPL-3.0-or-later, like the rest of this repository. See `../LICENSE`.
