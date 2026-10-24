"""The local Hub lists the online Hub's worlds without signing in (10-24): core/template_publish.remote_catalog."""
from __future__ import annotations

import io
import json

import pytest

from neonrp.core import template_publish as tp


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    monkeypatch.setattr(tp, "_REMOTE", {"at": 0.0, "body": None})
    monkeypatch.setenv("NEONRP_HUB_SITE", "https://hub.example.test/")


def test_reads_the_catalog_without_a_credential_and_keeps_it(monkeypatch):
    seen = []

    def fake(req, timeout=0):
        seen.append(req)
        return io.BytesIO(json.dumps({"templates": [{"id": "a"}, {"title": "no id"}, "junk"]}).encode())

    monkeypatch.setattr(tp.urllib.request, "urlopen", fake)
    got = tp.remote_catalog()
    assert got == {"base": "https://hub.example.test", "templates": [{"id": "a"}]}
    assert seen[0].full_url == "https://hub.example.test/catalog.json"
    assert not seen[0].has_header("Authorization")
    assert tp.remote_catalog() is got and len(seen) == 1   # kept for a while


def test_offline_gives_an_empty_list(monkeypatch):
    def down(req, timeout=0):
        raise OSError("offline")

    monkeypatch.setattr(tp.urllib.request, "urlopen", down)
    assert tp.remote_catalog() == {"base": "https://hub.example.test", "templates": []}
