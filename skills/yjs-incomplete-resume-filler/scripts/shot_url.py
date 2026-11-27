# -*- coding: utf-8 -*-
"""按 URL 子串附加标签并截图 / 打印标题文本。
Usage: PYTHONPATH="" python shot_url.py <url_sub> <png_path> [text]
"""
import asyncio
import sys

from cdp import CDP

async def main():
    url_sub, path = sys.argv[1], sys.argv[2]
    async with CDP(url_sub) as c:
        print("URL:", await c.js("location.href"))
        print("TITLE:", await c.js("document.title"))
        if len(sys.argv) > 3 and sys.argv[3] == "text":
            print("TEXT:", (await c.js("document.body.innerText.slice(0,1500)")) or "")
        else:
            print(await c.shot(path))

asyncio.run(main())
