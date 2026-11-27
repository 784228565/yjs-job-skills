# pipeline — 抓取 / 筛选 / diff / 队列 / 预检

> `yjs-job-pipeline` 技能的前三段原本委托给 `yjs-foreign-job-scraper`，该技能目录在当前机器上已缺失。这里归拢的是实际在跑的等价脚本，保证整条链路可以跑通。

## 脚本一览

| 脚本 | 输入 | 输出 | 说明 |
|---|---|---|---|
| `yjs_fetch_pool.py` | `--out <目录>` | `pool_foreign_segmented.json`、`pool_size_<seg>.json` | 按企业规模分段抓外企池（`cotype=01,02,06`），HMAC 签名接口 |
| `analyze_pool.py` | `--dir <目录>` | `pool_analyzed.json`、`pool_hits.json`、`pool_final.json` | 薪资 / 规模 / 方向三维筛选与打分（**旁路**：供人工复核与报表，不是 diff 的上游） |
| `diff_new.py` | `--dir`、`--snapshot`、可选 `--state` | `new_jobs.json` | 直接读全量池，与旧快照对比找新上架岗位 |
| `queue_build.py` | `--dir`、`--state` | `deliver_queue.json` | 生成投递队列（std / relaxed 两档，同公司限投） |
| `queue_build_agent.py` | 同上 | 同上 | 队列构建的 agent 版（保留人工判断接口） |
| `jd_check.py` | `--queue`、`--out` | `jd_details.json` | 逐岗开详情页，剔除 3 年以上经验 / 博士 / 已下线 / 已申请 |

## 运行顺序

```bash
export YJS_SIGN_KEY="..."        # Windows: $env:YJS_SIGN_KEY="..."

python yjs_fetch_pool.py --out pool_2026-11-27
python analyze_pool.py --dir pool_2026-11-27              # 可选：复核 / 报表
python diff_new.py --dir pool_2026-11-27 --snapshot pool_2026-11-26/pool_foreign_segmented.json
python queue_build.py --dir pool_2026-11-27 --state deliver_state.json
python jd_check.py --queue pool_2026-11-27/deliver_queue.json --out pool_2026-11-27/jd_details.json
```

最后一段投递在 `../skills/yjs-job-pipeline/scripts/deliver_pool.py`。

## 关键口径

- **分段**：`cosize` 4/5/6/7 分别对应 500-1000 / 1000-5000 / 5000-10000 / 10000+ 人；每段首次请求前有 60–210 秒冷却，连续 405 是限流不是失效。
- **薪资线**：`analyze_pool.py` 为 **年薪 ≥20 万**（2026-11-04 从 24 万放宽）；`queue_build.py` 的 `std` 档同为 20 万，`relaxed` 档对强契合方向放宽到 8–9 万。
- **去重**：`queue_build.py` 会剔除 `deliver_state.json` 中已投的 jobid，并做「同公司只留薪资最高的 2 个」限制。
- **URL 归一化**：投递地址统一成 `q.yingjiesheng.com/jobdetail/<id>.html`，去掉 `property` 跟踪参数，保证去重主键稳定。

## 签名密钥

`yjs_fetch_pool.py` 通过 HMAC-SHA256 对请求路径签名，密钥从环境变量 `YJS_SIGN_KEY` 读取，仓库不提供。未设置时脚本会直接退出并提示。

## 依赖

- Python 3.10+（仅标准库）
- 能访问 `q.yingjiesheng.com` 的网络
- `jd_check.py` 另需 `websocket-client`，并复用 `deliver_pool.Tab`（脚本会自动在仓库内或 `~/.workbuddy/skills/` 下查找）
