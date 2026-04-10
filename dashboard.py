"""
Dashboard — A lightweight Flask web app to visualize the jobs database.
Run:  python dashboard.py
Open:  http://localhost:5050
"""

import sqlite3
from flask import Flask, jsonify, send_from_directory

app = Flask(__name__, static_folder="static")
DB_PATH = "jobs.db"


def _get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
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
    print("\n  🚀  Dashboard running at  http://localhost:5050\n")
    app.run(host="0.0.0.0", port=5050, debug=True)
