# -*- coding: utf-8 -*-
"""yingjiesheng 个人中心「待完善投递」列表工具。

Usage:
  PYTHONPATH="" python yjs_list.py                 # 点开 tab、dump 未完成列表（不刷新页面）
  PYTHONPATH="" python yjs_list.py click 0         # 点击第 i 条「完善简历」按钮（新标签打开 51job）
  PYTHONPATH="" python yjs_list.py --reload        # 强制刷新后取列表（可能触发滑块→先跑 slide_captcha.py）

注意：
  - 默认停在「投递反馈」tab，必须真实点击「待完善投递 (N)」(.tab-tabs-item) 才渲染 #incompleteList。
  - tab 点击要带轨迹（mouseMoved→press→微移→release），简单 press/release 会被 Vue 忽略。
  - 点击前要等 van-toast Loading 遮罩消失（fixed 定位，offsetParent 探测不到）。
  - 多标签时用 URL 前缀匹配会误中 51job 页（prp 参数带 yjs 地址）；本脚本自动选 IDLE 的 yjs 标签。
"""
import asyncio
import json
import sys
import time

import websockets

from cdp import CDP, list_tabs

YJS = "q.yingjiesheng.com/pc/personal"

LOADING_PROBE = '''(()=>{const t=[...document.querySelectorAll('.van-toast')].find(e=>{const cs=getComputedStyle(e);return cs.display!=='none'&&cs.visibility!=='hidden'&&cs.opacity!=='0'&&e.innerText.trim();});return t? 'LOADING' : 'IDLE';})()'''


async def _probe(tab, expr):
    async with websockets.connect(tab["webSocketDebuggerUrl"], max_size=50 * 1024 * 1024) as ws:
        await ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate",
                                  "params": {"expression": expr, "returnByValue": True}}))
        end = time.time() + 15
        while time.time() < end:
            msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=max(0.1, end - time.time())))
            if msg.get("id") == 1:
                return msg["result"]["result"].get("value")


async def pick_idle_tab():
    """选 IDLE 的 yjs 个人中心标签（避免卡 Loading 的旧标签）。"""
    tabs = [t for t in list_tabs()
            if t.get("type") == "page" and t.get("url", "").startswith("https://q.yingjiesheng.com/pc/personal")]
    if not tabs:
        return None
    idle = [t for t in tabs if (await _probe(t, LOADING_PROBE)) == "IDLE"]
    pool = idle or tabs
    return pool[-1]


async def wait_idle(c: CDP, timeout=30):
    """等 van-toast Loading 遮罩消失。"""
    for _ in range(timeout):
        n = await c.js(LOADING_PROBE)
        if n == "IDLE":
            return True
        await asyncio.sleep(1)
    return False


async def open_incomplete_list(c: CDP):
    body = await c.js("document.body.innerText.slice(0,200)") or ""
    if "slide to verify" in body:
        return "CAPTCHA"
    if not await wait_idle(c):
        return "STILL_LOADING"
    c0 = await c.js('''(()=>{
      const el=[...document.querySelectorAll(".tab-tabs-item")].find(e=>(e.textContent||"").includes("待完善投递"));
      if(!el) return null;
      el.scrollIntoView({block:"center"});
      const inner=[...el.querySelectorAll("*")].find(e=>e.children.length===0 && (e.textContent||"").includes("待完善")) || el;
      const r=inner.getBoundingClientRect();
      return JSON.stringify({x:Math.round(r.x+r.width/2), y:Math.round(r.y+r.height/2), t:el.textContent.trim()});
    })()''')
    if not c0:
        return "NO_TAB"
    c0 = json.loads(c0)
    print("tab:", c0["t"])
    # trajectory click (plain press/release may be ignored by Vue tab)
    x, y = c0["x"], c0["y"]
    await c.send("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y})
    await asyncio.sleep(0.3)
    await c.send("Input.dispatchMouseEvent", {"type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1})
    await asyncio.sleep(0.15)
    await c.send("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x + 2, "y": y, "button": "left"})
    await asyncio.sleep(0.15)
    await c.send("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": x + 2, "y": y, "button": "left", "clickCount": 1})
    # poll for list render (Vue may take a few seconds)
    for _ in range(10):
        await asyncio.sleep(1)
        has = await c.js("!!document.querySelector('#incompleteList')")
        rows = await c.js("document.querySelector('#incompleteList')? document.querySelector('#incompleteList').children.length : 0")
        if has and rows:
            break
    return "OK"


async def dump_list(c: CDP):
    r = await c.js('''(()=>{
      const box=document.querySelector("#incompleteList");
      if(!box) return JSON.stringify({err:"no #incompleteList"});
      return JSON.stringify([...box.children].map((r,i)=>{
        const b=[...r.querySelectorAll("button, span, a")].find(b=>(b.textContent||"").trim()==="完善简历" && b.offsetParent!==null);
        const rr=b? b.getBoundingClientRect():null;
        return {i, txt:(r.textContent||"").trim().replace(/\\s+/g," ").slice(0,120),
                btn: b? {x:Math.round(rr.x+rr.width/2), y:Math.round(rr.y+rr.height/2)}:null};
      }));
    })()''')
    print(r)
    return r


async def main():
    tab = await pick_idle_tab()
    if not tab:
        print("STATE: NO_TAB")
        return
    async with CDP(YJS, tab_id=tab["id"]) as c:
        if "--reload" in sys.argv:
            await c.reload(wait=6)
        state = await open_incomplete_list(c)
        if state != "OK":
            print("STATE:", state)
            return
        raw = await dump_list(c) or "[]"
        lst = json.loads(raw)
        if isinstance(lst, dict):
            print("LIST ERROR:", lst)
            return
        if sys.argv[1:2] == ["click"]:
            i = int(sys.argv[2])
            btn = next((r["btn"] for r in lst if r.get("i") == i and r.get("btn")), None)
            if not btn:
                print("no btn for index", i)
                return
            await c.click(btn["x"], btn["y"])
            await asyncio.sleep(5)
            for t in list_tabs():
                if t.get("type") == "page" and "51job" in t.get("url", ""):
                    print("NEW TAB:", t["url"][:140])


if __name__ == "__main__":
    asyncio.run(main())
