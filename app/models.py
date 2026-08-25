import json
from datetime import date, datetime

from .database import get_db


# --- Activity CRUD ---


def create_activity(activity_date, activity_type, duration_minutes=None,
                    distance_km=None, calories=None, notes=None, details=None):
    """Create a new activity record. Returns the new activity's ID."""
    db = get_db()
    details_json = json.dumps(details) if details else "{}"
    cursor = db.execute(
        """INSERT INTO activities (activity_date, activity_type, duration_minutes,
           distance_km, calories, notes, details)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (activity_date, activity_type, duration_minutes, distance_km,
         calories, notes, details_json),
    )
    db.commit()
    return cursor.lastrowid


def get_activities(activity_type=None, date_from=None, date_to=None,
                   limit=20, offset=0):
    """Get activities with optional filters. Returns list of Row objects."""
    db = get_db()
    query = "SELECT * FROM activities WHERE 1=1"
    params = []

    if activity_type:
        query += " AND activity_type = ?"
        params.append(activity_type)
    if date_from:
        query += " AND activity_date >= ?"
        params.append(date_from)
    if date_to:
        query += " AND activity_date <= ?"
        params.append(date_to)

    query += " ORDER BY activity_date DESC, created_at DESC"
    query += " LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    rows = db.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def count_activities(activity_type=None, date_from=None, date_to=None):
    """Count activities matching filters (for pagination)."""
    db = get_db()
    query = "SELECT COUNT(*) FROM activities WHERE 1=1"
    params = []

    if activity_type:
        query += " AND activity_type = ?"
        params.append(activity_type)
    if date_from:
        query += " AND activity_date >= ?"
        params.append(date_from)
    if date_to:
        query += " AND activity_date <= ?"
        params.append(date_to)

    return db.execute(query, params).fetchone()[0]


def get_activity_by_id(activity_id):
    """Get a single activity by ID. Returns dict or None."""
    db = get_db()
    row = db.execute(
        "SELECT * FROM activities WHERE id = ?", (activity_id,)
    ).fetchone()
    if row is None:
        return None
    activity = dict(row)
    # Parse the JSON details for convenience
    activity["details_parsed"] = json.loads(activity.get("details") or "{}")
    return activity


def delete_activity(activity_id):
    """Delete an activity by ID. Returns True if deleted, False if not found."""
    db = get_db()
    cursor = db.execute("DELETE FROM activities WHERE id = ?", (activity_id,))
    db.commit()
    return cursor.rowcount > 0


# --- Exercise Types ---


def get_exercise_types():
    """Get all exercise types, ordered: defaults first, then custom alphabetically."""
    db = get_db()
    rows = db.execute(
        "SELECT * FROM exercise_types ORDER BY is_default DESC, name ASC"
    ).fetchall()
    return [dict(row) for row in rows]


def get_exercise_type_by_name(name):
    """Get a single exercise type by name."""
    db = get_db()
    row = db.execute(
        "SELECT * FROM exercise_types WHERE name = ?", (name,)
    ).fetchone()
    if row is None:
        return None
    result = dict(row)
    result["fields_parsed"] = json.loads(result.get("fields") or "[]")
    return result


def create_exercise_type(name, category, fields):
    """Create a custom exercise type. Returns the new ID."""
    db = get_db()
    fields_json = json.dumps(fields) if isinstance(fields, list) else fields
    cursor = db.execute(
        "INSERT INTO exercise_types (name, category, fields, is_default) VALUES (?, ?, ?, 0)",
        (name.lower().strip(), category, fields_json),
    )
    db.commit()
    return cursor.lastrowid


def delete_exercise_type(type_id):
    """Delete a custom exercise type. Refuses to delete defaults. Returns True/False."""
    db = get_db()
    cursor = db.execute(
        "DELETE FROM exercise_types WHERE id = ? AND is_default = 0", (type_id,)
    )
    db.commit()
    return cursor.rowcount > 0
