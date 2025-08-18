
#!/usr/bin/env python3
"""
Enterprise Broadcast Server (Flask + SQLite) — Clean Version
Features:
  • Broadcast or target specific clients
  • CTA link always provided by server
  • Simple Bootstrap web UI
  • Optional Telegram bot control (server-side)
  • SQLite DB: clients, messages, read receipts
  • Minimal, readable code (no "khichadi")

Environment variables:
  FLASK_SECRET        Flask session secret
  BMSG_DB             SQLite DB path (default: bmsg.db)
  BMSG_ADMIN_SECRET   UI action secret (default: change-this-secret)
  BMSG_TG_TOKEN       Telegram bot token (optional)
Usage:
  pip install -r requirements.txt
  python server.py --secret <ADMIN_SECRET> --host 0.0.0.0 --port 5000
"""
from __future__ import annotations
import os, json, sqlite3
from datetime import datetime
from typing import List
from flask import Flask, request, jsonify, render_template_string, redirect, url_for, flash

# # Optional Telegram (server-side only)
# try:
#     from telegram.ext import Updater, CommandHandler
# except Exception:
#     Updater = None

DB_PATH       = os.environ.get("BMSG_DB", "bmsg.db")
ADMIN_SECRET  = os.environ.get("BMSG_ADMIN_SECRET", "change-this-secret")

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "dev-secret")

SCHEMA = """
CREATE TABLE IF NOT EXISTS clients(
  client_id TEXT PRIMARY KEY,
  hostname  TEXT,
  platform  TEXT,
  last_seen TEXT,
  created_at TEXT
);
CREATE TABLE IF NOT EXISTS messages(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at TEXT,
  msg TEXT NOT NULL,
  url TEXT,
  broadcast INTEGER NOT NULL DEFAULT 0,
  targets TEXT
);
CREATE TABLE IF NOT EXISTS reads(
  client_id TEXT,
  message_id INTEGER,
  read_at TEXT,
  PRIMARY KEY (client_id, message_id)
);
"""

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

with db() as c:
    c.executescript(SCHEMA)

# ---------------- Web UI (Bootstrap) ----------------
HTML = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
  <title>Broadcast Console</title>
</head>
<body class="bg-light">
<div class="container py-4">
  <div class="d-flex align-items-center justify-content-between mb-3">
    <h1 class="h4">Broadcast Console</h1>
    <a class="btn btn-outline-secondary" href="{{ url_for('clients_json') }}">Clients JSON</a>
  </div>

  {% with messages = get_flashed_messages() %}
    {% if messages %}
      <div class="alert alert-info">{{ messages[0] }}</div>
    {% endif %}
  {% endwith %}

  <form class="card p-3 shadow-sm mb-4" method="post" action="{{ url_for('send') }}">
    <div class="row g-2">
      <div class="col-md-4">
        <label class="form-label">Admin Secret</label>
        <input class="form-control" required name="secret" placeholder="Enter admin secret">
      </div>
      <div class="col-md-8">
        <label class="form-label">CTA URL</label>
        <input class="form-control" name="url" placeholder="https://example.com/policy">
        <div class="form-text">Client CTA opens exactly this URL.</div>
      </div>
    </div>
    <div class="mt-2">
      <label class="form-label">Message</label>
      <textarea class="form-control" rows="3" required name="msg" placeholder="Type your notification..."></textarea>
    </div>
    <div class="form-check mt-2">
      <input class="form-check-input" type="checkbox" id="broadcast" name="broadcast" value="1" checked>
      <label class="form-check-label" for="broadcast">Broadcast to all</label>
    </div>
    <div class="mt-2">
      <label class="form-label">Or select specific clients</label>
      <div class="border rounded p-2 overflow-auto" style="max-height:220px">
        {% for cl in clients %}
          <div class="form-check">
            <input class="form-check-input" type="checkbox" name="targets" value="{{ cl['client_id'] }}" id="c{{ loop.index }}">
            <label class="form-check-label" for="c{{ loop.index }}">{{ cl['client_id'] }} — {{ cl['hostname'] }} ({{ cl['platform'] }})</label>
          </div>
        {% endfor %}
      </div>
    </div>
    <button class="btn btn-primary mt-3">Send</button>
  </form>

  <h2 class="h6">Recent Messages</h2>
  <ul class="list-group">
    {% for m in recent %}
      <li class="list-group-item">
        <div class="small text-muted">#{{ m['id'] }} • {{ m['created_at'] }}</div>
        <div>{{ m['msg'] }}</div>
        {% if m['url'] %}<div class="small">URL: {{ m['url'] }}</div>{% endif %}
        <div class="small">{{ 'Broadcast' if m['broadcast'] else 'Targets: ' + (m['targets'] or '[]') }}</div>
      </li>
    {% endfor %}
  </ul>
</div>
</body>
</html>
"""

@app.route("/")
def home():
    with db() as c:
        clients = c.execute("SELECT * FROM clients ORDER BY last_seen DESC").fetchall()
        recent  = c.execute("SELECT * FROM messages ORDER BY id DESC LIMIT 10").fetchall()
    return render_template_string(HTML, clients=clients, recent=recent)

@app.route("/clients")
def clients_json():
    with db() as c:
        rows = c.execute("SELECT * FROM clients ORDER BY last_seen DESC").fetchall()
    return jsonify([dict(r) for r in rows])

@app.route("/admin/send", methods=["POST"])
def send():
    secret   = (request.form.get("secret") or "")
    msg      = (request.form.get("msg") or "").strip()
    url      = (request.form.get("url") or "").strip()
    broadcast= 1 if request.form.get("broadcast") else 0
    targets  = request.form.getlist("targets")

    if secret != ADMIN_SECRET:
        flash("Invalid admin secret")
        return redirect(url_for('home'))
    if not msg:
        flash("Message required")
        return redirect(url_for('home'))
    if not broadcast and not targets:
        flash("Select targets or enable broadcast")
        return redirect(url_for('home'))

    with db() as c:
        c.execute(
            "INSERT INTO messages(created_at,msg,url,broadcast,targets) VALUES(?,?,?,?,?)",
            (datetime.utcnow().isoformat(), msg, url, broadcast, None if broadcast else json.dumps(targets))
        ); c.commit()
    flash("Message queued")
    return redirect(url_for('home'))

# ---------------- Client API ----------------
@app.route("/register", methods=["POST"])
def register():
    data = request.get_json(force=True)
    client_id = data.get("client_id")
    hostname  = data.get("hostname")
    platform  = data.get("platform")
    if not client_id:
        return jsonify({"error":"client_id required"}), 400
    now = datetime.utcnow().isoformat()
    with db() as c:
        c.execute(
            "INSERT INTO clients(client_id,hostname,platform,last_seen,created_at) VALUES(?,?,?,?,?) "
            "ON CONFLICT(client_id) DO UPDATE SET hostname=excluded.hostname, platform=excluded.platform, last_seen=excluded.last_seen",
            (client_id, hostname, platform, now, now)
        ); c.commit()
    return jsonify({"status":"ok"})

@app.route("/poll", methods=["POST"])
def poll():
    data = request.get_json(force=True)
    client_id = data.get("client_id")
    if not client_id:
        return jsonify({}), 400

    with db() as c:
        c.execute("UPDATE clients SET last_seen=? WHERE client_id=?", (datetime.utcnow().isoformat(), client_id))
        rows = c.execute("SELECT * FROM messages ORDER BY id DESC LIMIT 50").fetchall()
        for r in rows:
            r = dict(r)
            if r["broadcast"] == 1:
                read = c.execute("SELECT 1 FROM reads WHERE client_id=? AND message_id=?", (client_id, r["id"])).fetchone()
                if not read:
                    return jsonify({"id": r["id"], "msg": r["msg"], "url": r["url"] or ""})
            else:
                targets = json.loads(r["targets"] or "[]")
                if client_id in targets:
                    read = c.execute("SELECT 1 FROM reads WHERE client_id=? AND message_id=?", (client_id, r["id"])).fetchone()
                    if not read:
                        return jsonify({"id": r["id"], "msg": r["msg"], "url": r["url"] or ""})
    return jsonify({})

@app.route("/ack", methods=["POST"])
def ack():
    data = request.get_json(force=True)
    client_id  = data.get("client_id")
    message_id = data.get("message_id")
    if not client_id or not message_id:
        return jsonify({"error":"client_id and message_id required"}), 400
    with db() as c:
        c.execute("INSERT OR IGNORE INTO reads(client_id,message_id,read_at) VALUES(?,?,?)",
                  (client_id, message_id, datetime.utcnow().isoformat()))
        c.commit()
    return jsonify({"status":"ok"})

# ---------------- Telegram (Optional) ----------------
def start_bot(token: str):
    if Updater is None:
        print("Install python-telegram-bot to use the bot")
        return
    up = Updater(token=token, use_context=True)
    dp = up.dispatcher

    def help_cmd(update, ctx):
        update.message.reply_text(
            "Commands:\n"
            "/broadcast <url> | <message>\n"
            "/send <client_id> <url> | <message>"
        )
    def broadcast_cmd(update, ctx):
        try:
            text = " ".join(ctx.args)
            url, msg = [s.strip() for s in text.split("|",1)] if "|" in text else ("", text)
            with db() as c:
                c.execute("INSERT INTO messages(created_at,msg,url,broadcast) VALUES(?,?,?,1)",
                          (datetime.utcnow().isoformat(), msg, url)); c.commit()
            update.message.reply_text("Broadcast queued")
        except Exception as e:
            update.message.reply_text(f"Error: {e}")
    def send_cmd(update, ctx):
        try:
            if len(ctx.args) < 2:
                update.message.reply_text("Usage: /send <client_id> <url> | <message>"); return
            client_id = ctx.args[0]
            text = " ".join(ctx.args[1:])
            url, msg = [s.strip() for s in text.split("|",1)] if "|" in text else ("", text)
            with db() as c:
                c.execute("INSERT INTO messages(created_at,msg,url,broadcast,targets) VALUES(?,?,?,?,?)",
                          (datetime.utcnow().isoformat(), msg, url, 0, json.dumps([client_id]))); c.commit()
            update.message.reply_text("Message queued")
        except Exception as e:
            update.message.reply_text(f"Error: {e}")

    dp.add_handler(CommandHandler("start", help_cmd))
    dp.add_handler(CommandHandler("help", help_cmd))
    dp.add_handler(CommandHandler("broadcast", broadcast_cmd))
    dp.add_handler(CommandHandler("send", send_cmd))

    print("Telegram bot started")
    up.start_polling()

if __name__ == "__main__":
    import argparse, threading
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--secret", default=None, help="Admin secret (overrides env)")
    parser.add_argument("--no-bot", action="store_true")
    args = parser.parse_args()
    if args.secret:
        ADMIN_SECRET = args.secret

    token = os.environ.get("BMSG_TG_TOKEN")
    if token and not args.no_bot:
        threading.Thread(target=start_bot, args=(token,), daemon=True).start()

    app.run(host=args.host, port=args.port)
