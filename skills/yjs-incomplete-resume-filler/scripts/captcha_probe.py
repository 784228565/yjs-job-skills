# -*- coding: utf-8 -*-
import asyncio, json, sys
from cdp import CDP

async def main():
    async with CDP(sys.argv[1] if sys.argv[1:] else "q.yingjiesheng.com") as c:
        js = r'''(()=>{
          const els=[...document.querySelectorAll('[class*=slider],[class*=captcha],[class*=verify]')];
          return JSON.stringify(els.map(e=>{const r=e.getBoundingClientRect();return {
            tag:e.tagName,cls:(e.className||'').toString().slice(0,90),
            x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height),
            text:(e.innerText||'').trim().slice(0,50),op:!!e.offsetParent};}).slice(0,40));})()'''
        print(await c.js(js))
        print("viewport:", await c.js("JSON.stringify({w:innerWidth,h:innerHeight,s:devicePixelRatio})"))
        print("frames:", await c.js("[...document.querySelectorAll('iframe')].map(f=>f.src).slice(0,10)"))

asyncio.run(main())
