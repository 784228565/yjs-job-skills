"""CDP 诊断工具：不只看通不通，还告诉你为什么不通、该怎么办。

退出码：
  0 - CDP 完全正常（含 page target）
  1 - Chrome 在运行但调试端口不通（最常见：没开调试模式 / >=136 默认 profile 被禁）
  2 - Chrome 未运行（直接启动调试 Chrome 即可）
  3 - 端口有响应但 HTTP 层异常（端口可能被其他程序占用）

用法：python check_cdp.py [port]
"""
import json
import socket
import subprocess
import sys
import urllib.request

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 9222


def chrome_count():
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq chrome.exe", "/NH"],
                         capture_output=True).stdout.decode("gbk", errors="ignore")
    return sum(1 for l in out.splitlines() if "chrome.exe" in l.lower())


def port_open():
    s = socket.socket()
    s.settimeout(3)
    try:
        s.connect(("127.0.0.1", PORT))
        return True
    except OSError:
        return False
    finally:
        s.close()


def main():
    n = chrome_count()
    print(f"[check] chrome processes: {n}")

    if not port_open():
        if n > 0:
            print(f"[FAIL] 端口 {PORT} 不通，但 Chrome 在运行 -> Chrome 未以调试模式启动")
            print("       （Chrome>=136 注意：必须用 junction profile，不能用默认 User Data）")
            print("       处置：完全关闭 Chrome 后运行 scripts/start_chrome_debug.bat")
            return 1
        print(f"[FAIL] 端口 {PORT} 不通，且 Chrome 未运行")
        print("       处置：运行 scripts/start_chrome_debug.bat（自动建 junction 并启动）")
        return 2

    try:
        ver = json.load(urllib.request.urlopen(
            f"http://127.0.0.1:{PORT}/json/version", timeout=5))
    except Exception as e:
        print(f"[FAIL] 端口 {PORT} 有监听但 HTTP 异常: {e}")
        print("       处置：端口可能被非 Chrome 程序占用，换个端口或排查占用进程")
        return 3

    browser = ver.get("Browser", "?")
    print(f"[OK] CDP 响应正常: {browser}")
    major = int(browser.split("/")[-1].split(".")[0]) if "/" in browser else 0
    if major >= 136:
        print(f"     Chrome {major} >= 136：确认当前启动用的是 junction profile "
              "（UserData-CDP），否则此端口本不该存在")

    targets = json.load(urllib.request.urlopen(
        f"http://127.0.0.1:{PORT}/json", timeout=5))
    pages = [t for t in targets if t.get("type") == "page"]
    print(f"[OK] page targets: {len(pages)}（可正常投递操作）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
