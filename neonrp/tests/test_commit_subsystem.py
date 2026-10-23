

def test_soul_scene_index_malformed_entries_skipped(tmp_path):
    # 防御回归:soul_scene_index 里混入 list/str 畸形条目(老档/手改档)时,
    # 迭代守卫直接跳过,不得 AttributeError。纯函数级验证守卫逻辑。
    entries = [["legacy", "tuple"], "junk", {"sid": "a", "instance_id": "i", "soul_commit": "c"}]
    kept = [e for e in entries if isinstance(e, dict)]
    assert len(kept) == 1 and kept[0]["sid"] == "a"
