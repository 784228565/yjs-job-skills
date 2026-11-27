# -*- coding: utf-8 -*-
"""从 new_jobs.json 构建投递队列（20万线 std + 方向强契合放宽档 relaxed）

沿用 11-14 定稿口径：
- 硬条件：外企池 + cosize >= 500人 + 非 BAD/WEAK/博士 + 非外链
- std：年薪 >= 20 万
- relaxed：方向强契合(STRONG) 且 >= 8万 或 实习日薪；MED/SUPPORT 档 >= 9 万
- 公司级一投：同公司只留薪资最高的 2 个
- 投递 URL 归一化为 q.yingjiesheng.com/jobdetail/<id>.html（去 property 跟踪参数）

用法：python queue_build.py --dir pool_2026-11-20 --state deliver_state.json
产出：<dir>/deliver_queue.json
"""
import argparse
import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analyze_pool import (STRONG, MED, SUPPORT, WEAK, DOCTOR, annual_wan,
                          daily_rate, hit_url, BIG)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--state", default=None)
    args = ap.parse_args()
    d = os.path.abspath(args.dir)

    new = json.load(open(os.path.join(d, "new_jobs.json"), encoding="utf-8"))
    done = set()
    if args.state and os.path.exists(args.state):
        st = json.load(open(args.state, encoding="utf-8"))
        done = {str(k) for k in st.get("done", {}).keys()}
    print(f"new_jobs: {len(new)} | 已投 {len(done)}")

    std, relaxed, excluded = [], [], []
    for j in new:
        jid = str(j.get("id"))
        name = j.get("jobname") or ""
        co = j.get("coname") or ""
        sal = j.get("salary") or ""
        area = j.get("jobarea") or ""
        degree = j.get("degree") or ""
        aw = annual_wan(sal)
        dr = daily_rate(sal)
        size = str(j.get("cosize") or "")
        url = hit_url(j)

        if jid in done:
            excluded.append((aw, co, name, sal, "已投"))
            continue
        if not url:
            excluded.append((aw, co, name, sal, "非yjs岗位"))
            continue
        if size not in BIG:
            excluded.append((aw, co, name, sal, "规模<500人"))
            continue
        if WEAK.search(name) or WEAK.search(co) or DOCTOR.search(name) or DOCTOR.search(degree):
            excluded.append((aw, co, name, sal, "BAD/WEAK/博士"))
            continue

        row = {"id": jid, "co": co, "job": name, "salary": sal, "aw": aw, "url": url,
               "area": area, "size": size, "degree": degree,
               "tags": j.get("jobTags") or [], "jobterm": j.get("jobterm") or ""}
        intern = (j.get("jobterm") == "实习") or ("实习" in (name + sal)) or (dr > 0)
        if aw >= 20:
            std.append(row)
        elif (STRONG.search(name) and (aw >= 8 or dr > 0)) or \
             ((MED.search(name) or SUPPORT.search(name)) and aw >= 9) or \
             (intern and (STRONG.search(name) or MED.search(name) or SUPPORT.search(name)) and dr > 0):
            relaxed.append(row)
        else:
            excluded.append((aw, co, name, sal, "低薪且方向弱"))

    # 公司级一投：同公司只留薪资最高的 2 个（yjs 外企普遍每公司仅一志愿，撞 isxyzapply=2）
    def trim_by_co(rows, cap=2):
        by_co = {}
        for r in rows:
            by_co.setdefault(r["co"], []).append(r)
        keep, drop = [], []
        for co, rs in by_co.items():
            rs.sort(key=lambda x: (-x["aw"], 0 if "上海" in x["area"] else 1))
            keep.extend(rs[:cap])
            if len(rs) > cap:
                drop.extend((x["aw"], x["co"], x["job"], x["salary"], "公司截留") for x in rs[cap:])
        return keep, drop

    std, dropped_std = trim_by_co(std, 2)
    excluded.extend(dropped_std)
    relaxed, dropped_relaxed = trim_by_co(relaxed, 2)
    excluded.extend(dropped_relaxed)

    # 投递优先级：上海优先（用户硬偏好 上海>东京），其次薪资，再次方向契合度
    def rank(r):
        return (0 if "上海" in r["area"] else 1,
                -r["aw"],
                0 if STRONG.search(r["job"]) else 1)
    std.sort(key=rank)
    relaxed.sort(key=rank)

    def show(title, rows):
        print(f"\n== {title} {len(rows)} 岗 ==")
        for i, r in enumerate(rows, 1):
            sh = "⭐" if "上海" in r["area"] else "  "
            print(f" {i:3d}{sh}{r['aw']:6.1f}万 | {r['co'][:22]:22} | {r['job'][:42]:42} | "
                  f"{r['area'][:12]:12} | {r['salary']}")

    show("20万线 std", std)
    show("方向强契合放宽档 relaxed", relaxed)
    print(f"\n== 剔除 {len(excluded)} ==")
    print(Counter(x[4] for x in excluded))

    queue = [{"id": r["id"], "co": r["co"], "job": r["job"], "url": r["url"],
              "salary": r["salary"], "aw": r["aw"], "area": r["area"]}
             for r in std + relaxed]
    out = os.path.join(d, "deliver_queue.json")
    json.dump(queue, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\nqueue -> {len(queue)} 岗 (std {len(std)} + relaxed {len(relaxed)}) -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
