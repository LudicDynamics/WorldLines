"""Same 40 write-down prompts through each platform x model: streaming, no retries, 90 s cap, reasoning as low as the
model allows (the straight write-down). Time to first token, total, stalls/errors, accuracy, cost."""
import json, os, re, sys, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import httpx
PROV = Path(__file__).parent; sys.path.insert(0, str(PROV)); import keys
HERE = Path(os.environ.get("EXTRACT_CMP_DIR") or PROV.parent / "extract_cmp"); sys.path.insert(0, str(HERE))  # the extract_cmp beats + scorer
import run as R

OUT = Path(os.environ.get("GW_OUT") or (PROV / "gw")); OUT.mkdir(exist_ok=True)
ds = json.load(open(os.path.expanduser("~/.neonrp/config.json")))["models"]["deepseek"]
V, CF = keys.vercel(), keys.cloudflare()
PLAT = {"deepseek": (ds["base_url"], {"Authorization": "Bearer " + ds["api_key"]}),
        "vercel": (V["base_url"], {"Authorization": "Bearer " + V["api_key"]}),
        "cloudflare": (CF["base_url"], dict(CF["headers"]))}
ARMS = [  # name, platform, model, extra
    ("deepseek-v4-flash@deepseek", "deepseek", "deepseek-v4-flash", {"thinking": {"type": "disabled"}}),
    ("gpt-5-mini@vercel", "vercel", "openai/gpt-5-mini", {"reasoning_effort": "minimal"}),
    ("gpt-5-mini@cloudflare", "cloudflare", "openai/gpt-5-mini", {"reasoning_effort": "minimal"}),
    ("gemini-2.5-flash@vercel", "vercel", "google/gemini-2.5-flash", {"reasoning_effort": "none"}),
    ("gemini-2.5-flash@cloudflare", "cloudflare", "google-ai-studio/gemini-2.5-flash", {"reasoning_effort": "none"}),
    ("gemini-3.8-flash@cloudflare", "cloudflare", "google-ai-studio/gemini-3.8-flash", {"reasoning_effort": "minimal"}),
    ("gemini-3.8-flash-low@cloudflare", "cloudflare", "google-ai-studio/gemini-3.8-flash", {"reasoning_effort": "low"}),
    ("gemini-3.5-flash-lite@cloudflare", "cloudflare", "google-ai-studio/gemini-3.5-flash-lite", {"reasoning_effort": "none"}),
    # the background (thinking) write-down: deepseek thinking vs gemini 3.8 flash low
    ("SLOW deepseek-v4-flash-think@deepseek", "deepseek", "deepseek-v4-flash", {}),
]
only = sys.argv[1].split(",") if len(sys.argv) > 1 else None
cases = {c["key"]: c for c in json.load(open(HERE / "cases.json"))}
labels = {l["key"]: l for l in R.LABELS["beats"]}; keys_ = list(labels)
live = R.LiveLLM(think=False)
prompts = {k: live.prompt(cases[k]) for k in keys_}
def clean(s): return " ".join(re.sub(r"[A-Za-z0-9_\-]{30,}", "<redacted>", str(s)).split())[:200]

def call(plat, model, extra, k):
    base, hdr = PLAT[plat]
    sysm, user = prompts[k]
    body = {"model": model, "stream": True, "stream_options": {"include_usage": True}, "max_completion_tokens": 4000,
            "messages": [{"role": "system", "content": sysm}, {"role": "user", "content": user}], **extra}
    t0 = time.perf_counter(); ttft = None; parts = []; usage = {}
    try:
        with httpx.stream("POST", base + "/chat/completions", json=body, timeout=httpx.Timeout(90, connect=15),
                          headers={"Content-Type": "application/json", "User-Agent": "neonrp-bench/1.0", **hdr}) as r:
            if r.status_code >= 400:
                return {"raw": "", "ttft": None, "s": time.perf_counter() - t0, "error": f"HTTP {r.status_code}: {clean(r.read().decode('utf-8', 'replace'))}"}
            for ln in r.iter_lines():
                if time.perf_counter() - t0 > 90:
                    raise TimeoutError("90 s cap")
                if not ln.startswith("data:"):
                    continue
                d = ln[5:].strip()
                if d == "[DONE]":
                    break
                j = json.loads(d)
                if j.get("usage"):
                    usage = j["usage"]
                for ch in j.get("choices") or []:
                    dl = ch.get("delta") or {}
                    if dl.get("content") or dl.get("reasoning_content") or dl.get("reasoning"):
                        ttft = ttft or time.perf_counter() - t0
                    parts.append(dl.get("content") or "")
        return {"raw": "".join(parts), "ttft": ttft, "s": time.perf_counter() - t0, "usage": usage}
    except Exception as e:  # noqa: BLE001
        return {"raw": "".join(parts), "ttft": ttft, "s": time.perf_counter() - t0, "usage": usage, "error": f"{type(e).__name__}: {clean(e)}"}

for name, plat, model, extra in ARMS:
    if only and name not in only:
        continue
    f = OUT / f"{name}.json"
    cache = json.loads(f.read_text()) if f.exists() else {}
    todo = [k for k in keys_ if k not in cache]
    if todo:  # one probe first: a rejected parameter is dropped, not 40 failures
        r0 = call(plat, model, extra, todo[0])
        if r0.get("error") and "HTTP 400" in r0["error"] and extra:
            print(f"  {name}: {r0['error'][:120]} -> retry without {list(extra)}", flush=True); extra = {}
            r0 = call(plat, model, extra, todo[0])
        cache[todo[0]] = {**r0, "extra": extra}; todo = todo[1:]
    with ThreadPoolExecutor(3) as ex:
        for k, res in zip(todo, ex.map(lambda k: call(plat, model, extra, k), todo)):
            cache[k] = {**res, "extra": extra}
            f.write_text(json.dumps(cache, ensure_ascii=False))
    f.write_text(json.dumps(cache, ensure_ascii=False))
    preds = {k: live.to_pred(cases[k], cache[k]["raw"]) for k in keys_}
    sc = R.score(labels, cases, preds, [])
    s = sorted(cache[k]["s"] for k in keys_); tt = sorted(cache[k]["ttft"] for k in keys_ if cache[k].get("ttft"))
    errs = [cache[k]["error"] for k in keys_ if cache[k].get("error")]
    u = [cache[k].get("usage") or {} for k in keys_]
    cost = sum(float(x.get("cost") or 0) for x in u)
    tin = sum(int(x.get("prompt_tokens") or 0) for x in u); tout = sum(int(x.get("completion_tokens") or 0) for x in u)
    rsn = sum(int((x.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0) for x in u)
    timeouts = sum(1 for k in keys_ if cache[k]["s"] > 20)
    print(f"{name:28s} 首字p50 {tt[len(tt)//2] if tt else 0:4.1f}s 总p50 {s[20]:4.1f}s p90 {s[36]:4.1f}s max {s[-1]:5.1f}s >20s {timeouts} 错{len(errs)} | "
          f"钱 {sc['money_exact']} 物品 {sc['items_exact']} 地点 {sc['location_acc']} 漏扣 {sc['missed_payments']} 多扣 {sc['overcharges']} | "
          f"in {tin} out {tout} (reason {rsn}) cost {'$%.4f' % cost if cost else '-'}" + (f" | {errs[0][:100]}" if errs else ""), flush=True)
