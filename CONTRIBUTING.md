# Contributing to WorldLines

**Language:** [English](./CONTRIBUTING.md) · [简体中文](./CONTRIBUTING.zh.md) · [日本語](./CONTRIBUTING.ja.md) · [한국어](./CONTRIBUTING.ko.md)

Thanks for considering a contribution — bug reports, fixes, worlds and ideas are all welcome.

## How this repository works

This repository is the public release of WorldLines. Development happens upstream, in a private development
repository; each release lands here as **one release commit** (a squashed snapshot). Don't expect a fine-grained commit
history here — read the release notes instead.

## Issues

- **Bugs:** include the neonrp / worldlines versions, your OS, the steps to reproduce, and what you expected vs. what
  happened. A log or screenshot helps.
- **Ideas:** feature ideas, new packs, world or template proposals are welcome — open an issue to talk it over.

## Pull requests

Open pull requests here, against this repository.

1. An accepted PR is **merged into this repository first**, so your authorship stays in this public history.
2. It is then carried upstream and included in the next release.
3. The maintainers will note in the PR which release it shipped in.

Keep a PR to one topic and say *what* changed and *why*. For larger changes, open an issue first so we can agree on
scope before you write code.

### Contributor License Agreement

Before your first pull request can be merged, you need to sign our [Contributor License Agreement](./CLA.md) (CLA). A
bot comments on the pull request; you sign by replying with the sentence it gives. You only do this once, and it covers
all your later contributions. You keep the copyright in your work; the CLA lets us ship it under this repository's
licenses and in the WorldLines products built on it (hosted services and app-store apps).

## Layout and licenses

| Folder | What | License |
|---|---|---|
| `neonrp/` | The engine (Python) | Apache-2.0 |
| `worldlines/` | The product: web UI (`worldlines/ui`), desktop shell (in the repository, not released yet), launcher package, templates, example worlds | AGPL-3.0 |
| `documents/` | Specs and the docs source | CC BY 4.0 |
| `benchmarks/` | Test suites behind the engine's design decisions | code Apache-2.0 · data CC BY 4.0 |

Contributions are accepted under the license of the folder they touch, plus the rights granted in the [CLA](./CLA.md).

## Development setup

Engine:

```bash
cd neonrp
uv sync --all-extras --dev
uv run ruff check src tests
uv run pytest -q
```

Web UI:

```bash
cd worldlines/ui
npm ci
npm run lint
npm run build:local
```

Please make sure the relevant checks pass before opening a PR.

## Creating worlds, characters and templates

Open the repository in Claude Code or Codex and use the workbench (`CLAUDE.md` / `AGENTS.md` at the repository root),
together with the specs in [`documents/spec/`](./documents/spec). Validate your work with `neonrp template lint` (templates)
and `neonrp validate` (worlds) before submitting.

## Secrets

Never commit secrets. API keys stay in `~/.neonrp/config.json` on your own machine — not in worlds, templates, tests
or screenshots.

## Code of conduct and security

Be decent. Assume good faith. Criticize ideas, not people. See [CODE_OF_CONDUCT.md](./CODE_OF_CONDUCT.md) for the full
policy. Report vulnerabilities privately as described in [SECURITY.md](./SECURITY.md) — not in public issues.

## Contact

- Issues: https://github.com/LudicDynamics/WorldLines/issues
- Discord: https://discord.gg/HJYWbdqWrE
- Email: `info@worldlines.gg`
