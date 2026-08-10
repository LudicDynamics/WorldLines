# rp-hub/web — Distribution Hub frontend

Catalog UI for WorldHub + SoulHub. Reads `worlds/index.json` and
`souls/index.json` directly from S3 over public-read; no backend of
its own. Visually a continuation of [worldlines.gg](https://worldlines.gg/) —
same colour tokens, same typography, same dark-mode card treatment.

## Stack

- Vite 7 + React 19 + Tailwind 4
- `react-router-dom` for `/worlds`, `/worlds/:slug`, `/souls`,
  `/souls/:slug`
- `lucide-react` for icons
- No i18n yet — easy to bolt on (see worldlines.gg/www for the
  pattern). Catalog labels are short enough that single-language
  works for v0.1.

## Develop

```bash
cd rp-hub/web
npm install
npm run dev
```

The dev server reads the **live** S3 registries, so what you see
locally is what production sees. To work offline, mock `fetchRegistry`
in `src/lib/registry.ts`.

## Build + deploy

```bash
npm run build          # → dist/
../aws/deploy-web.sh s3://<bucket> [<cloudfront-distribution-id>]
```

`deploy-web.sh` handles `aws s3 sync` + cache-control headers
(short TTL on `index.html`, immutable on Vite's hashed `assets/*`)
and CloudFront invalidation if a distribution id is provided.

## Routes

| Route | Page |
|---|---|
| `/` | redirects to `/worlds` |
| `/worlds` | catalog (filtered to worlds) |
| `/worlds/:slug` | detail + version history |
| `/souls` | catalog (filtered to souls) |
| `/souls/:slug` | detail + version history |

## Design notes

- **Colours** follow worldlines.gg — accent `#8B5CF6`. Worlds use the
  cyan world-agent colour `#06B6D4`; souls use the pink character
  colour `#EC4899`. This carries the same accent meaning the main
  site established for "world" vs. "character/soul" content.
- **Typography** matches: Young Serif for display, Inter for body,
  Space Mono for hash and CLI commands.
- **No marketing copy.** This is a catalog. The chrome is borrowed
  from worldlines.gg (Header / Footer / Logo) so it feels like the
  same site, but the body is data-first. Marketing pages live at
  `rp-loadingpage/worldlines.gg/www/` and stay there.

## Boundary with `rp-loadingpage/`

`rp-loadingpage/worldlines.gg/www/` is the marketing site. It
*talks about* WorldLines and links here for downloads.

`rp-hub/web/` is the catalog. It *talks to* the live S3 registries
and updates the moment a new build is uploaded.

The split lets the marketing site stay handcrafted (with hero
animations, scroll-snap sections, i18n) while the catalog stays
boring and fast.

## Integrating into worldlines.gg

When ready to mount under `worldlines.gg/hub/`, two options:

1. **Static iframe** — deploy this app to its own bucket, embed via
   `<iframe>` on a `worldlines.gg/hub` route. Cleanest separation,
   no shared state.
2. **Subpath build** — set Vite's `base: '/hub/'` and deploy the
   `dist/` into the same bucket as worldlines.gg under `/hub/`.
   Shared chrome, single deploy.

Pick when there's actually content to mount — until then, dev under
the standalone `vite` host.
