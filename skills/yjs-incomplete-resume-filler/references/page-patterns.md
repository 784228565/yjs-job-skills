# 51job 三类简历页面打法参考

## 1. JobsSelect 志愿页（旧版流程第一页）

URL: `xyz.51job.com/External/Others/JobsSelect.aspx?JobID=...&CtmID=...`

- 志愿是 `<select name="grdJobs$ctl02$drpJobs" onchange="judgeOrder(this)">`，第 1 个通常已预填（JobSelectType=0 手动选 / =1 预填）。
- **坑**：预填值若没有触发过 `onchange`，点 btnOk postback 后**原地重渲本页**（服务端认为没选志愿）。
  修复：先 `dispatchEvent(new Event("change",{bubbles:true}))` 让 judgeOrder 跑一遍，再点 `input[name=btnOk]`。
- btnOk 的 onclick = `iframeShow(); __doPostBack('btnOk','')`，普通鼠标点击即可。

## 2. FillInResume 分步向导（旧版，中集/联影/百联/恩智浦）

URL: `xyz.51job.com/External/MyResume/FillInResume.aspx?CtmID=...`

- 每步底部图片按钮：`input[type=image][name=imgbtnNext]`（下一步）/ `imgbtnPrevious` / `imgbtnSave` / 末步 `imgbtnSubmit`。
- **报错文本是残留**：font[color=red] 的错误提示不会自动清除，看步骤标题是否前进判断真实状态。
- 文本键入：点击 + Ctrl+A + `Input.insertText` 即可（ASP.NET 非 Vue）；日期 readonly 框用 `key_chars` 逐字键入（如 "2020-07-01"）。
- select 下拉：`select_option(sel, 精确文本)`（set value + dispatch change）。
- GPA 必填格式 `**/4`（如 `3.55/4`）。
- 附件必填时：上传入口在 `UpLoad.aspx` same-origin iframe → 用 `upload_iframe.py`。
- 末步可能有「隐私声明」checkbox + imgbtnSubmit。
- **提交成功标志**：跳转 `young.yingjiesheng.com/xyzsuccess?...resumeid=...`，title=投递成功。

## 3. consumer/pc/resume 模块化简历页（新版，中钢/宝武）

URL: `xyz.51job.com/consumer/pc/resume/index?ctmid=...`

- 模块式：右侧锚点导航红点=必填；每模块「编辑」展开 Element UI 表单、「保存」提交。
- **el-date-picker 键入规则**：必须完整格式 `2021-09-01` + Enter；`2021-09` 简写被 Vue 拒绝，blur 即清空。输入框被视口裁切时面板不弹——先 `scrollIntoView({block:'center'})` 再取坐标点击。
- **学校/专业搜索**：`el-autocomplete` 选项是 li；搜索后必须**真实鼠标点击精确文本项**（"西南大学"≠"西南大学网络与继续教育学院"），只键入不落 Vue 值。
- **jbs_three_layers_input（TwoLayers 级联组件，外语水平/政治面貌）**：普通点击/键入/hover 全无效。正解：从 DOM 元素向上找带 `__vue__.toggleDropDownVisible` 的实例，然后
  `c.handleChange([父节点, 叶子节点], 叶子, false)` 直选。组件懒加载字典：options 空时先 `toggleDropDownVisible()` 触发 loadDictData。`over()` 无参，hover 不切换第二层。
- 附件：原生 `input[type=file][name=attach]`（photo 是照片），`DOM.setFileInputFiles` 直接注入。
- 全部必填完成后「立即投递」(DIV.resume-apply-btn.active) 激活；点击后弹「添加第二志愿」提示 → 点「我知道了，继续投递」→ xyzsuccess。

## 4. yingjiesheng 列表交互

- `?tab=2` reload 后默认停在「投递反馈」；「待完善投递 (N)」是 `.tab-tabs-item`，必须**真实鼠标点击**才渲染 `#incompleteList`。
- 「完善简历」是 el-button 无 href，JS .click() 无效，必须 Input.dispatchMouseEvent 真实点击 → window.open 新标签。
- 列表行内还有「取消投递」按钮，坐标接近，点击前确认文本是「完善简历」。
- 全部完成后「待完善投递」tab 整个消失（只剩 投递反馈/职位收藏）——这是清零验证标志。

## 5. 阿里云盾滑块与软风控

- 触发：刷新过于频繁时正文变 "Access Verification / slide to verify"，`#incompleteList`/`.tab-tabs-item` 全空。
- 拖动参考 `slide_captcha.py`；连续失败显示 "Refresh to retry" 后，刷新页面可能直接放行（不保证）。
- CDP 拟真拖动常被阿里云盾识别拒绝（检测 webdriver 标志+行为）；**最快的解法是让用户在 Chrome 窗口手动拖一次滑块**。
- **软风控（空 200）**：自动化密集后 applyV2 等 API 返回 HTTP 200 但 body 为空（transferSize=0），页面 van-toast "Loading..." 永不消失。这不是代码问题——`performance.getEntriesByType('resource')` 可查 responseStatus 确认。
  - 处理：**停止一切自动化 30-60 分钟冷却**；期间反复刷新只会加重风控。
  - van-toast 是 fixed 定位，`offsetParent` 探测不到是否显示，必须用 getComputedStyle(display/visibility/opacity) 判断。
- **tab 点击要带轨迹**：mouseMoved→press→微移→release；简单 press/release 会被 Vue 忽略（时好时坏）。
- **多标签陷阱**：51job 流程页 URL 的 prp 参数带 yjs 地址，URL 子串匹配会误中；必须用 `url.startswith('https://q.yingjiesheng.com/pc/personal')` 过滤，并优先选 IDLE（无 Loading 遮罩、无验证页）的标签。
- **默认不要 reload**：reload 很容易触发滑块；优先复用已打开且空闲的标签页。
