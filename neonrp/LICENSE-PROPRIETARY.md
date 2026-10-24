# Proprietary components in the PyPI packages

The `neonrp` and `worldlines` packages that Ludic Dynamics publishes on PyPI contain open-source code and a few
proprietary components. Builds made from the public repository (https://github.com/LudicDynamics/WorldLines) contain
only the open-source parts.

## Open source

| Package | Part | License |
|---|---|---|
| `neonrp` | the `neonrp` Python package | Apache License 2.0 (`LICENSE`, `NOTICE`) |
| `worldlines` | the launcher and the web UI, except the pages listed below | GNU AGPL v3.0 or later (`LICENSE`) |
| both | world and character content | CC-BY-4.0 for text and data, CC-BY-NC-4.0 for images and audio (`CONTENT-LICENSE.md`) |

## Proprietary (`LicenseRef-WorldLines-Proprietary`)

| Package | Part |
|---|---|
| `neonrp` | the `neonrp_private` Python package |
| `worldlines` | `worldlines_shim/spa/hub.html`, `worldlines_shim/spa/player.html`, `worldlines_shim/spa/chat.html` |

These components are not licensed under the open-source licenses above, and their source code is not published.

You may install them as part of these packages and use them, unmodified, to run WorldLines. You may not copy them
apart from the package, modify them, distribute them separately, or reverse engineer them, except where the law
allows it regardless of this notice.

They are provided "as is", without warranty of any kind.

Copyright © 2026 Ludic Dynamics. All rights reserved. Questions: info@worldlines.gg
