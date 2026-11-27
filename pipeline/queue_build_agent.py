# -*- coding: utf-8 -*-
"""构建今日投递队列 = 主队列(analyze/queue_build 产出) + AI agent 放宽档，
并拆成每批 <=BATCH 个岗位（规避 yjs WAF：单批超过约 12 个必触发滑块）。

用法:
  python queue_build_agent.py --pool pool_2026-11-24 --state deliver_state.json --batch 12
产出:
  <pool>/deliver_queue.json          总队列
  <pool>/deliver_queue_agent.json    仅 AI 放宽档
  <pool>/deliver_batch1.json ...     分批次
"""
import json, os, re, argparse, shutil
from collections import Counter

# 词边界，避免 Thai / Analysis / Failure 误命中
AI_WORD = re.compile(r'(?<![A-Za-z])AI(?![A-Za-z])')
AGENT_KW = re.compile(r'Agent|智能体|LLM|大模型|AIGC|RAG|Copilot|Prompt|提示词|生成式|GenAI|'
                      r'机器学习|深度学习|算法工程师|NLP|自然语言|计算机视觉|人工智能|机器视觉')
DATA_KW = re.compile(r'数据分析|大数据|数据挖掘|数据工程|数据科学|Data Analyst|Data Scientist|BI')
WEAK = re.compile(r'销售代表|电话销售|销售工程师|销售支持|销售管培|销售新星|销售精英|店长|店经理|柜长|'
                  r'房产|豪宅|房屋|地产|中介|管家|经纪人|置业|保险代理|'
                  r'客服专员|客服工程师|行政前台|储备干部|招聘|猎头|人力资源|HRBP|'
                  r'商务拓展|市场营销专员|市场专员|采购专员|供应链管理培训生|管培生|客户经理|跟单|'
                  r'店员|CNC|数控|安规测试|化学测试|海工机械|数据中心运维')
DOCTOR = re.compile(r'博士')


def hit_url(j):
    jid = str(j.get("id") or "")
    return f"https://q.yingjiesheng.com/jobdetail/{jid}.html" if jid.isdigit() else ""


def to_row(j):
    return {"id": str(j.get("id")), "co": j.get("coname") or "", "job": j.get("jobname") or "",
            "url": hit_url(j), "salary": j.get("salary") or "", "area": j.get("jobarea") or ""}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pool", required=True)
    ap.add_argument("--state", default="deliver_state.json")
    ap.add_argument("--batch", type=int, default=12)
    a = ap.parse_args()

    pool_dir = a.pool
    pool = json.load(open(os.path.join(pool_dir, "pool_foreign_segmented.json"), encoding="utf-8"))
    st = json.load(open(a.state, encoding="utf-8"))
    done = {str(k) for k in st.get("done", {}).keys()}

    main_q_path = os.path.join(pool_dir, "deliver_queue.json")
    if os.path.exists(main_q_path):
        main_q = json.load(open(main_q_path, encoding="utf-8"))
    else:
        main_q = []
    main_ids = {str(r["id"]) for r in main_q}

    seen_co = Counter(str(r["co"]) for r in main_q)
    agent_rows = []
    for j in pool:
        jid = str(j.get("id"))
        name = j.get("jobname") or ""
        co = j.get("coname") or ""
        if jid in done or jid in main_ids:
            continue
        if not (AI_WORD.search(name) or AGENT_KW.search(name) or DATA_KW.search(name)):
            continue
        if WEAK.search(name) or WEAK.search(co):
            continue
        if DOCTOR.search(name) or DOCTOR.search(j.get("degree") or ""):
            continue
        if seen_co[co] >= 2:
            continue
        seen_co[co] += 1
        agent_rows.append(to_row(j))

    agent_rows.sort(key=lambda r: (0 if "上海" in r["area"] else 1, r["co"]))
    json.dump(agent_rows, open(os.path.join(pool_dir, "deliver_queue_agent.json"), "w",
                               encoding="utf-8"), ensure_ascii=False, indent=1)

    total = main_q + agent_rows
    json.dump(total, open(main_q_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    n = a.batch
    batches = [total[i:i + n] for i in range(0, len(total), n)]
    for i, b in enumerate(batches, 1):
        json.dump(b, open(os.path.join(pool_dir, f"deliver_batch{i}.json"), "w",
                          encoding="utf-8"), ensure_ascii=False, indent=1)

    print(f"主队列 {len(main_q)} + AI 放宽档 {len(agent_rows)} = 总队列 {len(total)}")
    print(f"拆批: {[len(b) for b in batches]}（每批 <= {n}）\n")
    for i, b in enumerate(batches, 1):
        print(f"--- batch{i} ---")
        for r in b:
            print(f"  {r['id']:<10} {r['co'][:20]:<20} {r['job'][:34]:<34} {r['area'][:8]:<8} {str(r.get('salary',''))[:14]}")


if __name__ == "__main__":
    main()
