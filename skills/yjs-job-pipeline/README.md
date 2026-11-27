# yjs-job-pipeline

> 应届生求职网（yingjiesheng.com）外企岗位的「抓取 → 筛选 → 增量 diff → 站内投递」四段管道，一次运行即可从接口抓全量池到完成一批新岗位的投递，全程状态落盘、可续跑。

## 用途

把每天重复的「翻岗位、比薪资规模、查有没有投过、一个个点投递」固化成一条可以重复执行的命令链。适合把它挂在每天早上跑一次：抓到新岗位 → 筛出值得投的 → 自动投掉 → 留下截图和状态表。

## 核心功能

- **分段抓取**：按企业规模（500-1000 / 1000-5000 / 5000-10000 / 10000+ 人）分段拉外企池（`cotype=01,02,06`），单段限流只影响该段，可用 `--only` 补抓。
- **三维筛选**：薪资（年薪达标线）、企业规模、岗位方向（数据/AI/算法/软件…）加权排序；剔除销售、房产、管家、博士要求岗。
- **增量发现**：与旧快照 diff，只留新上架岗位，并用 `deliver_state.json` 排掉已投过的。
- **站内投递**：CDP 复用已登录 Chrome，真实坐标点击 `.delivery-btn`，以「投递成功」弹窗或按钮变「已申请」为成功信号。
- **幂等续跑**：结果与状态实时落盘；断网、关窗、崩溃后重跑同一条命令，只补未成功的岗位。
- **证据留存**：每个岗位投递前后各截一张图，状态机七种终态一目了然。

## 适用场景

| 适合 | 不适合 |
|---|---|
| 每日增量投递 yjs 站内岗位 | 需要跳转外部 ATS（Workday / 公司官网表单）的岗位 |
| 首次建池 + 全量刷新 | 需要绕过验证码、伪造身份的场合 |
| 需要可审计投递记录（截图 + 状态表） | 想要「无人值守全自动」——滑块必须人工过一次 |

## 主要内容

| 文件 | 作用 |
|---|---|
| `SKILL.md` | 技能定义：触发词、四段流程、投递状态机、边界与红线 |
| `scripts/deliver_pool.py` | 第四段投递引擎；核心类 `Tab` 可被其它脚本 import 复用于任意 yjs 页面自动化 |

抓取、分析、diff 三段的实体脚本在仓库根目录的 [`pipeline/`](../../pipeline/) 下（原 `yjs-foreign-job-scraper` 技能已不在本机，详见根 README「已知限制」）。

## 快速开始

```bash
# 单跑投递段：队列 JSON 形如 [{"id","co","job","url"}]
python scripts/deliver_pool.py \
    --queue pool_2026-11-27/deliver_queue.json \
    --state deliver_state.json \
    --cooldown 30 --passes 2 \
    --shots logs/deliver_2026-11-27
```

常用参数：

| 参数 | 默认 | 说明 |
|---|---|---|
| `--queue` | 必填 | 投递队列 JSON |
| `--state` | `deliver_state.json` | 去重状态文件，首次运行自动初始化 |
| `--cooldown` | 30 | 岗位间隔秒数，低于 30 易触发 WAF |
| `--waf-wait` | 20 | 命中滑块后等待重试的秒数 |
| `--passes` | 2 | 整批重试轮数 |
| `--results` | 队列同目录 `delivery_results.json` | 明细结果 |

## 输入与输出

**输入**：队列 JSON（`id / co / job / url`，可选 `delivered: true` 跳过）、已登录的 Chrome（9222）。

**输出**：

| 文件 | 内容 |
|---|---|
| `delivery_results.json` | 每岗 `{id, co, job, status, confirm, pre, post}` |
| `deliver_state.json` | `done` 映射，跨批次去重的唯一依据 |
| `logs/deliver_<日期>/` | 每岗投递前后截图 |

**状态机**：

| 状态 | 含义 | 计入已投 |
|---|---|---|
| `Submitted` | 弹窗「投递成功」或按钮变「已申请」 | ✅ |
| `Skipped` | 之前已投过 | ✅ |
| `NeedsUser` | 滑块验证，需人工滑一次 | ❌ |
| `Unknown` | 点了但无成功信号，需看截图复核 | ❌ |
| `Redirect` | 详情页跳外链 ATS | ❌ |
| `Error` | 页面不可读或脚本异常 | ❌ |
| `NeedsInvestigation` | 找不到投递按钮等异常 | ❌ |

## 注意事项

- **不要 kill 用户的 Chrome**。9222 不通时请用户手动以调试模式重启。
- **外链岗位投不了**：详情页离开 `yingjiesheng.com` 就停止自动化并记 `Redirect`，应在队列阶段剔除。
- **无邮件回执**：yjs 站内投递不发确认邮件，别因为收件箱没信就重投。
- **标签要关干净**：每岗结束必须关标签，残留标签累积会导致后续开标签超时。
- **代理无关**：脚本启动即剥离全部代理变量并置 `NO_PROXY=*`，本机 Clash 不影响 CDP 直连。

## 依赖

- Python 3.10+，`websocket-client`（投递引擎只用标准库 + 它）
- Chrome 以 `--remote-debugging-port=9222` 启动并已登录 yjs
- 抓取段另需环境变量 `YJS_SIGN_KEY`（签名密钥，见根 README）
