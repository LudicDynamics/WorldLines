# provider_cmp — 写状态这一步,各平台 × 各模型(10-22)

同 40 拍(`benchmarks/extract_cmp` 的 cases/labels,引擎自己的转移提示),流式、不重试、单次 90 秒,思考调到模型允许的最低档(= 「先快后修正」的快版本)。并发 3。key 只从 `~/.neonrp/vercel-ai-gateway.env` / `cloudflare-ai-gateway.env` / `config.json` 读(`keys.py`),不进仓库。

| 模型 @ 平台 | 首字 p50 | 总 p50 / p90 / 最慢 | 钱 | 物品 | 地点 | 每拍成本(列表价) |
|---|---|---|---|---|---|---|
| deepseek-v4-flash @ 官方直连 | 1.4 s | 1.7 / 2.4 / 3.0 s | 28/40 | 32/40 | 32/38 | $0.00023(缓存命中 97%) |
| gpt-5-mini @ Cloudflare | 1.6 s | 2.1 / 2.9 / 5.1 s | 26/40(多扣 11) | 31/40 | 33/38 | $0.0010 |
| gemini-2.5-flash @ Cloudflare | 1.3 s | 1.6 / 2.3 / 2.8 s | 30/40 | 30/40 | 36/38 | $0.0013 |
| gemini-3.8-flash(默认思考)@ Cloudflare | 9.0 s | 9.1 / 18.5 / 22 s | 34/40 | 34/40 | 38/38 | $0.0096 |
| gemini-3.8-flash(思考 low)@ Cloudflare | 2.5 s | 2.8 / 4.2 / 56 s | 33/40 | 36/40 | 38/38 | $0.0064 |

- Vercel 免费档:gpt-5-mini、gemini-2.5-flash 40 次里 30 次 429(限流),不算数;deepseek、Gemini 3.x 免费档不开放。
- gemini-3.5-flash-lite 走 Cloudflare 统一计费报「缺 Authorization」,没测成。
- 成本 = token × Vercel 目录里的列表价;Cloudflare 统一计费另有手续费(未核实)。只算写状态这一步,不含叙事。
- 40 拍、一个世界、一个人标的真值;差一两拍在噪声里。

## 后台修正的版本(开思考)对比

| | 总 p50 / p90 / 最慢 | 钱 | 物品 | 地点 | 推进时间的拍 | 条目数 | 每拍成本 |
|---|---|---|---|---|---|---|---|
| deepseek-v4-flash 关思考(快版本,参照) | 1.7 / 2.4 / 3.0 s | 28/40 | 32/40 | 32/38 | 14/40 | 90 | $0.00023 |
| deepseek-v4-flash 开思考 @ 官方直连 | 3.5 / 7.5 / 8.9 s | 31/40 | 34/40 | 35/38 | 21/40 | 118 | ≈$0.0003 |
| gemini-3.8-flash 思考 low @ Cloudflare | 2.8 / 4.2 / 56 s | 33/40 | 36/40 | 38/38 | 21/40 | 135 | $0.0071(网关记账实价) |

- 56 s 那次:Cloudflare 网关日志 `timings.latency` = 55.95 s,网关自身 ≈16 ms —— 慢在 Google 上游(东京节点 NRT),不是网关/网络;25 s 那次同样。
- Cloudflare 每次请求的实际扣费 = Google 的 US/EU 区域价($0.825 / $4.125 每百万),请求上没有加价。
- gpt-5-mini 写得最多(168 条、推进时间 29/40),但多扣钱 11 次:写得多不等于写得对。
