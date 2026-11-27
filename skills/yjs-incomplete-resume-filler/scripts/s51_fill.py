# -*- coding: utf-8 -*-
"""旧版 FillInResume 字段填写工具。
Usage: PYTHONPATH="" python s51_fill.py <CtmID-sub> sel <name> <选项文本>
       PYTHONPATH="" python s51_fill.py <CtmID-sub> text <name> <文本>
       PYTHONPATH="" python s51_fill.py <CtmID-sub> hidden <name> <值>
       PYTHONPATH="" python s51_fill.py <CtmID-sub> domsel <name>       # 打印该字段祖先 HTML
"""
import asyncio, json, sys
from cdp import CDP

async def main():
    sub, cmd, name = sys.argv[1], sys.argv[2], sys.argv[3]
    async with CDP(sub) as c:
        if cmd == "sel":
            opt = sys.argv[4]
            expr = ('(()=>{const s=document.querySelector(' + json.dumps('[name="'+name+'"]') + ');'
                    'if(!s)return "missing";const o=[...s.options].find(x=>x.text.trim()===' + json.dumps(opt) + ');'
                    'if(!o)return "noopt";s.value=o.value;'
                    's.dispatchEvent(new Event("change",{bubbles:true}));'
                    'if(s.onchange)try{s.onchange();}catch(e){}'
                    'return s.options[s.selectedIndex].text.trim();})()')
            print("after:", await c.js(expr))
        elif cmd == "text":
            print("ok:", await c.type_text(f'[name="{name}"]', sys.argv[4]))
            print("readback:", await c.js(f'document.querySelector(\'[name="{name}"]\')?.value'))
        elif cmd == "js":
            print(await c.js(name))
        elif cmd == "get":
            print(await c.js(f'(()=>{{const e=document.querySelector(\'[name="{name}"]\');return e?e.value:"missing";}})()'))
        elif cmd == "hidden":
            print(await c.js(f'(()=>{{const e=document.querySelector(\'[name="{name}"]\');if(!e)return "missing";e.value={json.dumps(sys.argv[4])};return e.value;}})()'))
        elif cmd == "domsel":
            print(await c.js(f'(()=>{{const e=document.querySelector(\'[name="{name}"]\');if(!e)return "missing";return e.parentElement.parentElement.outerHTML.slice(0,4000);}})()'))
        elif cmd == "allsel":
            print(await c.js(f'''(()=>{{const s=document.querySelector('[name="{name}"]');if(!s)return "missing";
              return JSON.stringify([...s.options].map(o=>({{v:o.value,t:o.text.trim()}})).slice(0,80));}})()'''))

asyncio.run(main())
