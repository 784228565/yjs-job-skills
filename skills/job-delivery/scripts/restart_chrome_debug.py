"""One-shot: kill all Chrome, relaunch in CDP debug mode via junction, verify.

⚠️ CONSENT REQUIRED: this script kills ALL chrome.exe processes. The caller
(host agent) MUST have explicit user consent before running it — per the skill's
"Chrome 进程保护" red line, the agent must not kill the user's Chrome without
consent. Tabs are restored via --restore-last-session.

Usage (command line only — importing this module has NO side effects):
    python restart_chrome_debug.py

Exit code 0 = CDP up and verified; non-zero = failure (see printed reason).
"""
import json
import socket
import subprocess
import sys
import time
import urllib.request

import config

CHROME = config.CHROME_PATH
PORT = config.DEBUG_PORT


def chrome_count():
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq chrome.exe", "/NH"],
                         capture_output=True).stdout.decode("gbk", errors="ignore")
    return sum(1 for l in out.splitlines() if "chrome.exe" in l.lower())


def port_open():
    s = socket.socket()
    s.settimeout(2)
    try:
        s.connect(("127.0.0.1", PORT))
        return True
    except OSError:
        return False
    finally:
        s.close()


def kill_all_chrome():
    print(f"[1/4] killing chrome (current: {chrome_count()} processes)...")
    subprocess.run(["taskkill", "/F", "/IM", "chrome.exe"], capture_output=True)
    time.sleep(2)
    n = chrome_count()
    print(f"      remaining: {n}")
    if n > 0:
        print("ERROR: Chrome survived taskkill; aborting.")
        return False
    return True


def launch_debug_chrome():
    profile = config.ensure_cdp_profile_junction()
    print(f"[2/4] launching chrome via junction on port {PORT}...")
    flags = 0x00000008 | 0x00000200 | 0x01000000  # detached|new group|breakaway
    subprocess.Popen(
        [CHROME, f"--remote-debugging-port={PORT}",
         f"--user-data-dir={profile}",
         "--disable-gpu", "--disable-gpu-compositing",
         "--restore-last-session"],
        creationflags=flags, close_fds=True)


def wait_for_port(timeout=20):
    print("[3/4] waiting for debug port...")
    for _ in range(timeout):
        time.sleep(1)
        if port_open():
            print(f"      port {PORT}: OPEN")
            return True
    print(f"      port {PORT}: CLOSED")
    return False


def verify_cdp():
    print("[4/4] verifying CDP endpoint...")
    try:
        ver = json.load(urllib.request.urlopen(
            f"http://127.0.0.1:{PORT}/json/version", timeout=5))
        targets = json.load(urllib.request.urlopen(
            f"http://127.0.0.1:{PORT}/json", timeout=5))
        pages = [t for t in targets if t.get("type") == "page"]
        print(f"      Browser: {ver.get('Browser')}")
        print(f"      page targets: {len(pages)}")
        return True
    except Exception as e:
        print("ERROR: /json/version failed:", e)
        return False


def main():
    if not kill_all_chrome():
        return 1
    launch_debug_chrome()
    if not wait_for_port():
        return 2
    if not verify_cdp():
        return 3
    print(f"DONE chrome_processes={chrome_count()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
