"""Statistics and aggregation queries for progress charts."""
from datetime import date, timedelta

from .database import get_db


def _week_start(d):
    """Get Monday of the week containing date d."""
    return d - timedelta(days=d.weekday())


def _get_week_labels(weeks_back):
    """Generate list of week-start dates going back N weeks from today."""
    today = date.today()
    current_week = _week_start(today)
    return [current_week - timedelta(weeks=i) for i in range(weeks_back - 1, -1, -1)]


def workouts_per_week(weeks_back=12):
    """Count of workouts per week for the last N weeks.
    Returns dict with 'labels' (week start dates) and 'data' (counts).
    """
    db = get_db()
    weeks = _get_week_labels(weeks_back)
    start_date = weeks[0].isoformat()

    rows = db.execute("""
        SELECT activity_date, COUNT(*) as cnt
        FROM activities
        WHERE activity_date >= ?
        GROUP BY activity_date
    """, (start_date,)).fetchall()

    # Build a lookup: week_start -> count
    week_counts = {w: 0 for w in weeks}
    for row in rows:
        d = date.fromisoformat(row["activity_date"])
        ws = _week_start(d)
        if ws in week_counts:
            week_counts[ws] += row["cnt"]

    return {
        "labels": [w.strftime("%b %d") for w in weeks],
        "data": [week_counts[w] for w in weeks],
    }


def distance_per_week(weeks_back=12):
    """Total distance (km) per week for distance-based activities.
    Returns dict with 'labels' and 'data'.
    """
    db = get_db()
    weeks = _get_week_labels(weeks_back)
    start_date = weeks[0].isoformat()

    rows = db.execute("""
        SELECT activity_date, SUM(distance_km) as total_dist
        FROM activities
        WHERE activity_date >= ? AND distance_km IS NOT NULL AND distance_km > 0
        GROUP BY activity_date
    """, (start_date,)).fetchall()

    week_totals = {w: 0.0 for w in weeks}
    for row in rows:
        d = date.fromisoformat(row["activity_date"])
        ws = _week_start(d)
        if ws in week_totals:
            week_totals[ws] += row["total_dist"] or 0

    return {
        "labels": [w.strftime("%b %d") for w in weeks],
        "data": [round(week_totals[w], 1) for w in weeks],
    }


def duration_per_week(weeks_back=12):
    """Total duration (minutes) per week.
    Returns dict with 'labels' and 'data'.
    """
    db = get_db()
    weeks = _get_week_labels(weeks_back)
    start_date = weeks[0].isoformat()

    rows = db.execute("""
        SELECT activity_date, SUM(duration_minutes) as total_dur
        FROM activities
        WHERE activity_date >= ? AND duration_minutes IS NOT NULL
        GROUP BY activity_date
    """, (start_date,)).fetchall()

    week_totals = {w: 0 for w in weeks}
    for row in rows:
        d = date.fromisoformat(row["activity_date"])
        ws = _week_start(d)
        if ws in week_totals:
            week_totals[ws] += row["total_dur"] or 0

    return {
        "labels": [w.strftime("%b %d") for w in weeks],
        "data": [week_totals[w] for w in weeks],
    }


def activity_type_breakdown(weeks_back=12):
    """Count of activities by type over the last N weeks.
    Returns dict with 'labels' (type names) and 'data' (counts).
    """
    db = get_db()
    weeks = _get_week_labels(weeks_back)
    start_date = weeks[0].isoformat()

    rows = db.execute("""
        SELECT activity_type, COUNT(*) as cnt
        FROM activities
        WHERE activity_date >= ?
        GROUP BY activity_type
        ORDER BY cnt DESC
    """, (start_date,)).fetchall()

    return {
        "labels": [row["activity_type"].capitalize() for row in rows],
        "data": [row["cnt"] for row in rows],
    }


def get_summary_stats(weeks_back=12):
    """Get all summary chart data in one call."""
    return {
        "workouts_per_week": workouts_per_week(weeks_back),
        "distance_per_week": distance_per_week(weeks_back),
        "duration_per_week": duration_per_week(weeks_back),
        "type_breakdown": activity_type_breakdown(weeks_back),
    }


# --- Per-type drill-down stats ---


def distance_over_time(activity_type, weeks_back=12):
    """Get distance per session over time for a specific activity type.
    Returns dict with 'labels' (dates) and 'data' (distances).
    """
    db = get_db()
    weeks = _get_week_labels(weeks_back)
    start_date = weeks[0].isoformat()

    rows = db.execute("""
        SELECT activity_date, distance_km
        FROM activities
        WHERE activity_type = ? AND activity_date >= ?
              AND distance_km IS NOT NULL AND distance_km > 0
        ORDER BY activity_date ASC
    """, (activity_type, start_date)).fetchall()

    return {
        "labels": [row["activity_date"] for row in rows],
        "data": [round(row["distance_km"], 2) for row in rows],
    }


def pace_over_time(activity_type, weeks_back=12):
    """Get pace (min/km) per session over time.
    Only includes sessions with both distance and duration.
    Returns dict with 'labels' (dates) and 'data' (pace values).
    """
    db = get_db()
    weeks = _get_week_labels(weeks_back)
    start_date = weeks[0].isoformat()

    rows = db.execute("""
        SELECT activity_date, duration_minutes, distance_km
        FROM activities
        WHERE activity_type = ? AND activity_date >= ?
              AND distance_km IS NOT NULL AND distance_km > 0
              AND duration_minutes IS NOT NULL AND duration_minutes > 0
        ORDER BY activity_date ASC
    """, (activity_type, start_date)).fetchall()

    labels = []
    data = []
    for row in rows:
        pace = row["duration_minutes"] / row["distance_km"]
        labels.append(row["activity_date"])
        data.append(round(pace, 2))

    return {"labels": labels, "data": data}


def duration_over_time(activity_type, weeks_back=12):
    """Get duration per session over time for a specific type.
    Returns dict with 'labels' (dates) and 'data' (minutes).
    """
    db = get_db()
    weeks = _get_week_labels(weeks_back)
    start_date = weeks[0].isoformat()

    rows = db.execute("""
        SELECT activity_date, duration_minutes
        FROM activities
        WHERE activity_type = ? AND activity_date >= ?
              AND duration_minutes IS NOT NULL
        ORDER BY activity_date ASC
    """, (activity_type, start_date)).fetchall()

    return {
        "labels": [row["activity_date"] for row in rows],
        "data": [row["duration_minutes"] for row in rows],
    }


def strength_exercise_names(weeks_back=26):
    """Get distinct exercise names from strength activities.
    Extracts from JSON details.exercises[].name.
    """
    import json
    db = get_db()
    weeks = _get_week_labels(weeks_back)
    start_date = weeks[0].isoformat()

    rows = db.execute("""
        SELECT details
        FROM activities
        WHERE activity_type = 'strength' AND activity_date >= ?
              AND details IS NOT NULL AND details != '{}'
    """, (start_date,)).fetchall()

    names = set()
    for row in rows:
        try:
            details = json.loads(row["details"])
            for ex in details.get("exercises", []):
                if ex.get("name"):
                    names.add(ex["name"].strip().lower())
        except (json.JSONDecodeError, TypeError):
            continue

    return sorted(names)


def strength_exercise_progression(exercise_name, weeks_back=26):
    """Get weight and volume progression for a specific strength exercise.
    Returns dict with 'labels' (dates), 'weight' (max weight per session),
    and 'volume' (total sets*reps*weight per session).
    """
    import json
    db = get_db()
    weeks = _get_week_labels(weeks_back)
    start_date = weeks[0].isoformat()

    rows = db.execute("""
        SELECT activity_date, details
        FROM activities
        WHERE activity_type = 'strength' AND activity_date >= ?
              AND details IS NOT NULL AND details != '{}'
        ORDER BY activity_date ASC
    """, (start_date,)).fetchall()

    labels = []
    weights = []
    volumes = []
    exercise_lower = exercise_name.strip().lower()

    for row in rows:
        try:
            details = json.loads(row["details"])
        except (json.JSONDecodeError, TypeError):
            continue

        session_max_weight = 0
        session_volume = 0
        found = False

        for ex in details.get("exercises", []):
            if ex.get("name", "").strip().lower() == exercise_lower:
                found = True
                w = ex.get("weight_kg", 0) or 0
                s = ex.get("sets", 0) or 0
                r = ex.get("reps", 0) or 0
                session_max_weight = max(session_max_weight, w)
                session_volume += s * r * w

        if found:
            labels.append(row["activity_date"])
            weights.append(round(session_max_weight, 1))
            volumes.append(round(session_volume, 1))

    return {
        "labels": labels,
        "weight": weights,
        "volume": volumes,
    }


def get_type_stats(activity_type, weeks_back=12):
    """Get all per-type chart data in one call."""
    if activity_type == "strength":
        exercises = strength_exercise_names(weeks_back)
        return {
            "type": "strength",
            "exercises": exercises,
            "duration": duration_over_time(activity_type, weeks_back),
        }
    else:
        return {
            "type": activity_type,
            "distance": distance_over_time(activity_type, weeks_back),
            "pace": pace_over_time(activity_type, weeks_back),
            "duration": duration_over_time(activity_type, weeks_back),
        }
