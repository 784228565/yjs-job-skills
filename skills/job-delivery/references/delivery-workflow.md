# 投递工作流详解

> ⚠️ **WorkBuddy 移植注意**：本文档为 Codex 原始版本，其中引用的 `browser-client`、`get_shared_cdp()`、`cdp_fallback`、`auto_start` 在 WorkBuddy 中不存在。**不要按照文中"三级降级(Tier-2/Tier-3)"流程操作**——那会触发 agent 反复切换、无法推进的已知 bug。WorkBuddy 下的浏览器操作策略以 `SKILL.md` 原则 7 为准：「2 路径封顶，失败即标 NeedsUser」。

## 单岗位投递完整流程

```
浏览器连接检查（列出标签页）
  -> 打开URL -> 截图 -> 分析截图
  |
  +-- [未登录/登录过期] --> 截图告知用户，等待指示
  +-- [已投递]          --> 记录 Skipped(已投递) -> 下一个岗位
  +-- [登录正常+岗位存在] --> 点击投递按钮
        |
        +-- [新标签页打开] --> 关闭原标签页 -> 截图 -> 在新页面继续投递
        |     +-- [投递成功] --> 记录 Submitted -> 确认检查 -> 下一个岗位
        |     +-- [投递失败/表单错误] --> 记录问题 -> 备选路径
        +-- [同页面URL跳转] --> 截图 -> 在新URL继续投递
        |     +-- [投递成功] --> 记录 Submitted -> 确认检查 -> 下一个岗位
        |     +-- [投递失败] --> 记录问题 -> 备选路径
        +-- [投递按钮失效/无跳转] --> 备选路径
              |
              +-- Google搜索 "career+公司名" -> 截图分析搜索结果
              |     +-- [需注册/登录] --> 注册/登录（Gmail获取验证码）
              |     +-- [已登录]      --> 搜索岗位
              |           +-- [搜索到]   --> 截图确认岗位页 -> 点击投递按钮
              |           |                 +-- [新标签页] --> 关原页->截图->继续
              |           |                 +-- [同页跳转] --> 截图->继续
              |           +-- [搜索不到] --> 标记"未找到" -> 下一个岗位
              +-- [找不到官网] --> 记录问题 -> 下一个岗位
```

## 浏览器连接检查

每次浏览器操作前，先执行轻量连接检查：

1. 调用列出标签页（list tabs）等轻量操作，验证浏览器是否响应。
2. 如果操作超时或返回错误：
   - **先截图**当前浏览器可见状态（不管显示什么，先截下来）。
   - 自动运行插件自带的 `open-chrome-window.js`（用 `config.find_plugin_browser_script()` 动态定位，不写死版本号）。
   - 等待 3 秒，重试连接检查。
3. 连续失败 2 次 → 标记为阻断性问题（浏览器不可用），记录到 issue_log.md，跳过当前岗位。
4. 连接恢复正常后继续执行。

## CDP 饱和超时降级（Tier-2）

复杂 React SPA 页面可能导致浏览器客户端 CDP 命令队列积压，抛出 TimeoutError 等异常。此时自动切换至 RawCDPChrome。**进入降级后，"截图优先"规则放宽：允许以 CDP/DOM 操作为主、截图仅作结果复核**（browser-client 此时已不可用）。

### 触发条件（以下任一出现即触发）

- 浏览器工具返回超时（>30 秒无响应）。
- 错误信息包含（词边界匹配）：`TimeoutError`、`CDP`、`timeout`、`Protocol error`、`Connection closed`、`Target closed`、`Session closed`、`Command timed out`、`waiting for target`。
- `fill()`、`click()`、`screenshot()`、`evaluate()` 任一操作卡死或超时。

### 降级步骤

1. 捕获超时异常后，记录日志："原浏览器操作超时，已切换至原始 CDP 模式继续投递"。
2. 执行以下 Python 代码（通过共享连接，自动按需启动 Chrome 调试模式）：

```python
import sys; sys.path.insert(0, r"C:\Users\78422\.codex\skills\job-delivery\scripts")
from cdp_fallback import get_shared_cdp
cdp = get_shared_cdp()   # auto_start=True，端口不通时自动拉起调试 Chrome
```

3. 降级后所有后续步骤改用 RawCDPChrome 执行，不再回退到原浏览器客户端。
4. 任务完成后调用 `cdp_fallback.close_shared_cdp()` 关闭 WebSocket，不关闭 Chrome 进程。

### 降级后操作映射

| 原浏览器工具操作 | RawCDPChrome Python 替代 |
|---|---|
| navigateToUrl(url) | `cdp.navigate(url)` |
| actOnVisiblePage(fill) | `cdp.fill(selector, value)` |
| actOnVisiblePage(click) | `cdp.click_element(selector)` |
| actOnVisiblePage(checkbox) | `cdp.click_checkbox(selector)` |
| upload(selector, path) | `cdp.upload_file(selector, path)` |
| saveScreenshot(path) | `cdp.save_screenshot(path)` |
| evaluateScript(js) | `cdp.evaluate(js)` |

### 完整降级示例

候选人身份用 `config.candidate_contact()` 读取（**不要把真实邮箱/姓名写进代码；也不要猜 candidate_profile.json 的内部结构**——身份字段嵌套在 `candidate` 键下，直接 `profile.get("first_name")` 会得到空串）：

```python
import sys; sys.path.insert(0, r"C:\Users\78422\.codex\skills\job-delivery\scripts")
import config
from cdp_fallback import get_shared_cdp, close_shared_cdp

me = config.candidate_contact()   # {full_name, first_name, last_name, email, phone, location}
assert me["email"], "candidate_profile.json 缺少 email"
cdp = get_shared_cdp()

cdp.navigate("https://jobs.example.com/position/xxx")
cdp.save_screenshot(str(config.SCREENSHOT_DIR / "step1.png"))

cdp.fill('input[name="firstName"]', me["first_name"])
cdp.fill('input[name="lastName"]',  me["last_name"])
cdp.fill('input[name="email"]',     me["email"])

# 上传简历（MIME 类型按扩展名自动推断）
cdp.upload_file('input[type="file"]', str(config.RESUME_PATH))

cdp.click_element('button[type="submit"]')
cdp.save_screenshot(str(config.SCREENSHOT_DIR / "result.png"))

close_shared_cdp()
```

## browser-use 降级（Tier-3）

当 RawCDPChrome 也失败时（如元素定位失败、表单验证不通过），使用 browser-use 作为最后兜底：

1. 调用 `fill_form_with_browser_use()`（同步）或 `await afill_form_with_browser_use()`（异步上下文）。
2. 传入当前 URL、表单数据（来自 `candidate_profile.json` 和 `answer_bank.md`）、简历路径。
3. browser-use 用 LLM 视觉理解页面并自动填写表单字段。
4. **默认不自动提交**（`auto_submit=False`）：填写完成后截图，由调用方复核后再提交。确需自动提交时传 `auto_submit=True`。

优势：不需要手动指定 CSS selector，LLM 自动识别表单结构。
代价：依赖 LLM API，成本较高、速度较慢。

降级优先级：`browser-client`（默认）→ `RawCDPChrome`（Tier-2，CDP 超时）→ `browser-use`（Tier-3，CDP 也失败）。

## 截图分析规范

### 截图时机

- 打开任何新 URL 后立即截图。
- 页面跳转后截图。
- 提交表单后截图。
- 弹窗/提示出现后截图。

### 分析内容

每次截图后必须分析：
1. **登录状态**：页面是否有登录用户的标记（头像、用户名、"我的"、"已登录"等）。
2. **岗位状态**：岗位标题是否存在、是否显示已下架/已关闭/已过期/404 等。
3. **可操作元素**：投递/申请按钮是否存在且可点击。
4. **弹窗/遮挡**：是否有弹窗、广告、cookie 提示遮挡操作。

### 岗位已失效信号（截图文本匹配，需结合语境）

以下文本出现在截图中**且明确指向该岗位状态**时判定失效。整词匹配，避免通用词（closed/removed/expired/duplicate）在正常文案中的误报：

| 语言 | 信号文本 |
|------|---------|
| 中文 | 已结束、已关闭、已下架、已过期、停止招聘、招满、不再招聘、暂停招聘 |
| 英文 | closed、expired、no longer accepting、position filled、no longer available |
| 日文 | 募集終了、受付終了、掲載終了、締切 |
| 通用 | 404、Not Found、页面不存在、链接失效、该职位不存在、已删除 |

### 已投递信号（截图文本匹配）

以下文本出现即判定用户已投递过该岗位，直接跳过（**已投递 ≠ 已失效**，是好事，不重投、不走备选路径）：

| 语言 | 信号文本 |
|------|---------|
| 中文 | 已投递、已申请、您已投递、您已申请、已投递过、重复投递 |
| 英文 | already applied、you have applied、previously applied |
| 日文 | 応募済み、既に応募、応募履歴あり |

### 不可直接解析 HTML（正常路径）

**正常路径下禁止**：跳过截图直接解析 HTML/DOM；用 Python requests/urllib 直接请求页面；用 JS eval 替代截图分析页面内容。

**唯一合法路径（正常路径）**：截图 → 分析截图 → 决策。浏览器不可用时 → 截图当前状态 → 记录问题 → 报告用户。
（进入 CDP 降级后此限制放宽，见"CDP 饱和超时降级"。）

## 页面跳转与标签页管理

点击投递按钮后的常见跳转模式：

1. **新标签页打开**（最常见）：LinkedIn、Boss直聘等点击"申请"后在新标签页打开外部 ATS（Greenhouse、Lever、Workday）。此时立即切换到新标签页、关闭原标签页、在新标签页截图后继续。
2. **同页面 URL 跳转**：当前标签页 URL 变化进入投递流程，截图确认后继续。
3. **无跳转/弹窗**：部分平台用弹窗或内嵌表单投递，截图确认后在弹窗内完成。

核心原则：**原页面永远是信息页，跳转后的新页面才是真正的投递页面。不要在原页面逗留。**

## 直接投递详细步骤

### ATS 平台识别

| ATS/平台 | 识别特征 | 投递策略 |
|-----------|---------|---------|
| LinkedIn Easy Apply | linkedin.com + "Easy Apply"按钮 | 自动填充 LinkedIn profile |
| Boss直聘 | zhipin.com | 使用在线简历沟通 |
| 51job | 51job.com | 投递简历按钮 |
| 猎聘 | liepin.com | 立即投递按钮 |
| Greenhouse | greenhouse.io | 标准表单填写 |
| Lever | lever.co | 标准表单+确认页 |
| Workday | myworkdayjobs.com | **跳过（重 ATS，已知能力缺口）** |
| 官网招聘系统 | career/company 域名 | 按网站流程投递；新标签页打开则关原页继续 |

> **已知限制**：Workday 类重型 ATS（多步账户创建 + 动态表单）当前直接跳过并记录，不自动投递。

### 表单填写策略

使用集中配置的资源（见 `config.py`）：
- **简历**：`config.RESUME_PATH`
- **答案库**：`config.ANSWER_BANK_PATH`
- **候选档案**：`config.CANDIDATE_PROFILE_PATH`（姓名、邮箱、电话、地点等均由此读取）

自动填写的字段（从 candidate_profile.json 获取）：姓名、邮箱、电话、地点。

**停止并询问用户的字段**：签证/工作许可、薪资期望、自愿身份声明（默认"不愿透露"/留空）、自定义开放问题。

### 投递成功确认

只有以下情况才算投递成功：
- 页面显示"投递成功"/"申请已发送"/"Application submitted"/"Thank you for applying"。
- URL 中包含 thanks/thank-you/submitted/confirmation。
- 平台状态明确显示申请已发送。

不算成功：已收藏/已保存；仅点击提交按钮但未看到确认；自动填充完成但未提交。

## 备选路径详细步骤

### Google 搜索

1. 打开 google.com，**先截图**。
2. 搜索关键词：`career [公司英文名]` 或 `[公司英文名] careers`，**截图**搜索结果。
3. 找不到官网 → 记录问题，标记"未找到官网"，跳过该岗位。
4. 点击进入官网，**截图**确认页面状态。

### 官网注册/登录

1. 截图确认是否需要登录。
2. 如需注册：使用 candidate_profile.json 中的姓名、邮箱；密码用 12 位以上随机生成并记录到笔记；邮箱验证码通过 Gmail MCP 获取；注册成功后截图记录账号信息。
3. 如需登录：检查 Chrome 是否已保存密码自动填充；没有保存密码且用户未提供 → 记录阻断性问题。

### 官网搜索岗位

1. 截图找到搜索框。
2. 输入岗位名称关键词（从队列文件获取）。
3. 搜索结果截图分析。
4. 找到匹配岗位 → 走该网站投递流程；搜索不到 → 在 issue_log.md 记录并标记跳过。

## 错误处理和重试

- **CDP 命令超时** → 自动切换至 RawCDPChrome（见 CDP 降级）；端口不通则 auto_start 拉起调试 Chrome。
- **浏览器连接失败** → 自动运行 `open-chrome-window.js`，等待 3 秒重试一次；连续 2 次失败标记阻断并跳过。
- **页面加载超时（>30秒）** → 重试一次，仍超时则记录问题并跳过。
- **弹窗遮挡** → 截图弹窗状态 → 尝试关闭（ESC/关闭按钮），失败则记录问题。
- **表单验证失败** → 检查填写内容，修正后重试一次，仍失败则记录问题。
- **上传简历失败** → 检查文件是否存在，重试一次，仍失败则记录问题。

## SPA 表单惰性渲染处理（Greenhouse/React 系常见）

症状：点了 Apply 按钮，表单不展开；页面上只有 cookie 框/订阅框等无名 input，named 字段（first_name/last_name/email）迟迟不出现（真实案例：Greenhouse job-boards）。

**禁止**在这种页面反复刷新重开。按以下配方处理（CDP 层）：

```python
import time
# 1) 先滚动触发懒加载（分 3 段滚到底，每段停 0.8s）
for frac in (0.33, 0.66, 1.0):
    cdp.evaluate(f"window.scrollTo(0, document.body.scrollHeight * {frac})")
    time.sleep(0.8)

# 2) 轮询等 named 字段出现（最多 12 秒）
found = False
for _ in range(24):
    if cdp.evaluate("!!document.querySelector('input[name=\"first_name\"],input[name=\"firstName\"],input[type=\"email\"]')"):
        found = True
        break
    time.sleep(0.5)

# 3) 仍未出现 → 用坐标级真实点击再点一次 Apply，然后再轮询一次
if not found:
    cdp.click_element('button')   # 或带文本的 Apply 按钮
    for _ in range(24):
        if cdp.evaluate("!!document.querySelector('input[name=\"first_name\"],input[name=\"firstName\"],input[type=\"email\"]')"):
            found = True
            break
        time.sleep(0.5)

# 4) 两轮都失败 → 记录 NeedsInvestigation 并附截图，切下一个岗位（计入收敛预算）
```

要点：**滚动 → 轮询 → 坐标点击 → 再轮询**，两轮封顶。不要用 JS `.click()` 连点（React 可能不响应非可信事件）。

## 投递后确认检查

每次投递成功后（status=Submitted）自动执行，详见 `application-confirmation-checker` skill：

1. 记录 `submitted_at` = 当前 ISO 时间。
2. 传入 `company_name`、`company_domain`（从队列文件获取）、`submitted_at`。
3. 等待 checker 按三层搜索 + 五轮轮询（60s/90s/120s/180s/300s）返回结果。
4. 根据返回 `status` 更新 `delivery_log.csv`：
   - `success` → confirmation 列写入邮件主题 → 下一个岗位
   - `pending` → confirmation 列写入"待补查" → 下一个岗位
   - `failed` → confirmation 列写入"未确认"，issue_log 记录详情 → 下一个岗位

详见 [scripts/raw_cdp_chrome.py](../scripts/raw_cdp_chrome.py)、[scripts/cdp_fallback.py](../scripts/cdp_fallback.py)、[scripts/browser_use_form_fill.py](../scripts/browser_use_form_fill.py)。
