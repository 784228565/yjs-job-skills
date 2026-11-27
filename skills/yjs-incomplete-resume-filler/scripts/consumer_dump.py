# -*- coding: utf-8 -*-
"""Dump consumer/pc/resume 新版模块化简历页结构。
Usage: PYTHONPATH="" python consumer_dump.py [text|fields|all]
"""
import asyncio
import json
import sys

from cdp import CDP

async def main():
    async with CDP("xyz.51job.com/consumer/pc/resume") as c:
        mode = sys.argv[1] if sys.argv[1:] else "all"
        print("URL:", await c.js("location.href"))
        print("TITLE:", await c.js("document.title"))
        if mode == "shot":
            print(await c.shot(sys.argv[2]))
            return
        if mode == "files":
            r = await c.send("DOM.getDocument")
            root = r["result"]["root"]["nodeId"]
            r = await c.send("DOM.querySelectorAll", {"nodeId": root, "selector": "input[type=file]"})
            for n in r["result"].get("nodeIds", []):
                d = await c.send("DOM.describeNode", {"nodeId": n})
                print(n, d["result"]["node"].get("attributes"))
            return
        if mode == "form":
            js = r'''(()=>{
              const vis=e=>{const cs=getComputedStyle(e),r=e.getBoundingClientRect();
                return cs.display!=='none'&&cs.visibility!=='hidden'&&r.width>0&&r.height>0;};
              return JSON.stringify([...document.querySelectorAll('.el-form-item')].filter(vis).map((e,i)=>{
                const lab=(e.querySelector('.el-form-item__label')||{}).innerText||'';
                const inp=[...e.querySelectorAll('input,textarea')].filter(vis).map(x=>({ph:x.placeholder||'',val:(x.value||'').slice(0,80),ro:x.readOnly}));
                const err=(e.querySelector('.el-form-item__error')||{}).innerText||'';
                return {i,lab:lab.trim(),req:e.classList.contains('is-required'),inp,err:err.trim(),txt:(e.innerText||'').trim().replace(/\s+/g,' ').slice(0,120)};
              }),null,1);})()'''
            print(await c.js(js))
            return
        if mode == "outline":
            js = r'''(()=>{
              const vis=e=>{const cs=getComputedStyle(e),r=e.getBoundingClientRect();
                return cs.display!=='none'&&r.width>0&&r.height>0;};
              return JSON.stringify([...document.querySelectorAll('[class*=resume],[class*=module],[class*=anchor]')]
                .filter(vis).map(e=>({tag:e.tagName,cls:(e.className||'').toString().slice(0,90),
                  txt:(e.innerText||'').trim().replace(/\s+/g,' ').slice(0,90)}))
                .filter(e=>e.txt).slice(0,120));})()'''
            raw = await c.js(js)
            try:
                for e in json.loads(raw):
                    print(f"{e['tag']:<6} {e['cls']:<90} {e['txt']!r}")
            except Exception:
                print(raw)
            return
        if mode == "dom":
            sel = sys.argv[2]
            r = await c.js(f'''(()=>{{const e=document.querySelector({json.dumps(sel)});
                if(!e)return "missing";return e.outerHTML.slice(0,6000);}})()''')
            print(r)
            return
        if mode in ("all", "text"):
            txt = await c.js("document.body.innerText.slice(0,6000)")
            print("=== TEXT ===\n" + (txt or ""))
        if mode in ("all", "fields"):
            js = r'''(()=>{
              const vis=e=>{const cs=getComputedStyle(e);const r=e.getBoundingClientRect();
                return cs.display!=='none'&&cs.visibility!=='hidden'&&r.width>0&&r.height>0;};
              const lab=e=>{let p=e;for(let i=0;i<5&&p;i++,p=p.parentElement){
                const t=(p.textContent||'').trim();if(t&&t.length<120)return t;}return '';};
              const f=[...document.querySelectorAll('input,select,textarea')].map((e,i)=>({
                i,tag:e.tagName,type:e.type||'',name:e.name||'',id:e.id||'',
                ph:e.placeholder||'',val:(e.value||'').slice(0,80),
                cls:(e.className||'').toString().slice(0,80),vis:vis(e),ctx:lab(e).slice(0,100)
              }));
              const b=[...document.querySelectorAll('button,a,div[class*=btn],span[class*=btn]')].filter(vis)
                .map(e=>({tag:e.tagName,cls:(e.className||'').toString().slice(0,60),txt:(e.innerText||'').trim().slice(0,50)}))
                .filter(e=>e.txt);
              return JSON.stringify({fields:f,buttons:b.slice(0,80)});
            })()'''
            raw = await c.js(js)
            try:
                d = json.loads(raw)
                print("=== FIELDS ===")
                for f in d["fields"]:
                    if mode == "fields" and not f["vis"]:
                        continue
                    print(f"{f['i']:>3} {f['tag']:<8} {f['type']:<8} vis={f['vis']} name={f['name']!r} id={f['id']!r} ph={f['ph']!r} val={f['val']!r} cls={f['cls']!r} ctx={f['ctx']!r}")
                print("=== BUTTONS ===")
                for b in d["buttons"]:
                    print(f"{b['tag']:<6} {b['cls']:<60} {b['txt']!r}")
            except Exception:
                print("RAW:", raw)

asyncio.run(main())
