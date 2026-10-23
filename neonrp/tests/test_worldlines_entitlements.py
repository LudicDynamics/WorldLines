"""What the signed-in account may use (10-21): core/worldlines_auth.entitlements — billing's GET /v1/me/entitlements
(``tier``: free · story · vivid), cached a minute per session; None when signed out or the platform does not answer.
No network: urlopen is a stub."""
from __future__ import annotations

import io
import json
import urllib.error
import urllib.request

from neonrp.core import worldlines_auth as A


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_entitlements_read_cached_and_absent(monkeypatch):
    calls: list[str] = []

    def urlopen(req, timeout=None):
        calls.append(req.full_url)
        assert req.headers["Authorization"] == "Bearer tok-1"
        return _Resp(json.dumps({"plan": "story", "tier": "story", "limits": {}}).encode())

    A._ENT.clear()
    monkeypatch.setattr(A, "access_token", lambda: "tok-1")
    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    assert A.entitlements()["tier"] == "story" and calls[0].endswith("/v1/me/entitlements")
    assert A.entitlements()["tier"] == "story" and len(calls) == 1, "cached a minute"
    monkeypatch.setattr(A, "access_token", lambda: None)
    assert A.entitlements() is None, "signed out"
    monkeypatch.setattr(A, "access_token", lambda: "tok-2")
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=None: (_ for _ in ()).throw(urllib.error.URLError("down")))
    assert A.entitlements() is None, "the platform did not answer"
    A._ENT.clear()
