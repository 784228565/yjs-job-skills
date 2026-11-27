# -*- coding: utf-8 -*-
"""新开 yjs 个人中心标签并取待完善列表（用于当前标签卡死时）。
成功打印列表 JSON；失败打印状态（CAPTCHA/LOADING）。
"""
import asyncio
import json

from cdp import CDP, list_tabs

LOADING_PROBE = '''(()=>{const t=[...document.querySelectorAll('.van-toast')].find(e=>{const cs=getComputedStyle(e);return cs.display!=='none'&&cs.visibility!=='hidden'&&cs.opacity!=='0'&&e.innerText.trim();});return t? 'LOADING' : 'IDLE';})()'''


async def main():
    async with CDP("q.yingjiesheng.com") as c0:
        r = await c0.send("Target.createTarget", {"url": "https://q.yingjiesheng.com/pc/personal?tab=2"})
        tid = r["result"]["targetId"]
    await asyncio.sleep(9)
    tab = next(t for t in list_tabs() if t.get("id") == tid)
    async with CDP("x", tab_id=tab["id"]) as c:
        body = await c.js("document.body.innerText.slice(0,120)") or ""
        if "slide to verify" in body:
            print("STATE: CAPTCHA")
            return
        state = await c.js(LOADING_PROBE)
        if state == "LOADING":
            print("STATE: LOADING (new tab also blocked)")
            return
        # click tab with trajectory
        c0b = await c.js('''(()=>{
          const el=[...document.querySelectorAll(".tab-tabs-item")].find(e=>(e.textContent||"").includes("待完善投递"));
          if(!el) return null;
          el.scrollIntoView({block:"center"});
          const inner=[...el.querySelectorAll("*")].find(e=>e.children.length===0 && (e.textContent||"").includes("待完善")) || el;
          const r=inner.getBoundingClientRect();
          return JSON.stringify({x:Math.round(r.x+r.width/2), y:Math.round(r.y+r.height/2), t:el.textContent.trim()});
        })()''')
        if not c0b:
            print("STATE: NO_TAB")
            return
        c0b = json.loads(c0b)
        print("tab:", c0b["t"])
        x, y = c0b["x"], c0b["y"]
        await c.send("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y})
        await asyncio.sleep(0.3)
        await c.send("Input.dispatchMouseEvent", {"type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1})
        await asyncio.sleep(0.15)
        await c.send("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x + 2, "y": y, "button": "left"})
        await asyncio.sleep(0.15)
        await c.send("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": x + 2, "y": y, "button": "left", "clickCount": 1})
        for _ in range(10):
            await asyncio.sleep(1)
            rows = await c.js("document.querySelector('#incompleteList')? document.querySelector('#incompleteList').children.length : 0")
            if rows:
                break
        print("TABID:", tab["id"])
        print(await c.js('''(()=>{
          const box=document.querySelector("#incompleteList");
          if(!box) return JSON.stringify({err:"no #incompleteList"});
          return JSON.stringify([...box.children].map((r,i)=>{
            const b=[...r.querySelectorAll("button, span, a")].find(b=>(b.textContent||"").trim()==="完善简历" && b.offsetParent!==null);
            const rr=b? b.getBoundingClientRect():null;
            return {i, txt:(r.textContent||"").trim().replace(/\\s+/g," ").slice(0,120),
                    btn: b? {x:Math.round(rr.x+rr.width/2), y:Math.round(rr.y+rr.height/2)}:null};
          }));
        })()'''))


asyncio.run(main())
