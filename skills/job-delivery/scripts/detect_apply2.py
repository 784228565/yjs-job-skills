"""Lenient re-detection for SPA/time-out jobs + better NielsenIQ apply check."""
import sys, time, re, json
sys.path.insert(0, '.')
from raw_cdp_chrome import RawCDPChrome

CANDIDATES = [
    (17, "https://league.rc114.com/Union/Position?jobId=262D9FD7-F8D8-4305-8BE6-A6EC3B7E6FF5"),
    (19, "https://www.joinrs.com/fr/jobs/2771739"),
    (20, "https://leetcode.cn/company/yitutech/jobs/INTERNSHIP"),
    (21, "https://www.amazon.jobs/jobs/10468413"),
    (22, "https://www.smartrecruiters.com/NielsenIQ/744000116594998-analyst-sr-analyst-customer-success-analytics-insights-"),
    (24, "https://www.worldquant.com/career-listing/?id=4069460006"),
]

cdp = RawCDPChrome().connect(new_tab=True)

def detect(url):
    try:
        cdp.navigate(url)
    except Exception as e:
        print("  navigate warn:", e)
    time.sleep(6)  # generous settle for SPA
    try:
        cdp.evaluate("window.scrollTo(0, document.body.scrollHeight);")
    except Exception:
        pass
    time.sleep(2)
    info = cdp.evaluate(r"""(function(){
        var txt = (document.body && document.body.innerText) || '';
        var lower = txt.toLowerCase();
        var emails = (txt.match(/[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/g) || []);
        var applySel = Array.from(document.querySelectorAll('a,button')).filter(function(el){
            var t = (el.textContent||'').trim().toLowerCase();
            return /apply|申请|投递|立即申请|submit|报名|apply now|easy apply/.test(t) && t.length < 30;
        }).map(function(el){return (el.textContent||'').trim().slice(0,25);});
        var loginHit = /登录|sign in|log in|create account|create an account|注册|sign up/.test(txt.slice(0, 4000)) && !/(Junting ?Wu|吴俊庭|退出|个人中心|我的简历)/.test(txt.slice(0, 4000));
        return JSON.stringify({
            url: location.href,
            len: txt.length,
            emails: emails.slice(0,8),
            apply_btns: applySel.slice(0,10),
            login_hint: loginHit,
            title: document.title.slice(0,60)
        });
    })()""")
    return json.loads(info)

results = []
for rank, url in CANDIDATES:
    try:
        d = detect(url)
        d["rank"] = rank
        results.append(d)
        print(f"[#{rank}] {d['title']} | len={d['len']} login={d['login_hint']} "
              f"apply={d['apply_btns']} emails={d['emails']}")
    except Exception as e:
        print(f"[#{rank}] ERROR {e}")

cdp.disconnect()
out = r"C:\Users\78422\Desktop\工作agent\投递状态记录\applypilot-dashboard\scan\detect_results2.json"
with open(out, "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)
print("Saved", out)
