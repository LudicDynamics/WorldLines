---
title: "Publish to the Hub"
description: "Two zones: the Free Zone goes public first and is moderated after; the Default Zone is reviewed first. The engine checks five things before anything is uploaded."
---

<!-- section: zones -->
## Two zones

> **Status: ships with 1.0**

| | Free Zone | Default Zone |
|---|---|---|
| How a work gets in | Publish with your account; public as soon as the checks pass | Listed after review |
| Moderation | Public first, moderated after: taken down on a report or when an admin finds a problem | Reviewed before it is listed |
| Can be exported as a package | Yes | No (play only) |
| Hands out reward cards, lets players take characters home | No | Yes |
| `zone` in `template.json` | `open` (unset counts as Free Zone) | `reviewed` |

The official worlds (Greyoak House, Stoneford and the rest) are in the Default Zone.

<!-- section: flow -->
## How to publish

**Local creation desk** (the local web page `worldlines` opens):

1. Sign in with a Worldlines account (guest accounts cannot publish).
2. On the Template page, press "Publish". The engine runs the pre-publish checks (below); if they pass it uploads, and the work is in the Free Zone **at once**.
3. To get into the Default Zone: in "My published works", press "Apply for the Default Zone". While it waits for review the work stays in the Free Zone.

**The web Hub desk and the iOS desk** can submit straight to the Default Zone: during quick review, if nobody raises a problem within 30 minutes it is approved automatically. Nobody else sees it before then.

Publishing the same template again adds a new revision to the same work. A public work cannot switch zones directly; use "Apply for the Default Zone".

**Official accounts** publish to the Default Zone from the command line:

```bash
neonrp template publish stoneford-town --official
```

Raise `version` in `template.json` before each publish. A non-official account is refused.

**Fetching** a Default Zone world (sign in with a full account):

```bash
neonrp template fetch <work id>     # download or update into ~/.worldlines/official
```

<!-- section: checks -->
## Pre-publish checks

Before uploading, the engine checks five things. If one fails, nothing is sent and you get a list of what to fix:

| Check | Fails when |
|---|---|
| Linked characters are in your local library | A `{"lib": …}` row in the template points at a character that isn't there |
| No secrets | The template or a linked character contains an API-key-shaped string or a credentials file |
| [Lint](/docs/creators/lint) has no block | There are still problems that must be fixed |
| Card in four languages | Chinese / English / Japanese / Korean is missing a title or a one-line pitch (written in `card` of `i18n/<lang>/template.json`) |
| Has a cover | `card.cover` doesn't point at an image inside the template |

The platform runs its own automatic checks again on receipt.

<!-- section: zone-lint -->
## Checks graded by zone

A few checks are stricter in one zone than the other:

| Check | Default Zone | Free Zone |
|---|---|---|
| Truth quiz (`truth_quiz`, required by the `mystery-trpg` contract) | block | warn |
| A template that ships its own audio files says whose they are and the license (`audio.credits` pointing at e.g. `assets/audio/CREDITS.md`) | block | warn |

<!-- section: export -->
## Export

Only Free Zone works can be exported as a package. If a Default Zone world is marked `forkable: true` (both built-in worlds are), "Make a copy" first; the copy is your own work, so you can export it and publish it to the Free Zone. See [Export and import](/docs/creators/export-import).

<!-- section: http -->
## HTTP

```
GET  /api/v1/local/templates/<id>/publish            dry run: checks only, returns {checks, work, signed_in}
POST /api/v1/local/templates/<id>/publish            publish to the Free Zone
POST /api/v1/local/templates/<id>/publish  {"zone": "curated"}   submit for Default Zone review
GET  /api/v1/local/hub/mine                           my published works
POST /api/v1/local/hub/submit {id}                    apply for the Default Zone
POST /api/v1/local/hub/unpublish {id}                 take down
```

Failed checks return `422 checks_failed` with the problem list; not signed in returns `401 not_signed_in`.
