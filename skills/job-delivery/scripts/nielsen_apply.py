"""NielsenIQ #22 SmartRecruiters apply probe: find + click Apply, capture state."""
import sys, time, json
sys.path.insert(0, '.')
from raw_cdp_chrome import RawCDPChrome

URL = "https://www.smartrecruiters.com/NielsenIQ/744000116594998-analyst-sr-analyst-customer-success-analytics-insights-"
cdp = RawCDPChrome().connect(new_tab=True)
try:
    cdp.navigate(URL)
except Exception as e:
    print("nav warn:", e)
time.sleep(6)
cdp.evaluate("window.scrollTo(0, document.body.scrollHeight);")
time.sleep(2)

# Find apply button by broad text match
found = cdp.evaluate(r"""(function(){
    var cands = Array.from(document.querySelectorAll('a,button')).map(function(el){
        return {t:(el.textContent||'').trim().slice(0,30), href: el.href||'', cls: el.className||''};
    }).filter(function(c){ return /apply|申请|submit/i.test(c.t); });
    return JSON.stringify({url:location.href, candidates: cands.slice(0,10)});
})()""")
print("PRE-CLICK:", found)

# Try to click the apply button via text match
try:
    cdp.click_element('Apply')
    print("Clicked 'Apply' (CSS/text match)")
except Exception as e:
    print("click by 'Apply' failed:", e)
    # try alternative texts
    for txt in ['申请', 'Submit', 'Apply Now', 'apply for this job']:
        try:
            cdp.click_element(txt)
            print("Clicked via text:", txt)
            break
        except Exception:
            pass

time.sleep(4)
state = cdp.evaluate(r"""(function(){
    var txt=(document.body&&document.body.innerText)||'';
    return JSON.stringify({
        url: location.href,
        len: txt.length,
        login: /sign in|log in|create account|register|登录|注册/.test(txt.slice(0,3000)),
        snippet: txt.slice(0,300).replace(/\n/g,' ')
    });
})()""")
print("POST-CLICK STATE:", state)
cdp.save_screenshot(r"C:\Users\78422\Desktop\工作agent\投递状态记录\applypilot-dashboard\scan\nielsen_after_click.png")
cdp.disconnect()
