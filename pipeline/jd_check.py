# -*- coding: utf-8 -*-
"""JD 正文预检：逐岗开 .html 详情页，抽取投递按钮状态 + JD 正文 + 经验/学历硬要求

背景（11-14/11-17 实测）：yjs 列表标签「无需经验」不可信，JD 正文常写「5 年以上」。
本脚本在投递前扫一遍队列，把硬性不符（要求 3+ 年经验 / 博士 / 已下线 / 已申请）的岗位剔除，
避免浪费投递名额与 WAF 额度。

用法：
  python jd_check.py --queue pool_2026-11-20/deliver_queue.json \
      --out pool_2026-11-20/jd_details.json --shots logs/jd_check
"""
import argparse
import json
import os
import re
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (
    os.path.join(_HERE, "..", "skills", "yjs-job-pipeline", "scripts"),
    os.path.expanduser("~/.workbuddy/skills/yjs-job-pipeline/scripts"),
):
    if os.path.isdir(_p):
        sys.path.insert(0, _p)
        break
from deliver_pool import Tab  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")

# 抓取正文 + 按钮状态
READ_JS = r"""(()=>{
  const btn=document.querySelector('.delivery-btn');
  const t=(document.body.innerText||'').replace(/\s+/g,' ');
  // JD 正文容器优先级
  let jd='';
  const sels=['.job-detail','.jobdetail','.detail-content','.job-info',
              '.position-detail','.content-detail','[class*=jd]','.jobDescription'];
  for(const s of sels){
    const e=document.querySelector(s);
    if(e&&e.innerText&&e.innerText.length>120){jd=e.innerText;break;}
  }
  if(!jd) jd=t;
  return JSON.stringify({
    url:location.href, title:document.title.slice(0,80),
    btn: btn?btn.innerText.trim():null,
    captcha: !!document.querySelector('#tcaptcha_transform_dy, iframe[src*=captcha], [class*=captcha]'),
    jd: jd.slice(0,3000), len:t.length
  });
})()"""

# 经验硬要求：仅在「任职要求/岗位要求/职位描述」语境中出现才算硬门槛
EXP_HARD = re.compile(r'(?:任职要求|岗位要求|职位要求|任职资格|经验要求|任职要求)\s*[:：]?[^。]{0,80}?'
                      r'(\d+)\s*年(?:以上|及以上|\+)')
EXP_LOOSE = re.compile(r'(\d+)\s*年(?:以上|及以上|\+)\s*(?:相关)?(?:工作)?经验')
DOCTOR_REQ = re.compile(r'(博士|Ph\.?D|PhD)\s*(?:学历|学位|及以上)?')
BACHELOR_REQ = re.compile(r'本科(?:及以上|以上)?学历')
# 在校生硬要求：用户 2024-07 已毕业，不是在校生，硬性要求在读的不投
STUDENT_REQ = re.compile(r'(?:在校生|在读学生|在读本科|在读硕士|在读研究生|全日制在读|在校大学生|'
                         r'仅限.{0,6}在读|应届在校生)')


def evaluate(rec):
    """返回 (verdict, reason)。verdict ∈ ok / skip_exp / skip_phd / skip_down / skip_applied / unknown"""
    jd = rec.get("jd") or ""
    btn = rec.get("btn") or ""
    if rec.get("captcha"):
        return "unknown", "captcha"
    if not btn:
        return "skip_down", "无投递按钮(可能下架/渲染失败)"
    if "已申请" in btn or "已投递" in btn:
        return "skip_applied", btn
    if "不可申请" in btn:
        return "skip_applied", "不可申请(公司志愿锁定)"
    m = EXP_HARD.search(jd)
    if m and int(m.group(1)) >= 3:
        return "skip_exp", f"要求{m.group(1)}年以上经验"
    if DOCTOR_REQ.search(jd) and "本科" not in jd:
        return "skip_phd", "要求博士学历"
    if STUDENT_REQ.search(jd):
        return "skip_student", "硬性要求在读在校生(用户已毕业)"
    return "ok", ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--queue", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--shots", default="logs/jd_check")
    ap.add_argument("--cooldown", type=float, default=6.0)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    queue = json.load(open(args.queue, encoding="utf-8"))
    if args.limit:
        queue = queue[:args.limit]
    out_path = args.out
    details = {}
    if os.path.exists(out_path):
        details = {str(k): v for k, v in json.load(open(out_path, encoding="utf-8")).items()}

    print(f"JD 预检 {len(queue)} 岗, cooldown={args.cooldown}s", flush=True)
    for i, j in enumerate(queue, 1):
        jid = str(j["id"])
        if jid in details and details[jid].get("verdict") in ("ok", "skip_exp", "skip_phd", "skip_down", "skip_applied"):
            continue
        if i > 1:
            time.sleep(args.cooldown)
        rec = {"id": jid, "co": j.get("co", ""), "job": j.get("job", ""),
               "url": j.get("url"), "ts": time.strftime("%H:%M:%S")}
        tab = None
        try:
            tab = Tab(j["url"])
            st = None
            for _ in range(20):
                time.sleep(1.0)
                try:
                    st = json.loads(tab.eval(READ_JS) or "{}")
                except Exception:
                    st = None
                if st and (st.get("btn") or st.get("captcha")):
                    break
            if not st:
                rec.update(verdict="unknown", reason="页面不可读")
            else:
                rec.update({k: st.get(k) for k in ("url", "title", "btn", "captcha", "jd")})
                v, reason = evaluate(rec)
                rec.update(verdict=v, reason=reason)
        except Exception as e:
            rec.update(verdict="unknown", reason=repr(e)[:160])
        finally:
            if tab:
                tab.close()
        details[jid] = rec
        json.dump(details, open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        flag = "OK " if rec.get("verdict") == "ok" else "-- "
        print(f"{flag}[{i}/{len(queue)}] {jid} {rec.get('co','')[:14]} | {rec.get('job','')[:34]} | "
              f"btn={rec.get('btn')} | {rec.get('verdict')} {rec.get('reason','')}", flush=True)

    from collections import Counter
    print("\n=== 预检统计 ===")
    print(Counter(v.get("verdict") for v in details.values()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
