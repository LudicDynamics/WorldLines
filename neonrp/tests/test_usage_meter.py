"""C0-11 (docs/testing/PRE-RELEASE-TEST-CHECKLIST.md): every model response's token usage is summed in-process."""
from neonrp.core import llm_openai as L


def test_every_response_adds_its_usage():
    before = L.usage_snapshot()
    L._emit_raw_json("openai.chat.response", "r1", {"response_merged": {"usage": {"prompt_tokens": 100, "completion_tokens": 20,
                                                                                    "prompt_cache_hit_tokens": 64}}})
    L._emit_raw_json("openai.chat_stream.response", "r2", {"response_merged": {"usage": {"prompt_tokens": 50, "completion_tokens": 5}}})
    L._emit_raw_json("openai.chat.request", "r3", {"messages": []})  # requests are not counted
    after = L.usage_snapshot()
    assert after["calls"] - before["calls"] == 2
    assert after["prompt_tokens"] - before["prompt_tokens"] == 150
    assert after["completion_tokens"] - before["completion_tokens"] == 25
    assert after["cache_hit_tokens"] - before["cache_hit_tokens"] == 64
