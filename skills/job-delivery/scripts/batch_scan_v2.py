"""Batch scan queue jobs #11..#26: navigate, screenshot, detect state.

State detection:
- dead: 404 / 已下线 / 过期 / not found
- student_portal: university career center (requires student login) -> skip
- login_required: needs account login
- apply_ready: has apply/投递 button
- unknown
"""
import sys, time, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from raw_cdp_chrome import RawCDPChrome
import openpyxl
from config import find_latest_queue_file

OUT = Path(r"C:\Users\78422\Desktop\工作agent\投递状态记录\applypilot-dashboard\scan")
OUT.mkdir(parents=True, exist_ok=True)
RESULTS = OUT / "scan_results.csv"

START, END = 11, 26

def load_jobs():
    q = find_latest_queue_file()
    wb = openpyxl.load_workbook(q, data_only=True)
    ws = wb['投递队列']
    headers = [c.value for c in ws[1]]
    ri = headers.index('排名'); ci = headers.index('公司'); ji = headers.index('岗位名称')
    ui = headers.index('投递地址'); li = headers.index('地点')
    jobs = []
    for r in ws.iter_rows(min_row=2, values_only=True):
        if r[ri] is None: continue
        rank = int(r[ri])
        if START <= rank <= END:
            jobs.append({
                'rank': rank, 'company': str(r[ci] or ''), 'title': str(r[ji] or ''),
                'url': str(r[ui] or ''), 'loc': str(r[li] or '')
            })
    return sorted(jobs, key=lambda x: x['rank'])

def detect_state(cdp):
    probe = cdp.evaluate(r"""
    (function(){
      var body = (document.body||{}).innerText || '';
      var b = body.toLowerCase();
      var low = body;
      var has = function(kw){ return low.indexOf(kw) > -1; };
      // apply buttons
      var applyBtn = Array.from(document.querySelectorAll('a,button,div,span')).some(function(e){
        var t=(e.textContent||'').trim();
        return t==='立即投递'||t==='申请'||t==='投简历'||t==='Apply'||t==='申请职位'||t.indexOf('立即投递')===0||t.indexOf('申请此职位')===0;
      });
      // student portal markers
      var student = has('统一身份认证')||has('学生登录')||has('校园账号')||has('学号登录')||has('cas登录');
      // dead markers
      var dead = has('已下线')||has('职位审核中或已下线')||has('页面不存在')||has('404')||has('not found')||has('已过期')||has('该职位已')||has('不存在或已删除');
      // login markers
      var login = has('登录后')||has('请先登录')||has('登录/注册')||has('账号登录')||location.href.indexOf('login')>-1||location.href.indexOf('passport')>-1;
      return JSON.stringify({
        bodyLen: body.length,
        applyBtn: applyBtn, student: student, dead: dead, login: login,
        url: location.href.slice(0,120),
        sample: body.slice(0,120).replace(/\\n/g,' ')
      });
    })()
    """)
    return json.loads(probe) if probe else {}

def main():
    jobs = load_jobs()
    print(f"Scanning {len(jobs)} jobs (rank {START}-{END})")
    cdp = RawCDPChrome().connect(new_tab=True)
    results = []
    for j in jobs:
        rank = j['rank']
        print(f"\n--- #{rank} {j['company']} | {j['title']} ---")
        print(f"  URL: {j['url'][:90]}")
        try:
            cdp.evaluate(f"window.location.href={json.dumps(j['url'])}")
            time.sleep(5)
            st = detect_state(cdp)
            print(f"  state: dead={st.get('dead')} student={st.get('student')} login={st.get('login')} apply={st.get('applyBtn')} len={st.get('bodyLen')}")
            print(f"  sample: {st.get('sample','')[:80]}")
            cdp.save_screenshot(str(OUT / f"rank{rank}.png"))
            verdict = 'dead' if st.get('dead') else ('student_skip' if st.get('student') else ('login_req' if st.get('login') and not st.get('applyBtn') else ('apply_ready' if st.get('applyBtn') else 'unknown')))
            results.append([rank, j['company'], j['title'], j['url'], verdict, st.get('bodyLen'), st.get('sample','')[:60]])
        except Exception as e:
            print(f"  ERROR: {e}")
            results.append([rank, j['company'], j['title'], j['url'], 'error', '', str(e)[:60]])
        time.sleep(0.5)
    cdp.disconnect()
    # write results
    import csv
    with open(RESULTS, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['rank','company','title','url','verdict','body_len','sample'])
        w.writerows(results)
    print(f"\n=== DONE. Results saved to {RESULTS} ===")
    for r in results:
        print(f"  #{r[0]} {r[1]} -> {r[4]}")

if __name__ == "__main__":
    main()
