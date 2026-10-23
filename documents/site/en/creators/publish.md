---
title: "Publish to the Hub"
description: "Create and approve locally, sign in, upload."
---

<!-- section: flow -->
## Flow

> **Status: mixed** — each section says what ships with 1.0 and what is still in design.

```text
create locally → Lint passes → local approval → sign in → upload to Hub (draft) → review → listed
```

- The Hub's "draft → review → listed" flow is in the code but not live yet: every upload lands as a draft;
- signing in from the local app, syncing with the Hub, and using Lint results for local approval — in design.

<!-- section: gates -->
## Gates

The Hub also runs server-side checks (e.g. rejecting secrets, image and multi-language checks before public listing). In 3.0 Lint runs on your machine first and the Hub re-checks.
