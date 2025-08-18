#!/usr/bin/env python3
"""
Enterprise Broadcast Client — Default Windows Pop-up + Auto Startup
Uses ctypes for default Windows MessageBox popups.
Adds itself to Windows startup (HKCU Run key) to run via pythonw.exe silently.
"""

import os, sys, time, uuid, socket, platform, subprocess, argparse, winreg, ctypes

# -------- Dependency Check --------
def ensure_deps():
    import importlib.util
    if importlib.util.find_spec("requests") is None:
        print("Installing missing dependency: requests")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "requests"])

ensure_deps()

import requests  # type: ignore
import webbrowser

POLL_SECONDS = 5

# -------- Machine ID --------
def machine_id() -> str:
    try:
        return f"{socket.gethostname()}-{uuid.getnode()}"
    except Exception:
        return socket.gethostname()

# -------- Register at Server --------
def register(server: str, cid: str):
    try:
        requests.post(f"{server}/register", json={
            "client_id": cid, "hostname": socket.gethostname(), "platform": platform.platform()
        }, timeout=10)
    except Exception as e:
        print("Register error:", e)

# -------- ACK --------
def ack(server: str, cid: str, mid: int):
    try:
        requests.post(f"{server}/ack", json={"client_id": cid, "message_id": mid}, timeout=10)
    except Exception as e:
        print("Ack error:", e)

# -------- Default Windows Popup --------
def show_notification(message: str, url: str, mid: int, server: str, cid: str):
    MB_OKCANCEL = 0x01
    MB_ICONINFO = 0x40
    result = ctypes.windll.user32.MessageBoxW(
        0, message, "Service Notification", MB_OKCANCEL | MB_ICONINFO
    )

    # Result: OK = 1, Cancel = 2, X (close) = 2 bhi return hota hai
    if url:
        webbrowser.open(url)

    # Always send ack
    ack(server, cid, mid)

# -------- Startup Registry --------
def add_to_startup():
    exe = sys.executable.replace("python.exe", "pythonw.exe")
    script = os.path.abspath(__file__)
    run_key = r"Software\\Microsoft\\Windows\\CurrentVersion\\Run"
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, run_key, 0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, "BroadcastClient", 0, winreg.REG_SZ, f'"{exe}" "{script}" --run-silent')

# -------- Loop --------
def loop(server: str):
    cid = machine_id()
    if "--run-silent" not in sys.argv:
        print("Client ID:", cid, "| Server:", server)
    register(server, cid)
    add_to_startup()  # ensure registry entry exists
    while True:
        try:
            r = requests.post(f"{server}/poll", json={"client_id": cid}, timeout=15)
            if r.ok:
                data = r.json() or {}
                if data.get("id"):
                    show_notification(data.get("msg",""), data.get("url",""), data["id"], server, cid)
        except Exception as e:
            if "--run-silent" not in sys.argv:
                print("Poll error:", e)
        time.sleep(POLL_SECONDS)

# -------- Main --------
def main():
    p = argparse.ArgumentParser()
    p.add_argument("--server", default=os.environ.get("BMSG_SERVER","http://localhost:5000"))
    p.add_argument("--run-silent", action="store_true")
    args = p.parse_args()

    loop(args.server)

if __name__ == "__main__":
    main()
