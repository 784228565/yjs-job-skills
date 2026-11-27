"""Batch process jobs 1-5: navigate, screenshot, analyze, log."""
import sys, time, json
sys.path.insert(0, r'C:\Users\78422\.codex\skills\job-delivery\scripts')
import config, openpyxl
from raw_cdp_chrome import RawCDPChrome
from init_delivery_log import append_row

# Read queue
p = config.find_latest_queue_file()
wb = openpyxl.load_workbook(p, read_only=True)
ws = wb['投递队列']
rows = list(ws.iter_rows(min_row=1, values_only=True))
hdr = rows[0]
i_rank = hdr.index('排名')
i_co = hdr.index('公司')
i_job = hdr.index('岗位名称')
i_url = hdr.index('投递地址')


def process_one_job(cdp_instance, rank, company, job_title, url):
    result = {'rank': rank, 'company': company, 'job': job_title, 'url': url}
    try:
        cdp_instance.connect(new_tab=True)
        cdp_instance.navigate(url)
        time.sleep(4)

        current_url = cdp_instance.evaluate('location.href')
        title = cdp_instance.evaluate('document.title')
        result['final_url'] = current_url
        result['title'] = title

        ss_path = str(config.SCREENSHOT_DIR / f'job_{rank:03d}.png')
        cdp_instance.save_screenshot(ss_path)
        result['screenshot'] = ss_path

        # deizao -> extract data-href -> jump to shixiseng
        is_deizao = 'deizao.cn' in url
        if is_deizao:
            data_href = cdp_instance.evaluate(
                "(function(){var a=document.querySelector('.copylink');"
                "return a?(a.dataset.href||''):'';})()"
            )
            result['data_href'] = data_href
            if data_href and data_href.startswith('http'):
                cdp_instance.navigate(data_href)
                time.sleep(5)
                current_url = cdp_instance.evaluate('location.href')
                title = cdp_instance.evaluate('document.title')
                result['final_url'] = current_url
                result['title'] = title
                ss2 = str(config.SCREENSHOT_DIR / f'job_{rank:03d}_real.png')
                cdp_instance.save_screenshot(ss2)
                result['screenshot_real'] = ss2

        body_text = (cdp_instance.evaluate('(document.body.innerText||"")') or '')
        result['body_start'] = body_text.replace('\n', ' ')[:200]

        # Signal detection via JS — check both body text AND visible button/element text
        signals = {}
        for name, expr in [
            ('logged_in', "/(Junting\\s?Wu|吴俊庭|退出|个人中心|我的简历)/.test(document.body.innerText) || !/(登录|Login|login|sign in|log in|注册)/.test(document.body.innerText)"),
            ('applied',   "/已投递|已申请|already applied|previously applied|重复投递/"
                         ".test(document.body.innerText)"),
        ]:
            val = cdp_instance.evaluate(f"(function(){{return Boolean({expr});}})()")
            signals[name] = bool(val)

        # Offline detection: check body text + visible element text (buttons especially)
        offline_btn_text = cdp_instance.evaluate(
            """(function(){
                var off=['当前职位已下线','已下线','职位已过期','已过期','已关闭',
                        '停止招聘','no longer accepting','position filled',
                        '该职位不存在','链接失效'];
                // Check body text first
                var bt=(document.body.innerText||'');
                for(var i=0;i<off.length;i++){if(bt.indexOf(off[i])!==-1)return true;}
                // Also check visible elements (buttons, divs with class like 'offline')
                var els=document.querySelectorAll('button,a,div,span,.apply-btn,.job-status');
                for(var j=0;j<els.length;j++){
                    var e=els[j];
                    if(e.offsetParent===null)continue;
                    var t=(e.innerText||e.value||e.className||'').trim();
                    for(var k=0;k<off.length;k++){if(t.indexOf(off[k])!==-1)return true;}
                }
                return false;
            })()"""
        )
        signals['offline'] = bool(offline_btn_text)

        # Apply button detection
        has_btn = cdp_instance.evaluate(
            """(function(){
                var btns=['立即申请','投递简历','申请','点击投递','Apply Now','Submit',
                           '投个简历','马上申请','立即投递'];
                return btns.some(function(b){
                    return !!Array.from(document.querySelectorAll('button,a,input,div,span'))
                        .find(function(e){var v=(e.innerText||e.value||'').trim();
                            return v===b && e.offsetParent!==null;});
                });
            })()"""
        )
        signals['has_apply_btn'] = bool(has_btn)
        result.update(signals)

        # Decision
        if signals.get('applied'):
            result['result'], result['reason'] = 'Skipped', '已投递'
        elif signals.get('offline'):
            result['result'], result['reason'] = 'Skipped', '岗位已下线/过期'
        elif not signals.get('logged_in'):
            result['result'], result['reason'] = 'NeedsUser', '未登录'
        elif signals.get('has_apply_btn'):
            result['result'], result['reason'] = 'PENDING_APPLY', '有投递按钮待填表'
        else:
            result['result'], result['reason'] = 'NeedsUser', '无法判定需看截图'

    except Exception as exc:
        result['result'] = 'Blocked'
        result['reason'] = f'异常:{str(exc)[:100]}'
    finally:
        try:
            cdp_instance.disconnect()
        except Exception:
            pass
    return result


# Process rank 6-15
cdp = RawCDPChrome()
results = []
for r in rows[6:16]:
    rk = r[i_rank]
    co = r[i_co]
    job = r[i_job]
    u = r[i_url]
    print(f'\n=== #{rk}: {co} | {job[:40]} ===')
    res = process_one_job(cdp, rk, co, job, u)
    results.append(res)
    print(f'  => {res["result"]} | {res.get("reason", "")}')
    print(f'     URL: {str(res.get("final_url", ""))[:80]}')
    if res.get('data_href'):
        print(f'     real: {res["data_href"][:80]}')

# Write delivery_log
for r in results:
    append_row(
        seq_no=r['rank'],
        company=r['company'],
        job_title=r['job'],
        url=r['url'],
        result=r['result'],
        method='Direct',
        issues=r.get('reason', ''),
        notes=f'auto_detect | final={str(r.get("final_url", ""))[:60]}',
    )

print('\n===== RESULTS =====')
for r in results:
    print(f'  #{r["rank"]:3d} [{r["result"]:12s}] {r["company"][:25]} | {r.get("reason", "")}')
