"""Scan remaining queue ranks (>=27) for on-page HR emails / no-login apply buttons.
Mirrors the WorldQuant discovery pattern. Outputs scan_rest_results.json + .csv
"""
import sys, time, re, json, csv
sys.path.insert(0, '.')
from raw_cdp_chrome import RawCDPChrome
from config import find_latest_queue_file
import openpyxl
from urllib.parse import urlparse

q = find_latest_queue_file()
wb = openpyxl.load_workbook(q, data_only=True)
ws = wb['投递队列']
headers = [c.value for c in ws[1]]
rank_i = headers.index('排名')
url_i = headers.index('投递地址')
comp_i = headers.index('公司')
title_i = headers.index('岗位名称')

rows = []
for r in ws.iter_rows(min_row=2, values_only=True):
    if r[rank_i] is None:
        continue
    try:
        rank = int(r[rank_i])
    except Exception:
        continue
    if rank < 27:
        continue
    url = str(r[url_i] or '')
    if not url.startswith('http'):
        continue
    rows.append((rank, str(r[comp_i] or ''), str(r[title_i] or ''), url))

print(f"Scanning {len(rows)} jobs (ranks 27+)...")

cdp = RawCDPChrome().connect(new_tab=True)
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
results = []

def probe(rank, comp, title, url):
    try:
        cdp.navigate(url)
    except Exception:
        pass
    time.sleep(5)
    try:
        cdp.evaluate("window.scrollTo(0, document.body.scrollHeight);")
    except Exception:
        pass
    time.sleep(1.5)
    try:
        info = cdp.evaluate(r"""(function(){
            var txt=(document.body&&document.body.innerText)||'';
            var emails=(txt.match(/[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/g)||[]);
            var applySel=Array.from(document.querySelectorAll('a,button')).filter(function(el){
                var t=(el.textContent||'').trim().toLowerCase();
                return /apply|応募|申请|submit|报名|easy apply/i.test(t)&&t.length<30;
            }).map(function(el){return (el.textContent||'').trim().slice(0,25);});
            var login=/sign in|log in|create account|register|登录|注册|student login|学生登录/.test(txt.slice(0,3500));
            return JSON.stringify({url:location.href,len:txt.length,
                emails:emails.slice(0,8),apply:applySel.slice(0,8),login:login,
                title:document.title.slice(0,50)});
        })()""")
        d = json.loads(info)
    except Exception as e:
        d = {"url": url, "len": 0, "emails": [], "apply": [], "login": None, "title": "ERR:"+str(e)[:40]}
    d.update({"rank": rank, "company": comp, "title_job": title})
    return d

for rank, comp, title, url in rows:
    d = probe(rank, comp, title, url)
    results.append(d)
    flag = ""
    if d.get("emails"):
        flag += " [EMAIL]"
    if d.get("apply"):
        flag += " [APPLY]"
    print(f"[#{rank}] {comp[:18]:18} len={d.get('len',0):5} login={d.get('login')} "
          f"emails={d.get('emails')}{flag}")

cdp.disconnect()
base = r"C:\Users\78422\Desktop\工作agent\投递状态记录\applypilot-dashboard\scan"
with open(base + r"\scan_rest_results.json", "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)
# CSV summary
with open(base + r"\scan_rest_results.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["rank", "company", "title", "url", "len", "login", "emails", "apply_btns"])
    for r in results:
        w.writerow([r.get("rank"), r.get("company"), r.get("title_job"), r.get("url"),
                    r.get("len"), r.get("login"),
                    ";".join(r.get("emails", [])), ";".join(r.get("apply", []))])
print("Saved scan_rest_results.json + .csv")
