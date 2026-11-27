"""Central configuration for job-delivery.

Single source of truth for all paths, credentials, and runtime settings.
Secrets and PII are NOT hardcoded here:
  - The Composio API key is read from the environment variable COMPOSIO_API_KEY.
  - Candidate identity (name/email/phone) is loaded at runtime from
    candidate_profile.json, never embedded in code or docs.

Override any path via environment variables if your layout differs.
"""

import glob
import json
import os
from pathlib import Path

# --- Base directories ---------------------------------------------------------
# All paths can be overridden with environment variables.
WORK_AGENT_DIR = Path(os.environ.get(
    "JD_WORK_AGENT_DIR", r"C:\Users\78422\Desktop\工作agent"))
STATUS_DIR = Path(os.environ.get(
    "JD_STATUS_DIR", str(WORK_AGENT_DIR / "投递状态记录")))
SCREENSHOT_DIR = Path(os.environ.get(
    "JD_SCREENSHOT_DIR", str(STATUS_DIR / "screenshots")))
DASHBOARD_DIR = Path(os.environ.get(
    "JD_DASHBOARD_DIR", str(STATUS_DIR / "applypilot-dashboard")))
QUEUE_DIR = Path(os.environ.get(
    "JD_QUEUE_DIR", str(WORK_AGENT_DIR / "筛选agent")))

# --- Files --------------------------------------------------------------------
RESUME_PATH = Path(os.environ.get(
    "JD_RESUME_PATH",
    str(WORK_AGENT_DIR / "Junting_Wu_Resume_EN_2page_updated.pdf")))
CANDIDATE_PROFILE_PATH = Path(os.environ.get(
    "JD_CANDIDATE_PROFILE", str(DASHBOARD_DIR / "candidate_profile.json")))
ANSWER_BANK_PATH = Path(os.environ.get(
    "JD_ANSWER_BANK", str(DASHBOARD_DIR / "answer_bank.md")))
DELIVERY_LOG_CSV = STATUS_DIR / "delivery_log.csv"
ISSUE_LOG_MD = STATUS_DIR / "issue_log.md"
DELIVERY_SUMMARY_MD = STATUS_DIR / "delivery_summary.md"

# --- Network / credentials ----------------------------------------------------
# Composio (Gmail MCP) key. NEVER hardcode; set in your environment.
COMPOSIO_API_KEY = os.environ.get("COMPOSIO_API_KEY", "")
COMPOSIO_BASE = os.environ.get(
    "COMPOSIO_BASE", "https://connect.composio.dev/mcp")
# Local proxy (e.g. Mihomo/Clash) needed to reach composio.dev. Optional.
PROXY = os.environ.get("JD_PROXY") or os.environ.get("HTTPS_PROXY", "")

# --- Browser / CDP ------------------------------------------------------------
DEBUG_PORT = int(os.environ.get("JD_DEBUG_PORT", "9222"))
CHROME_PATH = os.environ.get(
    "JD_CHROME_PATH",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe")

# Real (default) Chrome profile. Chrome >= 136 IGNORES --remote-debugging-port
# when it is used with this default directory (verified on Chrome 150,
# 2026-07-25). A directory junction with a non-default path bypasses the check
# while sharing the exact same profile files (login sessions preserved).
CHROME_PROFILE_DIR = Path(os.environ.get(
    "JD_CHROME_PROFILE",
    os.path.join(os.environ.get("LOCALAPPDATA", ""),
                 "Google", "Chrome", "User Data")))
CHROME_CDP_JUNCTION = Path(os.environ.get(
    "JD_CHROME_CDP_PROFILE",
    str(CHROME_PROFILE_DIR.parent / "UserData-CDP")))


def ensure_cdp_profile_junction():
    """Return a non-default path to the real Chrome profile via a junction.

    Creates the junction on first use (no admin needed for /J junctions).
    """
    import subprocess
    if not os.path.lexists(str(CHROME_CDP_JUNCTION)):
        if not CHROME_PROFILE_DIR.is_dir():
            raise FileNotFoundError(
                "Chrome profile not found: " + str(CHROME_PROFILE_DIR))
        r = subprocess.run(
            ["cmd", "/c", "mklink", "/J",
             str(CHROME_CDP_JUNCTION), str(CHROME_PROFILE_DIR)],
            capture_output=True)
        if r.returncode != 0:
            raise RuntimeError(
                "mklink /J failed: "
                + r.stderr.decode("gbk", errors="ignore"))
    return str(CHROME_CDP_JUNCTION)


def ensure_dirs():
    """Create writable directories if missing. Returns the screenshot dir."""
    for d in (STATUS_DIR, SCREENSHOT_DIR):
        d.mkdir(parents=True, exist_ok=True)
    return SCREENSHOT_DIR


def find_plugin_browser_script():
    """Locate open-chrome-window.js regardless of bundled plugin version.

    Avoids hardcoding a versioned path that breaks on every plugin update.
    Returns the newest matching script path, or None if not found.
    """
    pattern = str(Path.home() /
                  ".codex/plugins/cache/openai-bundled/browser/*/"
                  "scripts/open-chrome-window.js")
    matches = sorted(glob.glob(pattern))
    return matches[-1] if matches else None


def find_latest_queue_file():
    """Return the newest 队列*.xlsx in QUEUE_DIR, ignoring temp/lock files.

    Preference order: today's file first, else the most recently dated file.
    Returns a Path or None.
    """
    if not QUEUE_DIR.is_dir():
        return None
    candidates = [
        p for p in QUEUE_DIR.glob("队列*.xlsx")
        if not p.name.startswith("~$")  # skip Excel lock files
    ]
    if not candidates:
        return None
    # Prefer today's date in filename, else newest by mtime.
    from datetime import date
    today = date.today().strftime("%Y-%m-%d")
    for p in candidates:
        if today in p.name:
            return p
    return max(candidates, key=lambda p: p.stat().st_mtime)


def load_candidate_profile():
    """Load candidate identity from candidate_profile.json (PII lives here).

    Returns the RAW nested dict; empty dict if the file is missing/unreadable.
    The file's top level is NOT flat: identity lives under the "candidate" key.
    """
    try:
        return json.loads(CANDIDATE_PROFILE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def candidate_contact():
    """Normalized contact info for form filling (stable contract).

    Reads the nested candidate_profile.json and returns a flat dict:
        full_name, first_name, last_name, email, phone, location
    Fields are empty strings when unavailable. Use THIS in delivery code and
    examples instead of guessing the JSON's internal layout.
    """
    c = load_candidate_profile().get("candidate", {})
    full = c.get("legal_name") or c.get("preferred_name") or ""
    parts = full.split(None, 1)
    return {
        "full_name": full,
        "first_name": parts[0] if parts else "",
        "last_name": parts[1] if len(parts) > 1 else "",
        "email": c.get("email", ""),
        "phone": c.get("phone", ""),
        "location": c.get("current_location", ""),
    }


if __name__ == "__main__":
    print("STATUS_DIR       :", STATUS_DIR)
    print("SCREENSHOT_DIR   :", SCREENSHOT_DIR)
    print("RESUME_PATH      :", RESUME_PATH, RESUME_PATH.exists())
    print("QUEUE (latest)   :", find_latest_queue_file())
    print("PLUGIN BROWSER JS:", find_plugin_browser_script())
    print("API key set      :", bool(COMPOSIO_API_KEY))
    print("PROXY            :", PROXY or "(none)")
