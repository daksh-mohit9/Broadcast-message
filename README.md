
# Broadcast Messaging Tool — Clean Enterprise Version

## What you get
- ✅ Broadcast + specific client messaging
- ✅ CTA button always opens server-provided URL
- ✅ Optional Telegram bot (server-side)
- ✅ Windows startup helpers (Startup folder / HKCU Run), consent-based
- ✅ Stable machine IDs, read receipts
- ✅ Minimal, clean code

## Setup
### Server
```bash
pip install -r requirements.txt
python server.py --secret YOUR_ADMIN_SECRET --host 0.0.0.0 --port 5000
```
Open `http://<server>:5000` to use the web UI.

**Telegram (optional):**
Set `BMSG_TG_TOKEN` env var and use commands:
```
/broadcast <url> | <message>
/send <client_id> <url> | <message>
```

### Client (Windows/Linux with Tk)
```bash
python client.py --server http://<server>:5000
# no-console on Windows:
pythonw client.py --server http://<server>:5000 --run-silent
```

Add to startup (consented):
```bash
python client.py --server http://<server>:5000 --install-startup
# or
python client.py --server http://<server>:5000 --install-reg
```

## Notes
- This tool is transparent and uninstallable. No AV evasion is included.
- Keep `ADMIN_SECRET` safe.
