"""G2 (the handover 10-06): one level's connectivity graph — nodes, edges, ports, entry, frozen."""
from pathlib import Path

from neonrp.core.place_tree import WORLD, level_graph

W = Path("src/neonrp/templates/stoneford-elena")


def test_town_level_graph_has_its_ports_and_entry():
    g = level_graph(W, "T001")
    assert g["entry"] == "gate_north" and g["ports"]["gate_north"] == ["R001", "R002", "R004"]
    ids = {n["id"] for n in g["nodes"]}
    assert all(e["a"] in ids and e["b"] in ids for e in g["edges"]), "no dangling edge"
    assert len({(min(e["a"], e["b"]), max(e["a"], e["b"])) for e in g["edges"]}) == len(g["edges"]), "each pair once"


def test_world_and_dungeon_levels():
    w = level_graph(W, WORLD)
    t1 = next(n for n in w["nodes"] if n["id"] == "T001")
    assert t1["has_children"] and any(e.get("id") for e in w["edges"])
    d = level_graph(W, "D001")
    assert d["entry"] == "D001_R001" and d["frozen"] is False, "rooms without pos: not laid out yet"
    assert level_graph(W, "NOPE") is None
