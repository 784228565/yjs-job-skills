"""Valeo step 3 (v3): Send application email via Gmail.

Bypasses _navigate() timeout by using direct JS location assignment + manual sleep.
"""
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from raw_cdp_chrome import RawCDPChrome

# 个人信息不写死在脚本里（本仓库曾因硬编码手机号/邮箱做过一次脱敏）
MY_PHONE = os.environ.get("MY_PHONE", "<手机号>")
MY_EMAIL = os.environ.get("MY_EMAIL", "<邮箱>")

OUT = Path(r"C:\Users\78422\Desktop\工作agent\投递状态记录\applypilot-dashboard\valeo")
OUT.mkdir(parents=True, exist_ok=True)

TO_EMAIL = "qiuhong.huang@valeo.com"
CC_EMAIL = "eve.qian@valeo.com"
SUBJECT = "【应聘初级AI算法软件工程师（上海）】【西南大学（硕士）】【计算机科学与技术】【吴俊庭/Junting Wu】【上海】"

BODY = rf"""黄老师 / 钱老师，您好：

我是吴俊庭（Junting Wu），西南大学计算机科学与技术专业硕士（2024年7月毕业），现居上海。通过校园招聘渠道了解到法雷奥汽车内部控制（上海）有限公司正在招聘「初级 AI 算法软件工程师（上海）/ 工业化AI算法实习生」岗位，特此投递。

教育背景：
- 硕士：西南大学，计算机科学与技术，2021.09 – 2024.07
- 博士（退学）：上海大学，计算机科学与技术，2024.09 – 2026.02（因个人职业规划退学）
- 本科：西南大学，软件工程，2016.09 – 2020.06

核心技能与岗位匹配度（要求：工业数据 + 深度学习 CNN / PyTorch）：

1. 深度学习/CNN：熟悉 PyTorch 框架，有 DD-Former（EI 第一作者）、电磁逆散射（SCI Q2）等论文发表经历。
2. 工业数据处理：农业合作社数字化项目负责结构化/非结构化数据采集清洗分析；OCR 管线项目使用 OpenCV/RapidOCR。
3. Python 工程：熟练 pandas/numpy 数据分析、自动化脚本、LLM 应用集成（RAG/MCP Agent）。
4. 英语能力：CET-6，英文论文写作与阅读无障碍。

为什么选择法雷奥：
法雷奥作为全球 TOP 级汽车零部件科技公司在智能驾驶和汽车电子领域的技术积累令我向往。上海嘉定智能系统事业部专注于自动驾驶系统开发，与我深度学习+工业数据方向高度契合。我希望能在工业场景中将算法能力转化为实际产品价值。

实习安排：
- 可到岗时间：随时可到岗
- 实习时长：3–6 个月以上，每周 4–5 天
- 工作地点：上海（可接受嘉定园区）

随信附上中英文简历 PDF。如需补充材料（成绩单、论文全文、代码示例等），请随时告知。

期待您的回复，祝工作顺利！

此致
敬礼

吴俊庭（Junting Wu）
电话：{MY_PHONE}
邮箱：{MY_EMAIL}
GitHub：https://github.com/784228565
日期：2026年7月28日"""

RESUME_PATH = r"C:\Users\78422\Desktop\工作agent\Junting_Wu_Resume_EN_2page_updated.pdf"


def main():
    print("Step 1: Connecting...")
    cdp = RawCDPChrome().connect(new_tab=True)
    print("Connected.")

    # Step 2: Navigate via direct JS (bypass _navigate timeout)
    print("Step 2: Navigating to Gmail via JS...")
    cdp.evaluate("window.location.href='https://mail.google.com/mail/u/0/#inbox'")
    print("Waiting 12s for Gmail SPA...")
    time.sleep(12)

    url = cdp.evaluate("location.href")
    print("URL:", url)
    title = cdp.evaluate("document.title")
    print("Title:", title)

    state = cdp.evaluate(r"""(function(){
      var u=location.href;
      return JSON.stringify({
        url: u.slice(0,100),
        isLogin: u.indexOf('accounts.google.com')>-1,
        readyState: document.readyState,
        bodyLen: (document.body||{}).innerText.length
      });
    })()""")
    print("State:", state)
    cdp.save_screenshot(str(OUT / "04_gmail_state.png"))

    if '"isLogin":true' in str(state):
        print("NOT LOGGED IN!")
        cdp.disconnect()
        return

    # Step 3: Click compose
    print("Step 3: Opening compose...")
    cr = cdp.evaluate(r"""(function(){
      var sels=['div[gh="cm"]','div[aria-label*="写"]','div[aria-label*="新建"]','div[aria-label*="Compose"]'];
      for(var i=0;i<sels.length;i++){var e=document.querySelector(sels[i]);if(e){e.click();return sels[i];}}
      return 'none';
    })()""")
    print("Clicked:", cr)
    time.sleep(2)
    cdp.save_screenshot(str(OUT / "05_compose.png"))

    # Step 4: Fill fields using CDP Input.insertText approach
    # Gmail compose uses contenteditable divs, not input elements
    print("Step 4: Filling fields...")

    # Use a more robust fill approach - click into field then type
    def safe_fill(field_desc, selector_or_text, value):
        try:
            # For Gmail, we need to find and focus the right area, then insert text
            result = cdp.evaluate(f"""
            (function(){{
              var sel = {json.dumps(selector_or_text)};
              // Try as CSS selector first
              var el = document.querySelector(sel);
              if(!el){{
                // Try finding by aria-label containing text
                var all = document.querySelectorAll('[aria-label]');
                for(var i=0;i<all.length;i++){{if(all[i].getAttribute('aria-label').indexOf({json.dumps(value[:10] if len(value)>10 else value)})>-1){{el=all[i];break;}}}}
              }}
              if(!el) return 'NF';
              el.focus();
              el.click();
              return 'OK:' + el.tagName;
            }})()
            """)
            print(f"  {field_desc} focus: {result}")
            if result and result.startswith("OK"):
                # Insert text via CDP Input.insertText
                cdp._loop.run_until_complete(cdp._send("Input.insertText", {"text": value}))
                time.sleep(0.2)
            return result
        except Exception as e:
            print(f"  {field_desc} error: {e}")
            return None

    # Fill To
    safe_fill("To", 'div[aria-label*="收件人"], div[aria-label*="To"]', TO_EMAIL)
    time.sleep(0.5)

    # Fill Subject
    safe_fill("Subject", 'input[name="subject"], input[aria-label*="主题"], input[aria-label*="Subject"]', SUBJECT)
    time.sleep(0.5)

    # Fill Body - Gmail uses contenteditable
    safe_fill("Body", 'div[aria-label*="正文"], div[role="textbox"], div[aria-label*="Message Body"]', BODY)
    time.sleep(1)

    cdp.save_screenshot(str(OUT / "06_filled.png"))

    # Step 5: Attach resume
    print("Step 5: Attaching resume...")
    try:
        cdp.upload_file('input[type="file"]', RESUME_PATH)
        print("  Attached!")
    except Exception as e:
        print(f"  Attach error: {e}")
    time.sleep(2)
    cdp.save_screenshot(str(OUT / "07_attached.png"))

    print("=== DONE - check screenshots ===")
    cdp.disconnect()


if __name__ == "__main__":
    main()
