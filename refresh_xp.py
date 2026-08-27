"""CLI: Recompute and persist XP scores for all activities.

Activity XP is stored in the database (the `score` column) and normally
computed once at write time. Run this script after changing the scoring
formulas (in app/scoring.py) or skill distributions so every stored score
is brought back in sync with the current logic.

Usage:
    python refresh_xp.py
"""
from app import create_app
from app.config import get_config

app = create_app()

with app.app_context():
    from app.database import get_db
    from app.models import recompute_activity_score

    db = get_db()
    rows = db.execute("SELECT id FROM activities ORDER BY id").fetchall()
    total = len(rows)

    if total == 0:
        print("No activities found. Nothing to refresh.")
        raise SystemExit(0)

    print(f"Recomputing XP for {total} activities...")

    updated = 0
    scored = 0
    for i, row in enumerate(rows, 1):
        score = recompute_activity_score(row["id"])
        updated += 1
        if score is not None:
            scored += 1
        if i % 100 == 0 or i == total:
            print(f"  {i}/{total} processed")

    print(
        f"Done. Refreshed {updated} activities "
        f"({scored} scored, {updated - scored} not scoreable)."
    )
