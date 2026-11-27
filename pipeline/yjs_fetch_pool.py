# -*- coding: utf-8 -*-
"""yjs 外企岗位池分段抓取（HMAC-SHA256 签名接口 /open/noauth/job/search）

- 按企业规模 cosize 分段：4=500-1000人 5=1000-5000人 6=5000-10000人 7=10000人以上
- 外企池 cotype=01,02,06
- 单 IP 限流：连续 405 需长冷却（段5 ~150s，段6 ~180s）
- 幂等：pool_size_<seg>.json 已存在且非空则跳过该段（--only 可强制重抓）
用法：
  python yjs_fetch_pool.py --out pool_2026-11-20
  python yjs_fetch_pool.py --out pool_2026-11-20 --only 6
"""
import argparse
import hashlib
import hmac
import json
import os
import sys
import time
import urllib.parse
import urllib.request

# 剥离代理环境变量（本机 Clash 7897 会干扰直连）
for _k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
    os.environ.pop(_k, None)
os.environ["NO_PROXY"] = "*"

sys.stdout.reconfigure(encoding="utf-8")

# 签名密钥不随仓库分发：从环境变量读取（见 README「签名密钥」一节）
KEY = os.environ.get("YJS_SIGN_KEY", "").strip()

SEGMENTS = [
    ("4", "500-1000人", 240),
    ("5", "1000-5000人", 150),
    ("6", "5000-10000人", 180),
    ("7", "10000人以上", 210),
]
PAGESIZE = 50
MAXPAGES = 21


def sign(p):
    if not KEY:
        raise SystemExit(
            "缺少签名密钥：请先设置环境变量 YJS_SIGN_KEY（获取方式见 README「签名密钥」一节）"
        )
    return hmac.new(KEY.encode(), ("/" + p).encode(), hashlib.sha256).hexdigest()


def fetch(params):
    ts = int(time.time())
    q = {"version": "2.3.5", "api_key": "xy", "timestamp": ts}
    q.update(params)
    qs = "&".join(f"{k}={urllib.parse.quote(str(v), safe='')}" for k, v in q.items())
    path = "open/noauth/job/search?" + qs
    req = urllib.request.Request(
        "https://youngapi.yingjiesheng.com/" + path,
        headers={
            "sign": sign(path),
            "From-Domain": "yjs_web",
            "Accept": "application/json",
            "Referer": "https://q.yingjiesheng.com/",
            "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                           "Chrome/157.0.0.0 Safari/537.36"),
            "property": urllib.parse.quote(json.dumps(
                {"partner": "", "webId": 6, "fromdomain": "yjs_web", "isLogin": "否"})),
        })
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.loads(r.read().decode())


def grab(cosize, label, outdir, cool):
    jobs = {}
    page = 1
    total = None
    consecutive_405 = 0
    while page <= MAXPAGES:
        params = {"keyword": "", "jobarea": "", "landmark": "", "metro": "", "degree": "",
                  "jobterm": "", "workYear": "", "saltype": "", "cotype": "01,02,06",
                  "cosize": cosize, "industry": "", "requestId": "",
                  "pagesize": str(PAGESIZE), "pageno": str(page),
                  "searchType": "2", "scene": "7"}
        try:
            resp = fetch(params)
            consecutive_405 = 0
        except Exception as e:
            code = getattr(e, "code", None)
            consecutive_405 += 1
            if code == 405:
                print(f"[{label}] p{page} 405 限流 -> 冷却 {cool}s (连续 {consecutive_405})", flush=True)
                time.sleep(cool)
                if consecutive_405 >= 5:
                    print(f"[{label}] 连续 5 次 405，放弃本段剩余页", flush=True)
                    break
                continue
            print(f"[{label}] p{page} err {code or e} -> 冷却 {cool}s", flush=True)
            time.sleep(cool)
            if consecutive_405 >= 4:
                break
            continue
        try:
            jl = resp["resultbody"]["searchData"]["joblist"]
            items = jl["items"]
            if total is None:
                total = int(jl.get("totalCount", 0))
                print(f"[{label}] totalCount={total}", flush=True)
        except Exception as e:
            print(f"[{label}] parse err: {e}", flush=True)
            break
        if not items:
            break
        for j in items:
            jobs[str(j["jobid"])] = {
                "jobname": j.get("jobname"), "coname": j.get("coname"),
                "cotype": j.get("cotype"), "cosize": j.get("cosize"),
                "salary": j.get("providesalary"), "jobarea": j.get("jobarea"),
                "id": j.get("jobid"), "industry": j.get("coIndustryText"),
                "degree": j.get("degree"), "jobterm": j.get("jobterm"),
                "jobTags": j.get("jobTags"), "url": j.get("jumpUrlHttp"),
            }
        print(f"[{label}] page {page} -> {len(jobs)}", flush=True)
        if total and page * PAGESIZE >= total:
            break
        page += 1
        time.sleep(1.2)
    print(f"[{label}] DONE {len(jobs)}", flush=True)
    return jobs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, help="输出目录")
    ap.add_argument("--only", default=None, help="只抓指定规模段代码（4/5/6/7）")
    ap.add_argument("--force", action="store_true", help="已存在的段也重抓")
    args = ap.parse_args()

    outdir = os.path.abspath(args.out)
    os.makedirs(outdir, exist_ok=True)

    for code, label, cool in SEGMENTS:
        if args.only and code != args.only:
            continue
        seg_path = os.path.join(outdir, f"pool_size_{code}.json")
        if os.path.exists(seg_path) and not args.force:
            try:
                n = len(json.load(open(seg_path, encoding="utf-8")))
                if n:
                    print(f"===== SEG {code} {label}: 已存在 {n} 条，跳过 =====", flush=True)
                    continue
            except Exception:
                pass
        print(f"===== SEG {code} {label} =====", flush=True)
        got = grab(code, f"{code}-{label}", outdir, cool)
        if got:
            json.dump(list(got.values()), open(seg_path, "w", encoding="utf-8"),
                      ensure_ascii=False, indent=1)
        else:
            print(f"[{label}] 本段零结果，保留原文件不覆盖", flush=True)
        time.sleep(5)

    merged = {}
    for code, _label, _c in SEGMENTS:
        p = os.path.join(outdir, f"pool_size_{code}.json")
        try:
            for j in json.load(open(p, encoding="utf-8")):
                merged[str(j["id"])] = j
        except Exception as e:
            print(f"skip segment {code}: {e}", flush=True)
    out_path = os.path.join(outdir, "pool_foreign_segmented.json")
    json.dump(list(merged.values()), open(out_path, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"TOTAL_UNIQUE {len(merged)} -> {out_path}", flush=True)
    for code, label, _c in SEGMENTS:
        try:
            n = len(json.load(open(os.path.join(outdir, f"pool_size_{code}.json"), encoding="utf-8")))
        except Exception:
            n = 0
        print(f"  seg {code} {label}: {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
