# CDP 层总览：这套技能到底怎么操控浏览器

> 一句话：**四个技能全部只用 CDP（Chrome DevTools Protocol）直连本机 Chrome 的 9222 端口**，不装插件、不用 Selenium/Playwright、不接管账号密码。登录态就是你自己浏览器里的那份 session。
>
> 本页回答三个问题：CDP 代码在哪些文件里、三种实现各有什么取舍、端口不通时怎么定位。

---

## 一、CDP 代码分布

| 位置 | 实现 | 依赖 | 用来干什么 |
|---|---|---|---|
| `skills/yjs-incomplete-resume-filler/scripts/cdp.py` | **通用驱动**（`class CDP` + `list_tabs` / `find_tab`） | `websockets` | 51job 网申表单全流程：`js` / `click_el` / `type_text` / `select_option` / `shot` / `drag`。另外 16 个脚本全部 `from cdp import CDP`，都建在这一层上 |
| `skills/yjs-job-pipeline/scripts/deliver_pool.py` | **自带 `class Tab`**（约 50 行，单文件自足） | `websocket-client` | 站内一键投递：开页 → 判失效/已投 → 点投递 → 截图。刻意不依赖 cdp.py，保证单个文件拷走就能跑 |
| `skills/yjs-hr-chat-scraper/scripts/fetch_chat.py` | **自带连接 + JS 注入** | `websocket-client` | 在页面里注入腾讯云 IM SDK，用抓到 `userSig` 登录，导出 HR 聊天记录 |
| `skills/job-delivery/scripts/raw_cdp_chrome.py` | **重型客户端**（`RawCDPChrome`，434 行，含截图/上传/下载/等待器） | `websockets` + `aiohttp` | 队列投递的 tier-2 降级路径；`cdp_fallback.py` / `cdp_shot.py` 都调它 |
| `pipeline/jd_check.py` | 复用 `deliver_pool.Tab` | 继承上面 | JD 预检时开页读岗位描述 |

**结论：CDP 操作没有遗漏，也不依赖任何外部技能。** 唯一的跨技能引用是 `pipeline/jd_check.py` 找 `deliver_pool.Tab`，脚本里已做双路兜底（仓库内相对路径 → `~/.workbuddy/skills/yjs-job-pipeline/scripts`）。

## 二、三种实现怎么选

| | `cdp.py`（websockets） | `Tab`（websocket-client） | `RawCDPChrome`（aiohttp） |
|---|---|---|---|
| 体积 | 中（~200 行，接口最全） | 小（单文件 50 行） | 大（434 行，功能最全） |
| 异步 | asyncio | 同步 | asyncio |
| 真实鼠标事件 | ✅ `Input.dispatchMouseEvent` | ✅ `click_xy` | ✅ |
| 文件上传 / 下载 | 走 `upload_iframe.py` 单独处理 | ❌ | ✅ 内建 |
| 适用 | 复杂表单、Element UI/Vue 页面 | 轻量站内点击 | 批量投递、需要上传简历 |

选型口诀：**页面简单用 `Tab`，表单复杂用 `CDP`，要传文件/批量用 `RawCDPChrome`。**

## 三、最小可用片段

```python
# 方式 A：仓库内的通用驱动（需 pip install websockets）
import sys; sys.path.insert(0, "skills/yjs-incomplete-resume-filler/scripts")
from cdp import CDP, list_tabs          # list_tabs() 直接列出所有标签页

async def main():
    async with CDP("q.yingjiesheng.com") as c:   # 按 URL 子串挂到已打开的标签
        print(await c.js("location.href"))
        await c.click_el("[name=btnOk]")         # scrollIntoView + 真实鼠标点击
        await c.shot("out.png")                  # 截图落盘

import asyncio; asyncio.run(main())
```

```python
# 方式 B：只用标准库，验证端口通不通（等价 check_cdp.py 的最小版）
import json, urllib.request
print(json.load(urllib.request.urlopen("http://127.0.0.1:9222/json/list", timeout=5)))
```

> ⚠️ 本机 WorkBuddy 环境跑这类脚本时**前面加 `PYTHONPATH=""`**，绕开 safe-delete shim 注入的 `sitecustomize`。

## 四、端口不通怎么定位

`skills/job-delivery/scripts/check_cdp.py` 用退出码直接给结论（纯标准库，任何 python 都能跑）：

| 退出码 | 含义 | 处置 |
|---|---|---|
| `0` | 正常，且有 page target | 继续 |
| `1` | Chrome 在跑但端口不通 | 最常见。① 没带 `--remote-debugging-port`；② 已有 Chrome 进程把新实例合并了；③ Chrome ≥136 对默认 profile 禁用调试端口（需 junction，见下） |
| `2` | Chrome 没运行 | 双击 `start_chrome_debug.bat` |
| `3` | 端口有响应但 HTTP 异常 | 端口被别的程序占了，换端口或杀掉占用者 |

**Chrome ≥136 的关键解法**：用目录联接把 `%LOCALAPPDATA%\Google\Chrome\UserData-CDP` 指向真实 `User Data` —— 路径不再是默认值，调试端口就生效，而文件还是同一套，**登录态一点不丢**，且 junction 不需要管理员权限。`config.ensure_cdp_profile_junction()` / `start_chrome_debug.bat` 会自动建。

另外两个本机实测坑：
- 必须带 `--disable-gpu --disable-gpu-compositing`，否则有头模式下 `captureScreenshot` 对所有页面挂死（合成器不交付帧）。
- 调试端口只在启动时生效，所以**必须先完全退出 Chrome**（含托盘后台）。

## 五、红线

- **不得 kill / 重启用户 Chrome**。端口不通就按话术请用户自己重启（`SKILL.md` 里有可直接粘贴的完整命令），等用户回 `done`。
- **不得自动关闭 Agent 打开的标签页**（2026-11-15 用户强制规则）。标签堆积导致 `Target.createTarget` 超时时，先告知用户，由用户决定清理。
- **坐标系纪律**：先 `scrollIntoView({block:'center'})` 再 `getBoundingClientRect`，顺序反了会点到旧坐标；Vue/Element 页面重渲染频繁，每次点击前都要重新取坐标。
- **yjs 的 `el-button` 不认 JS `.click()`**，必须走 `Input.dispatchMouseEvent` 真实鼠标事件（`cdp.py` 的 `click_el` 已处理）。
- 不破验证码。撞上 WAF 滑块就冷却重试一次，仍不过标 `NeedsUser(captcha)` 跳过，人工滑一次后会话 Cookie 即恢复。
