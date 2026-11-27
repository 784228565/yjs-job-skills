# -*- coding: utf-8 -*-
"""抓取应届生求职网/51job「嗨聊」HR 聊天记录（腾讯云 IM 底座），输出结构化 JSON/CSV。

前置条件:
  1. 本机 Chrome 以 --remote-debugging-port=9222 启动（登录任意网页即可，不需要 51job 登录态）
  2. 有效的 im_creds.json（见 extract_creds.py / references/capture_guide.md）

用法示例:
  python fetch_chat.py --creds im_creds.json --max-convs 5 --max-per-conv 20
  python fetch_chat.py --creds im_creds.json --keyword 某公司 --since 2026-10-01
  python fetch_chat.py --creds im_creds.json --scan-reply        # 只扫描待回复 HR
"""
import argparse, base64, csv, datetime, json, logging, os, sys, time, zlib

import websocket  # websocket-client

log = logging.getLogger('fetch_chat')

CDP = 'http://127.0.0.1:{port}'
SDK_ASSET = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'assets', 'tx_umd.min.js')
CHAT_PAGE = 'https://chat.51job.com/'
SYSTEM_IDS = {'special1', 'special10', 'special35'}  # 谁对我感兴趣 / OK仔广播站 / 校招发布


# ---------- CDP 最小封装 ----------
class Tab:
    def __init__(self, cdp_port, url_substr=None, create_url=None):
        import urllib.request
        tabs = json.load(urllib.request.urlopen(CDP.format(port=cdp_port) + '/json'))
        t = next((x for x in tabs if x.get('type') == 'page' and url_substr in x.get('url', '')), None)
        if not t and create_url:
            import urllib.parse
            req = urllib.request.Request(
                CDP.format(port=cdp_port) + '/json/new?' + urllib.parse.quote(create_url, safe=''),
                method='PUT')
            t = json.load(urllib.request.urlopen(req))
            time.sleep(4)
        if not t:
            raise SystemExit(f'找不到标签页: {url_substr}，且无法创建')
        self.ws = websocket.create_connection(t['webSocketDebuggerUrl'], timeout=60, suppress_origin=True)
        self.mid = 0

    def cmd(self, method, **params):
        self.mid += 1
        self.ws.send(json.dumps({'id': self.mid, 'method': method, 'params': params}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get('id') == self.mid:
                return msg

    def eval(self, expr, timeout=60):
        self.ws.settimeout(timeout)
        r = self.cmd('Runtime.evaluate', expression=expr, returnByValue=True, awaitPromise=True)
        res = r.get('result', {})
        if 'exceptionDetails' in res:
            raise RuntimeError(str(res['exceptionDetails'])[:300])
        return res.get('result', {}).get('value')


# ---------- 凭证 ----------
def load_creds(path):
    c = json.load(open(path, encoding='utf-8'))
    # 过期检查：userSig = zlib+base64，payload 含 TLS.time / TLS.expire（48h）
    try:
        raw = base64.b64decode(c['userSig'].replace('*', '+') + '==')
        payload = json.loads(zlib.decompress(raw).decode('utf-8', 'ignore'))
        expire_at = payload.get('TLS.time', 0) + payload.get('TLS.expire', 0)
        remain = expire_at - time.time()
        if remain <= 0:
            log.error('凭证已过期 %.1f 小时，请重新抓包提取（见 references/capture_guide.md）', -remain / 3600)
            sys.exit(2)
        log.info('凭证有效，剩余 %.1f 小时', remain / 3600)
    except Exception as e:
        log.warning('无法解析 userSig 过期时间（%s），继续执行', e)
    return c


# ---------- 页面侧 JS ----------
JS_BOOT = r'''
window.__result = null;
(async () => {
  try {
    const creds = %s;
    if (!window.TencentCloudChat) {
      const src = window.__sdk_src;
      eval(src);
    }
    const tim = TencentCloudChat.create({ SDKAppID: creds.sdkAppID });
    const lr = await tim.login({ userID: creds.userID, userSig: creds.userSig });
    if (lr.code !== 0) { window.__result = { error: 'login failed: ' + lr.code + ' ' + lr.message }; return; }
    let waited = 0;
    while (!tim.isReady() && waited < %d) { await new Promise(r => setTimeout(r, 500)); waited += 500; }
    if (!tim.isReady()) { window.__result = { error: 'SDK not ready (timeout)' }; return; }
    window.__tim = tim;
    window.__result = { ok: true };
  } catch (e) {
    window.__result = { error: String(e).slice(0, 300) };
  }
})()
'''

JS_CONVERSATIONS = r'''
(async () => {
  try {
    const tim = window.__tim;
    let all = [], next = undefined;
    for (let i = 0; i < 20; i++) {
      const p = next ? { nextReqMessageID: next, count: 100 } : { count: 100 };
      const r = await tim.getConversationList(p);
      if (r.code !== 0) return { error: 'getConversationList: ' + r.code + ' ' + r.message };
      const list = (r.data && r.data.conversationList) || [];
      all = all.concat(list.map(c => ({
        id: c.conversationID, type: c.type, name: c.userProfile ? c.userProfile.nick : c.groupProfile ? c.groupProfile.name : '',
        userID: c.userProfile ? c.userProfile.userID : '', lastTime: c.lastMessage ? c.lastMessage.lastTime : 0,
        lastFlow: c.lastMessage ? c.lastMessage.flow : '', unread: c.unreadCount || 0
      })));
      const nt = r.data && r.data.nextReqMessageID;
      if (r.data && r.data.isCompleted) break;
      if (!nt || list.length === 0) break;
      next = nt;
    }
    return { conversations: all };
  } catch (e) { return { error: String(e).slice(0, 300) }; }
})()
'''

JS_MESSAGES = r'''
(async (arg) => {
  try {
    const tim = window.__tim;
    let out = [], next = undefined;
    for (let i = 0; i < 40; i++) {
      const p = { conversationID: arg.conversationID, count: 50 };
      if (next) p.nextReqMessageID = next;
      const r = await tim.getMessageList(p);
      if (r.code !== 0) return { error: 'getMessageList: ' + r.code + ' ' + r.message };
      const list = (r.data && r.data.messageList) || [];
      out = out.concat(list.map(m => {
        let content = '', extra = null;
        try {
          if (m.type === 'TIMTextElem') content = m.payload.text;
          else if (m.type === 'TIMImageElem') content = (m.payload.imageInfoArray && m.payload.imageInfoArray[0].url) || '[图片]';
          else if (m.type === 'TIMCustomElem') {
            content = m.payload.description || '[自定义消息]';
            try { extra = JSON.parse(m.payload.data); } catch (e) { extra = m.payload.data; }
          } else content = '[' + m.type + ']';
        } catch (e) { content = '[解析失败]'; }
        return {
          id: m.ID, time: m.time, flow: m.flow, from: m.from,
          nick: m.nick || '', type: m.type, content: String(content).slice(0, 2000),
          extra: extra
        };
      }));
      if (r.data && r.data.isCompleted) break;
      next = r.data && r.data.nextReqMessageID;
      if (!next) break;
    }
    return { messages: out.slice(-arg.limit) };
  } catch (e) { return { error: String(e).slice(0, 300) }; }
})(%s)
'''


def is_system(conv):
    uid = conv.get('userID') or ''
    return uid in SYSTEM_IDS or str(conv.get('id', '')).startswith('C2C@')


def norm_sender(conv, msg):
    if msg['flow'] == 'out':
        return 'self'
    return 'system' if is_system(conv) else 'hr'


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--creds', default='im_creds.json')
    ap.add_argument('--cdp-port', type=int, default=9222)
    ap.add_argument('--keyword', help='只抓会话名包含此关键词的会话')
    ap.add_argument('--since', help='起始日期 YYYY-MM-DD（按消息时间过滤）')
    ap.add_argument('--until', help='结束日期 YYYY-MM-DD')
    ap.add_argument('--max-per-conv', type=int, default=50)
    ap.add_argument('--max-convs', type=int, default=0, help='0=不限')
    ap.add_argument('--hr-only', action='store_true', help='只保留 HR/系统发来的消息（去掉自己发的）')
    ap.add_argument('--include-system', action='store_true', help='包含系统号会话（默认排除）')
    ap.add_argument('--scan-reply', action='store_true', help='只扫描「最后一条消息来自 HR 且未回复」的会话，不导出全文')
    ap.add_argument('--outdir', default='chat_out')
    ap.add_argument('--timeout', type=int, default=120, help='SDK ready 等待秒数')
    a = ap.parse_args()

    os.makedirs(a.outdir, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s %(message)s',
        handlers=[logging.FileHandler(os.path.join(a.outdir, 'fetch_chat.log'), encoding='utf-8'),
                  logging.StreamHandler(sys.stderr)])

    creds = load_creds(a.creds)
    ts0 = time.mktime(datetime.datetime.strptime(a.since, '%Y-%m-%d').timetuple()) if a.since else 0
    ts1 = time.mktime((datetime.datetime.strptime(a.until, '%Y-%m-%d') + datetime.timedelta(days=1)).timetuple()) if a.until else float('inf')

    log.info('连接 CDP :%d ...', a.cdp_port)
    tab = Tab(a.cdp_port, url_substr='chat.51job.com', create_url=CHAT_PAGE)
    log.info('注入腾讯 IM SDK (%s) ...', SDK_ASSET)
    sdk_src = open(SDK_ASSET, encoding='utf-8', errors='ignore').read()
    tab.eval('window.__sdk_src = ' + json.dumps(sdk_src), timeout=120)
    tab.eval(JS_BOOT % (json.dumps(creds), a.timeout * 1000), timeout=a.timeout + 60)
    boot = tab.eval('window.__result', timeout=30)
    if not boot or not boot.get('ok'):
        log.error('登录失败: %s', boot)
        sys.exit(3)
    log.info('腾讯 IM 登录成功 (userID=%s)', creds['userID'])

    convs = tab.eval(JS_CONVERSATIONS, timeout=120)
    if 'error' in convs:
        log.error('拉取会话列表失败: %s', convs['error'])
        sys.exit(4)
    convs = convs['conversations']
    log.info('共 %d 个会话', len(convs))

    selected = []
    for c in convs:
        if not a.include_system and is_system(c):
            continue
        if a.keyword and a.keyword not in (c.get('name') or ''):
            continue
        selected.append(c)
    if a.max_convs:
        selected = selected[:a.max_convs]
    log.info('筛选后 %d 个会话（keyword=%s, include_system=%s）', len(selected), a.keyword, a.include_system)

    records, needs_reply, errors = [], [], 0
    for i, c in enumerate(selected):
        try:
            r = tab.eval(JS_MESSAGES % json.dumps({'conversationID': c['id'], 'limit': a.max_per_conv}), timeout=120)
        except Exception as e:
            log.warning('[%d/%d] %s 读取异常: %s', i + 1, len(selected), c['id'], e)
            errors += 1
            continue
        if 'error' in r:
            log.warning('[%d/%d] %s 失败: %s', i + 1, len(selected), c['id'], r['error'])
            errors += 1
            continue
        msgs = r['messages']
        if a.scan_reply:
            real_msgs = [m for m in msgs if m['flow'] in ('in', 'out')]
            if real_msgs and real_msgs[-1]['flow'] == 'in' and real_msgs[-1]['time'] >= ts0:
                needs_reply.append({'conversation': c['name'], 'id': c['id'], 'unread': c.get('unread', 0),
                                    'last_msg_time': datetime.datetime.fromtimestamp(real_msgs[-1]['time']).isoformat(),
                                    'last_msg': real_msgs[-1]['content'][:80]})
            continue
        seen = set()
        for m in msgs:
            if not (ts0 <= m['time'] < ts1):
                continue
            sender = norm_sender(c, m)
            if a.hr_only and sender == 'self':
                continue
            if m['id'] in seen:
                continue
            seen.add(m['id'])
            records.append({
                'conversation_id': c['id'], 'conversation_name': c.get('name', ''),
                'sender_type': sender, 'sender_id': m['from'], 'sender_nick': m.get('nick', ''),
                'time': datetime.datetime.fromtimestamp(m['time']).isoformat(sep=' ', timespec='seconds'),
                'msg_type': m['type'], 'content': m['content'],
                'extra': json.dumps(m['extra'], ensure_ascii=False) if m['extra'] is not None else '',
            })
        log.info('[%d/%d] %s (%s): %d 条', i + 1, len(selected), c.get('name'), c['id'][:16], len(msgs))
        time.sleep(0.3)

    ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    if a.scan_reply:
        out = os.path.join(a.outdir, f'needs_reply_{ts}.json')
        json.dump({'generated_at': ts, 'count': len(needs_reply), 'conversations': needs_reply},
                  open(out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        log.info('待回复会话 %d 个 → %s', len(needs_reply), out)
        for n in needs_reply:
            print('  📩', n['conversation'], '|', n['last_msg_time'], '|', n['last_msg'])
    else:
        # 全局按 (conversation_id, msg id) 去重（防御 SDK 分页重叠）
        uniq, seen = [], set()
        for r in records:
            key = (r['conversation_id'], r['content'], r['time'])
            if key in seen:
                continue
            seen.add(key)
            uniq.append(r)
        jout = os.path.join(a.outdir, f'chat_{ts}.json')
        json.dump({'generated_at': ts, 'count': len(uniq), 'errors': errors, 'messages': uniq},
                  open(jout, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        cout = os.path.join(a.outdir, f'chat_{ts}.csv')
        with open(cout, 'w', encoding='utf-8-sig', newline='') as f:
            w = csv.DictWriter(f, fieldnames=list(uniq[0].keys()) if uniq else
                               ['conversation_id', 'conversation_name', 'sender_type', 'sender_id', 'sender_nick', 'time', 'msg_type', 'content', 'extra'])
            w.writeheader()
            w.writerows(uniq)
        log.info('导出 %d 条消息（会话错误 %d 个）→ %s / %s', len(uniq), errors, jout, cout)
    log.info('完成')


if __name__ == '__main__':
    main()
