# Codex → WorkBuddy 工具映射

job-delivery skill 已从 Codex 移植到 WorkBuddy。以下为核心工具替换：

| Codex 工具 | WorkBuddy 等效 |
|------|------|
| `browser-client` (Playwright) | `agent-browser` skill（CDP 直连 `ws://localhost:9222`） |
| `RawCDPChrome` (`scripts/raw_cdp_chrome.py`) | 保留使用，或 Node.js Bash 内联 WebSocket 直连 CDP |
| `browser-use` (`scripts/browser_use_form_fill.py`) | 保留作为三级降级方案 |
| Gmail MCP | `agent-mail` MCP (`mcp__agent-mail__SearchMessages` / `GetMessage` / `download_attachment`) |
| `application-confirmation-checker` skill | `agent-mail` MCP 直接搜索确认邮件 |
| `config.find_plugin_browser_script()` | 不再需要——WorkBuddy 无 plugin 概念，CDP 端口检测用 `curl localhost:9222/json/list` |
| `get_shared_cdp()`, `auto_start` | 不再需要——用户手动启动 Chrome 或双击 `start_chrome_debug.bat` |
| `~/.codex/skills/` | `~/.workbuddy/skills/` |
| `$skill` 调用 | 自然语言触发，由 `SKILL.md` frontmatter `description` 自动匹配 |
| 文件读写 | `Read` / `Write` / `Edit` / `Bash` / `PowerShell` 工具 |
| 网页搜索 | `WebSearch` / `WebFetch` / `web-access` skill |
| CSV/xlsx 处理 | `minimax-xlsx` skill / `xlsx` skill / Python openpyxl |
| PDF 简历 | `pdf` skill / `pdfkit-py` skill |
| DOCX 处理 | `Word / DOCX` skill |

## 保留的脚本（无需改动）

以下脚本直接可用（依赖标准库，不依赖 Codex plugin）：
- `scripts/check_cdp.py` — CDP 端口检测
- `scripts/start_chrome_debug.bat` — Chrome 调试模式启动
- `scripts/config.py` — `find_latest_queue_file()`, `ensure_cdp_profile_junction()`
- `scripts/init_delivery_log.py` — CSV 初始化
- `scripts/raw_cdp_chrome.py` — CDP 直连（Python websocket-client）
- `scripts/browser_use_form_fill.py` — LLM 视觉填表
- `scripts/batch_scan.py`, `scripts/batch_scan_rest.py`, `scripts/batch_scan_v2.py` — �量扫描
- `scripts/detect_apply.py`, `scripts/detect_apply2.py` — 投递检测
- 各平台 apply 脚本（amazon, nielsen, valeo 等）
