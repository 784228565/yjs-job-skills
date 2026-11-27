# 安全与隐私

这套技能需要在**已登录**的浏览器里操作，涉及账号、简历、聊天记录三类敏感数据。发布与日常使用都按下面的规则处理。

## 一、凭证清单

| 文件 / 变量 | 敏感级别 | 有效期 | 存放要求 |
|---|---|---|---|
| `im_creds.json`（`sdkAppID / userID / userSig`） | 等同账号密码 | 48 小时 | 只存本机，已加入 `.gitignore` |
| `YJS_SIGN_KEY`（接口签名密钥） | 中 | 随前端版本轮换 | 只放环境变量，不入库 |
| Chrome 调试端口 9222 | 高 | 会话级 | 仅监听 `127.0.0.1`，不要暴露到局域网 |
| 简历 PDF / 投递截图 | 高（含姓名、手机、邮箱） | — | 不入库，`*.png` / `out/` 已忽略 |
| `chat_out/*.json` | 高（含 HR 联系方式） | — | 不入库 |

## 二、本次发布做了哪些脱敏

| 处理 | 原状 | 现状 |
|---|---|---|
| 移除凭证 | `skills/yjs-hr-chat-scraper/im_creds.json` 内含真实 `userSig` | 已删除，仅保留 `config.example.json` |
| 移除截图 | `yjs-incomplete-resume-filler/out/` 与 `scripts/*.png`（14 张，约 11 MB，含真实姓名/手机/邮箱/表单内容） | 已排除，不入库 |
| 密钥外置 | `pipeline/yjs_fetch_pool.py` 硬编码 HMAC 密钥 | 改为读 `YJS_SIGN_KEY` 环境变量，未设置时直接退出 |
| 路径泛化 | `C:\Users\<用户名>\...` 出现在 3 处文档与 1 处脚本提示 | 改为 `%USERPROFILE%` 或 `<简历目录>` |
| 关键词脱敏 | `fetch_chat.py` 示例用了真实公司名 | 改为「某公司」 |
| 运行产物 | `__pycache__`、`pool_*`、`deliver_state.json` | 已排除 |

脱敏后仍保留的功能：抓取、筛选、diff、队列、预检、投递、简历填写、聊天导出。**没有为了脱敏删掉任何执行逻辑**，只把「本机专属的值」换成了需要你填的占位符或环境变量。

## 三、仍需你确认的个人信息

`skills/yjs-incomplete-resume-filler/SKILL.md` 的「用户简历口径」一节保留了真实教育背景、GPA、语言成绩、意向城市与实践单位。这是技能自动填表时的事实来源，删掉会影响可用性。

- 仓库设为 **Private**：可以保留。
- 仓库设为 **Public**：建议把该节替换为占位符（学校 `__`、GPA `__`、语言成绩 `__`），或迁到本地 `references/profile.local.md` 并在 `.gitignore` 中排除。

## 四、发布前自检

```bash
# 真实邮箱 / 手机号 / 用户名 / 密钥，应零命中
grep -rInE "78422|[0-9]{11}|@(gmail|qq|163)\.com|userSig|YJS_SIGN_KEY *=" . \
  --include="*.md" --include="*.py" --include="*.json"
```

命中 `im_creds.json`、`userSig` 属于正常（只是文件名/字段名），命中真实值则必须处理。

## 五、使用侧风险

1. **账号风险**：自动化操作可能触发平台风控（降权、限制投递、封号）。控制频率（岗位间隔 ≥30s、每日总量设上限），保留人工确认环节。
2. **不可逆操作**：投递一旦成功无法撤回；`deliver_pool.py` 的 `--passes 2` 会重试未成功岗位，不会重投已成功岗位。
3. **验证码红线**：脚本只做「拟真拖动 + 失败转人工」，不接打码平台、不硬闯滑块。
4. **数据外流**：不要把 `chat_out/`、`pool_*/`、截图目录同步到网盘或公开仓库。

## 六、建议的仓库设置

- Visibility：**Private**
- 开启 Secret scanning（GitHub 默认对公开仓库开启，私有仓库需手动开）
- 不要给仓库配置任何 Action 自动运行这些脚本（需要登录态与调试端口）
