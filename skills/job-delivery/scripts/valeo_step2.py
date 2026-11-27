"""Valeo step 2: navigate to the 51job apply page (the 立即投递 link target).

The campus page's 立即投递 is <a id="apply" href="https://jobs.51job.com/all/169502961.html">.
CDP coordinate click didn't trigger navigation → go directly.
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from raw_cdp_chrome import RawCDPChrome

APPLY_URL = "https://jobs.51job.com/all/169502961.html"
OUT = Path(r"C:\Users\78422\Desktop\工作agent\投递状态记录\applypilot-dashboard\valeo")
OUT.mkdir(parents=True, exist_ok=True)


def main():
    cdp = RawCDPChrome().connect(target_url=APPLY_URL, new_tab=True)
    time.sleep(3)  # let JS render

    url = cdp.evaluate("location.href")
    print("URL:", url)
    title = cdp.evaluate("document.title")
    print("Title:", title)

    # Full body text for understanding the page type
    body = cdp.evaluate(r"""
    (function(){
      return document.body ? document.body.innerText.slice(0, 800) : 'NO BODY';
    })()
    """)
    print("=== BODY TEXT ===")
    print(body)

    # Check for login gate / apply form markers
    probe = cdp.evaluate(r"""
    (function(){
      return JSON.stringify({
        login_form: !!document.querySelector('form[action*="login"], form[id*="login"]'),
        any_form: !!document.querySelector('form'),
        apply_btn: !!document.querySelector('a.btn_apply, .btn-apply, .apply-btn, [class*="apply"]'),
        qr_code: !!document.querySelector('.qrcode, .qr-code, img[src*="qr"]'),
        iframe_count: document.querySelectorAll('iframe').length,
        iframes_src: Array.from(document.querySelectorAll('iframe')).map(function(f){return f.src||''}).slice(0,5),
        cookie_login: document.cookie.indexOf('login') > -1,
        text_has_login: (document.body||{}).innerText.indexOf('登录') > -1,
        text_has_apply: (document.body||{}).innerText.indexOf('申请') > -1 || (document.body||{}).innerText.indexOf('投递') > -1,
      });
    })()
    """)
    print("=== PROBE ===")
    print(probe)

    cdp.save_screenshot(str(OUT / "03_51job_apply_page.png"))
    cdp.disconnect()


if __name__ == "__main__":
    main()
