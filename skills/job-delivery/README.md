# job-delivery —— 队列驱动的浏览器投递 Agent（CDP 直连）

> 读投递队列 → 逐岗位开页截图 → 判断可投/已投/失效 → 填表提交 → 邮件确认 → 落 CSV + 汇总报告。
> 全程复用你本机 Chrome 的登录态，**不保存账号密码**，靠 CDP（Chrome DevTools Protocol）驱动。

这个技能是 `yjs-job-pipeline` 的上游/下游通用件：`yjs-job-pipeline` 负责「抓外企池 → 筛选 → 站内直投」，遇到外链 ATS 表单、或需要按 Excel 队列逐条投递时，就交给本技能。`yjs-job-pipeline/SKILL.md` 里「9222 不通时按 job-delivery 话术重启 Chrome」所指的就是本技能的 **Chrome 调试模式启动** 一节。

---

## 一、解决什么问题

投递真正的成本不在「点按钮」，而在这些脏活：

- 队列里混着「已下线 / 已投过 / 跳到外链」的岗位，逐个人眼判断
- 表单字段五花八门，填到一半卡在「签证状态」这类不该替你决定的题
- 投完没人核对到底成没成功（确认邮件、结果页）
- 一处报错就整批停摆，问题散落在聊天记录里无法复盘

本技能把上面四件事变成固定动作：**先截图再操作** → **能填的全填完再停** → **逐条写日志** → **最后出汇总**。

## 二、核心功能

| 能力 | 说明 |
|---|---|
| **队列顺序执行** | 自动定位最新 `队列*.xlsx`（忽略 `~$` 锁文件），读【投递队列】工作表，按序号升序逐条处理，不跳过不重排 |
| **截图优先判定** | 每次开页/跳转先截图再分析，用三语终止词表判断「已失效 / 已投递 / 可投」；整词匹配 + 语境判断，避免「已从收藏移除」这类误报 |
| **CDP 三段式降级** | `agent-browser` → 原生 CDP WebSocket → 标记 `NeedsUser`。**每个岗位最多试 2 条路径**，禁止在两条路径间反复横跳（这条是防「无限切换」的硬约束） |
| **先填后停** | 进表单先把姓名/邮箱/电话/地点/简历上传/答案库已有项全部填完，只剩不确定项时才停，并注明「已填完 X 项，仅剩 Y 待你回答」 |
| **答案库复用** | `answer_bank.md` 存历史答案（学历、语言、工作许可等），命中直接填，避免每次都问你 |
| **CDP 三层诊断** | `check_cdp.py` 用退出码区分 0 正常 / 1 端口不通 / 2 Chrome 没开 / 3 端口被占，**投递开始前**就暴露问题，不打断循环 |
| **Chrome 调试启动手册** | 含 Chrome ≥136 的三条硬坑与 junction 解法（见下），`start_chrome_debug.bat` 一键起 |
| **邮件确认闭环** | 投递成功后用 `agent-mail` MCP 搜公司域名确认邮件，结果写回 CSV 的 `confirmation` 列（`success` / `pending` / `failed`） |
| **状态口径收敛** | `result` 列只允许 `Submitted / Skipped / Blocked / NeedsUser` 四种最终态；扫描中间态只能进 `notes`，保证统计口径一致 |
| **Submitted 不可降级** | CSV 以 URL 为键 UPSERT 时，已 `Submitted` 的行永不被覆盖成 `Skipped`，新证据只追加备注（这条来自真实数据被误覆盖的事故） |

## 三、适用场景

- 目标站点是**站内一键投递**或**简单 ATS 表单**（Amazon、Valeo、NielsenIQ、SmartRecruiters 等，仓库里有对应实战脚本）
- 手上有 Excel 队列（`队列YYYY-MM-DD.xlsx`），要按优先级顺序批量投
- 需要人工确认边界的保守投递：拿不准的题宁可停下问你，也不瞎填
- 想把投递过程留痕（CSV + issue_log + 汇总报告），事后能复盘

**不适用**：需要破验证码/绕风控的站点；需要登录态托管给第三方的场景；纯 API 可投的站点（没必要上浏览器）。

## 四、主要内容

```
job-delivery/
├── SKILL.md                     主流程（核心原则 8 条 + 6 步工作流 + 实战补丁 10 条）
├── references/
│   ├── delivery-workflow.md     逐岗位操作细节、降级路径、页面模式
│   ├── queue-reading.md         Excel 队列列名兼容与定位规则
│   ├── gmail-mcp.md             邮件确认接口（agent-mail 兼容同一套）
│   └── workbuddy-tooling.md     WorkBuddy 环境下的工具边界
└── scripts/
    ├── check_cdp.py             CDP 预检（纯标准库，退出码 0/1/2/3）
    ├── start_chrome_debug.bat   一键以调试模式启动 Chrome（自动建 junction）
    ├── restart_chrome_debug.py  重启调试 Chrome（含残留进程检测）
    ├── config.py                路径/端口/队列目录集中配置
    ├── raw_cdp_chrome.py        原生 CDP 客户端（WebSocket 直连标签页），tier-2 降级用
    ├── cdp_fallback.py          CDP 降级封装
    ├── cdp_shot.py              纯截图工具
    ├── browser_use_form_fill.py tier-3 表单填充（需 browser-use，可选）
    ├── init_delivery_log.py     初始化 delivery_log.csv
    ├── batch_scan*.py           批量扫「哪些岗位还能投」
    ├── detect_apply*.py         判定页面处于可投/已投/失效
    └── amazon_apply*.py / valeo_apply.py / valeo_step2.py / nielsen_apply.py
                                 实战站点脚本（可当模板改）
```

## 五、Chrome 调试模式的三个硬坑（本技能最值钱的部分）

CDP 连不上，99% 是这三条之一：

1. **必须带 `--disable-gpu --disable-gpu-compositing`** —— 否则有头模式下 `captureScreenshot` 对所有页面挂死（合成器不交付帧）。
2. **调试端口只在 Chrome 启动时生效** —— 已有 Chrome 在跑（含托盘后台）时，新实例会被合并进旧进程，`--remote-debugging-port` 被静默忽略，端口永远不通。必须先完全退出 Chrome。
3. **Chrome ≥136 对默认 profile 禁用调试端口** —— `--user-data-dir` 指向默认 `User Data` 时端口不生效。解法：用**目录联接（junction）**把 `%LOCALAPPDATA%\Google\Chrome\UserData-CDP` 指向真实 `User Data`，路径非默认但仍是同一套文件，**登录态完整保留**且不需要管理员权限。

启动命令（脚本会自动建 junction）：

```bat
"C:\Program Files\Google\Chrome\Application\chrome.exe" ^
  --remote-debugging-port=9222 ^
  --user-data-dir="%LOCALAPPDATA%\Google\Chrome\UserData-CDP" ^
  --disable-gpu --disable-gpu-compositing
```

## 六、使用前必须改的地方

本技能是在一台具体机器上跑出来的，**路径与依赖都是本机口径**，搬家时要改：

| 位置 | 现在写的 | 改成 |
|---|---|---|
| `scripts/config.py` | `C:\Users\<user>\Desktop\工作agent`（可用环境变量 `JD_WORK_AGENT_DIR` 覆盖） | 你的工作目录 |
| `scripts/config.py` | 简历文件名 `Junting_Wu_Resume_EN_2page_updated.pdf` | 你自己的简历 PDF |
| `scripts/batch_scan*.py`、`detect_apply*.py` | 截图/结果输出到 `...\投递状态记录\applypilot-dashboard\scan` | 你的输出目录 |
| `scripts/batch_scan.py`、`detect_apply*.py` | 登录态判断正则里写死了本机用户姓名（`Junting Wu` / `吴俊庭`） | 换成你的姓名，**否则登录检测永远为假** |
| `scripts/detect_apply.py` 等 | 内置了几条具体岗位 URL 作为样例 | 换成你的队列 |
| 依赖 | `websockets>=12.0`、`aiohttp>=3.9`、`openpyxl>=3.1`、`requests>=2.31` | 装到跑脚本的那个 python 环境 |

> `check_cdp.py` 只用标准库，**任何环境都能直接跑**；`raw_cdp_chrome.py` 才需要 `websockets` + `aiohttp`。

## 七、红线（SKILL.md 里的强制约束，别改）

- **不得 kill / 重启用户 Chrome** —— 9222 不通就请用户手动重启，`check_cdp.py` 退出码 1/2 时按话术发给用户等 `done`。
- **不得自动关闭 Agent 打开的标签页**（2026-11-15 用户强制规则，覆盖早期「收尾必关标签」的补丁）—— 标签累积导致 `Target.createTarget` 超时时，先告知用户由用户决定是否清理。
- **单岗位预算 15 次浏览器动作**，同一岗位最多重开/刷新 2 次，超预算即 `NeedsUser` 切下一个。
- **不破验证码、不伪造身份信息** —— 腾讯验证码的隐藏占位容器（`#tcaptcha_transform_dy` / `#tcaptcha_iframe_dy`）会伪装成「页面有验证码」，SKILL.md 里有专门的假阳性排坑。
