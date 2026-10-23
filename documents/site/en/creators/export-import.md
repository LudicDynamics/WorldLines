---
title: "Export and import"
description: "Take the templates and characters you edited in the engine out as one package, and bring them back."
---

<!-- section: what -->
## One kind of package

> **Status: ships with 1.0**

Templates and characters share one format: a zip with a `pack.json` at its root saying what is inside.

| Package | Holds | Imported into |
|---|---|---|
| template | the template folder as on disk (world · plots · prompts · assets) + every library character it links | template → your template store; characters → the library, the template still links them |
| soul | one library character | the library |

<!-- section: how -->
## How to use it

**Web**: on the template page, "Export" downloads a `.template.zip`; "Import…" takes a package and switches to it.

**Command line**:

```bash
neonrp template export pct-house              # → ./pct-house.template.zip
neonrp template export --soul mira            # → ./mira.soul.zip
neonrp template import pct-house.template.zip # the template into your store, its characters into the library
neonrp template import x.zip --id my-copy     # import under another id
```

<!-- section: rules -->
## Name clashes and safety

- A taken template id → the next free `-2`, `-3` (with `--id`, a taken id is refused).
- A library character with the same name: identical → reused; different → installed under a new name and the template's link repointed; yours is left alone.
- Packages are checked in a scratch folder first: absolute or `..` paths, links, code files (`.py` `.js` `.sh` …), too many files or too large → the whole package is refused and nothing is written.

<!-- section: http -->
## HTTP

```
GET  /api/v1/local/templates/<id>/export     template package
GET  /api/v1/local/souls/<name>/export       soul package
POST /api/v1/local/import/package[?id=new]   body = the zip
```
