"""Single source of truth for the engine's debug toggle.

``DEBUG_ENABLED`` is True only when *both* ``__debug__`` (i.e. not running
under ``python -O``) and the ``NEONRP_DEBUG`` env var is set. Production
builds (``python -O``) collapse the constant to ``False`` at bytecode
compile time, so every ``if DEBUG_ENABLED:`` guard becomes ``if False:``
and the peephole optimiser drops the branch — including the imports of
the TUI debug panel and Textual widgets it would otherwise pull in.

That gives us a "comment-out at build time" equivalent without macros:
the dev tool is in the source tree, observable when ``NEONRP_DEBUG=1``,
and physically absent from optimised builds.
"""

from __future__ import annotations

import os

DEBUG_ENABLED: bool = __debug__ and bool(os.environ.get("NEONRP_DEBUG"))

# Runtime opt-in for surfaces that want recording regardless of the env var
# (e.g. the `neonrp play` REPL's /debug command). Still dead under ``python
# -O``: ``__debug__`` is False there, so ``is_enabled()`` stays False and the
# heavyweight guards that use the DEBUG_ENABLED *constant* (TUI panel imports)
# are stripped at compile time exactly as before.
_forced = False


def force_enable() -> None:
    """Enable debug recording for this process (REPL /debug, tests)."""
    global _forced
    _forced = True


def is_enabled() -> bool:
    """Dynamic check: the env-var constant OR a runtime ``force_enable()``."""
    return DEBUG_ENABLED or (_forced and __debug__)
