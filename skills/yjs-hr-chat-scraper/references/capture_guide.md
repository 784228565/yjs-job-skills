# 凭证获取指南（iPhone 抓包法）

腾讯 IM 凭证（imId + txImToken）只能从 App 的 HTTP 流量中提取，一次抓包 48 小时内有效。

## 步骤

1. **PC 装 mitmproxy**（需要 mitmproxy 包：`pip install mitmproxy`）
   ⚠️ **2026-10-29 实测：WorkBuddy default venv 的 mitmproxy 12.2.3 钩子系统半迁移**（旧式 response/error 钩子和 `-w` 全部静默失效，flows 文件恒 0 字节）。**必须用独立 venv 的 mitmproxy 11**：`%USERPROFILE%\.workbuddy\yjs_captures\mitm-venv`（事先建好，含 11.1.3）。
   配套落盘插件 `%USERPROFILE%\.workbuddy\yjs_captures\save_addon_v11.py`（经典 response 钩子 + FlowWriter 逐条 flush），flows 落盘到同目录 `v11_addon.flows`。
2. **启动抓包**：
   ```bash
   PYTHONPATH="" "%USERPROFILE%/.workbuddy/yjs_captures/mitm-venv/Scripts/mitmdump.exe" \
     --listen-host 0.0.0.0 --listen-port 8080 \
     -s "%USERPROFILE%/.workbuddy/yjs_captures/save_addon_v11.py" -q
   ```
   （旧版 `mitmweb --listen-host 0.0.0.0 --listen-port 8080 -w <固定路径>/yjs_chat_capture.flows` 在 mitmproxy 11 上仍可用）
   ⚠️ `-w`/插件输出用**固定绝对路径**（不要散落在临时/项目目录），否则下次重取凭证时找不到抓包文件（本机实测踩过：flows 落在旧项目目录里，回头搜了半天）
   ⚠️ 自检命令是 `curl -x http://127.0.0.1:8080 http://httpbin.org/ip`（**不要加 `--noproxy '*'`**，它会连 -x 一起绕过，代理端永远收不到流量）
3. **iPhone 设置 HTTP 代理**：Wi-Fi → 当前网络 → 配置代理 → 手动 → 服务器 = PC 局域网 IP（如 192.168.x.x），端口 8080
4. **安装并信任 CA 证书**：iPhone 浏览器访问 `http://mitm.it`（或 `http://<PC_IP>:8082` 如果另起了证书服务）→ 下载描述文件 → 设置 → 通用 → VPN与设备管理 → 安装 → 设置 → 通用 → 关于本机 → 证书信任设置 → **完全信任**
5. **触发流量**：**从后台划掉（force-quit）应届生/51job 求职 App 再重开**，进入「嗨聊」消息列表随便点几个会话。必须冷启动——仅切前台/息屏恢复不会发新的 txinit，App 会复用本地旧 token（2026-10-23 实测：不冷启动时 42MB 流量里 txinit 仍是两天前的旧条目）。自检：提取时脚本打印的"抓于 <时间>"应就是刚才
6. **提取凭证**：
   ```bash
   # 用装了 mitmproxy 包的 python（本机为 default venv，见下方"注意"）
   python scripts/extract_creds.py capture.flows --out im_creds.json
   ```

## 注意

- 腾讯 IM 长连接走 QUIC/UDP，mitmproxy 抓不到也不需要——凭证在 `POST cupid.51jobapp.com/imbc/open/job51/txinit` 的响应里
- 应届生 App 和 51job App 共用同一套 IM（SDKAPPID=1400329），任一 App 抓到的凭证都可用
- **重取凭证的高发失败模式**：忘了冷启动 App → flows 里 txinit 还是旧条目 → `extract_creds.py` 退出码 2 并提示。按提示杀掉 App 重开再进嗨聊即可，不用重新配代理
- 大 flows 文件（数十 MB，且 mitmweb 可能在持续追加）不要直接流式分析，先复制快照再读；`extract_creds.py` 内部已自动快照
- `mitmproxy` 包与 `fetch_chat.py` 所需的 `websocket-client` 可能不在同一 python 环境（本机 mitmproxy 在 default venv），跑脚本前确认环境
- **抓完务必**：iPhone 代理改回「关闭」，否则电脑关机后手机断网
- 凭证 48 小时过期，过期后重新执行本流程
