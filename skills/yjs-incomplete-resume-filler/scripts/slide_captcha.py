# -*- coding: utf-8 -*-
"""阿里云盾滑块验证（yingjiesheng 刷新时触发）。

Usage: PYTHONPATH="" python slide_captcha.py <url_sub>

策略：
  1. 定位 .aliyunCaptcha-sliding-slider 手柄与轨道宽度
  2. CDP.drag 拟真拖动（悬停→按压→抖动+回退→释放）
  3. 失败时页面提示 "Refresh to retry" -> 刷新页面；实测连续失败风控后刷新一次会自动放行
"""
import asyncio, json, sys

from cdp import CDP

LOCATE = r'''
(()=>{
  const s=document.querySelector(".slider-move") || document.querySelector(".aliyunCaptcha-sliding-slider");
  if(!s || !s.offsetParent) return null;
  const track=document.querySelector(".aliyun-captcha") || s.parentElement;
  const rs=s.getBoundingClientRect();
  return JSON.stringify({trackW:track.getBoundingClientRect().width, x:Math.round(rs.x+rs.width/2), y:Math.round(rs.y+rs.height/2), handleW:rs.width});
})()
'''

async def main():
    url_sub = sys.argv[1] if len(sys.argv) > 1 else "q.yingjiesheng.com"
    async with CDP(url_sub) as c:
        for attempt in range(3):
            info = await c.js(LOCATE)
            if not info:
                body = await c.js('document.body.innerText.slice(0,120)') or ""
                print("no slider;", body[:100])
                return
            info = json.loads(info)
            print(f"attempt {attempt+1}: handle=({info['x']},{info['y']}) dist={info['trackW']-info['handleW']-2}")
            await asyncio.sleep(1.5)  # read-and-think pause
            await c.drag(info["x"], info["y"], info["trackW"] - info["handleW"] - 2)
            await asyncio.sleep(4)
            body = await c.js('document.body.innerText.slice(0,200)') or ""
            if "slide to verify" not in body:
                print("PASSED")
                return
            if "Refresh to retry" in body or "failed" in body.lower():
                print("failed -> reload")
                await c.reload(wait=8)
        print("still blocked after 3 attempts; wait a few minutes or slide manually once")

asyncio.run(main())
