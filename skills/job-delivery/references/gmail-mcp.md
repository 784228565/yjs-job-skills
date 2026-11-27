# Gmail MCP - 投递确认邮件检查 & 验证码获取

> ⚠️ **WorkBuddy 已用 `agent-mail` MCP 替代**：本文档描述的是 Codex Composio Gmail 方式（需要代理、API key）。WorkBuddy 会话中请直接使用 `mcp__agent-mail__SearchMessages` / `mcp__agent-mail__GetMessage`，无需本文档中的代理配置和 composio API 流程。

> **安全约定（务必遵守）**
> API 密钥、代理等敏感信息**一律从环境变量读取，绝不写进本文件或代码**。
> - `COMPOSIO_API_KEY`：Composio 的 `x-consumer-api-key`。
> - `HTTPS_PROXY` / `JD_PROXY`：访问 composio.dev 所需的本地代理（如 Mihomo/Clash）。
>
> ⚠️ 本技能历史版本曾将真实 API key 明文写入文档。**该 key 已视为泄露，请立即在
> Composio 后台轮换（revoke 旧 key、签发新 key），并只通过环境变量注入。**

## 快速模板（从环境变量读取，已验证可用）

```python
import os, json, time, requests

KEY = os.environ["COMPOSIO_API_KEY"]            # 不再硬编码
PROXY = os.environ.get("JD_PROXY") or os.environ.get("HTTPS_PROXY")
if PROXY:
    os.environ["HTTPS_PROXY"] = PROXY
    os.environ["HTTP_PROXY"] = PROXY

BASE = os.environ.get("COMPOSIO_BASE", "https://connect.composio.dev/mcp")
H = {"x-consumer-api-key": KEY, "Content-Type": "application/json",
     "Accept": "application/json, text/event-stream"}

# 1. 初始化会话（关键: Mcp-Session-Id 大写 M/S/I）
r = requests.post(BASE, json={"jsonrpc": "2.0", "id": "1", "method": "initialize",
    "params": {"protocolVersion": "2024-11-05", "capabilities": {},
    "clientInfo": {"name": "codex", "version": "1"}}}, headers=H, timeout=15)
H["Mcp-Session-Id"] = r.headers["Mcp-Session-Id"]
time.sleep(1)

# 2. 搜索确认邮件
def search_mail(query, max_results=5):
    req = {"jsonrpc": "2.0", "id": "2", "method": "tools/call", "params":
        {"name": "COMPOSIO_MULTI_EXECUTE_TOOL", "arguments":
        {"tools": [{"tool_slug": "GMAIL_FETCH_EMAILS",
        "params": {"max_results": max_results, "verbose": False, "query": query}}],
        "session_id": "park", "thought": "", "current_step": "step",
        "current_step_metric": 1}}}
    r = requests.post(BASE, json=req, headers=H, timeout=30)
    lr = [l[5:].strip() for l in r.text.split("\n") if l.startswith("data:")]
    data = json.loads("".join(lr))
    txt = data.get("result", {}).get("content", [{}])[0].get("text", "")
    if txt:
        return json.loads(txt).get("data", {}).get("results", [{}])[0] \
                   .get("response", {}).get("data", {}).get("messages", [])
    return []

# 3. 搜索公司名确认投递
msgs = search_mail("{company} OR herp.careers", 5)
for m in msgs[:5]:
    print(f"From:{m.get('from','')[:40]} | Subj:{m.get('subject','')[:60]}")
```

## 关键参数

| 参数 | 来源 | 说明 |
|------|------|------|
| API Key | 环境变量 `COMPOSIO_API_KEY` | `x-consumer-api-key` 头，**禁止硬编码** |
| 代理 | 环境变量 `JD_PROXY` 或 `HTTPS_PROXY` | 必须！GFW 会拦截 composio.dev |
| Session 头 | `Mcp-Session-Id` | M/S/I 大写，不是 mcp-session-id |
| 延迟 | `time.sleep(1)` | 防止 Mihomo SSL 重置 |
| 响应格式 | SSE | 需解析 `data:` 行 |
| 工具参数 | `session_id: "park"` | COMPOSIO_MULTI_EXECUTE_TOOL 必需 |

## 常见陷阱

1. API Key 从环境变量读取；若 `os.environ["COMPOSIO_API_KEY"]` 抛 `KeyError`，说明未注入。
2. `Mcp-Session-Id` 大小写必须匹配：M、S、I 大写。
3. 无代理 → `ConnectionRefusedError`，必须设置 `HTTPS_PROXY` / `JD_PROXY`。
4. 响应是 SSE 格式不是 JSON，须用 `data:` 前缀解析。
5. `COMPOSIO_MULTI_EXECUTE_TOOL` 参数结构：`{tools: [{tool_slug, params}], session_id}`。
6. Gmail 搜索对所有 query 返回同一封邮件 → 用 `max_results` 代替 query 限制。

## 投递后确认检查流程

```
1. 表单提交后 → 等待30秒
2. Gmail搜索: "{公司名} OR herp.careers OR {域名}"
     ├── 找到确认邮件(如"応募が完了しました") → 确认成功 ✅
     └── 未找到 → 等待15秒重试，最多2分钟
3. 2分钟后仍未找到 → 记录到 issue_log，标记 NeedsUser
```
