"""Amazon #21: navigate directly to apply URL, capture required flow."""
import sys, time, json
sys.path.insert(0, '.')
from raw_cdp_chrome import RawCDPChrome

APPLY = "https://www.amazon.jobs/applicant/jobs/10468413/apply"
cdp = RawCDPChrome().connect(new_tab=True)
try:
    cdp.navigate(APPLY)
except Exception as e:
    print("nav warn:", e)
time.sleep(7)
cdp.evaluate("window.scrollTo(0, document.body.scrollHeight);")
time.sleep(2)

state = cdp.evaluate(r"""(function(){
    var txt=(document.body&&document.body.innerText)||'';
    return JSON.stringify({
        url: location.href,
        title: document.title.slice(0,60),
        len: txt.length,
        snippet: txt.slice(0,500).replace(/\n/g,' ')
    });
})()""")
print("APPLY PAGE STATE:", state)
cdp.save_screenshot(r"C:\Users\78422\Desktop\工作agent\投递状态记录\applypilot-dashboard\scan\amazon_apply_page.png")
cdp.disconnect()
