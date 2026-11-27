"""browser-use integration: AI-powered web form filling (tier-3 fallback).

Uses browser-use's Agent with LLM vision to understand and fill web forms
without explicit CSS selectors. Used when both browser-client and RawCDPChrome
fail.

Both a sync entry (fill_form_with_browser_use) and an async entry
(afill_form_with_browser_use) are provided so callers already inside an event
loop don't crash on asyncio.run().

Paths and identity come from config.py / candidate_profile.json, not hardcoded.

Example:
    from browser_use_form_fill import fill_form_with_browser_use
    result = fill_form_with_browser_use(
        url="https://example.com/apply",
        form_data={"name": "...", "email": "..."},
    )
"""

import asyncio
import logging
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config  # noqa: E402

logger = logging.getLogger(__name__)

RESUME_PATH = config.RESUME_PATH
SCREENSHOT_DIR = config.ensure_dirs()


def _screenshot_path(url: str) -> str:
    """Build a collision-resistant screenshot filename from a URL.

    Uses host + sanitized path; falls back to 'page' when the path is empty
    (e.g. URLs ending in '/' or with only query strings).
    """
    parsed = urlparse(url)
    stem = Path(parsed.path).stem or "page"
    stem = re.sub(r"[^A-Za-z0-9_-]+", "_", stem)[:40] or "page"
    host = re.sub(r"[^A-Za-z0-9_-]+", "_", parsed.netloc)[:30] or "site"
    ts = time.strftime("%H%M%S")
    return str(SCREENSHOT_DIR / f"browser_use_{host}_{stem}_{ts}.png")


def fill_form_with_browser_use(
    url: str,
    form_data: dict,
    resume_path: str = None,
    task_hint: str = "",
    headless: bool = False,
    auto_submit: bool = False,
) -> dict:
    """Sync wrapper. Do NOT call from inside a running event loop."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(
            afill_form_with_browser_use(
                url, form_data, resume_path, task_hint, headless, auto_submit))
    raise RuntimeError(
        "fill_form_with_browser_use() cannot run inside an active event loop. "
        "Use: await afill_form_with_browser_use(...)")


async def afill_form_with_browser_use(
    url: str,
    form_data: dict,
    resume_path: str = None,
    task_hint: str = "",
    headless: bool = False,
    auto_submit: bool = False,
) -> dict:
    """Use a browser-use Agent to fill a web form.

    Args:
        url: The form page URL.
        form_data: Dict of field_name -> value.
        resume_path: Path to resume file for upload fields.
        task_hint: Extra instructions, e.g. "also upload resume".
        headless: Run the browser headless.
        auto_submit: If True, allow the agent to submit the form; otherwise it
            fills and screenshots only (caller reviews then submits).

    Returns:
        {"success": bool, "error": str|None, "screenshot": str|None, ...}
    """
    try:
        from browser_use import Agent, Browser
    except ImportError:
        return {"success": False,
                "error": "browser-use not installed", "screenshot": None}

    fields_desc = "\n".join(f"  - {k}: {v}" for k, v in form_data.items())
    task = f"Go to {url}. Fill in the following fields:\n{fields_desc}\n"
    rp = resume_path or (str(RESUME_PATH) if RESUME_PATH.exists() else None)
    if rp and Path(rp).exists():
        task += f"Upload the resume file at '{rp}' to any file input on the page.\n"
    if task_hint:
        task += f"\nAdditional instructions: {task_hint}\n"
    if auto_submit:
        task += ("\nAfter filling all fields correctly, submit the form and "
                 "screenshot the confirmation page.")
    else:
        task += ("\nAfter filling all fields, do NOT submit the form. "
                 "Take a screenshot and confirm all fields are filled correctly.")

    browser = None
    ss_path = _screenshot_path(url)
    try:
        browser = Browser(headless=headless)
        agent = Agent(task=task, browser=browser)
        result = await agent.run()
        try:
            await agent.take_screenshot(ss_path)
        except Exception as sse:
            logger.warning("Could not capture browser-use screenshot: %s", sse)
            ss_path = None
        logger.info("browser-use form fill completed: %s", url)
        return {"success": True, "error": None,
                "screenshot": ss_path, "result": str(result)}
    except Exception as e:
        logger.error("browser-use form fill failed: %s", e)
        return {"success": False, "error": str(e), "screenshot": None}
    finally:
        if browser is not None:
            try:
                await browser.close()
            except Exception as ce:
                logger.debug("Error closing browser-use browser: %s", ce)
