---
name: yjs-job-pipeline
description: 应届生求职网（yingjiesheng.com）外企岗位全链路管道：签名接口分段抓取岗位池、薪资/规模/方向三维筛选、快照 diff 找新上岗位、CDP 复用 Chrome 登录态一键投递（含 WAF 限速规避）。当用户要求「抓取/更新 yjs 岗位池、找新上岗位、按薪资规模筛选外企岗、批量投递 yjs 岗位、跑每日投递管道」时使用。抓取/分析/diff 三步委托 yjs-foreign-job-scraper 技能完成，本技能负责整体编排与最后一步投递。
---

# yjs-job-pipeline：抓取 → 分析 → diff → 投递 全链路

## 目标

把「外企岗位池抓取 → 筛选 → 增量发现 → 自动投递」固化为可重复执行的四段管道，
单次运行即可从接口抓全量池到完成一批新岗位的站内投递，全程状态可落盘、可续跑。

## 适用场景

- 首次建池 / 定期全量刷新外企岗位池（500 人以上、月薪≥2万 或 年薪≥24万）。
- 对比两个时间点的快照，找出「新上架」岗位（增量投递候选）。
- 对筛选后的岗位队列执行 yjs 站内一键投递。
- 投递状态持久化（deliver_state.json），跨批次去重防重复投递。

不适用：需跳转到外部 ATS（51job 网申、Workday、公司官网表单）的岗位——这些在
抓取阶段无法识别，由投递脚本以 `Redirect` 状态暴露，应在投递前从队列剔除。

## 输入要求

| 输入 | 必需 | 说明 |
|---|---|---|
| 输出目录 `--out` | 抓取阶段 | 池文件落盘目录（建议按日期命名，如 `pool_2026-10-20/`） |
| 旧快照 `--snapshot` | diff 阶段 | 上一次的全量池 JSON 文件路径 |
| 投递队列 JSON | 投递阶段 | `[{id, co, job, url, delivered?}]`；`delivered:true` 跳过；建议投递前剔除 `url` 非 yingjiesheng.com 的外链岗 |
| deliver_state.json | 投递阶段 | 已投记录唯一去重依据；**首次运行不存在时脚本自动初始化** |
| Chrome 调试模式 | 投递阶段 | `curl http://127.0.0.1:9222/json/list` 必须通；不通请用户用 `job-delivery` 技能的话术重启 Chrome，**不得自行 kill 用户 Chrome** |

抓取接口、签名、cosize 分段等参数定义以 **yjs-foreign-job-scraper 技能为唯一事实源**，
本技能不重复抄录（避免两处漂移）。投递只需知道：单条岗位含
`id, jobname, coname, cosize, salary, jobarea, degree, jobTags[], url`，其中 `url`
是带 property 参数的详情直链，可直接作为投递输入。

## 处理流程（四段）

```bash
# python 指 venv default（已装 websocket-client）：
#   ~/.workbuddy/binaries/python/envs/default/bin/python

# 1. 抓取（委托 yjs-foreign-job-scraper 技能脚本）
python ~/.workbuddy/skills/yjs-foreign-job-scraper/scripts/fetch_pool.py --out pool_<日期>
#    段返回 0 / 连续 405 = 限流：冷却 90-180s 后用 --only <段号> 单独补抓

# 2. 分析（薪资/规模/方向三维筛选）
python ~/.workbuddy/skills/yjs-foreign-job-scraper/scripts/analyze_pool.py --dir pool_<日期>
#    产出 pool_analyzed / pool_hits / pool_final.json

# 3. 增量 diff
python ~/.workbuddy/skills/yjs-foreign-job-scraper/scripts/diff_new.py \
    --dir pool_<日期> --snapshot pool_<旧日期>/pool_foreign_segmented.json

# 4. 投递（本技能脚本，原生 CDP + websocket-client）
python ~/.workbuddy/skills/yjs-job-pipeline/scripts/deliver_pool.py \
    --queue pool_<日期>/new_jobs.json --state deliver_state.json \
    --cooldown 30 --passes 2 --shots logs/deliver_<日期>
#    --results 默认 <队列所在目录>/delivery_results.json
```

投递阶段内部步骤（每个岗位）：
1. `/json/new` 开新标签加载岗位详情页（SPA 轮询渲染，最多 24s）。
2. 截图 `{序号}_{id}_pre.png`；读 `.delivery-btn` 文案判断状态。
3. 真实坐标点击（`Input.dispatchMouseEvent`，先 `scrollIntoView` 取中点）。
4. 等待 3.5s，校验成功信号：弹窗含「投递成功」**或**按钮变为「已申请」。
5. 截图 `{序号}_{id}_post.png`；写 results JSON；Submitted/Skipped 实时写入 deliver_state。
6. 关标签，进入下一岗位（收尾关标签是硬要求，残留标签累积会导致后续开标签超时）。

## 投递脚本行为细节（以 deliver_pool.py 代码为准）

- **幂等续跑**：结果实时落盘 `delivery_results.json`；中断（断网/关窗/崩溃）后
  **重跑同一命令**即可，脚本只补跑状态非 Submitted/Skipped 的岗位，已成功的不会重投。
- **多轮重试 `--passes`（默认 2）**：首轮后未成功岗位以相同 cooldown 再跑一轮。
  Redirect（外链）岗位二轮只会重复打开外链，投递前从队列剔除即可。
- **单岗位即时重试**：NeedsUser / Error 当轮等 `--waf-wait`（默认 20s）后自动重试一次，
  仍失败才记录终态并继续下一岗位。
- **退出码**：全部 Submitted 才返回 0；存在任何其他状态返回 1——可直接用于
  每日管道串联判断。
- **代理无关**：脚本启动即剥离全部代理环境变量并置 `NO_PROXY=*`，本机 Clash(7897)
  不影响 CDP 直连 127.0.0.1。
- **端口**：默认 9222，可用环境变量 `JD_DEBUG_PORT` 覆盖。
- **跳过判定**：队列中 `delivered:true` 的项直接跳过；按钮文案含「已申请」或「已投递」
  均记 Skipped。

## 投递前预检（30 秒）

1. `curl http://127.0.0.1:9222/json/list` 通；不通按 job-delivery 话术请用户重启
   调试 Chrome，不得自行 kill。
2. 队列 JSON 存在、含 `id/co/job/url`，外链岗已剔除。
3. python 环境有 websocket-client（venv default 已有）。
4. 估算时间：约 1 分钟/岗位（30s 冷却 + SPA 渲染 + 截图），按队列长度预留时间。

## 分析维度（筛选规则，analyze_pool.py 实际逻辑）

1. **薪资达标**：解析 `salary` 文本——`A-B万/月` 取下限月薪，有 `N薪` 标记按
   `下限月薪 × N` 折算年薪；`X万/年` 直接取年薪。达标线：**年薪 ≥ 24 万**。
2. **规模达标**：`cosize ∈ {500-1000人, 1000-5000人, 5000-10000人, 10000人以上}`。
3. **方向匹配**（加分制）：岗位名命中 `数据|算法|AI|机器学习|深度学习|分析|量化|
   建模|软件|开发|工程师|Data|Analyst|Engineer|Scientist|Quant|...` 记 3 分；
   工作地含「上海」记 4 分；按分数降序。
4. **剔除规则**：岗位/公司名命中 `销售代表|电话销售|房产|豪宅|管家|经纪人|
   置业|保险代理` 等直接剔除；要求博士（岗位名或 degree 含「博士」）剔除。
5. **去重**：diff 出的新岗位再排除 deliver_state.json `done` 中已投 jobid。

## 输出结果

| 文件 | 内容 |
|---|---|
| `pool_<日期>/pool_foreign_segmented.json` | 全量岗位池（分段去重合并） |
| `pool_<日期>/pool_hits.json` | 薪资+规模达标清单 |
| `pool_<日期>/pool_final.json` | 达标且方向匹配（投递候选） |
| `pool_<日期>/new_jobs.json` | 相对旧快照的新增岗位 |
| `delivery_results.json` | 每岗位 `{id, co, job, status, confirm/reason, pre, post}` |
| `deliver_state.json` | `done` 映射：jobid → 投递记录（跨批次去重唯一依据） |
| `logs/deliver_<日期>/` | 每岗位投递前后截图（核验证据） |

投递状态机：

| 状态 | 含义 | 写入 deliver_state |
|---|---|---|
| `Submitted` | 成功信号确认（弹窗「投递成功」/ 按钮「已申请」） | ✅ |
| `Skipped` | 之前已投过（按钮「已申请」或「已投递」） | ✅ |
| `NeedsUser` | WAF 验证码页，转人工滑一次即恢复 | ❌ |
| `Unknown` | 点了无成功信号，人工复核 post 截图 | ❌ |
| `Error` | 页面状态不可读或脚本异常（有 err 截图） | ❌ |
| `Redirect` | 详情页跳转外部 ATS，转其它流程 | ❌ |
| `NeedsInvestigation` | 无投递按钮等异常 | ❌ |

## 边界条件与红线

- **WAF 限速**：连续快速开页会触发 q.yingjiesheng.com「Access Verification」滑块
  （标题 "Verification"，页面含 captcha 容器）。处置：岗位间 `--cooldown ≥30s`；
  已命中则 `--waf-wait` 后自动重开重试一次；仍不过 → 标 `NeedsUser(captcha)`
  跳过该岗位继续。**不破解、不硬闯滑块**；需要人工滑一次后会话 Cookie 即恢复。
- **环境依赖**：投递脚本只用标准库 + websocket-client（venv default 已有）。
  job-delivery 技能的 RawCDPChrome 依赖 aiohttp/websockets，本机 venv 未装，勿用。
- **Chrome 红线**：不得 kill/重启用户 Chrome；9222 不通时按 job-delivery 技能话术
  请用户手动重启调试 Chrome。
- **外链岗位**：详情页 `url` 离开 yingjiesheng.com 即停止自动化并记录
  `Redirect`，不猜测外链表单内容。
- **无确认邮件**：yjs 一键投递无邮件回执，以站内「已申请」状态 + 截图为最终依据，
  不要因收件箱无信而重投。
- **抓取 405**：抓取阶段单段连续 405 = 限流，不是接口失效；冷却后用 `--only` 补抓。
- **代理探测**：旧 batch 脚本依赖的 127.0.0.1:3456 本地代理不在常驻运行，优先用
  本技能的直连 9222 实现。

## 资源

- `scripts/deliver_pool.py` — 第四段投递引擎（完整 CLI，`--help` 查看参数；
  核心类 `Tab` 可直接 import 复用于其它 yjs 页面自动化）。
