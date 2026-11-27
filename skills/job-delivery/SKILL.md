---
name: job-delivery
description: "投递agent - 严格按照队列文件顺序逐岗位执行浏览器自动化投递。操作前必须先截图分析。使用CDP(Chrome DevTools Protocol)直连Chrome自动化操作。集成agent-mail检查确认邮件。实时记录问题并输出最终汇总报告。使用场景：(1) 用户要求按照投递队列执行岗位投递，(2) 用户提到投递agent、投递任务、批量投递、投递队列，(3) 用户需要自动化完成招聘网站上的岗位申请，(4) 用户需要记录投递状态和问题汇总。"
description_zh: "CDP浏览器自动化投递流水线 — 读队列 → 开标签 → 截图分析 → 投递 → 追踪CSV。已移植自Codex(@codex/skills/job-delivery)，适配WorkBuddy CDP原生WebSocket + agent-mail。"
version: 1.0.0
agent_created: true
---

# 投递agent

投递agent是一个严格按照队列文件顺序执行岗位投递的浏览器自动化agent。每个岗位操作前必须先截图再分析，投递失败时走备选路径，所有问题即时记录并最终汇总。

## 核心原则

1. **先截图，后操作（默认路径不可绕过）** - 打开任何网站后，必须先截图并分析，再决定下一步。截图是默认的页面状态来源。即使浏览器操作超时或报错，也必须截图当前可见状态再报告。**例外**：一旦进入 CDP 降级（见原则7），允许以**原生 CDP WebSocket**（Node.js 全局 `WebSocket` + `fetch` 直连 `ws://localhost:9222`）的 DOM/JS 操作为主、截图仅作结果复核——因为此时 agent-browser 已不可用，截图优先仅适用于正常路径。
2. **队列文件为准** - 只按照队列文件的【投递队列】工作表、序号列顺序投递，不跳过、不重排。
3. **复用登录会话** - 直接使用用户Chrome浏览器的已有登录状态，不重新登录。
4. **每条问题必记录** - 任何异常都必须实时记录到issue_log.md，最终输出汇总报告。正常路径下页面状态判断基于截图；CDP 降级路径下以 CDP 为准（见原则1例外）。
5. **浏览器连接检查** - 每次浏览器操作前，执行轻量连接检查：`curl -s http://localhost:9222/json/list`。若端口不通，提醒用户按下方"Chrome调试模式启动"话术重启 Chrome（**不得自行 kill 用户 Chrome——安全边界红线**）。连续失败2次则标记为阻断并跳过该岗位。
5.1 **【2026-11-15 用户强制规则，覆盖下文"收尾关标签"】不得自动关闭任何 Agent 打开的标签页** - 任务收尾时**不调用** `Target.closeTarget`、不关闭任何标签、不 kill / 重启用户 Chrome。所有由 Agent 打开的页面**原样保留在浏览器里**，只有**用户手动关闭浏览器**时才结束。本规则优先于下文"实战补丁第 4 条（投递脚本必须收尾关标签）"。若单次批量任务产生大量标签导致 `Target.createTarget` 超时，**先告知用户**由用户决定是否手动清理，不得自行关。
6. **跳转即切换** - 点击投递按钮时，如果跳转到新标签页或重定向到外部URL，立即关闭原标签页（已无用处），将新页面视为真正的投递页面。在新页面上先截图再继续操作。
7. **WorkBuddy 浏览器操作策略（禁止无限切换）** — WorkBuddy 环境下无 browser-client 底层绑定，核心路径只有两条：(1) `agent-browser` skill（首选，提供截图/Runtime.evaluate/鼠标点击），(2) 原生 CDP WebSocket（Node.js 全局 `WebSocket` + `fetch` 直连 `ws://localhost:9222`，备选）。**每个岗位最多尝试 2 种路径，任一成功即停。2 种都失败 → 立即标记 NeedsUser + 记录原因，进入下一个岗位，禁止反复重试或在这两条路径间来回切换（红线）。** 触发切换的关键词：`TimeoutError`, `Protocol error`, `Connection closed`, `Target closed`。详见 [references/delivery-workflow.md](references/delivery-workflow.md)。
8. **投递后邮件确认** - 每次投递成功后，通过 `agent-mail` MCP（`mcp__agent-mail__GetMessage` / `mcp__agent-mail__SearchMessages`）检查收件箱确认邮件。详见步骤6。

## 状态记录路径

投递状态记录目录: `C:\Users\78422\Desktop\工作agent\投递状态记录`

目录下维护以下文件:
- `delivery_log.csv` - 每条岗位的投递记录（追加写入）
- `issue_log.md` - 实时问题记录（追加写入）
- `delivery_summary.md` - 最终汇总报告（覆盖写入）

**状态口径**：`delivery_log.csv` 的 `result` 列只允许写入四种**最终状态**：`Submitted`（已投递）、`Skipped`（跳过/已投过/已失效）、`Blocked`（阻断）、`NeedsUser`（需用户介入）。扫描阶段的**中间状态**（如 HasApplyButton、Clicked、NeedsInvestigation、RenderingPending 等）不是最终投递结果，只能写入 `notes` 列或独立的扫描清单文件，不得写入 `result` 列，保证汇总统计口径一致。

使用 [scripts/init_delivery_log.py](scripts/init_delivery_log.py) 初始化CSV日志文件。

## Chrome调试模式启动（CDP降级前提）

CDP降级功能要求Chrome以远程调试模式运行。**三条硬性前提**（本机已验证）：

1. **启动时必须带 `--disable-gpu --disable-gpu-compositing`**，否则有头模式下 `captureScreenshot` 对所有页面挂死（合成器不交付帧）。（2026-07-23 验证）
2. **调试端口只在 Chrome 启动时生效**。若已有 Chrome 进程在运行（含后台驻留/系统托盘），后启动的实例会被合并进现有进程，`--remote-debugging-port` 被静默忽略，端口永远不通。必须先**完全退出** Chrome 再以调试模式启动。
3. **Chrome ≥ 136 对默认 profile 禁用调试端口**（2026-07-25 在 Chrome 150 实测）：`--user-data-dir` 指向默认 `User Data` 时 `--remote-debugging-port` 被忽略。**解法：用目录联接（junction）** `%LOCALAPPDATA%\Google\Chrome\UserData-CDP` → 指向真实 `User Data`，同一套文件、路径非默认，调试端口生效且登录态完整保留。`config.ensure_cdp_profile_junction()` 会自动创建（junction 无需管理员权限）。

方式1 — 请用户运行脚本（推荐，自动处理残留 Chrome 检测 + junction 创建）：

    双击或执行 [scripts/start_chrome_debug.bat](scripts/start_chrome_debug.bat)

方式2 — 请用户手动启动（完全关闭所有 Chrome 后；junction 已由脚本或 `config.ensure_cdp_profile_junction()` 创建过）：

    chrome --remote-debugging-port=9222 --user-data-dir="%LOCALAPPDATA%\Google\Chrome\UserData-CDP" --disable-gpu --disable-gpu-compositing

需要用户配合时，直接把下面这段发给用户（与本机验证过的模板一致）：

> 请关闭所有 Chrome 窗口（注意系统托盘的后台 Chrome 也要退出），然后按 Win+R 粘贴以下命令回车：
> `"C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="%LOCALAPPDATA%\Google\Chrome\UserData-CDP" --disable-gpu --disable-gpu-compositing`
> 之前的标签页会自动恢复。完成后回复 done。
> （若提示 UserData-CDP 不存在，先双击运行一次 start_chrome_debug.bat，它会自动建好 junction。）

注意：正常方式打开的 Chrome 没有调试端口，CDP 无法连接。WorkBuddy 环境下直接用 `curl -s http://localhost:9222/json/list` 检测端口，不通则走上述用户配合流程。

## 工作流

### 步骤0: CDP 预检（每次投递运行开始前必做）

在读取队列文件之前，先通过 `scripts/check_cdp.py` 验证 CDP 可用：

    python scripts/check_cdp.py

按退出码处理（**不得在投递中途才发现 CDP 不可用**）：

- **退出码 0**（CDP 正常）-> 直接进入步骤1。
- **退出码 1**（Chrome 在运行但端口不通）-> 立���按"Chrome调试模式启动"节的话术请用户重启 Chrome，**等用户回复 done 后再继续**。不得自行 kill 用户 Chrome（安全边界红线）。
- **退出码 2**（Chrome 未运行）-> 请用户双击 `scripts/start_chrome_debug.bat` 启动调试 Chrome。
- **退出码 3**（端口被占用/HTTP 异常）-> 记录阻断性问题并报告用户。

这样"需要重启 Chrome"只会在投递**开始前**出现一次，不会打断投递循环。

### 步骤1: 加载队列文件

读取队列目录下**最新的** `队列*.xlsx`（优先当天日期，否则取修改时间最新者；忽略 `~$` 开头的 Excel 锁文件）。用 `config.find_latest_queue_file()` 定位，不要写死某个日期的文件名。

读取其【投递队列】工作表，按【序号/排名】列升序排列（该列缺失则用数据行号生成序号），逐个处理每条记录。每条记录至少包含: 序号/排名、岗位名称、公司名称/公司、投递链接/投递地址（列名兼容新旧两种格式，详见 [references/queue-reading.md](references/queue-reading.md)）。

详见 [references/queue-reading.md](references/queue-reading.md)。

### 步骤2: 逐岗位投递（核心循环）

对队列中每个岗位，按顺序执行以下子步骤。详见 [references/delivery-workflow.md](references/delivery-workflow.md)。

#### 2a. 打开投递链接并截图分析

1. **先执行浏览器连接检查**（列出标签页），确保浏览器连接正常。若检查失败，按核心原则第5条处理
2. 用Chrome浏览器打开队列中的投递链接URL
3. 等待页面加载完成后立即截图
4. 分析截图确认:
  - 当前是否处于已登录状态
  - 目标岗位是否仍然存在且可投递

如果未登录/登录过期 -> 截图记录问题，**截图告知用户并等待指示**（不得自行进入备选路径）
如果岗位已失效（截图页面出现以下任一信号）-> 记录问题，走备选路径（2c）。如果页面显示"已投递" -> 记录Skipped+原因"已投递"，直接进入下一个岗位：

岗位已失效信号（截图文本匹配）：

| 语言 | 终止信号（截图可见文本） |
|------|-------------------------|
| 中文 | 已结束、已关闭、已下架、已过期、停止招聘、招满、不再招聘、暂停招聘、过期 |
| 英文 | closed, expired, no longer accepting, position filled, unavailable, removed |
| 日文 | 募集終了、受付終了、掲載終了、締切 |
| 通用 | 404, Not Found, 页面不存在, 链接失效, 该职位不存在, 已删除 |

注意：以上模式需在截图文字中出现并**结合语境**判断，避免通用词误报——例如 "closed/removed/expired/duplicate" 可能出现在"链接已过期""已从收藏移除"等正常文案中，仅当其明确指向**该岗位/职位**状态时才判定失效。整词匹配，不做子串匹配。不需要解析HTML，靠截图视觉判断。

补充信号 — 已投递（无需再次投递，直接跳过）：

| 语言 | 已投递信号（截图可见文本） |
|------|--------------------------|
| 中文 | 已投递、已申请、您已投递、您已申请、已投递过、重复投递 |
| 英文 | already applied、you have applied、previously applied、duplicate |
| 日文 | 応募済み、既に応募、応募履歴あり |

注意：已投递 ≠ 岗位已失效。已投递是好事（之前已处理），直接跳过即可，不需要走备选路径。

#### 2b. 直接投递

截图确认正常后，在当前页面直接投递:
1. 找到投递/申请按钮，点击。如果点击后打开新标签页或URL跳转到外部系统，**关闭原标签页**，切换到新页面并**截图** — 新页面才是真正的投递网址
2. **先填后停（铁律）**：进入表单页后，**必须先把所有能确定的字段全部填完**（姓名/邮箱/电话/地点 + 上传简历 + 答案库已有答案的问题），**然后**才处理不确定字段。禁止一遇到不确定字段就整页放弃——能填多少填多少，把"停"的代价降到最低。
3. 不确定字段的处理优先级：查 `answer_bank.md` 已有答案 -> 填上；答案库没有且属"停止并询问"类（签证/薪资/学籍/自愿声明）-> 截图记录具体问题文本到 issue_log.md，**把已填内容保留在页面上不要关闭标签页**，标记 NeedsUser 并注明"已填完X项，仅剩Y问题待用户回答"。
4. 确认提交（提交后在结果页截图确认）

**单岗位收敛预算（防止无限切换）**: 每个岗位最多 15 次浏览器动作（点击/填写/导航各计1次）。预算耗尽仍未提交 -> 截图当前状态，记录 NeedsUser + 原因 + 已完成的动作摘要，立即切下一个岗位。**禁止在同一岗位反复重新打开/刷新超过2次。**

**投递结果判断**:
- 投递成功（页面显示"投递成功"、"已投递"、"Application submitted"、"Thank you for applying"等确认信息）-> 记录Submitted，进入步骤6确认检查
- 投递失败（提交后页面提示错误、表单校验未通过、网络超时等）-> 记录问题，走备选路径（2c）
- 投递按钮不可用或页面跳转到外部系统 -> 进入备选路径（2c）

#### 2c. 备选投递路径

当直接投递不可行时执行。备选路径中**每一个新页面都必须先截图再分析**，不得跳过:

1. **谷歌搜索**（先截图，再操作） - 用英文搜索 `career + 公司名称`，分析搜索结果截图，找到公司官方招聘网站入口。如果搜索结果中找不到官网 -> 记录问题，标记"未找到官网"，跳过该岗位
2. **登录/注册**（先截图，再操作） - 截图确认登录状态。如需登录/注册则完成（验证码获取见步骤3）
3. **搜索岗位**（先截图，再操作） - 截图确认搜索框位置，搜索岗位名称关键词，截图分析搜索结果
4. **完成投递** - 搜索到了则按网站流程投递（先截图确认岗位页面，再投递）。点击投递按钮后如跳转到新标签页，同样关闭原页面、在新页面截图再继续；搜索不到则标记"未找到"并跳过

### 步骤3: 邮箱验证码与激活链接

注册或登录需要邮箱验证时，使用 `agent-mail` MCP 服务获取验证码/激活链接。
- `mcp__agent-mail__SearchMessages` 搜索收件箱
- `mcp__agent-mail__GetMessage` 读取邮件全文
- `mcp__agent-mail__download_attachment` 下载附件

详见 [references/gmail-mcp.md](references/gmail-mcp.md)（原 Gmail MCP 文档，agent-mail 兼容相同接口）。

### 步骤4: 问题记录

出现以下情况时**立即**记录到 `issue_log.md`:
- 未登录、登录过期或需要验证
- 岗位页面无法打开、已下架或投递按钮不可用
- 队列文件无法读取、工作表不存在、关键列缺失
- 点击投递后新标签页加载失败、浏览器连接失败、页面加载超时、弹窗遮挡、表单字段匹配失败
- 备选投递中搜索不到岗位，或官网无法正常访问
- 邮箱验证码获取失败、激活链接无效或超时

每条问题格式: 【时间/步骤】|【页面URL或截图描述】|【具体现象】

### 步骤5: 最终汇总

每条岗位投递成功后，通过 `agent-mail` MCP 检查确认邮件（见步骤6）。

全部投递完成后输出汇总报告到 `delivery_summary.md`:
- 🔴阻断性问题（无法继续的操作）
- 🟡非阻断性问题（可绕过但需关注）
- 统计: 成功投递数(邮件确认) / 未确认 / 失败 / 跳过

### 步骤6: 投递确认检查

每次投递成功后（status=Submitted），通过 `agent-mail` MCP 检查确认邮件：

1. 记录 `submitted_at` = 当前ISO时间戳
2. 从队列文件中获取 `company_name` 和 `company_domain`
3. 使用 `mcp__agent-mail__SearchMessages` 搜索公司域名/名称的确认邮件
4. 若找到，用 `mcp__agent-mail__GetMessage` 读取全文确认
5. 将结果写入 `delivery_log.csv` 的 `confirmation` 列:
   - `success` -> 记录邮件主题和发送时间
   - `pending` -> 记录"待15分钟后补查"
   - `failed` -> 记录"未收到确认邮件"，写入 `issue_log.md`

通过 `agent-mail` MCP（`mcp__agent-mail__SearchMessages` / `mcp__agent-mail__GetMessage`）完成邮件确认，无需外部 skill 调用。

## 实战补丁（2026-09-11 批次沉淀，均为实测踩坑）

以下 5 条已在本机流水线（`C:\Users\78422\Desktop\工作agent\`）落地，后续运行直接沿用：

1. **「Submitted 不可降级」保护（数据安全红线）** - CSV 回写若以 URL 为键做 UPSERT，**同一岗位的聚合 URL 与还原直链是两条不同键**，极易把历史 `Submitted` 行误覆盖为 `Skipped`（实测：deizao `jobid/211703` → `inn_uwfredb0ouqv`，与历史已投行同岗）。规则：`result` 已为 `Submitted` 的行**永不降级**；新证据为「已下线」时只**追加备注**（如"2026-09-11 复核页面已下线，不改变已投记录"），不覆盖状态。
2. **quanzhi（全职招聘网）还原规则** - 还原信息在 **`input[name=btnUrl]`**，**不在** `data-href`/`onclick`。只读 data-href 会漏还原（实测还原率从 100% 掉到 77.8%）。优先级：`btnUrl` → `data-href` → `onclick` → 正文 `inn_[a-z0-9]+`。注意 `btnUrl` 也可能指向**猎聘**（`liepin.com/lptjob/...`）而非实习僧，需按域名分流。
3. **聚合页偶发「系统发生错误」** - deizao/quanzhi 服务端对部分 jobid 会返回错误页（bodyLen 5000+ 但标题为"系统发生错误"）。**不要据此判 Skipped**，需二次重探（换 tab / 加长等待）——实测 #31 二次重探即恢复正常并成功投递。
4. **投递脚本必须收尾关标签** - 批量投递脚本若不 `Target.closeTarget`，残留标签会累积（实测 22 个投递标签 + 既有 51 = 73 page），导致后续 `Target.createTarget` **超时失败**（表现为 `ERROR timeout Target.createTarget`）。收尾关掉自己开的标签即可恢复。
5. **closed 正则需覆盖各家私有话术** - 已知各家下线表述：实习僧「当前职位已下线」；智联/前程「该职位已下线」；**美团 `zhaopin.meituan.com`「当前职位无法投递」**（易漏）；quanzhi notice 页「已过期」。扫描正则必须包含「无法投递」这类变体，否则会把已下线岗位误判为 CAN_APPLY。

### 2026-09-17 批次追加（4 条，均为造成系统性误判的缺陷）

6. **验证码检测假阳性 —— 腾讯验证码 SDK 的隐藏占位容器（影响面最大）** - 凡接入腾讯验证码的站点（实习僧、超级简历等）**在每个页面都会预注入**两个隐藏占位：
   - `#tcaptcha_transform_dy`：DIV，`opacity: 0` + `position: absolute` + `top: -1e6px`（屏幕外）
   - `#tcaptcha_iframe_dy`：IFRAME，300×150

   二者 `offsetWidth/offsetHeight` **都 > 0**，因此「`offsetWidth>0` 即视为可见」的判定**完全失效**。叠加分类分支 `else if (info.capt)` 排在按钮检测之前，会导致**活岗被判 CAPTCHA 而搁置**、并虚增 `NeedsUser`（实测一批 29 条误判，直接漏投 5 个上海数据/AI 实习岗）。

   **正确判定 = 真实可命中**（矩形须落在视口内 **且** `elementFromPoint` 命中自身或后代）：
   ```js
   const visHit = e => {
     const r = e.getBoundingClientRect();
     if (r.width <= 0 || r.height <= 0) return false;
     if (r.bottom <= 0 || r.right <= 0 || r.top >= innerHeight || r.left >= innerWidth) return false;
     const cx = Math.min(Math.max(r.left + r.width / 2, 1), innerWidth - 2);
     const cy = Math.min(Math.max(r.top + r.height / 2, 1), innerHeight - 2);
     const hit = document.elementFromPoint(cx, cy);
     return !!hit && (hit === e || e.contains(hit) || hit.contains(e));
   };
   ```
   正文文案正则（`图形验证码|请拖动|安全验证`）**不能**替代上述判定——这些页面正文命中为空字符串，只有元素判定能区分真假。**修复后务必对历史 CAPTCHA 记录做一次复检**（实测 29 条 → 0 条真验证码，捞回 8 个可投岗）。

7. **导航失败会污染「僵尸页」检测 —— `chrome-error://chromewebdata`** - 导航失败时 Chrome 落在 `chrome-error://chromewebdata`。若把该 URL 写进 `lastLanded`，则**下一个同样失败的岗位会再次落到同一 URL**，被「落地 URL == 上次落地 URL = 僵尸页」规则误判（实测一批 9 条级联误判）。
   修复：`nav()` 检测到 `chrome-error:` 时**直接抛错归因，绝不写入 `lastLanded`**；同时开启 `Network` 域采集主文档 HTTP 状态码并失败重试 2 次，按状态码归因：`404/410 → CLOSED`、`403/429/451 → BLOCKED`（风控/地域墙，非死岗）、连接类错误 → `DEAD_LINK`。只靠 `Page.navigate` 的 `errorText` 无法区分这几种情况。

8. **rank 绝对不能作主键（数据污染级）** - 队列里的 `排名/rank` 只是**队列内的展示序号**，跨批与**批内**都会重复（实测 147 条里 `675`/`67`/`46`/`684` 各出现 3 次，`24`/`58`/`477`/`737` 等各 2 次）。用 rank 作键会导致：
   - 回写时 **A 岗位的结论被写到 B 岗位行上**（实测：益普索的 `Submitted` 被写到「博世 Bosch」行）
   - 合并多轮探测结果时**按 rank 去重会静默丢岗**（147 条缩到 128 条，丢失的岗其结论无处落地）

   **规则：实投结果、人工 override、多轮探测合并一律以 URL（归一化后）为主键**，rank 仅用于展示与排序。

9. **LinkedIn 两条不同申请路径，必须分别识别** - 点「申请」后有三种走向，不能一律按 Easy Apply 处理：
   - **档案发送**：站内提示「您的职业档案已发送给职位发布者。撤销」→ 无需表单，记 `Clicked / linkedin_profile_sent`
   - **Easy Apply 弹窗**：出现 `input[type=file]` + 「下一步/提交申请」→ 需上传简历并逐步提交
   - **跳转外部 ATS**：LinkedIn 会弹出「**您提交申请了吗？是/否**」确认框，说明申请实际发生在外部站。此时必须**记录新开的标签页 URL**（实测 Morgan Stanley → `morganstanley.eightfold.ai/careers/job/...`，Bloomberg 亦可能同理），否则会误判为"点击无响应"。

   **红线：「您提交申请了吗」确认框不要自动点「是」**——会虚报已申请，留人工按实情作答。另外 `jp.linkedin.com` 会 301 到 `www.linkedin.com` 且**可用**（未 geo-block），探测时需 `RELAX` 放行合法跨域跳转。

**去重键配套建议**：队列侧若给聚合 URL、CSV 侧存还原直链，`find_applicable.py` 必须**同时索引 `notes` 中的 URL**（本机已实现），否则已投岗位会反复回流。回写时在 `notes` 里保留「聚合原链: <url>」实现双向匹配。

### 2026-09-22 批次追加（3 条）

10. **CSV 同一 URL 存在多行冲突状态 → 生成任何工作清单前必须先做「URL 级优先级解析」（数据安全级，防重复投递）** - `delivery_status.csv` 是**追加式**的，同一 URL 会被多批次反复写入，导致**同一 URL 多行、状态互相矛盾**（实测 1799 唯一 URL 中有 **82 个**冲突；例：eBay `inn_c5wukh97vpbr` 同时存在 `NeedsInvestigation` 与 `Submitted` 两行）。
    若按「任一行 result == NeedsInvestigation 就选中」生成待投清单，会把**早已 Submitted 的岗位重新纳入待投**（实测误纳 5 个已投实习僧岗：eBay / 益普索 / 傅利叶 / Momenta / 阶跃星辰 → 修正后实习僧 NI 由 25 → 0）。
    **规则：先按归一化 URL 分组，再套用优先级取有效状态**，顺序为：
    `Submitted / Clicked`（终态成功，绝对优先）→ 已核实死岗 `Skipped`(method ∈ closed/expired/duplicate/404) → `PENDING_APPLY` → `NeedsUser` → `NeedsInvestigation`。
    产物建议落一份有效状态快照（本机 `_eff_status_*.json`），后续所有统计与选岗都以它为准，不要直接 `Counter(CSV.result)`。

11. **CDP 坐标点击对「视口外元素」静默失效 → 必须先 `scrollIntoView` 再取坐标** - `getBoundingClientRect()` 返回的是**相对视口**坐标，元素在折叠线以下时 `y` 会远大于视口高度（实测 TribePad `Submit Registration` 按钮 `y = 1557`，而视口仅 898px），此时 `Input.dispatchMouseEvent` 的点击**落在页面空白处且不报错**，表现为「点了没反应」。
    **正确做法**：
    ```js
    await ev(`(() => { const el = <定位表达式>; el.scrollIntoView({block:'center'}); return 1; })()`);
    await sleep(700);
    const pt = await ev(`(() => { const r = <定位表达式>.getBoundingClientRect();
      return {x: Math.round(r.x+r.width/2), y: Math.round(r.y+r.height/2)}; })()`);
    await clickXY(sid, pt.x, pt.y);
    ```
    仍无效时用 `el.click()`（JS click）兜底 —— 对原生表单提交足够（实测注册表单即靠兜底成功）。
    **另**：按钮文本匹配必须用**精确全等**（`^submit registration$`），用 `/register/i` 会命中导航栏的「Register」链接而误跳页并清空已填表单。

12. **TribePad（`*.tal.net`）ATS 申请配方 —— 免登录注册 + 简历解析全自动** - 实测 `blackrock.tal.net`（BlackRock 校招/项目类岗，**与 Workday 是两套系统**，账号不通用）：
    1. 职位页点 `Apply Now` → `tal.net/.../candidate/so/pm/1/pl/1/opp/<id>/apply`
    2. 申请中心有两个入口：`Upload Resume`（自动解析）或 `Fill in application form manually`（二者都是 `input[type=submit][name=submit_form]`）
    3. 点 `Upload Resume` → 进**注册页**（`candidate/application/<appId>`）：字段 `register_form_firstname` / `_lastname` / `_new_user`（邮箱）/ `reemail` / `_new_password` / `_passwordconf`，勾选框 `register_form_agree`（label 文本是 **`Yes*`** 不是 `Yes`），提交按钮 `Submit Registration`
    4. 注册成功标志：URL 的 `user-<id>` 变化 + 导航栏出现**候选人姓名**
    5. 回到申请中心点 `Upload Resume` → `.../parsecv/upload/<id>`，`input[type=file]#parse_cv_form_parse_cv_file` 用 `DOM.setFileInputFiles` 上传 → 点 `Parse CV` → 自动进入多步申请表 `candidate/eform/<id>/page/1`
    6. **申请表含不可代答项**：`Work Authorization`（「Do you have legal authorization to work in the country work location? Yes/No/Unsure」法律声明）+「**每个学年仅可提交一个 program 申请**」。**遇此二项必须停下交用户确认，不得猜测作答**（对应本技能安全边界「不得猜测或编造用户身份、签证」）。

### 2026-11-15 批次追加（BOSS 直聘：反风控 + 简历同步）

11. **BOSS 直聘（zhipin.com）会检测 CDP 注入并自行关页** - 给页面 attach `Runtime` 域后，页面会调 `window.close()`（Chrome 日志：`Scripts may close only the windows that were opened by them`），标签页变成 `about:blank`，且**不产生崩溃转储**（风控主动关页，不是崩溃）。
    - **安全做法**：只挂 `Page` / `DOM` / `Network` 域；读页面文本用 `DOM.getDocument(depth=-1)` 遍历树（过滤 `STYLE`/`SCRIPT` 子树），**不执行页面 JS**。
    - **最稳做法**：`PUT /json/new?<url>` 裸开标签页（不 attach）→ 页面加载完再 attach → 操作完换新页。
    - 交互元素多为 hover 才显示（`display:none` → `DOM.getBoxModel` 报 "Could not compute box model"）：先 `DOM.scrollIntoViewIfNeeded` → `Input.dispatchMouseEvent{mouseMoved}` 悬停 → 重新取盒模型 → 点击。**「悬停→点击」必须放在同一次 CDP 执行内**，分两次执行菜单会关掉。
    - 填输入框（无 Runtime）：点击聚焦 → `Input.dispatchKeyEvent`(Ctrl+A, `modifiers:2`) → `Input.insertText`。
    - 上传附件简历：`Page.setInterceptFileChooserDialog{enabled:true}` → 点「上传附件简历」→ 读 `Page.fileChooserOpened` 的 `backendNodeId` → `DOM.setFileInputFiles` → 弹窗点「确定添加」（落库接口 `/wapi/zpgeek/resume/attachment/save.json`）。
    - BOSS 自带「同步至在线简历」向导（附件 ⋮ → 同步至在线简历）逐段解析 PDF 供确认；**项目经历段长期卡「加载中」**，自动同步不可靠 → 按 PDF 口径手动改字段更稳。
    - 参照实现：`C:\Users\78422\WorkBuddy\2026-11-15-16-38-04\boss_ops.py` / `boss_upload4.py` / `chrome_watchdog.py`。

## 安全边界

- **Chrome 进程保护（红线）** - 任何步骤（包括 cleanup、连接恢复、降级重试）都**不得 kill、关闭或重启用户的 Chrome 进程**（禁止 taskkill/taskkill 等效操作）。调试模式重启必须由用户亲手执行，或经用户明确同意后由 start_chrome_debug.bat 交互式执行。若发现 Chrome 未以调试模式运行 -> 截图告知用户，按"Chrome调试模式启动"节的话术请用户操作，**不得自行处理**。
- 浏览器连接异常 -> 执行连接恢复流程（见核心原则第5条）
- CAPTCHA/Cloudflare/reCAPTCHA -> 停止该岗位（不破解），**保留该网页/标签页不关闭**、截图并记下 URL，标记 NeedsUser(captcha)，随后继续下一个岗位（不中断整体流程）
- 登录过期/需要重新登录 -> 截图告知用户，等待指示
- 支付/订阅提示 -> 立即停止，记录问题
- 不得猜测或编造用户身份、签证、薪资等信息
- **禁止自写批量脚本绕过本流程（红线）** - 不得临时编写 batch_apply/batch_scan 之类的脚本，用 JS `.click()` 点按钮来批量处理岗位。批量处理任何状态分组前必须满足两个前提：(1) 已在调试 Chrome 中确认对应平台**已登录**（截图证明）；(2) 逐岗位走本技能 2a-2c 流程（截图决策 + CDP `Input.dispatchMouseEvent` 坐标点击），允许把流程循环化，但不允许用 DOM 文本判断替代截图、用 JS click 替代坐标点击。

## 运行环境与依赖

- **集中配置**：所有路径、代理、API key、插件脚本探测都集中在 [scripts/config.py](scripts/config.py)。敏感信息（Composio key、候选人身份）**不硬编码**，分别从环境变量 `COMPOSIO_API_KEY` 与 `candidate_profile.json` 读取。
- **Python 依赖**：见 [scripts/requirements.txt](scripts/requirements.txt)（`websockets`、`aiohttp`、`openpyxl`、`requests`；`browser-use` 为可选的 Tier-3）。先用 `pip install -r scripts/requirements.txt` 安装。
- **路径环境变量**：`JD_STATUS_DIR`、`JD_RESUME_PATH`、`JD_QUEUE_DIR`、`JD_CHROME_PATH`、`JD_DEBUG_PORT`、`JD_PROXY` 等可覆盖默认值，便于迁移。

## 相关文件

- [队列读取说明](references/queue-reading.md)
- [投递工作流详解](references/delivery-workflow.md)
- [Gmail MCP使用指南](references/gmail-mcp.md)
- [集中配置](scripts/config.py)
- [状态记录脚本](scripts/init_delivery_log.py)
