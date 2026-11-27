# -*- coding: utf-8 -*-
"""Generic CDP (Chrome DevTools Protocol) helper for driving Chrome on localhost:9222.

Usage:
    from cdp import CDP
    c = CDP("q.yingjiesheng.com/pc/personal")   # attach to tab by URL substring
    print(c.js("location.href"))
    c.click_el("[name=btnOk]")                   # scrollIntoView + real mouse click
    c.type_text("[name=cc_CCA23_1_1]", "3.55/4") # click + Ctrl+A + insertText
    c.select_option("[name=cc_Gender_1_1]", "男") # set select value + change event
    c.shot("out.png")                            # screenshot -> file
    c.drag(x0, y0, dist)                         # human-like slider drag

Coordinate discipline (learned from real runs):
  - ALWAYS scrollIntoView({block:'center'}) BEFORE getBoundingClientRect; reverse order clicks stale coords.
  - Vue/Element pages re-render frequently: re-dump coords immediately before every click.
  - Real-mouse clicks (Input.dispatchMouseEvent) work everywhere; el-button on yjs ignores JS .click().
Run with PYTHONPATH="" prefix (WorkBuddy safe-delete shim workaround).
"""
import asyncio, base64, json, random, time, urllib.request

import websockets

PORT = 9222


def list_tabs():
    with urllib.request.urlopen(f"http://localhost:{PORT}/json/list", timeout=5) as r:
        return json.load(r)


def find_tab(url_sub):
    for t in list_tabs():
        if t.get("type") == "page" and url_sub in t.get("url", ""):
            return t
    return None


class CDP:
    def __init__(self, url_sub, bring_to_front=True, tab_id=None):
        if tab_id:
            self.tab = next((t for t in list_tabs() if t.get("id") == tab_id), None)
        else:
            self.tab = find_tab(url_sub)
        if not self.tab:
            raise RuntimeError(f"TAB NOT FOUND: {tab_id or url_sub}")
        self.url_sub = url_sub
        self._mid = 0
        self._ws = None
        self._bring = bring_to_front

    async def __aenter__(self):
        self._ws = await websockets.connect(
            self.tab["webSocketDebuggerUrl"], max_size=50 * 1024 * 1024)
        await self.send("Page.enable")
        await self.send("Runtime.enable")
        if self._bring:
            await self.send("Page.bringToFront")
        return self

    async def __aexit__(self, *exc):
        await self._ws.close()

    async def send(self, method, params=None, timeout=30):
        self._mid += 1
        mid = self._mid
        await self._ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
        end = time.time() + timeout
        while time.time() < end:
            try:
                msg = json.loads(await asyncio.wait_for(self._ws.recv(), timeout=max(0.1, end - time.time())))
            except asyncio.TimeoutError:
                break
            if msg.get("id") == mid:
                return msg
        return None

    async def js(self, expr, timeout=30):
        """Evaluate JS; returns value or 'EXC:...' string on exception."""
        r = await self.send("Runtime.evaluate",
                            {"expression": expr, "returnByValue": True, "awaitPromise": True}, timeout)
        if not r:
            return None
        res = r.get("result", {})
        if "exceptionDetails" in res:
            return "EXC:" + json.dumps(res["exceptionDetails"])[:300]
        return res.get("result", {}).get("value")

    async def click(self, x, y):
        for typ in ("mousePressed", "mouseReleased"):
            await self.send("Input.dispatchMouseEvent",
                            {"type": typ, "x": x, "y": y, "button": "left", "clickCount": 1})
            await asyncio.sleep(0.08)

    async def click_el(self, sel, sleep_after=0.5):
        """scrollIntoView -> fresh coords -> real mouse click. Returns True if found."""
        c = await self.js(f'''(()=>{{const e=document.querySelector("{sel}");if(!e||!e.offsetParent)return null;
            e.scrollIntoView({{block:"center"}});const r=e.getBoundingClientRect();
            return JSON.stringify({{x:Math.round(r.x+r.width/2),y:Math.round(r.y+r.height/2)}});}})()''')
        if not c or not isinstance(c, str):
            return False
        c = json.loads(c)
        await self.click(c["x"], c["y"])
        await asyncio.sleep(sleep_after)
        return True

    async def type_text(self, sel, text):
        """Click field, select-all, insertText. Works for plain inputs (ASP.NET pages)."""
        ok = await self.click_el(sel, sleep_after=0.3)
        if not ok:
            return False
        await self.send("Input.dispatchKeyEvent", {"type": "keyDown", "key": "Control", "code": "ControlLeft", "windowsVirtualKeyCode": 17})
        await self.send("Input.dispatchKeyEvent", {"type": "keyDown", "key": "a", "code": "KeyA", "windowsVirtualKeyCode": 65, "modifiers": 2})
        await self.send("Input.dispatchKeyEvent", {"type": "keyUp", "key": "a", "code": "KeyA", "windowsVirtualKeyCode": 65, "modifiers": 2})
        await self.send("Input.dispatchKeyEvent", {"type": "keyUp", "key": "Control", "code": "ControlLeft", "windowsVirtualKeyCode": 17})
        await self.send("Input.insertText", {"text": text})
        await asyncio.sleep(0.3)
        return True

    async def key_chars(self, sel, text):
        """Per-character keyDown/keyUp typing; use for readonly/date fields that reject insertText."""
        ok = await self.click_el(sel, sleep_after=0.4)
        if not ok:
            return False
        for ch in text:
            vk = ord(ch.upper()) if ch.isascii() else 0
            await self.send("Input.dispatchKeyEvent", {"type": "keyDown", "text": ch, "key": ch, "windowsVirtualKeyCode": vk})
            await self.send("Input.dispatchKeyEvent", {"type": "keyUp", "key": ch, "windowsVirtualKeyCode": vk})
            await asyncio.sleep(0.05)
        return True

    async def select_option(self, sel, option_text):
        """Set <select> to exact option text + dispatch change (triggers onchange handlers)."""
        expr = f'''(()=>{{const s=document.querySelector("{sel}");if(!s)return "missing:{sel}";
            const opt=[...s.options].find(o=>o.text==="{option_text}");
            if(!opt)return "noopt:{option_text}";
            s.value=opt.value;s.dispatchEvent(new Event("change",{{bubbles:true}}));
            return s.options[s.selectedIndex].text;}})()'''
        return await self.js(expr)

    async def shot(self, path):
        r = await self.send("Page.captureScreenshot", {"format": "png"}, timeout=20)
        if r and "result" in r:
            from pathlib import Path
            Path(path).write_bytes(base64.b64decode(r["result"]["data"]))
            return str(path)
        return None

    async def reload(self, wait=5):
        await self.send("Page.reload")
        await asyncio.sleep(wait)

    async def drag(self, x0, y0, dist, duration=3.0):
        """Human-like slider drag with approach hover, jitter, backtrack near the end."""
        for _ in range(6):
            await self.send("Input.dispatchMouseEvent", {"type": "mouseMoved",
                            "x": x0 + random.uniform(-60, 60), "y": y0 + random.uniform(-40, 40)})
            await asyncio.sleep(random.uniform(0.03, 0.09))
        await self.send("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x0, "y": y0})
        await asyncio.sleep(random.uniform(0.2, 0.5))
        await self.send("Input.dispatchMouseEvent", {"type": "mousePressed", "x": x0, "y": y0, "button": "left", "clickCount": 1})
        await asyncio.sleep(random.uniform(0.1, 0.3))
        pos, t0 = 0, time.time()
        while pos < dist and time.time() - t0 < duration:
            pos = min(pos + random.randint(1, 6), dist)
            if dist - pos < 15 and random.random() < 0.4:
                pos = max(pos - random.randint(1, 4), 0)
            await self.send("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x0 + pos,
                            "y": y0 + random.uniform(-2, 2), "button": "left"})
            await asyncio.sleep(random.uniform(0.02, 0.08))
        await asyncio.sleep(random.uniform(0.15, 0.4))
        await self.send("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": x0 + dist, "y": y0, "button": "left", "clickCount": 1})
