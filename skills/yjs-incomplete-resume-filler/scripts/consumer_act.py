# -*- coding: utf-8 -*-
"""新版简历页通用操作：按模块/文本/选择器真实鼠标点击。
Usage (PYTHONPATH="" python consumer_act.py):
  module <模块标题关键字> <按钮文本>   例: module 基本信息 编辑 / module 教育经历 添加
  text <精确文本> [nth]               例: text 保存
  sel <CSS选择器> [nth]
  active                              列出当前可见模块/弹窗/表单控件
"""
import asyncio
import json
import sys

from cdp import CDP

COORD_JS = r'''(selector, keyword, btnText, nth) => {
  const vis=e=>{const cs=getComputedStyle(e),r=e.getBoundingClientRect();
    return cs.display!=='none'&&cs.visibility!=='hidden'&&r.width>0&&r.height>0;};
  let pool=[];
  if(selector==='module'){
    const mods=[...document.querySelectorAll('.resume-module')].filter(e=>vis(e)&&(e.innerText||'').trim().startsWith(keyword));
    if(!mods.length)return JSON.stringify({err:'no module '+keyword});
    pool=[...mods[0].querySelectorAll('.resume-module-header *')].filter(e=>vis(e)&&(e.innerText||'').trim()===btnText);
  }else if(selector==='text'){
    pool=[...document.querySelectorAll('button,a,span,div,li')].filter(e=>vis(e)&&(e.innerText||'').trim()===keyword);
  }else{
    pool=[...document.querySelectorAll(keyword)].filter(vis);
  }
  const e=pool[nth||0];
  if(!e)return JSON.stringify({err:'no target',count:pool.length});
  e.scrollIntoView({block:'center'});
  const r=e.getBoundingClientRect();
  return JSON.stringify({x:Math.round(r.x+r.width/2),y:Math.round(r.y+r.height/2),
    tag:e.tagName,txt:(e.innerText||'').trim().slice(0,60),count:pool.length});
}'''

async def main():
    cmd = sys.argv[1] if sys.argv[1:] else "active"
    async with CDP("xyz.51job.com/consumer/pc/resume") as c:
        if cmd == "active":
            js = r'''(()=>{
              const vis=e=>{const cs=getComputedStyle(e),r=e.getBoundingClientRect();
                return cs.display!=='none'&&cs.visibility!=='hidden'&&r.width>0&&r.height>0;};
              const mods=[...document.querySelectorAll('.resume-module')].filter(vis).map(e=>(e.innerText||'').trim().replace(/\s+/g,' ').slice(0,90));
              const dlg=[...document.querySelectorAll('[role=dialog],.el-dialog,.el-drawer')].filter(vis).map(e=>(e.innerText||'').trim().replace(/\s+/g,' ').slice(0,600));
              const fields=[...document.querySelectorAll('input,select,textarea')].filter(vis).map((e,i)=>({tag:e.tagName,type:e.type||'',name:e.name||'',ph:e.placeholder||'',val:(e.value||'').slice(0,60),cls:(e.className||'').toString().slice(0,60)}));
              return JSON.stringify({mods,dlg,fields},null,1);})()'''
            print(await c.js(js))
            return
        selector, keyword, btn, nth = "module", "", "", 0
        if cmd == "module":
            selector, keyword, btn = "module", sys.argv[2], sys.argv[3]
            if len(sys.argv) > 4: nth = int(sys.argv[4])
        elif cmd == "text":
            selector, keyword = "text", sys.argv[2]
            if len(sys.argv) > 3: nth = int(sys.argv[3])
        elif cmd == "sel":
            selector, keyword = "sel", sys.argv[2]
            if len(sys.argv) > 3: nth = int(sys.argv[3])
        raw = await c.js(f"({COORD_JS})({json.dumps(selector)},{json.dumps(keyword)},{json.dumps(btn)},{nth})")
        print("TARGET:", raw)
        d = json.loads(raw)
        if "err" in d:
            return
        # trajectory click
        x, y = d["x"], d["y"]
        await c.send("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y})
        await asyncio.sleep(0.25)
        await c.send("Input.dispatchMouseEvent", {"type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1})
        await asyncio.sleep(0.12)
        await c.send("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x + 2, "y": y + 1, "button": "left"})
        await asyncio.sleep(0.12)
        await c.send("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": x + 2, "y": y + 1, "button": "left", "clickCount": 1})
        await asyncio.sleep(1.5)

asyncio.run(main())
