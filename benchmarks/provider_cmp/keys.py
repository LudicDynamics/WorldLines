import os
def env(name):
    kv = {}
    for ln in open(os.path.expanduser(f"~/.neonrp/{name}.env"), encoding="utf-8"):
        k, s, v = ln.strip().partition("=")
        if s: kv[k.strip().removeprefix("export ").strip()] = v.strip().strip("'\"")
    return kv
def vercel():
    return {"base_url": "https://ai-gateway.vercel.sh/v1", "api_key": env("vercel-ai-gateway")["AI_GATEWAY_API_KEY"], "headers": {}}
def cloudflare():
    e = env("cloudflare-ai-gateway")
    return {"base_url": f"https://gateway.ai.cloudflare.com/v1/{e['CLOUDFLARE_ACCOUNT_ID']}/{e['CLOUDFLARE_GATEWAY_ID']}/compat",
            "api_key": "unused", "headers": {"cf-aig-authorization": f"Bearer {e['CF_AIG_TOKEN']}"}}
