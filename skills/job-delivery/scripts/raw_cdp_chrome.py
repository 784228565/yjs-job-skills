"""Raw CDP Chrome client - WebSocket direct connection to a Chrome tab.

Reuses the user's Chrome profile (login session preserved). By default it does
NOT kill Chrome; with auto_start=True it will launch Chrome in debug mode if no
debug port is reachable.
"""

import asyncio
import base64
import json
import logging
import mimetypes
import re
import subprocess
import time
from pathlib import Path

logger = logging.getLogger(__name__)

# Pull defaults from central config (falls back to literals if unavailable).
try:
    import config as _cfg
    _DEFAULT_PORT = _cfg.DEBUG_PORT
    _DEFAULT_CHROME = _cfg.CHROME_PATH
    _DEFAULT_PROFILE = str(_cfg.WORK_AGENT_DIR)  # placeholder; real profile below
    try:
        import os
        _DEFAULT_PROFILE = os.path.join(
            os.environ.get("LOCALAPPDATA", ""), "Google", "Chrome", "User Data")
    except Exception:
        _DEFAULT_PROFILE = None
except Exception:  # pragma: no cover - config is optional at import time
    _DEFAULT_PORT = 9222
    _DEFAULT_CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    import os
    _DEFAULT_PROFILE = os.path.join(
        os.environ.get("LOCALAPPDATA", ""), "Google", "Chrome", "User Data")

# Match CDP/timeout failures. Bare alphabetic tokens use word boundaries so an
# embedded substring like "abcdp" does not trigger a downgrade. (A URL path
# segment such as "/cdp/" still matches "cdp"; that conservative over-match is
# acceptable since the fallback is an idempotent reconnect.)
_WORD_TOKENS = ("TimeoutError", "CDP", "cdp", "timeout", "Timeout")
_PHRASE_TOKENS = (
    "Protocol error", "Connection closed", "Target closed", "Session closed",
    "Command timed out", "waiting for target",
)
_CDP_REGEX = re.compile(
    "|".join(r"\b" + re.escape(t) + r"\b" for t in _WORD_TOKENS) +
    "|" + "|".join(re.escape(p) for p in _PHRASE_TOKENS)
)


def is_cdp_timeout_error(exc):
    combined = type(exc).__name__ + ": " + str(exc)
    return bool(_CDP_REGEX.search(combined))


class RawCDPChrome:
    def __init__(self, debug_port=_DEFAULT_PORT, auto_start=False,
                 chrome_path=_DEFAULT_CHROME, user_data_dir=_DEFAULT_PROFILE,
                 headless=False):
        self.debug_port = debug_port
        self.auto_start = auto_start
        self.chrome_path = chrome_path
        self.user_data_dir = user_data_dir
        self.headless = headless
        self._ws = None
        self._msg_id = 0
        self._current_url = ""
        self._target_id = None
        self._loop = None
        self._connected = False

    # === connection ===

    def connect(self, target_url=None, new_tab=True):
        """Connect synchronously. Safe to call from non-async code.

        new_tab=True (default) opens a fresh tab for this session so we never
        hijack whatever page the user currently has open. Set new_tab=False to
        attach to the current tab instead.
        """
        if self._connected:
            return self
        if self._in_running_loop():
            raise RuntimeError(
                "RawCDPChrome.connect() cannot run inside an active event loop. "
                "Use: await cdp._async_connect(target_url, new_tab)")
        self._loop = asyncio.new_event_loop()
        try:
            self._loop.run_until_complete(self._async_connect(target_url, new_tab))
        except (ConnectionError, OSError) as first_err:
            # NOTE: aiohttp raises ClientConnectorError (an OSError subclass,
            # NOT builtin ConnectionError) when the port is closed -- catch both
            # and normalize to builtin ConnectionError for callers.
            if not self.auto_start:
                raise ConnectionError(
                    "Cannot reach Chrome debug port " + str(self.debug_port)
                    + ". Start Chrome in debug mode first "
                    "(scripts/start_chrome_debug.bat).") from first_err
            if self._chrome_running():
                # A running Chrome silently IGNORES --remote-debugging-port, so
                # launching another chrome.exe would not open the port. Fail
                # loudly with an actionable message instead of a silent no-op.
                raise ConnectionError(
                    "Chrome is already running WITHOUT the debug port; a new "
                    "launch would be merged into the existing process and the "
                    "port would stay closed. Ask the user to fully close Chrome "
                    "(including system-tray/background mode) and run "
                    "scripts/start_chrome_debug.bat, then retry. Do NOT kill "
                    "the user's Chrome processes yourself.") from first_err
            logger.info("Debug port %s unreachable; auto-starting Chrome.",
                        self.debug_port)
            self._start_chrome()
            try:
                self._loop.run_until_complete(
                    self._async_connect(target_url, new_tab))
            except (ConnectionError, OSError) as second_err:
                raise ConnectionError(
                    "Chrome debug port " + str(self.debug_port)
                    + " still unreachable after auto-start.") from second_err
        self._connected = True
        return self

    @staticmethod
    def _chrome_running():
        """True if any chrome.exe process is alive (Windows)."""
        try:
            out = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq chrome.exe", "/NH"],
                capture_output=True, text=True, timeout=10)
            return "chrome.exe" in out.stdout
        except Exception:
            return False  # can't tell -> assume not running

    @staticmethod
    def _in_running_loop():
        try:
            asyncio.get_running_loop()
            return True
        except RuntimeError:
            return False

    def _start_chrome(self):
        """Launch Chrome with the debug port using the user's profile.

        Two hard requirements (verified on this machine):
        - --disable-gpu --disable-gpu-compositing: without them
          Page.captureScreenshot hangs on every page in headed mode.
        - Chrome >= 136 ignores --remote-debugging-port on the DEFAULT
          user-data-dir, so we launch with a directory JUNCTION path to the
          same profile (config.ensure_cdp_profile_junction).
        Only call this when no Chrome is running; an existing Chrome process
        would ignore the debug flag.
        """
        profile = self.user_data_dir
        try:
            import config as _c
            # Route the default profile through the junction (same files,
            # non-default path -> debug port works on Chrome >= 136).
            if not profile or os.path.normpath(profile) == os.path.normpath(
                    str(_c.CHROME_PROFILE_DIR)):
                profile = _c.ensure_cdp_profile_junction()
        except Exception as e:
            logger.warning("CDP profile junction unavailable (%s); "
                           "falling back to the given user_data_dir.", e)
        args = [self.chrome_path,
                "--remote-debugging-port=" + str(self.debug_port),
                "--disable-gpu", "--disable-gpu-compositing"]
        if profile:
            args.append("--user-data-dir=" + profile)
        if self.headless:
            args.append("--headless=new")
        subprocess.Popen(args)
        time.sleep(4)  # give Chrome a moment to open the debug port

    async def _async_connect(self, target_url=None, new_tab=True):
        import websockets
        import aiohttp
        base = "http://127.0.0.1:" + str(self.debug_port)
        async with aiohttp.ClientSession() as s:
            async with s.get(base + "/json") as resp:
                if resp.status != 200:
                    raise ConnectionError(
                        "Cannot reach Chrome debug port " + str(self.debug_port))
                targets = await resp.json()
        pages = [t for t in targets if t.get("type") == "page"]
        if new_tab or not pages:
            async with aiohttp.ClientSession() as s:
                async with s.put(base + "/json/new?about:blank") as r:
                    t = await r.json()
        else:
            t = pages[0]
        self._target_id = t["id"]
        self._ws = await websockets.connect(
            t["webSocketDebuggerUrl"], max_size=2**24, ping_interval=30)
        await self._send("Page.enable")
        await self._send("Runtime.enable")
        await self._send("Network.enable")
        if target_url:
            await self._navigate(target_url)
        else:
            r = await self._send("Runtime.evaluate",
                                 {"expression": "location.href"})
            self._current_url = r.get("result", {}).get("value", "")

    async def _send(self, method, params=None):
        self._msg_id += 1
        msg = {"id": self._msg_id, "method": method}
        if params:
            msg["params"] = params
        await self._ws.send(json.dumps(msg))
        # Read responses until we get the matching id (events are skipped).
        deadline = time.time() + 45
        while time.time() < deadline:
            raw = await asyncio.wait_for(self._ws.recv(),
                                         timeout=min(30, deadline - time.time()))
            data = json.loads(raw)
            if data.get("id") == self._msg_id:
                if "error" in data:
                    raise RuntimeError("CDP error: " +
                        data["error"].get("message", str(data["error"])))
                return data.get("result", {})
            # else: an event or a response for another id -> ignore
        raise TimeoutError("CDP command " + method + " timed out")

    async def _navigate(self, url):
        # window.location.href avoids some Page.navigate wrapper issues.
        await self._send("Runtime.evaluate", {
            "expression": "window.location.href=" + json.dumps(url),
            "userGesture": True,
        })
        deadline = time.time() + 15
        while time.time() < deadline:
            r = await self._send("Runtime.evaluate",
                                 {"expression": "document.readyState"})
            if r.get("result", {}).get("value") == "complete":
                break
            await asyncio.sleep(0.5)
        else:
            raise TimeoutError("Page load timeout")
        self._current_url = url

    def navigate(self, url):
        self._loop.run_until_complete(self._navigate(url))
        return self

    # === element interaction ===

    async def _query_selector(self, css):
        doc = await self._send("DOM.getDocument", {"depth": -1})
        nid = doc.get("root", {}).get("nodeId")
        if not nid:
            return None
        try:
            qr = await self._send("DOM.querySelector",
                                  {"nodeId": nid, "selector": css})
            return qr.get("nodeId")
        except RuntimeError:
            return None

    def fill(self, selector, value):
        self._loop.run_until_complete(self._fill(selector, value))
        return self

    async def _fill(self, selector, value):
        nid = await self._query_selector(selector)
        if not nid:
            raise RuntimeError("Element not found: " + selector)
        s = json.dumps(selector)
        await self._send("Runtime.evaluate", {
            "expression": ("(function(){var e=document.querySelector(" + s + ");"
                           "if(!e)return'NF';e.focus();e.value='';return'OK';})()"),
            "userGesture": True,
        })
        await asyncio.sleep(0.1)
        await self._send("Input.insertText", {"text": str(value)})
        await asyncio.sleep(0.05)
        await self._send("Runtime.evaluate", {
            "expression": ("(function(){var e=document.querySelector(" + s + ");"
                           "if(!e)return'NF';"
                           "e.dispatchEvent(new Event('input',{bubbles:true}));"
                           "e.dispatchEvent(new Event('change',{bubbles:true}));"
                           "return'OK';})()"),
            "userGesture": True,
        })

    def click_element(self, selector):
        self._loop.run_until_complete(self._click_element(selector))
        return self

    async def _click_element(self, selector):
        # Try CSS selector first; fall back to textContent search for buttons.
        s = json.dumps(selector)
        coords_expr = (
            "(function(){"
            "var e=document.querySelector(" + s + ");"
            "if(!e){e=Array.from(document.querySelectorAll('button,a,span,div'))"
            ".find(function(el){return el.textContent&&el.textContent.includes(" + s + ")});}"
            "if(!e)return JSON.stringify({err:'not found'});"
            "var r=e.getBoundingClientRect();"
            "return JSON.stringify({"
            "x:Math.round(r.left+r.width/2),"
            "y:Math.round(r.top+r.height/2),"
            "tag:e.tagName,text:(e.textContent||'').trim().slice(0,40)"
            "});})()"
        )
        r = await self._send("Runtime.evaluate", {
            "expression": coords_expr,
            "returnByValue": True,
            "userGesture": True,
        })
        val = r.get("result", {}).get("value", "")
        if not val or '"err":"not found"' in str(val):
            raise RuntimeError("Element not found: " + selector)
        pos = json.loads(val)
        x, y = pos["x"], pos["y"]
        await self._send("Input.dispatchMouseEvent", {
            "type": "mousePressed", "x": x, "y": y,
            "button": "left", "clickCount": 1,
        })
        await asyncio.sleep(0.05)
        await self._send("Input.dispatchMouseEvent", {
            "type": "mouseReleased", "x": x, "y": y,
            "button": "left", "clickCount": 1,
        })

    def upload_file(self, selector, file_path):
        self._loop.run_until_complete(self._upload_file(selector, file_path))
        return self

    async def _upload_file(self, selector, file_path):
        """Upload via base64+fetch+DataTransfer.

        Infers MIME type from the file extension. For large files (>8MB) the
        base64 payload can exceed the WebSocket frame limit, so we fail loudly
        with guidance rather than corrupting the upload.
        """
        fp = Path(file_path).resolve()
        if not fp.exists():
            raise FileNotFoundError("File not found: " + str(fp))
        data = fp.read_bytes()
        if len(data) > 8 * 1024 * 1024:
            raise ValueError(
                f"File too large for base64 upload ({len(data)} bytes): {fp}. "
                "Use a smaller file or DOM.setFileInputFiles.")
        mime = mimetypes.guess_type(str(fp))[0] or "application/octet-stream"
        b64 = base64.b64encode(data).decode()
        fname = fp.name
        s = json.dumps(selector)
        expr = (
            "fetch('data:" + mime + ";base64," + b64 + "')"
            ".then(function(r){return r.blob()})"
            ".then(function(b){"
            "var f=new File([b]," + json.dumps(fname) + ",{type:" + json.dumps(mime) + "});"
            "var dt=new DataTransfer();dt.items.add(f);"
            "var inp=document.querySelector(" + s + ");"
            "if(!inp)return'NOT_FOUND';"
            "Object.defineProperty(inp,'files',{value:dt.files,writable:false});"
            "inp.dispatchEvent(new Event('change',{bubbles:true}));"
            "return f.name})"
        )
        r = await self._send("Runtime.evaluate", {
            "expression": expr,
            "awaitPromise": True,
            "returnByValue": True,
            "userGesture": True,
        })
        result = r.get("result", {}).get("value", "")
        if result == "NOT_FOUND":
            raise RuntimeError("Upload element not found: " + selector)
        logger.info("Uploaded %s (%s) to %s: %s", fname, mime, selector, result)

    def click_checkbox(self, selector):
        """Click a checkbox (triggers Vue v-model via .click())."""
        self._loop.run_until_complete(self._click_checkbox(selector))
        return self

    async def _click_checkbox(self, selector):
        s = json.dumps(selector)
        await self._send("Runtime.evaluate", {
            "expression": (
                "(function(){var cb=document.querySelector(" + s + ");"
                "if(!cb)return'NOT_FOUND';if(!cb.checked)cb.click();"
                "return'OK'})()"
            ),
            "userGesture": True,
        })

    def save_screenshot(self, path):
        return self._loop.run_until_complete(self._save_screenshot(path))

    async def _save_screenshot(self, path):
        r = await self._send("Page.captureScreenshot", {"format": "png"})
        data = base64.b64decode(r.get("data", ""))
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(data)
        return str(out)

    def evaluate(self, expression):
        return self._loop.run_until_complete(self._evaluate(expression))

    async def _evaluate(self, expression):
        r = await self._send("Runtime.evaluate",
                             {"expression": expression, "returnByValue": True})
        return r.get("result", {}).get("value")

    # === teardown ===

    def disconnect(self):
        """Close the WebSocket and event loop. Chrome is left running."""
        try:
            if self._ws and self._loop and not self._loop.is_closed():
                self._loop.run_until_complete(self._ws.close())
        except Exception as e:
            logger.debug("Error closing websocket: %s", e)
        finally:
            self._ws = None
            if self._loop and not self._loop.is_closed():
                try:
                    self._loop.close()
                except Exception:
                    pass
            self._loop = None
            self._connected = False
            logger.info("RawCDPChrome disconnected (Chrome left running)")

    def __del__(self):
        try:
            self.disconnect()
        except Exception:
            pass
