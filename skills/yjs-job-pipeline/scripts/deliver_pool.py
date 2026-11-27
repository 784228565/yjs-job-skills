# -*- coding: utf-8 -*-
"""应届生求职网（q.yingjiesheng.com / young.yingjiesheng.com）岗位一键投递。

复用用户 Chrome 登录态（CDP 9222，须先以调试模式启动）。
对队列中每个岗位：开新标签 -> 等 SPA 渲染 -> 截图 -> 检查 .delivery-btn ->
真实坐标点击 -> 校验「投递成功」弹窗或按钮变「已申请」-> 记录状态。
WAF「Access Verification」滑块：等待后自动刷新重试一次，仍不过则标记
NeedsUser(captcha) 并继续（不硬闯滑块）。

用法:
  python deliver_pool.py --queue jobs.json [--state deliver_state.json]
      [--cooldown 30] [--waf-wait 20] [--shots logs/deliver]
      [--passes 2] [--results delivery_results.json]

幂等续跑: 结果实时落盘 results / state，中断后重跑同一命令只补跑
未成功岗位；deliver_state.json 首次运行自动初始化。

队列文件 jobs.json: [{"id","co","job","url", ...}]，可选 "delivered": true 跳过。
依赖: websocket-client（同步）。venv default 已有，无需 aiohttp/websockets。
"""
import argparse
import base64
import json
import os
import sys
import time
import urllib.parse
import urllib.request

sys.stdout.reconfigure(encoding='utf-8')
for _k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
    os.environ.pop(_k, None)
os.environ["NO_PROXY"] = "*"

import websocket  # websocket-client

PORT = int(os.environ.get("JD_DEBUG_PORT", "9222"))

CHECK_JS = """(()=>{
  const b=document.querySelector('.delivery-btn');
  const dlg=document.querySelector('.el-dialog__body, .el-message-box__body, [class*=dialog]');
  const cap=!!document.querySelector('#tcaptcha_transform_dy, iframe[src*=captcha], [class*=captcha]');
  return JSON.stringify({
    url: location.href,
    btn: b ? b.innerText.trim() : null,
    btnDisabled: b ? (b.disabled||b.className.includes('disabled')) : null,
    dlg: dlg ? dlg.innerText.trim().slice(0,300) : '',
    captcha: cap,
    title: document.title.slice(0,60)
  });
})()"""

CLICK_JS = """(()=>{
  const b=document.querySelector('.delivery-btn');
  if(!b) return JSON.stringify({err:'no btn'});
  b.scrollIntoView({block:'center'});
  const r=b.getBoundingClientRect();
  return JSON.stringify({x:Math.round(r.left+r.width/2), y:Math.round(r.top+r.height/2), t:b.innerText.trim()});
})()"""

DIALOG_JS = """(()=>{
  const sels=['.el-dialog__body','.el-message-box__body','.el-message','.el-notification','[role=dialog]'];
  const out=[];
  for(const s of sels){document.querySelectorAll(s).forEach(e=>{const t=(e.innerText||'').trim();if(t)out.push(t.slice(0,200))});}
  return JSON.stringify({dialogs:out, btn:(document.querySelector('.delivery-btn')||{}).innerText||null});
})()"""


def http_json(path, method='GET', timeout=15):
    req = urllib.request.Request(f'http://127.0.0.1:{PORT}{path}', method=method)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode('utf-8', 'replace'))


class Tab:
    """单个 CDP 标签页会话（同步 websocket-client）。"""

    def __init__(self, url):
        q = urllib.parse.quote(url, safe='')
        t = http_json(f'/json/new?{q}', 'PUT')
        self.id = t['id']
        self.ws = websocket.create_connection(
            t['webSocketDebuggerUrl'], timeout=50, suppress_origin=True)
        self.mid = 0
        self.send('Page.enable')
        self.send('Runtime.enable')

    def send(self, method, params=None):
        self.mid += 1
        self.ws.send(json.dumps({'id': self.mid, 'method': method, 'params': params or {}}))
        deadline = time.time() + 45
        while time.time() < deadline:
            msg = json.loads(self.ws.recv())
            if msg.get('id') == self.mid:
                if 'error' in msg:
                    raise RuntimeError(f"{method}: {msg['error']}")
                return msg.get('result', {})
        raise TimeoutError(method)

    def eval(self, expr):
        r = self.send('Runtime.evaluate', {
            'expression': expr, 'returnByValue': True, 'userGesture': True})
        res = r.get('result', {})
        if res.get('subtype') == 'error':
            raise RuntimeError('eval error: ' + str(res.get('description'))[:200])
        return res.get('value')

    def click_xy(self, x, y):
        time.sleep(0.5)
        for t in ('mousePressed', 'mouseReleased'):
            self.send('Input.dispatchMouseEvent',
                      {'type': t, 'x': x, 'y': y, 'button': 'left', 'clickCount': 1})

    def shot(self, path):
        r = self.send('Page.captureScreenshot', {'format': 'png'})
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'wb') as f:
            f.write(base64.b64decode(r.get('data', '')))
        return path

    def close(self, keep=False):
        """keep=True 时保留标签页（用户 2026-11-15 规则：只开不关，浏览器/标签由用户手动关闭）"""
        if keep:
            try:
                self.ws.close()
            except Exception:
                pass
            return
        try:
            self.ws.close()
        except Exception:
            pass
        try:
            http_json(f'/json/close/{self.id}', timeout=10)
        except Exception:
            pass


def wait_button(tab, tries=24, interval=1.0):
    st = None
    for _ in range(tries):
        time.sleep(interval)
        try:
            v = tab.eval(CHECK_JS)
            st = json.loads(v) if v else None
        except Exception:
            st = None
        if st and (st.get('btn') or 'yingjiesheng' not in (st.get('url') or '')):
            break
    return st


def judge_success(tab):
    """返回 (is_success, detail_dict)。"""
    st2 = json.loads(tab.eval(CHECK_JS) or '{}')
    dlg = st2.get('dlg') or ''
    if '投递成功' in dlg or '已申请' in (st2.get('btn') or ''):
        return True, st2
    d = json.loads(tab.eval(DIALOG_JS) or '{}')
    if '投递成功' in json.dumps(d, ensure_ascii=False):
        return True, dict(st2, dlg=d.get('dialogs'))
    return False, dict(st2, dlg2=d.get('dialogs'))


def deliver_one(j, seq, total, shotdir, log=print, keep_tabs=False):
    jid, url = str(j['id']), j['url']
    rec = {'id': jid, 'co': j.get('co', ''), 'job': j.get('job', ''), 'url': url,
           'ts': time.strftime('%Y-%m-%d %H:%M:%S')}
    log(f"[{seq}/{total}] {jid} {j.get('co','')} | {j.get('job','')}")
    tab = Tab(url)
    try:
        st = wait_button(tab)
        tab.shot(os.path.join(shotdir, f'{seq:02d}_{jid}_pre.png'))
        if not st:
            rec.update(status='Error', reason='page state unreadable')
            return rec
        rec['pre'] = {k: st.get(k) for k in ('url', 'btn', 'title')}
        if 'yingjiesheng' not in (st.get('url') or ''):
            rec.update(status='Redirect', redirect_url=st['url'])
            log('   -> 外部重定向: ' + st['url'][:120])
            return rec
        if st.get('captcha'):
            rec.update(status='NeedsUser', reason='captcha')
            log('   -> WAF 验证码页')
            return rec
        btn = st.get('btn') or ''
        if '已申请' in btn or '已投递' in btn:
            rec.update(status='Skipped', reason='already applied')
            log('   -> 已申请')
            return rec
        if not btn:
            rec.update(status='NeedsInvestigation', reason='no delivery button')
            log('   -> 无投递按钮')
            return rec

        pos = json.loads(tab.eval(CLICK_JS) or '{}')
        if 'err' in pos:
            rec.update(status='NeedsInvestigation', reason=pos['err'])
            return rec
        tab.click_xy(pos['x'], pos['y'])
        log(f"   clicked '{pos.get('t')}' @({pos['x']},{pos['y']})")
        time.sleep(3.5)
        ok, detail = judge_success(tab)
        tab.shot(os.path.join(shotdir, f'{seq:02d}_{jid}_post.png'))
        rec['post'] = {k: detail.get(k) for k in ('btn', 'dlg') if detail.get(k)}
        if ok:
            rec.update(status='Submitted',
                       confirm=(detail.get('dlg') or detail.get('btn') or '')[:120])
            log('   ✅ ' + (rec['confirm'] or 'Submitted'))
        else:
            rec.update(status='Unknown', reason='no success signal')
            log('   ⚠️ 未见成功信号: ' + json.dumps(rec['post'], ensure_ascii=False)[:200])
        return rec
    except Exception as e:
        rec.update(status='Error', reason=repr(e)[:200])
        log('   ERR: ' + repr(e)[:160])
        try:
            tab.shot(os.path.join(shotdir, f'{seq:02d}_{jid}_err.png'))
        except Exception:
            pass
        return rec
    finally:
        tab.close()
        time.sleep(2)


def update_state(state_path, rec):
    if rec['status'] not in ('Submitted', 'Skipped'):
        return False
    if os.path.exists(state_path):
        state = json.load(open(state_path, encoding='utf-8'))
    else:
        state = {'done': {}}  # 首次运行自动初始化
        print(f'   init {state_path}', flush=True)
    done = state.setdefault('done', {})
    if rec['id'] in done:
        return False
    done[rec['id']] = {'job': rec['job'], 'co': rec['co'],
                       'status': 'Submitted' if rec['status'] == 'Submitted' else 'Skipped',
                       'via': 'yjs_oneclick',
                       'ts': time.strftime('%Y-%m-%d %H:%M')}
    json.dump(state, open(state_path, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--queue', required=True, help='岗位队列 JSON（含 id/co/job/url）')
    ap.add_argument('--state', default='deliver_state.json', help='deliver_state.json 路径')
    ap.add_argument('--results', default=None, help='结果输出 JSON（默认 <queue目录>/delivery_results.json）')
    ap.add_argument('--cooldown', type=float, default=30, help='岗位间冷却秒数（防 WAF，默认 30）')
    ap.add_argument('--waf-wait', type=float, default=20, help='命中 WAF 后等待再刷新秒数（默认 20）')
    ap.add_argument('--shots', default='logs/deliver', help='截图目录')
    ap.add_argument('--passes', type=int, default=2, help='总轮数：首轮后未成功的再慢速重试（默认 2）')
    ap.add_argument('--keep-tabs', action='store_true', help='保留投递用标签页不关闭（用户规则：只开不关）')
    args = ap.parse_args()

    queue = json.load(open(args.queue, encoding='utf-8'))
    queue = [x for x in queue if not x.get('delivered')]
    results_path = args.results or os.path.join(
        os.path.dirname(os.path.abspath(args.queue)), 'delivery_results.json')
    results = []
    if os.path.exists(results_path):
        results = json.load(open(results_path, encoding='utf-8'))
    by_id = {str(r['id']): r for r in results}

    print(f'queue: {len(queue)} jobs, cooldown={args.cooldown}s, passes={args.passes}', flush=True)
    for p in range(1, args.passes + 1):
        todo = [j for j in queue if str(j['id']) not in by_id
                or by_id[str(j['id'])].get('status') not in ('Submitted', 'Skipped')]
        if not todo:
            break
        if p > 1:
            print(f'--- pass {p}: {len(todo)} remaining ---', flush=True)
        for i, j in enumerate(todo, 1):
            if p > 1 or i > 1:
                time.sleep(args.cooldown)
            rec = deliver_one(j, i, len(todo), args.shots, log=lambda s: print(s, flush=True), keep_tabs=args.keep_tabs)
            # WAF / 超时 -> 等 waf-wait 后原样重试一次
            if rec['status'] in ('NeedsUser', 'Error'):
                time.sleep(args.waf_wait)
                rec2 = deliver_one(j, i, len(todo), args.shots, log=lambda s: print(s, flush=True), keep_tabs=args.keep_tabs)
                if rec2['status'] not in ('NeedsUser', 'Error'):
                    rec = rec2
            by_id[str(j['id'])] = rec
            update_state(args.state, rec)
            json.dump(list(by_id.values()),
                      open(results_path, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

    final = list(by_id.values())
    ok = sum(1 for r in final if r['status'] == 'Submitted')
    print(f'\n=== Submitted {ok}/{len(final)} ===', flush=True)
    for r in sorted(final, key=lambda x: str(x['id'])):
        print(f"  {r['status']:<16} {r['co'][:16]} | {r['job'][:28]} | {r.get('reason') or r.get('confirm') or ''}",
              flush=True)
    return 0 if ok == len(final) else 1


if __name__ == '__main__':
    sys.exit(main())
