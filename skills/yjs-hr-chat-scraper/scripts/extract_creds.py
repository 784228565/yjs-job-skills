# -*- coding: utf-8 -*-
"""从 mitmproxy 抓包文件提取腾讯 IM 凭证 → im_creds.json
用法: python extract_creds.py <flows文件> [--out im_creds.json]
需要 mitmproxy 包: pip install mitmproxy
（注意：mitmproxy 与 fetch_chat.py 所需的 websocket-client 可能不在同一
python 环境；本机 mitmproxy 装在 default venv，见 SKILL.md 前置条件）

提取逻辑（2026-10-23 加固，修掉"静默保存过期凭证"的坑）：
- 收集所有 /imbc/open/job51/txinit 的凭证；userSig = zlib+base64，
  payload 含 TLS.time / TLS.expire（有效期 48h）
- 多条 txinit 时自动选过期时间最新的一条（抓包文件常跨天追加，旧条目会混在里面）
- 选中的凭证已过期 → 退出码 2 并提示冷启动 App，不静默保存过期凭证
- 不覆盖已有但更新的凭证文件
退出码：0 成功；1 未找到 txinit；2 最新凭证已过期；3 拒绝覆盖更新的已有凭证；5 缺 mitmproxy 包
"""
import base64
import json
import os
import sys
import time
import zlib
import argparse
from datetime import datetime


def sig_expire(user_sig):
    """解析 userSig 中的过期时间戳（Unix 秒）；失败返回 None"""
    if not user_sig:
        return None
    try:
        s = user_sig.replace('*', '+')
        raw = base64.b64decode(s + '=' * (-len(s) % 4))
        payload = json.loads(zlib.decompress(raw).decode('utf-8', 'ignore'))
        t, e = payload.get('TLS.time', 0), payload.get('TLS.expire', 0)
        return t + e if (t or e) else None
    except Exception:
        return None


def load_out_expire(path):
    try:
        c = json.load(open(path, encoding='utf-8'))
        return sig_expire(c.get('userSig', ''))
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('flows')
    ap.add_argument('--out', default='im_creds.json')
    a = ap.parse_args()

    try:
        from mitmproxy.io import FlowReader
    except ImportError:
        print('错误：未安装 mitmproxy 包（pip install mitmproxy）。'
              '建议装在独立 venv 里（含 mitmproxy 11），'
              '注意与 fetch_chat.py 的运行环境区分', file=sys.stderr)
        sys.exit(5)

    # 大文件（数十 MB）先复制快照再读，避免读到 mitmproxy 正在写入的半条记录
    import shutil
    import tempfile
    tmpdir = tempfile.mkdtemp(prefix='flows_snap_')
    snap = os.path.join(tmpdir, 'snapshot.flows')
    try:
        shutil.copyfile(a.flows, snap)
    except Exception as e:
        print(f'错误：无法读取抓包文件 {a.flows}: {e}', file=sys.stderr)
        sys.exit(1)

    found = []  # (expire_at|None, captured_ts, creds)
    try:
        with open(snap, 'rb') as f:
            for fl in FlowReader(f).stream():
                req = getattr(fl, 'request', None)
                if not req or getattr(fl, 'response', None) is None:
                    continue
                if req.path.split('?')[0] != '/imbc/open/job51/txinit':
                    continue
                try:
                    rb = json.loads(fl.response.get_text(strict=False))['resultbody']
                    sig = rb['txImToken'].replace('*', '+')
                    creds = {'sdkAppID': rb['txAppId'], 'userID': rb['imId'], 'userSig': sig}
                    found.append((sig_expire(sig), getattr(fl.request, 'timestamp_start', 0), creds))
                except Exception:
                    continue  # 单条解析失败不中断
    except Exception as e:
        print(f'警告：flows 文件读取中断（可能 mitmproxy 正在写入）：{e}', file=sys.stderr)
    finally:
        try:
            os.remove(snap)
            os.rmdir(tmpdir)
        except OSError:
            pass

    if not found:
        print('未找到 txinit 请求。确保抓包时杀掉并重开了应届生/51job App 并进入嗨聊'
              '（App 不冷启动不会发 txinit，会复用本地旧 token）。', file=sys.stderr)
        sys.exit(1)

    found.sort(key=lambda x: (x[0] if x[0] is not None else -1, x[1]))
    exp, ts, creds = found[-1]  # 取过期时间最新的一条
    cap = datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S') if ts else '?'
    print(f'共找到 {len(found)} 条 txinit，选用最新的一条（抓于 {cap}）')
    if len(found) > 1:
        print('提示：抓包文件中有多条 txinit（跨天追加导致），已自动选最新；建议定期清理旧 flows 文件')

    now = time.time()
    old_exp = load_out_expire(a.out)
    if exp is not None and old_exp is not None and old_exp > exp:
        print(f'警告：{a.out} 中的凭证比抓包里的更新（剩 {(old_exp - now) / 3600:.1f}h），不覆盖', file=sys.stderr)
        sys.exit(3)

    if exp is None:
        print('警告：无法解析 userSig 过期时间，仍按未知有效期保存（fetch_chat.py 会再次校验）')
    elif exp <= now:
        print(f'错误：最新凭证也已过期 {-(exp - now) / 3600:.1f} 小时（抓于 {cap}）。'
              '请杀掉应届生/51job App 后重开并进入嗨聊，触发新的 txinit 后再提取。', file=sys.stderr)
        sys.exit(2)

    json.dump(creds, open(a.out, 'w'), indent=1)
    print('saved', a.out, {k: (str(v)[:12] + '...' if k == 'userSig' else v) for k, v in creds.items()})
    if exp:
        print(f'凭证有效，剩余 {(exp - now) / 3600:.1f} 小时')


if __name__ == '__main__':
    main()
