"""CDP fallback decorator and utilities for job-delivery.

Three-tier fallback:
  1. browser-client (default) -- caller supplies the real operation
  2. RawCDPChrome (on CDP timeout)
  3. browser-use (AI-powered form filling, last resort)

The tier-1 "browser-client" operation is NOT implemented here; the caller
injects it (a callable). This module only orchestrates the fallback and holds
a shared RawCDPChrome connection so a timeout switches all later steps to CDP.
"""

import functools
import logging
import os
import sys

_scripts_dir = os.path.dirname(os.path.abspath(__file__))
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

from raw_cdp_chrome import RawCDPChrome, is_cdp_timeout_error  # noqa: E402

logger = logging.getLogger(__name__)


class JobDeliveryError(Exception):
    pass


# --- Shared CDP connection -----------------------------------------------------
# Once a CDP timeout occurs, we keep one RawCDPChrome alive and reuse it for the
# rest of the run (per SKILL.md: after downgrade, do not return to browser-client).
_shared_cdp = None


def get_shared_cdp():
    """Return the shared RawCDPChrome, creating/connecting it on first use."""
    global _shared_cdp
    if _shared_cdp is not None and _shared_cdp._connected:
        return _shared_cdp
    cdp = RawCDPChrome(auto_start=True)
    try:
        cdp.connect()
    except ConnectionError as ce:
        raise ConnectionError(
            "CDP fallback failed: cannot reach Chrome debug port "
            f"{cdp.debug_port}. Start Chrome in debug mode first."
        ) from ce
    _shared_cdp = cdp
    return _shared_cdp


def close_shared_cdp():
    global _shared_cdp
    if _shared_cdp is not None:
        try:
            _shared_cdp.disconnect()
        finally:
            _shared_cdp = None


# --- Decorator -----------------------------------------------------------------
def with_cdp_fallback(step_name=""):
    """Wrap a browser operation with CDP fallback.

    The wrapped function may accept a ``cdp`` keyword. On a CDP-timeout error we
    establish the shared CDP connection and, if the function accepts ``cdp``,
    re-invoke it once with that client injected so the operation is retried over
    CDP instead of being silently dropped.
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                if not is_cdp_timeout_error(e):
                    raise
                logger.warning(
                    "CDP timeout in step [%s]: %s. Switching to RawCDPChrome.",
                    step_name, e)
                cdp = get_shared_cdp()
                # Retry only if the function can actually use the CDP client.
                import inspect
                if "cdp" in inspect.signature(func).parameters:
                    kwargs["cdp"] = cdp
                    return func(*args, **kwargs)
                raise JobDeliveryError(
                    f"Step [{step_name}] hit a CDP timeout and the operation "
                    "cannot be replayed over RawCDPChrome (it does not accept a "
                    "'cdp' argument). Re-run this step via run_with_cdp_fallback."
                ) from e
        return wrapper
    return decorator


# --- Operation runner ----------------------------------------------------------
def run_with_cdp_fallback(operations, primary_op=None, current_url=None,
                          form_data=None):
    """Run a list of operation dicts with automatic three-tier fallback.

    Args:
        operations: list of dicts. Each:
            op: "navigate"|"fill"|"click"|"upload"|"screenshot"|"evaluate"|
                "checkbox"|"browser_use"
            selector: CSS selector (optional)
            value: fill value / URL / file path / JS expression
        primary_op: callable(op_dict) that performs the tier-1 browser-client
            action for one operation. REQUIRED for real runs; without it tier-1
            is skipped and we go straight to CDP (with a logged warning).
        current_url: starting URL (informational).
        form_data: form values forwarded to browser-use fallback ops.

    Returns:
        (cdp, results, used_cdp)
    """
    cdp = None
    used_cdp = False
    results = []

    if primary_op is None:
        logger.warning(
            "run_with_cdp_fallback called without primary_op; "
            "tier-1 browser-client is unavailable, using CDP from the start.")

    for i, op in enumerate(operations):
        try:
            if used_cdp:
                _run_cdp_op(get_shared_cdp(), op, form_data)
                results.append({"step": i, "status": "ok_cdp", "op": op.get("op")})
            else:
                if primary_op is None:
                    raise _NoPrimaryOp()
                primary_op(op)  # real tier-1 action
                results.append({"step": i, "status": "ok", "op": op.get("op")})
        except _NoPrimaryOp:
            # No tier-1 available: go straight to CDP for this and later steps.
            used_cdp = True
            try:
                _run_cdp_op(get_shared_cdp(), op, form_data)
                results.append({"step": i, "status": "ok_cdp", "op": op.get("op")})
            except Exception as e2:
                logger.error("CDP op failed at step %d: %s", i, e2)
                results.append({"step": i, "status": "failed",
                                "error": str(e2), "op": op.get("op")})
                raise JobDeliveryError(
                    f"Operation failed at step {i} (no tier-1, CDP failed): {e2}"
                ) from e2
        except Exception as e:
            if is_cdp_timeout_error(e):
                logger.warning(
                    "Browser operation timed out at step %d, switching to "
                    "RawCDPChrome", i)
                used_cdp = True
                try:
                    _run_cdp_op(get_shared_cdp(), op, form_data)
                    results.append({"step": i, "status": "ok_cdp",
                                    "op": op.get("op")})
                except Exception as e2:
                    logger.error("CDP fallback also failed at step %d: %s", i, e2)
                    results.append({"step": i, "status": "failed",
                                    "error": str(e2), "op": op.get("op")})
                    raise JobDeliveryError(
                        f"Operation failed even with CDP fallback at step {i}: {e2}"
                    ) from e2
            else:
                results.append({"step": i, "status": "failed",
                                "error": str(e), "op": op.get("op")})
                raise

    return cdp if cdp else (get_shared_cdp() if used_cdp else None), results, used_cdp


class _NoPrimaryOp(Exception):
    """Internal sentinel: no tier-1 browser operation was provided."""


# --- Single-op dispatch over RawCDPChrome --------------------------------------
def _run_cdp_op(cdp, op, form_data=None):
    """Execute a single operation dict via RawCDPChrome (or browser-use)."""
    op_type = op.get("op", "")
    selector = op.get("selector", "")
    value = op.get("value", "")

    if op_type == "navigate":
        cdp.navigate(value)
    elif op_type == "fill":
        cdp.fill(selector, value)
    elif op_type == "click":
        cdp.click_element(selector)
    elif op_type == "upload":
        cdp.upload_file(selector, value)
    elif op_type == "screenshot":
        cdp.save_screenshot(value)
    elif op_type == "evaluate":
        cdp.evaluate(value)
    elif op_type == "checkbox":
        cdp.click_checkbox(selector)
    elif op_type == "browser_use":
        _run_browser_use(value, op, form_data)
    else:
        raise ValueError("Unknown operation: " + op_type)


def _run_browser_use(url, op, form_data):
    """Tier-3: browser-use LLM form fill. Optionally submits when asked."""
    try:
        from browser_use_form_fill import fill_form_with_browser_use
    except ImportError as ie:
        raise JobDeliveryError("browser-use not available for fallback") from ie
    result = fill_form_with_browser_use(
        url,
        op.get("form_data", form_data or {}),
        op.get("resume_path"),
        op.get("task_hint", ""),
        auto_submit=op.get("auto_submit", False),
    )
    if not result.get("success"):
        raise JobDeliveryError(
            "browser-use fallback failed: " + str(result.get("error")))
