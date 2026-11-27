# -*- coding: utf-8 -*-
"""yjs 外企岗位池分析：薪资/规模/方向三维筛选

沿用 11-14 定稿口径：
- 薪资：年薪 ≥20 万（2026-11-04 用户放宽，原 24 万）；月薪制按下限 × 薪月数
- 规模：cosize ∈ {500-1000人, 1000-5000人, 5000-10000人, 10000人以上}
- 方向：STRONG 强契合（数据/AI/算法/软件…）+ MED 档 + 技术支持类
- 剔除：管家|房产|房屋|地产|销售工程师|客服工程师|储备干部|博士 要求

产出 pool_analyzed.json / pool_hits.json / pool_final.json
用法：python analyze_pool.py --dir pool_2026-11-20
"""
import argparse
import json
import os
import re
import sys
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8")

BIG = {"500-1000人", "1000-5000人", "5000-10000人", "10000人以上"}

STRONG = re.compile(r'数据|算法|机器学习|深度学习|人工智能|AI|大模型|LLM|NLP|计算机视觉|机器视觉|视觉算法|'
                    r'大数据|数据挖掘|Data|Analyst|Scientist|Machine Learning|Quant|量化|推荐|搜索|智能体|Agent')
MED = re.compile(r'软件|嵌入式|系统|自动化|机器人|数字|CAD|ROS|CNC|Python|Java|测试|IT|开发')
SUPPORT = re.compile(r'Customer Support|Technical Support|Application Support|Applications? Engineer|'
                     r'Support Engineer|FAE|技术支持|应用支持|应用工程师|实施工程师|售后工程师|'
                     r'维护工程师|服务工程师|Field Service|Implementation|解决方案|应用专员|'
                     r'Application Specialist|现场应用')
WEAK = re.compile(r'销售代表|电话销售|销售工程师|销售支持|销售管培|销售新星|销售精英|店长|店经理|柜长|'
                  r'房产|豪宅|房屋|地产|中介|管家|经纪人|置业|保险代理|'
                  r'客服专员|客服工程师|行政前台|储备干部|招聘|猎头|人力资源|HRBP|人力资源HR|'
                  r'商务拓展|市场营销专员|市场专员|采购专员|供应链管理培训生|管培生')
DOCTOR = re.compile(r'博士')


def annual_wan(sal):
    """salary 文本 -> 年薪（万元）。顺序敏感：先判 万/年。"""
    sal = sal or ""
    m = re.search(r'([\d.]+)-([\d.]+)万/年', sal)
    if m:
        return float(m.group(2))
    m = re.match(r'([\d.]+)-([\d.]+)万(?:·(\d+)薪)?', sal)
    if m:
        return float(m.group(1)) * int(m.group(3) or 12)
    m = re.match(r'([\d.]+)-([\d.]+)千(?:·(\d+)薪)?', sal)
    if m:
        return float(m.group(1)) / 10 * int(m.group(3) or 12)
    m = re.match(r'([\d.]+)-([\d.]+)元/天', sal)
    if m:
        return float(m.group(1)) / 22 * 12
    return 0


def daily_rate(sal):
    m = re.search(r'([\d.]+)元/天', sal or "")
    return float(m.group(1)) if m else 0


def hit_url(j):
    """投递 URL 归一化：q.yingjiesheng.com/jobdetail/<id>.html（去 property 跟踪参数，带 .html 后缀）"""
    jid = str(j.get("id") or "")
    if not jid.isdigit():
        return ""
    return f"https://q.yingjiesheng.com/jobdetail/{jid}.html"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    args = ap.parse_args()
    d = os.path.abspath(args.dir)

    pool = json.load(open(os.path.join(d, "pool_foreign_segmented.json"), encoding="utf-8"))
    print(f"POOL TOTAL: {len(pool)}")

    rows = []
    for j in pool:
        name = j.get("jobname") or ""
        co = j.get("coname") or ""
        sal = j.get("salary") or ""
        aw = annual_wan(sal)
        dr = daily_rate(sal)
        size = str(j.get("cosize") or "")
        degree = j.get("degree") or ""
        tags = j.get("jobTags") or []

        hit_sal = aw >= 20
        hit_size = size in BIG
        strong = bool(STRONG.search(name))
        med = bool(MED.search(name))
        support = bool(SUPPORT.search(name))
        bad = bool(WEAK.search(name) or WEAK.search(co) or DOCTOR.search(name) or DOCTOR.search(degree))
        is_intern = (j.get("jobterm") == "实习") or ("实习" in (name + sal)) or (dr > 0)

        rows.append({
            "id": j.get("id"), "job": name, "co": co, "size": size, "salary": sal,
            "area": j.get("jobarea"), "ind": j.get("industry"), "degree": degree,
            "jobterm": j.get("jobterm"), "tags": tags,
            "aw": aw, "daily": dr, "hit_sal": hit_sal, "hit_size": hit_size,
            "strong": strong, "med": med, "support": support, "bad": bad,
            "intern": is_intern, "url": hit_url(j),
        })

    hits = [r for r in rows if r["hit_sal"] and r["hit_size"] and not r["bad"]]
    hits.sort(key=lambda r: -r["aw"])
    print(f"HIT (薪资达标 + 中大型 + 未剔除): {len(hits)}")

    # 投递候选：20 万线（std）/ 方向强契合放宽档（relaxed）
    std, relaxed, excluded = [], [], []
    for r in rows:
        if r["bad"]:
            excluded.append((r["aw"], r["co"], r["job"], r["salary"], "BAD/WEAK/博士"))
            continue
        if not r["hit_size"]:
            excluded.append((r["aw"], r["co"], r["job"], r["salary"], "规模不达标"))
            continue
        if r["hit_sal"]:
            std.append(r)
        elif (r["strong"] and (r["aw"] >= 8 or r["daily"] > 0)) or \
             (r["med"] and r["aw"] >= 9) or \
             (r["support"] and r["aw"] >= 9) or \
             (r["intern"] and (r["strong"] or r["med"] or r["support"]) and r["daily"] > 0):
            relaxed.append(r)
        else:
            excluded.append((r["aw"], r["co"], r["job"], r["salary"], "低薪且方向弱"))

    # 公司级一投：同公司只留薪资最高的 2 个
    by_co = {}
    for r in std:
        by_co.setdefault(r["co"], []).append(r)
    std_trim = []
    for co, rs in by_co.items():
        rs.sort(key=lambda x: -x["aw"])
        std_trim.extend(rs[:2])
        if len(rs) > 2:
            excluded.extend((x["aw"], x["co"], x["job"], x["salary"], "公司截留") for x in rs[2:])
    std = std_trim

    print(f"\n== 20万线 std {len(std)} 岗 ==")
    for r in sorted(std, key=lambda x: -x["aw"]):
        print(f"  {r['aw']:6.1f}万 | {r['co'][:20]:20} | {r['job'][:40]:40} | {str(r['area'])[:12]:12} | {r['salary']}")
    print(f"\n== 方向强契合放宽档 relaxed {len(relaxed)} 岗 ==")
    for r in sorted(relaxed, key=lambda x: -x["aw"]):
        print(f"  {r['aw']:6.1f}万 | {r['co'][:20]:20} | {r['job'][:40]:40} | {str(r['area'])[:12]:12} | {r['salary']}")
    print(f"\n== 剔除 {len(excluded)} ==")
    print(Counter(x[4] for x in excluded))

    json.dump(rows, open(os.path.join(d, "pool_analyzed.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    json.dump(hits, open(os.path.join(d, "pool_hits.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    final = std + relaxed
    json.dump(final, open(os.path.join(d, "pool_final.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"\npool_final: {len(final)} 岗 (std {len(std)} + relaxed {len(relaxed)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
