"""Valeo (51job campus) full apply probe.

1. Load the Valeo job page in a fresh tab.
2. Locate the 立即投递 button precisely (resolve a real CSS selector).
3. Click it and capture the post-click state:
   - new target/tab spawned?
   - modal / iframe / login dialog appeared?
   - JS dialog (alert/confirm) fired?
4. Screenshot before + after for visual confirmation.
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from raw_cdp_chrome import RawCDPChrome

VALEO_URL = "https://campus.51job.com/valeo/jobinfo.html?jobid=169502961"
OUT = Path(r"C:\Users\78422\Desktop\工作agent\投递状态记录\applypilot-dashboard\valeo")
OUT.mkdir(parents=True, exist_ok=True)


def find_apply_button(cdp):
    """Return diagnostic info about the 立即投递 button."""
    expr = r"""
    (function(){
      var candidates = Array.from(document.querySelectorAll('*'));
      var hits = [];
      candidates.forEach(function(el){
        var t = (el.textContent||'').trim();
        if (t === '立即投递' || t.indexOf('立即投递') === 0) {
          // only leaf-ish elements
          if (el.children.length === 0 || el.querySelector('*') === null || el.tagName === 'A' || el.tagName === 'BUTTON') {
            hits.push({
              tag: el.tagName,
              id: el.id || '',
              cls: (el.className && el.className.toString) ? el.className.toString() : '',
              href: el.getAttribute ? (el.getAttribute('href')||'') : '',
              data: JSON.stringify(Object.fromEntries(
                Array.from(el.attributes).map(function(a){return [a.name, a.value];})
              )).slice(0,300)
            });
          }
        }
      });
      // also grab common apply selectors
      var sel = ['a.btn-apply','button.apply','.apply-btn','#applyBtn','.delivery','.btn_delivery','input[type=button]'];
      var found = {};
      sel.forEach(function(s){ var e=document.querySelector(s); found[s] = !!e; });
      return JSON.stringify({hits: hits.slice(0,8), selectors: found});
    })()
    """
    r = cdp.evaluate(expr)
    return r


def snapshot_tabs():
    import urllib.request
    try:
        with urllib.request.urlopen("http://127.0.0.1:9222/json") as resp:
            data = json.loads(resp.read().decode())
        pages = [t for t in data if t.get("type") == "page"]
        return [{"id": t["id"], "url": t.get("url", "")} for t in pages]
    except Exception as e:
        return [{"error": str(e)}]


def main():
    cdp = RawCDPChrome().connect(target_url=VALEO_URL, new_tab=True)
    cdp.save_screenshot(str(OUT / "01_loaded.png"))
    print("=== LOADED ===")
    print("URL:", cdp.evaluate("location.href"))
    print("TABS before click:", len(snapshot_tabs()))

    info = find_apply_button(cdp)
    print("=== APPLY BUTTON DIAG ===")
    print(info)

    # Try to click via textContent coordinate click on 立即投递
    try:
        cdp.click_element("立即投递")
        print("click_element(立即投递) dispatched")
    except Exception as e:
        print("click_element failed:", repr(e))

    time.sleep(2.5)

    print("=== POST-CLICK ===")
    print("URL now:", cdp.evaluate("location.href"))
    tabs_after = snapshot_tabs()
    print("TABS after click:", len(tabs_after))
    for t in tabs_after:
        print("  -", t.get("url", "")[:90])

    # Detect login dialog / modal by probing DOM for common 51job login markers
    probe = cdp.evaluate(r"""
    (function(){
      var body = document.body ? document.body.innerText : '';
      var markers = {
        login_iframe: !!document.querySelector('iframe[src*="login"], iframe[src*="passport"]'),
        has_apply_form: !!document.querySelector('form'),
        modal: !!document.querySelector('.modal, .dialog, .popup, .layui-layer, .ui-dialog'),
        qr: !!document.querySelector('img[src*="qr"], .qr-code, canvas'),
        text_snippet: body.slice(0, 200)
      };
      return JSON.stringify(markers);
    })()
    """)
    print("=== DOM PROBE ===")
    print(probe)

    cdp.save_screenshot(str(OUT / "02_after_click.png"))
    cdp.disconnect()
    print("DONE")


if __name__ == "__main__":
    main()
