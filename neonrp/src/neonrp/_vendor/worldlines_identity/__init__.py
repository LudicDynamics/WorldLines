"""Vendored from worldlines-identity (packages/client-python, 943f5d0) — the login half only
(loopback PKCE / device code / token manager / 0600 file store; standard library only). The JWT verifier half stays out:
NeonRP never verifies tokens, it only holds one. Not on PyPI; update by copying login.py again."""
from . import login  # noqa: F401
