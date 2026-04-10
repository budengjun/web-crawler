"""
generate_training_data.py — Auto-generate initial training data from existing jobs.db.

Uses rule-based heuristics to label jobs as relevant (1) or irrelevant (0).
The generated train_data.csv can then be used to train the MLP classifier.

Usage:
    python generate_training_data.py
"""

import sqlite3
import csv
import os

DB_PATH = "jobs.db"
OUTPUT_PATH = "train_data.csv"


def auto_label(title: str, location: str, description: str) -> int:
    """
    Rule-based labeling:
      1 = relevant (intern/co-op in Canada, software/AI/data field)
      0 = irrelevant (senior roles, wrong location, wrong field)
     -1 = uncertain (skip)
    """
    t = title.lower()
    loc = location.lower()
    desc = (description or "").lower()[:500]
    combined = f"{t} {loc} {desc}"

    # ── Strong positive signals ──
    is_intern = any(w in t for w in ["intern", "co-op", "coop", "internship", "co-operative"])
    is_new_grad = any(w in t for w in ["new grad", "entry level", "junior"])
    is_tech = any(w in t for w in [
        "software", "developer", "engineer", "data", "machine learning",
        "ml", "ai", "python", "full-stack", "fullstack", "backend",
        "frontend", "devops", "sre", "analyst", "scientist",
    ])
    in_canada = any(w in loc for w in ["canada", "vancouver", "bc", "toronto", "montreal", "remote"])

    # ── Strong negative signals ──
    is_senior = any(w in t for w in [
        "senior", "staff", "principal", "director", "manager",
        "lead", "head of", "vp ", "chief",
    ])

    # ── Decision logic ──
    if is_intern and is_tech and in_canada and not is_senior:
        return 1  # Perfect match
    if is_intern and is_tech and not is_senior:
        return 1  # Intern + tech is always good
    if is_senior:
        return 0  # Definitely not
    if not is_tech:
        return 0  # Wrong field
    if is_new_grad and is_tech:
        return 1  # New grad in tech is good

    return -1  # Uncertain, skip


def main():
    if not os.path.exists(DB_PATH):
        print(f"❌ Database not found at {DB_PATH}")
        print("   Run 'python main.py' first to scrape some jobs.")
        return

    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT title, company, location, description FROM jobs"
    ).fetchall()
    conn.close()

    if not rows:
        print("❌ No jobs in database. Run 'python main.py' first.")
        return

    labeled = {"positive": 0, "negative": 0, "skipped": 0}

    with open(OUTPUT_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["text", "label"])

        for title, company, location, description in rows:
            label = auto_label(title, location or "", description or "")

            if label == -1:
                labeled["skipped"] += 1
                continue

            text = f"{title} {company} {location} {(description or '')[:500]}".lower().strip()
            writer.writerow([text, label])

            if label == 1:
                labeled["positive"] += 1
            else:
                labeled["negative"] += 1

    total = labeled["positive"] + labeled["negative"]
    print(f"✅ Generated {OUTPUT_PATH} with {total} labeled samples:")
    print(f"   Positive (relevant):   {labeled['positive']}")
    print(f"   Negative (irrelevant): {labeled['negative']}")
    print(f"   Skipped (uncertain):   {labeled['skipped']}")

    if total < 10:
        print(f"\n⚠️  Only {total} samples — ML model needs at least 10.")
        print("   The scorer will use cosine-similarity fallback until you have more data.")
    else:
        print(f"\n🎉 Ready to train! Run:")
        print(f"   python -c \"from ml_scorer import MLScorer; MLScorer()\"")


if __name__ == "__main__":
    main()
