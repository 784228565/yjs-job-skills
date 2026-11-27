# -*- coding: utf-8 -*-
"""新版简历页 Element UI 下拉/autocomplete/普通输入填写（真实鼠标点击选项）。
Usage: PYTHONPATH="" python consumer_select.py select <标签> <选项精确文本>
       PYTHONPATH="" python consumer_select.py ac <标签> <搜索词> <选项精确文本>
       PYTHONPATH="" python consumer_select.py input <标签> <文本>
"""
import asyncio
import json
import sys

from cdp import CDP

VIS = r'''const vis=e=>{const cs=getComputedStyle(e),r=e.getBoundingClientRect();
  return cs.display!=='none'&&cs.visibility!=='hidden'&&r.width>0&&r.height>0;};'''

FIND = r'''(label) => {
  ''' + VIS + '''
  const item=[...document.querySelectorAll('.el-form-item')].find(e=>vis(e)&&
    ((e.querySelector('.el-form-item__label')||{}).innerText||'').trim()===label);
  if(!item)return JSON.stringify({err:'no item '+label});
  const inp=[...item.querySelectorAll('input,textarea')].find(vis);
  if(!inp)return JSON.stringify({err:'no input '+label});
  inp.id='tmp_field_input';
  inp.scrollIntoView({block:'center'});
  const r=inp.getBoundingClientRect();
  return JSON.stringify({x:Math.round(r.x+r.width/2),y:Math.round(r.y+r.height/2),val:inp.value});
}'''

FIND_OPTION = r'''(txt) => {
  ''' + VIS + '''
  const els=[...document.querySelectorAll('li,.el-select-dropdown__item,.el-autocomplete-suggestion li,[role=option]')]
    .filter(e=>vis(e)&&(e.innerText||'').trim()===txt);
  if(!els.length)return JSON.stringify({err:'no option '+txt,
    visible:[...document.querySelectorAll('li,[role=option]')].filter(vis).map(e=>(e.innerText||'').trim()).filter(Boolean).slice(0,30)});
  const e=els[els.length-1];
  e.scrollIntoView({block:'center'});
  const r=e.getBoundingClientRect();
  return JSON.stringify({x:Math.round(r.x+r.width/2),y:Math.round(r.y+r.height/2)});
}'''

async def click(c, d):
    x, y = d["x"], d["y"]
    await c.send("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y})
    await asyncio.sleep(0.2)
    await c.send("Input.dispatchMouseEvent", {"type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1})
    await asyncio.sleep(0.1)
    await c.send("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x + 2, "y": y + 1, "button": "left"})
    await asyncio.sleep(0.1)
    await c.send("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": x + 2, "y": y + 1, "button": "left", "clickCount": 1})

async def readback(c, label):
    raw = await c.js(f"({FIND})({json.dumps(label)})")
    try:
        return json.loads(raw).get("val")
    except Exception:
        return raw

async def main():
    cmd, label = sys.argv[1], sys.argv[2]
    async with CDP("xyz.51job.com/consumer/pc/resume") as c:
        raw = await c.js(f"({FIND})({json.dumps(label)})")
        d = json.loads(raw)
        print("field:", raw)
        if "err" in d:
            return
        await click(c, d)
        await asyncio.sleep(0.4)
        if cmd == "select":
            opt = sys.argv[3]
        elif cmd == "ac":
            query, opt = sys.argv[3], sys.argv[4]
            # select all + type query
            await c.send("Input.dispatchKeyEvent", {"type": "keyDown", "key": "Control", "code": "ControlLeft", "windowsVirtualKeyCode": 17})
            await c.send("Input.dispatchKeyEvent", {"type": "keyDown", "key": "a", "code": "KeyA", "windowsVirtualKeyCode": 65, "modifiers": 2})
            await c.send("Input.dispatchKeyEvent", {"type": "keyUp", "key": "a", "code": "KeyA", "windowsVirtualKeyCode": 65, "modifiers": 2})
            await c.send("Input.dispatchKeyEvent", {"type": "keyUp", "key": "Control", "code": "ControlLeft", "windowsVirtualKeyCode": 17})
            await c.send("Input.insertText", {"text": query})
            await asyncio.sleep(1.5)
        elif cmd == "input":
            text = sys.argv[3]
            await c.send("Input.dispatchKeyEvent", {"type": "keyDown", "key": "Control", "code": "ControlLeft", "windowsVirtualKeyCode": 17})
            await c.send("Input.dispatchKeyEvent", {"type": "keyDown", "key": "a", "code": "KeyA", "windowsVirtualKeyCode": 65, "modifiers": 2})
            await c.send("Input.dispatchKeyEvent", {"type": "keyUp", "key": "a", "code": "KeyA", "windowsVirtualKeyCode": 65, "modifiers": 2})
            await c.send("Input.dispatchKeyEvent", {"type": "keyUp", "key": "Control", "code": "ControlLeft", "windowsVirtualKeyCode": 17})
            await c.send("Input.insertText", {"text": text})
            await asyncio.sleep(0.6)
            print("readback:", await readback(c, label))
            return
        else:
            print("unknown cmd")
            return
        opt_raw = await c.js(f"({FIND_OPTION})({json.dumps(opt)})")
        print("option:", opt_raw)
        od = json.loads(opt_raw)
        if "err" in od:
            return
        await click(c, od)
        await asyncio.sleep(0.8)
        print("readback:", await readback(c, label))

asyncio.run(main())
