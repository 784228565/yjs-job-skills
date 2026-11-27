# -*- coding: utf-8 -*-
"""FillInResume 末步提交：勾可见 checkbox（如有）-> 点 imgbtnSubmit -> 报告结果。
Usage: python submit_final.py <CtmID>
"""
import asyncio
import sys

from cdp import CDP


async def main():
    ctmid = sys.argv[1]
    async with CDP(f"CtmID={ctmid}") as c:
        # tick any visible unchecked checkbox (privacy statement etc.)
        boxes = await c.js('''(()=>{
          const bs=[...document.querySelectorAll("input[type=checkbox]")].filter(x=>x.offsetParent!==null && !x.checked);
          return bs.length;
        })()''')
        print("visible unchecked checkboxes:", boxes)
        if boxes:
            await c.js('''(()=>{
              [...document.querySelectorAll("input[type=checkbox]")].filter(x=>x.offsetParent!==null && !x.checked)
                .forEach(x=>{x.scrollIntoView({block:'center'}); const r=x.getBoundingClientRect();
                  const cx=Math.round(r.x+r.width/2), cy=Math.round(r.y+r.height/2);
                  for(const t of ['mouseover','mousedown','mouseup','click']){
                    x.dispatchEvent(new MouseEvent(t,{bubbles:true,cancelable:true,view:window,clientX:cx,clientY:cy}));
                  }});
              return "done";
            })()''')
            await asyncio.sleep(0.8)
            print("after tick:", await c.js('''JSON.stringify([...document.querySelectorAll("input[type=checkbox]")].filter(x=>x.offsetParent!==null).map(x=>x.checked))'''))
        ok = await c.click_el("input[name=imgbtnSubmit]", sleep_after=6)
        print("submit clicked:", ok)
        print("url:", await c.js("location.href.slice(0,120)"))
        print("title:", await c.js("document.title"))


asyncio.run(main())
