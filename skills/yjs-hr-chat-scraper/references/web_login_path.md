# Web 端路径（免 iPhone 抓包）—— 2026-11-15 实测打通

> 结论：**大多数场景不要再用 iPhone + mitmproxy 抓包**。
> yjs 的「谁对我感兴趣」等 HR 互动数据在 **web 端个人中心可直接读**，30 秒出结果。
> 只有要「HR 聊天记录全文 / 待回复会话」才需要 IM 凭证。

---

## 路径 A：投递反馈 applyV2（推荐，回答「谁对我感兴趣」）

### 入口
`https://q.yingjiesheng.com/pc/personal?tab=2` → 右上角头像 → 「投递反馈」

页面实际会打开新标签 `q.yingjiesheng.com/pc/personal?tab=2`，其上有：
- 3 个**来源 tab**：应届生求职 / 网申 / 前程无忧（`<span>` 裸元素）
- 5 个**状态筛选**：全部 / 已查看 / 感兴趣 / 邀面试 / 不合适（`.tab-options-option2 > span`）
- 右上角计数区 `.counts`：如 `["1082 已投递","187 已查看","1 通过筛选","0 邀面试"]`

### 接口
```
GET https://youngapi.yingjiesheng.com/open/yjs/applyV2
    ?version=11.1.0&api_key=xy&timestamp=<unix秒>&partner=wspcsucceedb1
    &pageNo=1&pageSize=100&applyStatus=<状态码>&tab=<yjs|xyz|51job>&isJobValid=
```

**必需请求头**（缺一个就 400 / CORS 失败）：
```
sign: <前端算的 sha256>
user-token: <Yjs_UToken cookie>
account-id: <Yjs_UAccountId cookie>
uuid: <CookieUuid cookie>
partner: wspcsucceedb1
From-Domain: yjs_web
property: <URL编码的 JSON>
Referer: https://q.yingjiesheng.com/
```

### applyStatus 对照
| 值 | 含义 | 本机实测 |
|---|---|---|
| `''` | 全部 | 969 条 |
| `03` | 已查看 | 187 条 |
| **`04`** | **感兴趣** | **32 条 / 20 家** |
| `06` | 邀面试 | 0 条 |
| `07` | 不合适 | 有 |

### 响应结构
```json
{"status":"1","message":"成功","resultbody":{
  "items":[{ "coName":"汇丰银行（中国）有限公司", "jobName":"...", "ctmId":"136035",
             "jobId":"172493426", "salaryStr":"...", "companySizeStr":"5000-10000人",
             "companyTypeStr":"外资（欧美）", "sendDateTime":"2026-07-30 18:03",
             "statusUpdateTimeFormat":"2026-07-30 19:41", "jobTag":"[...]", "hrUid":"..." }],
  "totalNums":969, "count":100, "recommendJobs":[...] }}
```

### 抓取姿势（关键）
1. CDP 连接 → 打开 personal 页 → 等 SPA 渲染完
2. **点 UI 标签**（来源 tab × 状态标签），让页面自己发请求（页面会算 `sign`）
3. `Network.requestWillBeSent` 记 URL，`Network.responseReceived` + `loadingFinished` 后
   `Network.getResponseBody` 取 body
4. 解析 `applyStatus` query 参数确认状态码

**为什么不能自己 fetch**：`sign` 由前端 JS 算，裸 fetch 报 `TypeError: Failed to fetch`（CORS 预检失败）；
复用页面的 sign 改 `pageNo` 会 400（400 Bad Request）。

### 坑
| 坑 | 现象 | 解法 |
|---|---|---|
| 分页 | `items` 最多 100 条，页面**无分页器** | 「感兴趣」32 条一页装完没问题；「已查看」187 条只能拿前 100 |
| 重复计数 | 3 个来源 tab 数据独立 | 必须遍历 3 个 tab 再按 `(jobId, ctmId)` 去重合并 |
| `totalNums` | 各状态下都是 969（全部数），不是筛选后数 | 判断完整性看 `len(items)` 与 UI 计数 |
| 标签点击 | `document.querySelectorAll('a,button')` 找不到 | 状态标签是 `.tab-options-option2 span`；来源 tab 是裸 `span` |

---

## 路径 B：IM 凭证（web 端换，免 iPhone 抓包）

```
Chrome 登录态 cookie（应届生真实 profile）
  ├─ Yjs_UAccountId = 278645129          → URL 参数 accountId
  └─ Yjs_UToken    = <32位 hex>（HttpOnly）→ URL 参数 token + 请求头 USER-TOKEN
        ↓
https://chat.51job.com/?accountId=<aid>&token=<tk>
        ↓
页面自动 POST https://cupid.51job.com/imbc/open/ehire/txinit?api_key=ehire&timestamp=<unix秒>
  body   : {"accountId":"<aid>","thirdToken":"<Yjs_UToken>","memberType":"1"}
  headers: ACCOUNT-ID, USER-TOKEN, sign, UUID, From-Domain: ehire_web
        ↓
成功 → resultbody{userSig, sdkAppID, userID}
失败 → {"status":"110100","message":"账号异常，注销登录"}  ← 需重新登录应届生刷新 token
```

**这一步在 2026-11-15 实测失败**（token 已被服务端注销），所以路径 A 才是当前可用的答案来源。

---

## 通用 CDP 踩坑（本机 Chrome 157）

| 坑 | 现象 | 解法 |
|---|---|---|
| Bash 沙箱回收 Chrome | Chrome 启动后 ~10s 消失，`9222` 拒绝连接 | 启动 Chrome 与所有 CDP 操作都用 `dangerouslyDisableSandbox: true`；或把「启动→抓取→关闭」写进**同一个**脚本进程内 |
| `Runtime.evaluate` 的 `awaitPromise` 失效 | 注入 async IIFE 后返回值是 `{}` | 三步：`window.__p = (async()=>{...})()` → `window.__p.then(v=>{window.__out=v;window.__done=true}, e=>{window.__err=String(e);window.__done=true})` → 轮询 `window.__done` |
| alert 弹窗阻塞 JS | 页面弹「请传入必须参数：accountId、token」后所有 eval 卡住 | 监听 `Page.javascriptDialogOpening` → `Page.handleJavaScriptDialog {accept:true}` |
| 关掉最后一个标签页 | Chrome 直接退出，后续 `9222` 全断 | **只断 websocket（`tab.ws.close()`），不要 `close(tab)`** |
| Chrome ≥136 默认 profile 禁用调试端口 | `--remote-debugging-port` 无效 | 用 junction 路径 `%LOCALAPPDATA%\Google\Chrome\UserData-CDP` → `User Data`，并加 `--disable-gpu --disable-gpu-compositing`（否则 `Page.captureScreenshot` 永久挂起） |
| HttpOnly cookie | `document.cookie` 取不到 `Yjs_UToken` | CDP `Network.getCookies` |

### Chrome 启动命令（本机已验证）
```python
subprocess.Popen([CHROME, "--remote-debugging-port=9222",
                  f"--user-data-dir={LOCALAPPDATA}/Google/Chrome/UserData-CDP",
                  "--disable-gpu", "--disable-gpu-compositing",
                  "--no-first-run", "--no-default-browser-check"])
```
- 必须**没有任何 chrome.exe 在跑**，否则调试端口不会开
- junction 已存在：`%LOCALAPPDATA%\Google\Chrome\UserData-CDP` → `User Data`

### Python 环境
- `websocket-client` → `~/.workbuddy/binaries/python/envs/default/Scripts/python.exe`
- `mitmproxy`（仅路径 B 的 iPhone 抓包需要）→ 同上 default venv，但**必须是独立 venv 的 mitmproxy 11**
  （`~/.workbuddy/yjs_captures/mitm-venv`），default venv 的 12.2.3 钩子半迁移会静默丢数据

---

## 现成脚本（本次产出，在会话目录）
| 脚本 | 作用 |
|---|---|
| `grab_full.py` | 遍历 3 来源 tab × 5 状态抓全量并合并去重（**主脚本**） |
| `make_report.py` | 生成 Markdown 报告 / CSV / HTML 看板 |
| `fetch_web_interest.py` | IM 凭证路径（需要 token 有效） |
| `login_and_fetch.py` | 交互式：启动 Chrome 等用户登录 → 自动续跑 |

## 输出
- `chat_out_web/yjs_谁对我感兴趣_报告.md` — 报告
- `chat_out_web/yjs_谁对我感兴趣_明细.csv` — 明细（含薪资/规模/类型/时间）
- `chat_out_web/yjs_谁对我感兴趣.html` — 看板
- `chat_out_web/yjs_interest_full_<ts>.json` — 原始响应
