"""
Dashboard — A lightweight Flask web app to visualize the jobs database.
Run:  python dashboard.py
Open:  http://localhost:5050
"""

import sqlite3
from flask import Flask, jsonify, send_from_directory

import yaml
import os

app = Flask(__name__, static_folder="static")

# Load DB path from config if available
CONFIG_PATH = "config.yaml"
DB_PATH = "jobs.db"
if os.path.exists(CONFIG_PATH):
    try:
        with open(CONFIG_PATH, "r") as f:
            cfg = yaml.safe_load(f)
            DB_PATH = cfg.get("settings", {}).get("database_path", "jobs.db")
    except:
        pass

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS jobs (
    apply_link TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    company TEXT NOT NULL,
    location TEXT DEFAULT '',
    description TEXT DEFAULT '',
    posted_date TEXT,
    match_score INTEGER,
    match_reasoning TEXT,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    notified INTEGER DEFAULT 0
)
"""


def _get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    # Ensure table exists so we don't crash on first load
    conn.execute(CREATE_TABLE_SQL)
    conn.commit()
    return conn


# ── API endpoints ────────────────────────────────────

@app.route("/api/jobs")
def api_jobs():
    conn = _get_db()
    rows = conn.execute(
        "SELECT apply_link, title, company, location, description, "
        "posted_date, match_score, match_reasoning, first_seen, last_seen, notified "
        "FROM jobs ORDER BY first_seen DESC"
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/stats")
def api_stats():
    conn = _get_db()
    c = conn.cursor()

    total = c.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    scored = c.execute("SELECT COUNT(*) FROM jobs WHERE match_score IS NOT NULL").fetchone()[0]
    avg_score = c.execute("SELECT AVG(match_score) FROM jobs WHERE match_score IS NOT NULL").fetchone()[0]
    high_match = c.execute("SELECT COUNT(*) FROM jobs WHERE match_score > 80").fetchone()[0]
    companies = c.execute("SELECT COUNT(DISTINCT company) FROM jobs").fetchone()[0]
    notified = c.execute("SELECT COUNT(*) FROM jobs WHERE notified = 1").fetchone()[0]

    # Company breakdown
    company_rows = c.execute(
        "SELECT company, COUNT(*) as cnt FROM jobs GROUP BY company ORDER BY cnt DESC LIMIT 10"
    ).fetchall()

    conn.close()
    return jsonify({
        "total": total,
        "scored": scored,
        "avg_score": round(avg_score, 1) if avg_score else 0,
        "high_match": high_match,
        "companies": companies,
        "notified": notified,
        "company_breakdown": [{"name": r[0], "count": r[1]} for r in company_rows],
    })


# ── Serve frontend ───────────────────────────────────

@app.route("/")
def index():
    return send_from_directory("static", "index.html")


if __name__ == "__main__":
    print("\n  🚀  Job Scraper Dashboard running at  http://localhost:5050\n")
    app.run(host="0.0.0.0", port=5050, debug=True)
