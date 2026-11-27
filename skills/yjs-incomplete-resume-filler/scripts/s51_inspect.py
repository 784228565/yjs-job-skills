# -*- coding: utf-8 -*-
"""旧版 FillInResume 全字段检查（含隐藏项/文件上传/标签上下文）。
Usage: PYTHONPATH="" python s51_inspect.py [CtmID]
"""
import asyncio, json, sys
from cdp import CDP

JS = r'''(()=>{
  const vis=e=>{const cs=getComputedStyle(e),r=e.getBoundingClientRect();
    return cs.display!=='none'&&cs.visibility!=='hidden'&&r.width>0&&r.height>0;};
  const ctx=e=>{let p=e;for(let i=0;i<4&&p;i++,p=p.parentElement){const t=(p.innerText||'').trim();
    if(t&&t.length<150)return t.replace(/\s+/g,' ');}return '';};
  const arr=[...document.querySelectorAll('input,select,textarea')].map((e,i)=>({
    i,tag:e.tagName,type:e.type||'',name:e.name||'',id:e.id||'',
    val:(e.value||'').slice(0,80),vis:vis(e),ctx:ctx(e).slice(0,110),
    opts:e.tagName==='SELECT'?[...e.options].slice(0,12).map(o=>o.text.trim()):undefined
  }));
  const btns=[...document.querySelectorAll('input[type=image],input[type=submit],button,a')].filter(vis)
    .map(e=>({tag:e.tagName,type:e.type||'',name:e.name||'',id:e.id||'',val:e.value||'',txt:(e.innerText||'').trim().slice(0,40)}))
    .filter(e=>e.name||e.id||e.val||e.txt).slice(0,40);
  return JSON.stringify({arr,btns},null,1);
})()'''

async def main():
    sub = sys.argv[1] if sys.argv[1:] else "FillInResume.aspx"
    async with CDP(sub) as c:
        print(await c.js(JS))

asyncio.run(main())
