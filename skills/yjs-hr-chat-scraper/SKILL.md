---
name: yjs-hr-chat-scraper
description: 抓取并导出应届生求职网/51job「嗨聊」的 HR 聊天记录（腾讯云 IM 底座，SDKAPPID=1400329）。当用户要求读取/导出/备份 HR 聊天、查谁给我发过消息、扫描待回复的 HR、导出「谁对我感兴趣」浏览记录、监控招聘聊天消息时使用。支持按聊天对象、时间范围、消息数量过滤，输出结构化 JSON/CSV。凭证通过 iPhone 抓包获取（48 小时有效），用 CDP 驱动本机 Chrome 登录腾讯 IM 官方 SDK 读取。
---

# 应届生/51job HR 聊天抓取

聊天功能虽为 App-only，但消息存储在腾讯 IM 云端。用抓包拿到的凭证登录官方 SDK 即可在电脑上全量读取、过滤、导出。

## ⚡ 先看这里：优先用 web 端路径（2026-11-15 实测打通，免 iPhone 抓包）

**用户问「谁对我感兴趣 / 哪些企业对我感兴趣」时，不要走 iPhone 抓包** —— 直接读 web 端
个人中心的投递反馈接口，30 秒出结果：

```
https://q.yingjiesheng.com/pc/personal?tab=2   →  投递反馈
→ GET https://youngapi.yingjiesheng.com/open/yjs/applyV2
      ?version=11.1.0&api_key=xy&timestamp=<unix秒>&partner=wspcsucceedb1
      &pageNo=1&pageSize=100&applyStatus=<04>&tab=<yjs|xyz|51job>
   请求头必须带：sign / user-token(=Yjs_UToken) / account-id / uuid / partner / From-Domain: yjs_web
```

| applyStatus | 含义 | 备注 |
|---|---|---|
| `''` | 全部投递 | |
| `03` | 已查看 | |
| **`04`** | **感兴趣（谁对我感兴趣）** | 本次 32 条 / 20 家 |
| `06` | 邀面试 | |
| `07` | 不合适 | |

- 响应 `resultbody.items[]` 每条含 **`coName`（公司名）**、`jobName`、`salaryStr`、
  `companySizeStr`、`companyTypeStr`、`sendDateTime`、`statusUpdateTimeFormat`、`jobTag`、`hrUid`。
- `resultbody.totalNums` 是总数，`items` 最多 100 条/页。
- 页面有 3 个来源 tab（应届生求职 / 网申 / 前程无忧），**每个 tab 数据独立，要分别点一遍**。
- 筛选标签 DOM：`.tab-options-option2 > span`；来源 tab 是裸 `span`（文案：应届生求职/网申/前程无忧）。
- `sign` 由前端算，**裸 fetch 会被 CORS 拒（Failed to fetch）**；正确姿势是**点 UI 标签让页面自己发请求**，
  再用 CDP `Network.responseReceived` + `Network.getResponseBody` 拦截。

→ 完整踩坑与实现见 [references/web_login_path.md](references/web_login_path.md)

**只有当用户明确要「HR 聊天记录全文 / 逐条消息 / 待回复会话」时**，才需要下面的 IM 凭证方案。

## 前置条件

1. **Chrome 以调试端口启动**：`chrome.exe --remote-debugging-port=9222`（脚本可自动新建标签页，但 Chrome 本体必须带该参数启动）
2. **有效凭证 `im_creds.json`**：`{sdkAppID, userID, userSig}`，48 小时过期。获取方法见 [references/capture_guide.md](references/capture_guide.md)（iPhone mitmproxy 抓包 + `scripts/extract_creds.py`）。⚠️ 重取凭证时必须**杀掉 App 重开（冷启动）**——App 不冷启动会复用本地旧 token、不发新的 txinit，抓包再久也只有旧凭证（2026-10-23 实测：42MB 流量里 txinit 仍是两天前的旧条目）
3. Python 依赖分属两个环境（本机实测，别混）：
   - `fetch_chat.py`（抓取）：`websocket-client`（腾讯 IM SDK 已内置在 `assets/tx_umd.min.js`，无需外网）
   - `extract_creds.py`（提取）：`mitmproxy` 包（`pip install mitmproxy`）。本机该包装在 default venv：`~/.workbuddy/binaries/python/envs/default/Scripts/python.exe`，与 fetch_chat.py 的运行环境不是同一个

## 快速开始

```bash
# ① 提取凭证（需 mitmproxy 包，本机用 default venv 的 python；会自动选最新 txinit 并拒绝过期凭证）
python scripts/extract_creds.py <抓包文件.flows> --out im_creds.json

# ② 全部 HR 会话，每会话最近 50 条 → chat_out/chat_<时间戳>.json + .csv
python scripts/fetch_chat.py --creds im_creds.json

# 只看某个 HR / 某公司，近 7 天
python scripts/fetch_chat.py --creds im_creds.json --keyword 瑞候福 --since 2026-10-14

# 扫描待回复：最后一条消息来自 HR（且未回复）的会话
python scripts/fetch_chat.py --creds im_creds.json --scan-reply --since 2026-10-01

# 只要 HR 发的，排除系统号，每会话 100 条
python scripts/fetch_chat.py --creds im_creds.json --hr-only --max-per-conv 100
```

## 参数一览

| 参数 | 默认 | 说明 |
|---|---|---|
| `--creds` | im_creds.json | 凭证文件路径 |
| `--cdp-port` | 9222 | Chrome 调试端口 |
| `--keyword` | 无 | 只抓会话名包含此关键词的会话（公司名/HR 名） |
| `--since` / `--until` | 无 | 消息时间范围 `YYYY-MM-DD` |
| `--max-per-conv` | 50 | 每会话消息条数上限 |
| `--max-convs` | 0（不限） | 会话数量上限 |
| `--hr-only` | 关 | 只保留 HR/系统消息（去掉自己发的） |
| `--include-system` | 关 | 包含系统号（special1 谁对我感兴趣 / special10 / special35 校招发布） |
| `--scan-reply` | 关 | 只扫描待回复会话，输出 needs_reply_<时间戳>.json |
| `--outdir` | chat_out | 输出目录（含 fetch_chat.log 日志） |
| `--timeout` | 120 | SDK 就绪等待秒数 |

## 输出格式

每条消息一条记录，字段：

```
conversation_id   会话 ID（C2Cehire* 为 HR，C2Cspecial* 为系统号）
conversation_name 会话名（HR 昵称或公司）
sender_type       hr / self / system
sender_id         发送者 IM ID
sender_nick       发送者昵称
time              本地时间 YYYY-MM-DD HH:MM:SS
msg_type          TIMTextElem / TIMImageElem / TIMCustomElem / ...
content           文本内容 / 图片 URL / 自定义消息描述
extra             自定义消息附加数据（JSON 字符串；special1 卡片含 HR 浏览记录）
```

- 已做清洗：时间范围过滤、`--hr-only` 过滤、按 (会话, 时间, 内容) 去重、单条内容截断 2000 字符
- 日志：`fetch_chat.log`（凭证剩余时间、会话进度、错误明细）
- 错误处理：凭证过期（退出码 2）、登录失败（3）、会话列表失败（4）；单个会话失败不中断，最后统计 errors 数。`extract_creds.py`：未找到 txinit（1）、最新凭证仍过期（2）、拒绝覆盖更新的已有凭证（3）、缺 mitmproxy 包（5）

## 进阶

- **「谁对我感兴趣」**：`--include-system --keyword 谁对我感兴趣`，卡片消息解析出的 JSON 在 `extra` 字段（公司/jobid/浏览时间）
- **凭证过期重取**：按 references/capture_guide.md 重新抓包（**务必冷启动 App**）后运行 `scripts/extract_creds.py capture.flows`。提取脚本会解析 userSig 内的 `TLS.time/expire`：多条 txinit 自动选最新；最新凭证仍过期时退出码 2 并提示冷启动，不会静默保存过期凭证
- **排坑**（CDP Origin 校验、SDK ready 轮询、userSig 的 `*`→`+` 等）见 [references/protocol.md](references/protocol.md)

## 合规与隐私

- 仅抓取**本人账号**的聊天数据；`im_creds.json` 等同账号密码，只存本机、勿提交 git、勿外传
- 导出文件含 HR 的联系方式与聊天内容，注意本地保存与二次分享范围
- 保持默认抓取节奏（会话间隔 0.3s），不要并发请求腾讯 IM 接口
