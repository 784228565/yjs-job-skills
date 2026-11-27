"""Amazon #21 apply probe: locate apply button (EN/JP), click, capture state."""
import sys, time, json
sys.path.insert(0, '.')
from raw_cdp_chrome import RawCDPChrome

URL = "https://www.amazon.jobs/jobs/10468413"
cdp = RawCDPChrome().connect(new_tab=True)
try:
    cdp.navigate(URL)
except Exception as e:
    print("nav warn:", e)
time.sleep(6)
cdp.evaluate("window.scrollTo(0, document.body.scrollHeight);")
time.sleep(2)

# Enumerate apply-like candidates with broad match (EN + JP)
found = cdp.evaluate(r"""(function(){
    var all = Array.from(document.querySelectorAll('a,button'));
    var cands = all.map(function(el){
        return {t:(el.textContent||'').trim().slice(0,30), href: (el.href||'').slice(0,80), cls:(el.className||'').slice(0,40)};
    }).filter(function(c){ return /apply|応募|申请|submit|报名/i.test(c.t); });
    return JSON.stringify({url:location.href, count: cands.length, candidates: cands.slice(0,12)});
})()""")
print("PRE:", found)

# Try clicking via text tokens
clicked = False
for tok in ['応募', 'Apply', '申请', 'Apply now', 'Submit']:
    try:
        cdp.click_element(tok)
        print("Clicked:", tok)
        clicked = True
        break
    except Exception as e:
        pass
if not clicked:
    print("No apply button matched by text")

time.sleep(5)
state = cdp.evaluate(r"""(function(){
    var txt=(document.body&&document.body.innerText)||'';
    return JSON.stringify({
        url: location.href,
        len: txt.length,
        login: /sign in|log in|create account|register|登录|注册|amazon password|email address/i.test(txt.slice(0,3000)),
        snippet: txt.slice(0,250).replace(/\n/g,' ')
    });
})()""")
print("POST:", state)
cdp.save_screenshot(r"C:\Users\78422\Desktop\工作agent\投递状态记录\applypilot-dashboard\scan\amazon_after.png")
cdp.disconnect()
