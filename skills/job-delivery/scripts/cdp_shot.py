# -*- coding: utf-8 -*-
"""CDP helper: screenshot a tab + dump visible form fields. Usage:
   python cdp_shot.py <tab_id> <out_png> [eval_js_file]
"""
import asyncio
import base64
import json
import sys

import websockets


async def main():
    tab_id, out_png = sys.argv[1], sys.argv[2]
    ws_url = f"ws://localhost:9222/devtools/page/{tab_id}"
    async with websockets.connect(ws_url, max_size=64 * 1024 * 1024) as ws:
        mid = [0]

        async def send(method, params=None):
            mid[0] += 1
            await ws.send(json.dumps({"id": mid[0], "method": method, "params": params or {}}))
            while True:
                msg = json.loads(await ws.recv())
                if msg.get("id") == mid[0]:
                    return msg

        r = await send("Page.captureScreenshot", {"format": "png"})
        with open(out_png, "wb") as f:
            f.write(base64.b64decode(r["result"]["data"]))
        print("shot saved", out_png)

        if len(sys.argv) > 3:
            js = open(sys.argv[3], encoding="utf-8").read()
            r = await send("Runtime.evaluate", {"expression": js, "returnByValue": True, "awaitPromise": True})
            val = r.get("result", {}).get("result", {}).get("value")
            print(json.dumps(val, ensure_ascii=False, indent=1))


asyncio.run(main())
