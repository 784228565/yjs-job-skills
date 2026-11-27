# -*- coding: utf-8 -*-
"""新版简历页字段填写/附件注入。
Usage: PYTHONPATH="" python consumer_fill.py date <标签> <YYYY-MM-DD>
       PYTHONPATH="" python consumer_fill.py attach <pdf绝对路径>
"""
import asyncio
import json
import sys

from cdp import CDP

FIND_LABEL_INPUT = r'''(label) => {
  const vis=e=>{const cs=getComputedStyle(e),r=e.getBoundingClientRect();
    return cs.display!=='none'&&cs.visibility!=='hidden'&&r.width>0&&r.height>0;};
  const item=[...document.querySelectorAll('.el-form-item')].find(e=>vis(e)&&
    ((e.querySelector('.el-form-item__label')||{}).innerText||'').trim()===label);
  if(!item)return JSON.stringify({err:'no item '+label});
  const inp=[...item.querySelectorAll('input,textarea')].find(vis);
  if(!inp)return JSON.stringify({err:'no input '+label});
  inp.id='tmp_target_input';
  inp.scrollIntoView({block:'center'});
  const r=inp.getBoundingClientRect();
  return JSON.stringify({x:Math.round(r.x+r.width/2),y:Math.round(r.y+r.height/2),val:inp.value});
}'''

async def main():
    cmd = sys.argv[1]
    async with CDP("xyz.51job.com/consumer/pc/resume") as c:
        if cmd == "date":
            raw = await c.js(f"({FIND_LABEL_INPUT})({json.dumps(sys.argv[2])})")
            print("field:", raw)
            d = json.loads(raw)
            if "err" in d:
                return
            x, y = d["x"], d["y"]
            # click + select all
            await c.click(x, y)
            await c.send("Input.dispatchKeyEvent", {"type": "keyDown", "key": "Control", "code": "ControlLeft", "windowsVirtualKeyCode": 17})
            await c.send("Input.dispatchKeyEvent", {"type": "keyDown", "key": "a", "code": "KeyA", "windowsVirtualKeyCode": 65, "modifiers": 2})
            await c.send("Input.dispatchKeyEvent", {"type": "keyUp", "key": "a", "code": "KeyA", "windowsVirtualKeyCode": 65, "modifiers": 2})
            await c.send("Input.dispatchKeyEvent", {"type": "keyUp", "key": "Control", "code": "ControlLeft", "windowsVirtualKeyCode": 17})
            await asyncio.sleep(0.2)
            # type full date char by char (Element UI date picker requires Enter to commit)
            for ch in sys.argv[3]:
                vk = ord(ch) if ch.isascii() else 0
                await c.send("Input.dispatchKeyEvent", {"type": "keyDown", "text": ch, "key": ch, "windowsVirtualKeyCode": vk})
                await c.send("Input.dispatchKeyEvent", {"type": "keyUp", "key": ch, "windowsVirtualKeyCode": vk})
                await asyncio.sleep(0.06)
            await c.send("Input.dispatchKeyEvent", {"type": "keyDown", "key": "Enter", "code": "Enter", "windowsVirtualKeyCode": 13})
            await c.send("Input.dispatchKeyEvent", {"type": "keyUp", "key": "Enter", "code": "Enter", "windowsVirtualKeyCode": 13})
            await asyncio.sleep(1)
            print("readback:", await c.js("document.querySelector('#tmp_target_input')?.value"))
        elif cmd == "attach":
            pdf = sys.argv[2]
            r = await c.send("DOM.getDocument")
            root = r["result"]["root"]["nodeId"]
            r = await c.send("DOM.querySelectorAll", {"nodeId": root, "selector": "input[type=file][name=attach]"})
            nodes = r["result"].get("nodeIds", [])
            if not nodes:
                print("no attach input")
                return
            await c.send("DOM.setFileInputFiles", {"nodeId": nodes[0], "files": [pdf]})
            await asyncio.sleep(3)
            print("readback:", await c.js(r'''(()=>{const f=document.querySelector('input[type=file][name=attach]');
              const box=[...document.querySelectorAll('.el-form-item')].find(e=>(e.querySelector('.el-form-item__label')||{}).innerText?.trim()==='上传简历附件');
              return JSON.stringify({files:f?.files?.length, txt:box?.innerText?.replace(/\s+/g,' ').slice(0,150)});})()'''))

asyncio.run(main())
