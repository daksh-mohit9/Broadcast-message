#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations
import os, json, sqlite3
from datetime import datetime
from flask import Flask, request, jsonify, render_template_string, redirect, url_for, flash

# Stable base dir + DB path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("BMSG_DB", os.path.join(BASE_DIR, "bmsg.db"))
ADMIN_SECRET = os.environ.get("BMSG_ADMIN_SECRET", "change-this-secret")

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
    # Robust connection for concurrent access
    conn = sqlite3.connect(DB_PATH, timeout=5, check_same_thread=False)
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
    <title>Broadcast Console</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
      body { background:#f7f7fb; }
      .card { box-shadow: 0 1px 3px rgba(0,0,0,.06); }
      pre { white-space: pre-wrap; }
    </style>
  </head>
  <body>
    <div class="container py-4">
      <h1 class="mb-3">Broadcast Console</h1>

      {% with messages = get_flashed_messages() %}
        {% if messages %}
          <div class="alert alert-info">{{ messages[0] }}</div>
        {% endif %}
      {% endwith %}

      <div class="row g-3">
        <div class="col-lg-7">
          <div class="card">
            <div class="card-body">
              <h5 class="card-title">New Message</h5>
              <form method="post" action="{{ url_for('send') }}">
                <div class="mb-2">
                  <label class="form-label">Admin Secret</label>
                  <input class="form-control" name="secret" type="password" placeholder="secret">
                </div>
                <div class="mb-2">
                  <label class="form-label">CTA URL</label>
                  <input class="form-control" name="url" placeholder="https://...">
                  <div class="form-text">Client CTA opens exactly this URL.</div>
                </div>
                <div class="mb-2">
                  <label class="form-label">Message</label>
                  <textarea class="form-control" name="msg" rows="3" required></textarea>
                </div>
                <div class="form-check mb-2">
                  <input class="form-check-input" type="checkbox" value="1" id="broadcast" name="broadcast" checked>
                  <label class="form-check-label" for="broadcast">Broadcast to all</label>
                </div>
                <div class="mb-3">
                  <label class="form-label">Or select specific clients</label>
                  <div class="border rounded p-2" style="max-height: 200px; overflow:auto;">
                    {% for cl in clients %}
                      <div class="form-check">
                        <input class="form-check-input" type="checkbox" name="targets" value="{{ cl['client_id'] }}" id="cl{{ loop.index }}">
                        <label class="form-check-label" for="cl{{ loop.index }}">
                          {{ cl['client_id'] }} — {{ cl['hostname'] }} ({{ cl['platform'] }})
                        </label>
                      </div>
                    {% endfor %}
                    {% if not clients %}
                      <div class="text-muted small">No clients registered yet.</div>
                    {% endif %}
                  </div>
                </div>
                <button class="btn btn-primary">Send</button>
              </form>
            </div>
          </div>
        </div>

        <div class="col-lg-5">
          <div class="card mb-3">
            <div class="card-body">
              <h5 class="card-title">Maintenance</h5>

              <!-- Clear ALL messages (queue/history + reads) -->
              <form class="row g-2 align-items-end" method="post" action="{{ url_for('clear_messages') }}">
                <div class="col-6">
                  <label class="form-label">Admin Secret</label>
                  <input class="form-control" name="secret" type="password">
                </div>
                <div class="col-6">
                  <button class="btn btn-danger w-100" onclick="return confirm('Clear ALL messages? This also removes read receipts.')">Clear All Messages</button>
                </div>
              </form>

              <hr>

              <!-- Delete one message by ID -->
              <form class="row g-2 align-items-end" method="post" action="{{ url_for('delete_message') }}">
                <div class="col-5">
                  <label class="form-label">Admin Secret</label>
                  <input class="form-control" name="secret" type="password">
                </div>
                <div class="col-4">
                  <label class="form-label">Message ID</label>
                  <input class="form-control" name="message_id" placeholder="#id">
                </div>
                <div class="col-3">
                  <button class="btn btn-outline-danger w-100">Delete</button>
                </div>
              </form>

              <hr>

              <!-- Remove a saved client -->
              <form class="row g-2 align-items-end" method="post" action="{{ url_for('remove_client') }}">
                <div class="col-5">
                  <label class="form-label">Admin Secret</label>
                  <input class="form-control" name="secret" type="password">
                </div>
                <div class="col-4">
                  <label class="form-label">Client ID</label>
                  <input class="form-control" name="client_id" placeholder="client_id">
                </div>
                <div class="col-3">
                  <button class="btn btn-outline-warning w-100" onclick="return confirm('Remove client and its read receipts?')">Remove</button>
                </div>
              </form>
            </div>
          </div>

          <div class="card">
            <div class="card-body">
              <h5 class="card-title">Recent Messages</h5>
              {% for m in recent %}
                <div class="border rounded p-2 mb-2">
                  <div class="small text-muted">#{{ m['id'] }} • {{ m['created_at'] }}</div>
                  <div>{{ m['msg'] }}</div>
                  {% if m['url'] %}<div class="small">URL: {{ m['url'] }}</div>{% endif %}
                  <div class="small">{{ 'Broadcast' if m['broadcast'] else 'Targets: ' + (m['targets'] or '[]') }}</div>
                </div>
              {% endfor %}
              {% if not recent %}
                <div class="text-muted small">No messages yet.</div>
              {% endif %}
            </div>
          </div>
        </div>
      </div>

      <hr class="my-4">
      <h5>Clients JSON</h5>
      <pre class="bg-white p-3 border rounded" style="max-height:240px; overflow:auto;">{{ clients|tojson(indent=2) }}</pre>
    </div>
  </body>
</html>
"""

# ---------------- Routes ----------------

@app.route("/")
def home():
    with db() as c:
        clients_rows = c.execute("SELECT * FROM clients ORDER BY last_seen DESC").fetchall()
        recent_rows  = c.execute("SELECT * FROM messages ORDER BY id DESC LIMIT 10").fetchall()
    clients = [dict(r) for r in clients_rows]
    recent  = [dict(r) for r in recent_rows]
    return render_template_string(HTML, clients=clients, recent=recent)

@app.route("/clients")
def clients_json():
    with db() as c:
        rows = c.execute("SELECT * FROM clients ORDER BY last_seen DESC").fetchall()
    return jsonify([dict(r) for r in rows])

# ---------------- Admin: send + maintenance ----------------

@app.route("/admin/send", methods=["POST"])
def send():
    secret = (request.form.get("secret") or "")
    msg = (request.form.get("msg") or "").strip()
    url = (request.form.get("url") or "").strip()
    broadcast = 1 if request.form.get("broadcast") else 0
    targets = request.form.getlist("targets")

    if secret != ADMIN_SECRET:
        flash("Invalid admin secret"); return redirect(url_for('home'))
    if not msg:
        flash("Message required"); return redirect(url_for('home'))
    if not broadcast and not targets:
        flash("Select targets or enable broadcast"); return redirect(url_for('home'))

    with db() as c:
        c.execute(
            "INSERT INTO messages(created_at,msg,url,broadcast,targets) VALUES(?,?,?,?,?)",
            (datetime.utcnow().isoformat(), msg, url, broadcast, None if broadcast else json.dumps(targets))
        ); c.commit()
    flash("Message queued")
    return redirect(url_for('home'))

@app.post("/admin/clear_messages")
def clear_messages():
    secret = (request.form.get("secret") or "")
    if secret != ADMIN_SECRET:
        flash("Invalid admin secret"); return redirect(url_for("home"))
    with db() as c:
        c.execute("DELETE FROM reads")
        c.execute("DELETE FROM messages")
        c.commit()
    flash("All messages and read history cleared")
    return redirect(url_for("home"))

@app.post("/admin/delete_message")
def delete_message():
    secret = (request.form.get("secret") or "")
    mid = (request.form.get("message_id") or "").strip()
    if secret != ADMIN_SECRET:
        flash("Invalid admin secret"); return redirect(url_for("home"))
    if not mid.isdigit():
        flash("Valid message_id required"); return redirect(url_for("home"))
    mid_i = int(mid)
    with db() as c:
        c.execute("DELETE FROM reads WHERE message_id=?", (mid_i,))
        c.execute("DELETE FROM messages WHERE id=?", (mid_i,))
        c.commit()
    flash(f"Message #{mid_i} deleted")
    return redirect(url_for("home"))

@app.post("/admin/remove_client")
def remove_client():
    secret = (request.form.get("secret") or "")
    cid = (request.form.get("client_id") or "").strip()
    if secret != ADMIN_SECRET:
        flash("Invalid admin secret"); return redirect(url_for("home"))
    if not cid:
        flash("client_id required"); return redirect(url_for("home"))
    with db() as c:
        c.execute("DELETE FROM reads WHERE client_id=?", (cid,))
        c.execute("DELETE FROM clients WHERE client_id=?", (cid,))
        c.commit()
    flash(f"Client {cid} removed")
    return redirect(url_for("home"))

# Programmatic JSON admin APIs (optional)
@app.post("/api/admin/clear")
def api_clear():
    data = request.get_json(silent=True) or {}
    if data.get("secret") != ADMIN_SECRET: return jsonify({"error":"forbidden"}), 403
    with db() as c:
        c.execute("DELETE FROM reads"); c.execute("DELETE FROM messages"); c.commit()
    return jsonify({"status":"cleared"})

@app.post("/api/admin/delete")
def api_delete():
    data = request.get_json(silent=True) or {}
    if data.get("secret") != ADMIN_SECRET: return jsonify({"error":"forbidden"}), 403
    mid = data.get("message_id")
    if not isinstance(mid, int): return jsonify({"error":"message_id int required"}), 400
    with db() as c:
        c.execute("DELETE FROM reads WHERE message_id=?", (mid,))
        c.execute("DELETE FROM messages WHERE id=?", (mid,))
        c.commit()
    return jsonify({"status":"deleted","id":mid})

@app.post("/api/admin/remove_client")
def api_remove_client():
    data = request.get_json(silent=True) or {}
    if data.get("secret") != ADMIN_SECRET: return jsonify({"error":"forbidden"}), 403
    cid = data.get("client_id")
    if not cid: return jsonify({"error":"client_id required"}), 400
    with db() as c:
        c.execute("DELETE FROM reads WHERE client_id=?", (cid,))
        c.execute("DELETE FROM clients WHERE client_id=?", (cid,))
        c.commit()
    return jsonify({"status":"removed","client_id":cid})

# ---------------- Client API ----------------

@app.route("/register", methods=["POST"])
def register():
    data = request.get_json(silent=True) or {}
    client_id = data.get("client_id")
    hostname = data.get("hostname")
    platform = data.get("platform")
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
    data = request.get_json(silent=True) or {}
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
                try:
                    targets = json.loads(r["targets"] or "[]")
                except Exception:
                    targets = []
                if client_id in targets:
                    read = c.execute("SELECT 1 FROM reads WHERE client_id=? AND message_id=?", (client_id, r["id"])).fetchone()
                    if not read:
                        return jsonify({"id": r["id"], "msg": r["msg"], "url": r["url"] or ""})
    return jsonify({})

@app.route("/ack", methods=["POST"])
def ack():
    data = request.get_json(silent=True) or {}
    client_id = data.get("client_id")
    message_id = data.get("message_id")
    if not client_id or not message_id:
        return jsonify({"error":"client_id and message_id required"}), 400

    with db() as c:
        c.execute("INSERT OR IGNORE INTO reads(client_id,message_id,read_at) VALUES(?,?,?)",
                  (client_id, message_id, datetime.utcnow().isoformat()))
        c.commit()
    return jsonify({"status":"ok"})

# ---------------- Main ----------------

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--secret", default=None, help="Admin secret (overrides env)")
    args = parser.parse_args()

    if args.secret:
        ADMIN_SECRET = args.secret

    app.run(host=args.host, port=args.port, debug=True)
