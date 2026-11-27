# -*- coding: utf-8 -*-
"""yjs 岗位池增量 diff：对比旧快照找出新上架岗位，并剔除已投

用法：python diff_new.py --dir pool_2026-11-20 --snapshot <旧 pool_foreign_segmented.json>
产出：<dir>/new_jobs.json
"""
import argparse
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")


def load(p):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception as e:
        print(f"  skip {p}: {e}")
        return []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--snapshot", required=True, help="旧快照 pool_foreign_segmented.json 路径")
    ap.add_argument("--state", default=None, help="deliver_state.json，用于剔除已投")
    args = ap.parse_args()

    d = os.path.abspath(args.dir)
    new = load(os.path.join(d, "pool_foreign_segmented.json"))
    old = load(args.snapshot)
    new_map = {str(j.get("id")): j for j in new}
    old_map = {str(j.get("id")): j for j in old}
    print(f"旧快照 {len(old_map)} | 今日 {len(new_map)}")

    added = [j for k, j in new_map.items() if k not in old_map]
    removed = [k for k in old_map if k not in new_map]
    print(f"新增 {len(added)} | 下架 {len(removed)}")

    if args.state and os.path.exists(args.state):
        st = json.load(open(args.state, encoding="utf-8"))
        done = {str(k) for k in st.get("done", {}).keys()}
        before = len(added)
        added = [j for j in added if str(j.get("id")) not in done]
        print(f"剔除已投 {before - len(added)} 岗，剩 {len(added)}")

    out = os.path.join(d, "new_jobs.json")
    json.dump(added, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"saved -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
