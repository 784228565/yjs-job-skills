# -*- coding: utf-8 -*-
"""51job 附件上传（FillInResume / consumer 简历页的 UpLoad.aspx iframe 组件）。

两类场景：
  A. 新版 consumer/pc/resume 页：页面有原生 input[type=file]（photo/attach），直接注入即可。
  B. 旧版 FillInResume：上传入口在 same-origin iframe (xyz.51job.com/CommPage/Pages/UpLoad.aspx) 内，
     需要 DOM 穿透 contentDocument -> input#txtUpLoad -> setFileInputFiles -> 再点 iframe 内「上传」submit。

Usage: PYTHONPATH="" python upload_iframe.py <CtmID-or-url-sub> <pdf_path>

成功标志：iframe 内出现文件名 + 「查看」链接。
"""
import asyncio, json, sys

from cdp import CDP

UPLOAD_IFRAME = r'''
(()=>{
  const ifr=[...document.querySelectorAll("iframe")].find(f=>(f.src||"").includes("UpLoad.aspx"));
  if(!ifr) return null;
  const doc=ifr.contentDocument;
  const f=doc.querySelector("input[type=file]");
  const fr=ifr.getBoundingClientRect();
  const btn=[...doc.querySelectorAll("input[type=submit]")].find(b=>(b.value||"").includes("上传") && b.offsetParent!==null);
  const br=btn? btn.getBoundingClientRect():null;
  return JSON.stringify({
    hasFile: !!f, fileId: f? f.id : null,
    btn: br? {x:Math.round(fr.x+br.x+br.width/2), y:Math.round(fr.y+br.y+br.height/2)} : null,
    txt: doc.body.innerText.replace(/\s+/g," ").slice(0,80)
  });
})()
'''

PENETRATE = """
DOM.describeNode with depth=-1 on the UpLoad.aspx iframe node returns contentDocument;
querySelectorAll('input[type=file]') inside it -> DOM.setFileInputFiles on that nodeId.
"""

async def main():
    url_sub, pdf = sys.argv[1], sys.argv[2]
    async with CDP(url_sub) as c:
        # A: native file input on the page itself
        r = await c.send("DOM.getDocument")
        root = r["result"]["root"]["nodeId"]
        r = await c.send("DOM.querySelectorAll", {"nodeId": root, "selector": "input[type=file]"})
        nodes = r["result"]["nodeIds"]
        if nodes:
            for n in nodes:
                d = await c.send("DOM.describeNode", {"nodeId": n})
                attrs = d["result"]["node"].get("attributes", [])
                name = attrs[attrs.index("name") + 1] if "name" in attrs else str(n)
                print("native file input:", name)
            await c.send("DOM.setFileInputFiles", {"nodeId": nodes[0], "files": [pdf]})
            await asyncio.sleep(2)
            print("attached (native). readback:",
                  await c.js('(()=>{const f=document.querySelector("input[type=file]");const m=document.body.innerText.match(/[^\\s\\n]*\\.pdf[^\\s\\n]*/g);return JSON.stringify({files:f?f.files.length:-1, pdf:m});})()'))
            return

        # B: iframe upload component
        info = json.loads(await c.js(UPLOAD_IFRAME) or "{}")
        print("iframe info:", info)
        if not info.get("hasFile"):
            print("no UpLoad.aspx iframe found on page")
            return
        r = await c.send("DOM.querySelectorAll", {"nodeId": root, "selector": "iframe"})
        for n in r["result"]["nodeIds"]:
            d = await c.send("DOM.describeNode", {"nodeId": n})
            attrs = d["result"]["node"].get("attributes", [])
            src = attrs[attrs.index("src") + 1] if "src" in attrs else ""
            if "UpLoad.aspx" not in src:
                continue
            d2 = await c.send("DOM.describeNode", {"nodeId": n, "depth": -1})
            cd = d2["result"]["node"].get("contentDocument")
            r2 = await c.send("DOM.querySelectorAll", {"nodeId": cd["nodeId"], "selector": "input[type=file]"})
            for fn in r2["result"]["nodeIds"]:
                await c.send("DOM.setFileInputFiles", {"nodeId": fn, "files": [pdf]})
                print("file injected into iframe")
            await asyncio.sleep(1)
            if info.get("btn"):
                await c.click(info["btn"]["x"], info["btn"]["y"])
                await asyncio.sleep(4)
            print("readback:", await c.js(UPLOAD_IFRAME))
            return
        print("iframe walk failed")

asyncio.run(main())
