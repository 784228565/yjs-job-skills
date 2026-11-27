# yjs-hr-chat-scraper

> 投完简历之后的跟进工具：查「谁对我感兴趣」、导出 HR 聊天记录、扫描待回复会话。数据来自应届生 / 51job 的「嗨聊」（腾讯云 IM 底座）。

## 用途

投递只是上半场。真正决定进度的是：哪些 HR 看了你、谁在等你回、上一条消息是不是对方发的。这些信息散在 App 的聊天列表里，网页端只露一部分。

本技能提供两条互补的路径：

| 路径 | 适用问题 | 成本 |
|---|---|---|
| **A. Web 端投递反馈接口**（推荐） | 谁对我感兴趣 / 哪些企业看过我 | 30 秒，免抓包，只需 Chrome 已登录 |
| **B. 腾讯 IM 凭证** | HR 聊天全文、逐条消息、待回复会话 | 需 iPhone 抓包，凭证 48 小时有效 |

## 核心功能

- **谁对我感兴趣**：读 `applyV2` 接口的 `applyStatus=04`，输出公司名、岗位、薪资、公司规模、时间，支持「应届生求职 / 网申 / 前程无忧」三个来源 tab。
- **聊天全文导出**：登录腾讯云 IM 官方 SDK（`assets/tx_umd.min.js` 离线加载），按会话拉取历史消息，输出 JSON + CSV。
- **待回复扫描**：`--scan-reply` 只挑「最后一条来自 HR」的会话，生成 `needs_reply_*.json`。
- **过滤**：按公司/HR 关键词、时间范围、每会话条数、是否只要 HR 消息过滤。
- **凭证管理**：`extract_creds.py` 从 mitmproxy flows 里提取 `sdkAppID / userID / userSig`，自动选最新一条并拒绝过期凭证。

## 适用场景

| 适合 | 不适合 |
|---|---|
| 每天扫一遍「谁看过我 / 谁在等我回」 | 代替你回复 HR（本技能只读不写） |
| 备份/分析自己的求职沟通记录 | 抓取他人账号数据 |
| 统计投递转化（感兴趣 → 面试邀约） | 高频轮询（会触发腾讯 IM 限流） |

## 主要内容

| 文件 | 作用 |
|---|---|
| `SKILL.md` | 技能定义：两条路径的选择、参数、输出字段、合规要求 |
| `config.example.json` | 配置样例（端口、凭证路径、输出目录、默认参数） |
| `references/web_login_path.md` | Web 端投递反馈接口的完整字段与 CORS 踩坑 |
| `references/capture_guide.md` | iPhone + mitmproxy 抓包取凭证的步骤（含冷启动坑） |
| `references/protocol.md` | 腾讯 IM 协议细节与 CDP 排坑 |
| `assets/tx_umd.min.js` | 腾讯云 IM Web SDK（本地加载，不依赖外网） |
| `scripts/fetch_chat.py` | 登录 IM、拉会话、过滤、导出 JSON/CSV |
| `scripts/extract_creds.py` | 从 flows 文件提取并校验凭证 |

## 快速开始

### 路径 A：查「谁对我感兴趣」（推荐）

1. Chrome 以 `--remote-debugging-port=9222` 启动并已登录应届生。
2. 打开 `https://q.yingjiesheng.com/pc/personal?tab=2`，点「投递反馈」及三个来源 tab。
3. 用 CDP 的 `Network.responseReceived` + `Network.getResponseBody` 拦截 `youngapi.yingjiesheng.com/open/yjs/applyV2` 的响应（`applyStatus=04` 即「感兴趣」）。

> `sign` 由前端计算，裸 `fetch` 会被 CORS 拒；正确姿势是**点 UI 让页面自己发请求**，再拦响应。完整字段见 `references/web_login_path.md`。

### 路径 B：导出聊天记录

```bash
# 1. 抓包后提取凭证（需独立 venv 装 mitmproxy 11）
python scripts/extract_creds.py capture.flows --out im_creds.json

# 2. 全部会话，每会话最近 50 条
python scripts/fetch_chat.py --creds im_creds.json

# 3. 只看某公司 / 近 7 天
python scripts/fetch_chat.py --creds im_creds.json --keyword 某公司 --since 2026-11-20

# 4. 只扫待回复
python scripts/fetch_chat.py --creds im_creds.json --scan-reply --since 2026-11-01
```

常用参数：

| 参数 | 默认 | 说明 |
|---|---|---|
| `--creds` | `im_creds.json` | 凭证文件 |
| `--cdp-port` | 9222 | Chrome 调试端口 |
| `--keyword` | 无 | 会话名包含该关键词（公司/HR） |
| `--since` / `--until` | 无 | 时间范围 `YYYY-MM-DD` |
| `--max-per-conv` | 50 | 每会话消息条数上限 |
| `--hr-only` | 关 | 只保留 HR/系统消息 |
| `--scan-reply` | 关 | 只输出待回复会话 |
| `--outdir` | `chat_out` | 输出目录（含 `fetch_chat.log`） |

## 输出字段

```
conversation_id   会话 ID（C2Cehire* 为 HR，C2Cspecial* 为系统号）
conversation_name HR 昵称或公司名
sender_type       hr / self / system
time              本地时间 YYYY-MM-DD HH:MM:SS
msg_type          TIMTextElem / TIMImageElem / TIMCustomElem ...
content           文本内容 / 图片 URL / 自定义消息描述
extra             自定义消息附加数据（special1 卡片含浏览记录）
```

已做时间过滤、`--hr-only` 过滤、按（会话, 时间, 内容）去重、单条截断 2000 字符。

## 合规与隐私

- 仅抓取**本人账号**的数据。`im_creds.json` 等同账号密码，只存本机、勿提交 git（`.gitignore` 已排除）。
- 导出文件含 HR 联系方式与聊天内容，注意保存与二次分享范围。
- 保持默认节奏（会话间隔 0.3s），不要并发请求腾讯 IM 接口。

## 依赖

- Python 3.10+，`websocket-client`
- `extract_creds.py` 另需 `mitmproxy`（11.x，建议独立 venv）
- Chrome `--remote-debugging-port=9222`
- 抓包需要 iPhone + 同一局域网
