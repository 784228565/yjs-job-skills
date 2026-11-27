# -*- coding: utf-8 -*-
"""51job 旧版 FillInResume 分步简历向导工具（中集/联影/百联/恩智浦同款）。

Usage:
  PYTHONPATH="" python s51_step.py <CtmID>            # dump 当前步字段+错误+截图
  PYTHONPATH="" python s51_step.py <CtmID> next       # dump 后点 imgbtnNext 并 dump 下一步
  PYTHONPATH="" python s51_step.py <CtmID> next shot7 # 自定义截图名

成功标志：跳转 young.yingjiesheng.com/xyzsuccess?...resumeid=...（title=投递成功）。

坑：
  - 报错文本（如"GPA不能为空!"）在下一步可能仍残留显示；判断是否真错误看步骤是否前进。
  - 末步无 imgbtnNext，按钮是 imgbtnSubmit（有的还有隐私声明 checkbox 要先勾）。
  - 每步底部图片按钮 input[type=image][name=imgbtnNext/Previous/Save/Submit]。
"""
import asyncio, base64, json, sys, time
from pathlib import Path

from cdp import CDP

CTMID = sys.argv[1]
DO_NEXT = len(sys.argv) > 2 and sys.argv[2] == "next"
SHOT = sys.argv[3] if len(sys.argv) > 3 else "s51_step"
ART = Path(__file__).resolve().parent.parent / "out"
ART.mkdir(exist_ok=True)

DUMP = r"""
(() => {
  const out = {h1: (document.querySelector('#container h1')||{}).innerText || ''};
  const fields = [];
  document.querySelectorAll('input[type=text], input[type=radio], input[type=checkbox], select, textarea').forEach(e => {
    if (e.offsetParent === null) return;
    if (e.type === 'radio' || e.type === 'checkbox') { if (e.checked) fields.push('[' + e.type + '] ' + e.name + '=' + e.value); return; }
    if (e.tagName === 'SELECT') { fields.push('[sel] ' + (e.name||e.id) + '=' + ((e.options[e.selectedIndex]||{}).text||'').trim() + ' | ' + Array.from(e.options).slice(0,10).map(o=>o.text.trim()).join('/')); }
    else fields.push('[txt] ' + (e.id||e.name) + "='" + (e.value||'').slice(0,50) + "'");
  });
  out.fields = fields;
  out.errors = Array.from(document.querySelectorAll('font[color=red], .error')).filter(x => x.offsetParent !== null && (x.innerText||'').trim()).map(x => (x.innerText||'').trim().slice(0,80)).slice(0,10);
  out.url = location.href.slice(0,120);
  return JSON.stringify(out);
})()
"""

async def main():
    async with CDP(f"CtmID={CTMID}") as c:
        res = json.loads(await c.js(DUMP) or "{}")
        print("STEP:", res.get("h1"))
        for f in res.get("fields", []):
            print(" ", f)
        if res.get("errors"):
            print("ERRORS:", res["errors"])
        if DO_NEXT:
            loc = await c.js("(() => { const b = document.querySelector('input[name=imgbtnNext]'); if (!b) return null; b.scrollIntoView({block:'center'}); const r = b.getBoundingClientRect(); return JSON.stringify({x: Math.round(r.x+r.width/2), y: Math.round(r.y+r.height/2)}); })()")
            if loc and loc.startswith("{"):
                loc = json.loads(loc)
                await c.click(loc["x"], loc["y"])
                await asyncio.sleep(4)
                res2 = json.loads(await c.js(DUMP) or "{}")
                print("=> NEXT STEP:", res2.get("h1"))
                if res2.get("errors"):
                    print("ERRORS:", res2["errors"])
                print("URL:", res2.get("url"))
            else:
                print("NO NEXT BUTTON (last step -> use imgbtnSubmit / privacy checkbox)")
        print("shot:", await c.shot(ART / f"{SHOT}.png"))

asyncio.run(main())
