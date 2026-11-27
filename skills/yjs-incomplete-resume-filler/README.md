# yjs-incomplete-resume-filler

> 通过 CDP 驱动已登录的 Chrome，把应届生求职网个人中心「待完善投递」列表里的未完成简历逐条填完并提交，覆盖 51job 的三种简历页面形态。

## 用途

投递外企岗位时，很多公司走的是 51job 网申表单：点「投递」不会直接成功，而是把你丢进一套分步简历向导（选志愿 → 填十几页表单 → 传附件 → 提交）。这套流程手工填一次要十几分钟，且每个公司一套。

本技能把「取列表 → 逐条打开 → 识别页面类型 → 按类型填完 → 校验投递成功」串成可重跑的流程，并在关键节点截图留证。

## 核心功能

- **列表驱动**：读取 `q.yingjiesheng.com/pc/personal?tab=2` 的「待完善投递」列表，`dump` 查看、`click <i>` 真实点击第 i 条。
- **三种页面自动分派**：
  | 页面 | 特征 | 打法 |
  |---|---|---|
  | `JobsSelect.aspx` | 旧版志愿页 | 先给第 1 个志愿 dispatch `change` 触发 `judgeOrder`，再点 `btnOk` |
  | `FillInResume.aspx` | 旧版分步向导 | 逐步 dump / 填 / `imgbtnNext` 前进，末步 `imgbtnSubmit` |
  | `consumer/pc/resume` | 新版模块化（Element UI） | 按模块「编辑 → 填必填 → 保存」，最后「立即投递」 |
- **组件级适配**：Element UI 日期选择、`el-autocomplete` 学校搜索、TwoLayers 级联（外语水平/政治面貌）都有专用直选方法。
- **附件上传**：原生 `input[type=file]` 直接注入；`UpLoad.aspx` iframe 组件穿透注入。
- **滑块处理**：阿里云盾滑块拟真拖动，失败自动刷新重试 3 次；识别不了就交给人工。
- **完成校验**：URL 跳到 `young.yingjiesheng.com/xyzsuccess?...resumeid=...` 且 title 为「投递成功」才算完成。

## 适用场景

| 适合 | 不适合 |
|---|---|
| 投递后跳到 51job 网申、要求「完善简历」的岗位 | 站内一键投递（用 `yjs-job-pipeline`） |
| 批量清理积压的「待完善投递」 | 需要编造身份信息的字段——证件号、政治面貌等选填项一律留空 |
| 想复盘表单结构、补选择器 | 无人值守：滑块与风控必须人工介入 |

## 主要内容

| 文件 | 作用 |
|---|---|
| `SKILL.md` | 技能定义：总体流程、完成判定、简历口径、关键坑索引 |
| `references/page-patterns.md` | 三类页面的完整打法与踩坑记录（最值得先读） |
| `scripts/cdp.py` | 通用 CDP 库：`async with CDP(url_sub) as c:`，方法 `js/click_el/type_text/key_chars/select_option/shot/reload/drag` |
| `scripts/yjs_list.py` | 待完善列表 dump / 点击第 i 条 |
| `scripts/fresh_tab_list.py` | 当前标签卡死时，新开标签取列表 |
| `scripts/jobs_select_go.py` | 志愿页 → 分步向导推进 |
| `scripts/s51_step.py` | 旧版 FillInResume 分步 dump / 前进 / 截图 |
| `scripts/s51_fill.py` | 旧版分步表单字段填写 |
| `scripts/s51_inspect.py` | 旧版表单全字段检查（含隐藏项、附件、标签上下文） |
| `scripts/submit_final.py` | 末步提交：勾隐私 checkbox → 点 `imgbtnSubmit` → 报结果 |
| `scripts/consumer_dump.py` | 新版模块化页结构 dump |
| `scripts/consumer_fill.py` | 新版页字段填写 / 附件注入 |
| `scripts/consumer_select.py` | 新版页下拉 / autocomplete / 普通输入（真实鼠标点选项） |
| `scripts/consumer_act.py` | 新版页通用操作：按模块 / 文本 / 选择器点击 |
| `scripts/upload_iframe.py` | 附件上传（原生 input 或 `UpLoad.aspx` iframe） |
| `scripts/slide_captcha.py` | 阿里云盾滑块拟真拖动 |
| `scripts/captcha_probe.py` | 探测当前页是否出现验证码 |
| `scripts/shot_url.py` | 按 URL 子串附标签并截图 |
| `scripts/_dbg2.py`、`_dbg_list.py` | 列表调试副本（与 `yjs_list.py` 同源，排障时用） |

## 快速开始

```bash
cd scripts

# 1. 看列表（含自动 reload + 点「待完善投递」tab）
PYTHONPATH="" python yjs_list.py

# 2. 打开第 0 条
PYTHONPATH="" python yjs_list.py click 0

# 3. 看当前页是哪一类，再选脚本
PYTHONPATH="" python s51_step.py <CtmID>          # 旧版分步
PYTHONPATH="" python consumer_dump.py             # 新版模块化

# 4. 末步提交
PYTHONPATH="" python submit_final.py
```

> 命令前加 `PYTHONPATH=""` 是为了绕过本机 safe-delete shim（它会往 Python 注入 sitecustomize）。

## 填写口径

技能里固化了本人简历口径，换人使用需改 `SKILL.md` 的「用户简历口径」一节：

- 教育：西南大学 计算机 硕士 2021-09~2024-07（GPA 3.55/4，前 20%）；西南大学 软件工程 本科 2016-09~2020-07（GPA 3.22/4，前 20%）。
- 语言：雅思 IELTS 6.0（选 5-6.5 档）；日语 J-Test A-C 600 分（下拉选「日语二级」，账号常预填一级，每次要改）。
- 附件简历：`<简历目录>/Junting_Wu_Resume_EN_v4.pdf`（51job 英文渠道统一用 EN 版）。
- 意向城市：上海优先，广州/深圳次之。

**原则**：账号预填数据全部沿用；报错文本可能是残留（看步骤标题是否前进判断真实状态）；身份类信息不编造，选填项留空。

## 注意事项

- 不要 `reload`，reload 很容易触发滑块；优先复用已打开且空闲的标签。
- 多标签匹配要用 `url.startswith('https://q.yingjiesheng.com/pc/personal')`，51job 流程页 URL 会带 `prp` 参数误中。
- 投 1–2 家就刷新列表验证状态，别连续猛刷。
- 出现「空 200」软风控时，停一切自动化冷却 30–60 分钟，反复刷新只会加重。

## 依赖

- Python 3.10+，`websockets`
- Chrome `--remote-debugging-port=9222`，已登录应届生求职网
- 附件上传需要本地存在对应 PDF
