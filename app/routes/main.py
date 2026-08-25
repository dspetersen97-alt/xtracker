import socket
from datetime import date, timedelta

from flask import Blueprint, jsonify, render_template

from ..database import get_db

main_bp = Blueprint("main", __name__)


def _get_lan_ip():
    """Get the machine's LAN IP address."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "localhost"


def _get_quick_stats():
    """Get quick stats for the home page."""
    db = get_db()
    today = date.today()
    week_start = (today - timedelta(days=today.weekday())).isoformat()

    # Workouts this week
    row = db.execute(
        "SELECT COUNT(*) as cnt FROM activities WHERE activity_date >= ?",
        (week_start,)
    ).fetchone()
    workouts_this_week = row["cnt"]

    # Total workouts
    row = db.execute("SELECT COUNT(*) as cnt FROM activities").fetchone()
    total_workouts = row["cnt"]

    # Total distance this week
    row = db.execute(
        "SELECT COALESCE(SUM(distance_km), 0) as total FROM activities WHERE activity_date >= ? AND distance_km IS NOT NULL",
        (week_start,)
    ).fetchone()
    distance_this_week = round(row["total"], 1)

    # Last workout
    row = db.execute(
        "SELECT activity_type, activity_date FROM activities ORDER BY activity_date DESC LIMIT 1"
    ).fetchone()
    last_workout = None
    if row:
        last_workout = {"type": row["activity_type"], "date": row["activity_date"]}

    return {
        "workouts_this_week": workouts_this_week,
        "total_workouts": total_workouts,
        "distance_this_week": distance_this_week,
        "last_workout": last_workout,
    }


@main_bp.route("/")
def index():
    stats = _get_quick_stats()
    lan_ip = _get_lan_ip()
    port = 5000
    return render_template("index.html", stats=stats, lan_ip=lan_ip, port=port)


@main_bp.route("/health")
def health():
    return jsonify({"status": "ok"})
