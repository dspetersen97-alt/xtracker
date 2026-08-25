import json
from datetime import date, datetime

from .database import get_db


# --- Activity CRUD ---


def create_activity(activity_date, activity_type, duration_minutes=None,
                    distance_km=None, calories=None, notes=None, details=None,
                    title=None, avg_hr=None, max_hr=None,
                    avg_pace_sec_per_km=None, best_pace_sec_per_km=None,
                    total_ascent_m=None, total_descent_m=None, steps=None,
                    elapsed_time_minutes=None, min_elevation_m=None,
                    max_elevation_m=None, person=None):
    """Create a new activity record. Returns the new activity's ID."""
    db = get_db()
    details_json = json.dumps(details) if details else "{}"
    cursor = db.execute(
        """INSERT INTO activities (activity_date, activity_type, title,
           duration_minutes, distance_km, calories, avg_hr, max_hr,
           avg_pace_sec_per_km, best_pace_sec_per_km, total_ascent_m,
           total_descent_m, steps, elapsed_time_minutes, min_elevation_m,
           max_elevation_m, notes, details, person)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (activity_date, activity_type, title, duration_minutes, distance_km,
         calories, avg_hr, max_hr, avg_pace_sec_per_km, best_pace_sec_per_km,
         total_ascent_m, total_descent_m, steps, elapsed_time_minutes,
         min_elevation_m, max_elevation_m, notes, details_json, person),
    )
    db.commit()
    return cursor.lastrowid


def get_activities(activity_type=None, date_from=None, date_to=None,
                   person=None, limit=20, offset=0):
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
    if person:
        query += " AND person = ?"
        params.append(person)

    query += " ORDER BY activity_date DESC, created_at DESC"
    query += " LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    rows = db.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def count_activities(activity_type=None, date_from=None, date_to=None, person=None):
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
    if person:
        query += " AND person = ?"
        params.append(person)

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


# --- Settings ---


def get_setting(key, default=None):
    """Get a setting value by key."""
    db = get_db()
    row = db.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    if row is None:
        return default
    return row["value"]


def set_setting(key, value):
    """Set a setting value (upsert)."""
    db = get_db()
    db.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
        (key, value),
    )
    db.commit()


def get_units():
    """Get the current unit preference ('metric' or 'imperial')."""
    return get_setting("units", "metric")


def set_units(units):
    """Set the unit preference."""
    if units not in ("metric", "imperial"):
        raise ValueError("Units must be 'metric' or 'imperial'")
    set_setting("units", units)

# --- People ---


def get_people():
    """Get all people, ordered alphabetically."""
    db = get_db()
    rows = db.execute("SELECT * FROM people ORDER BY name ASC").fetchall()
    return [dict(row) for row in rows]


def get_person_by_name(name):
    """Get a person by name. Returns dict or None."""
    db = get_db()
    row = db.execute("SELECT * FROM people WHERE name = ?", (name,)).fetchone()
    if row is None:
        return None
    return dict(row)


def create_person(name, weight_kg=None, height_cm=None, sex=None, birth_year=None):
    """Create a new person with optional profile. Returns the new ID."""
    db = get_db()
    cursor = db.execute(
        "INSERT OR IGNORE INTO people (name, weight_kg, height_cm, sex, birth_year) VALUES (?, ?, ?, ?, ?)",
        (name.strip(), weight_kg, height_cm, sex, birth_year),
    )
    db.commit()
    return cursor.lastrowid


def update_person(person_id, name=None, weight_kg=None, height_cm=None, sex=None, birth_year=None):
    """Update a person's profile."""
    db = get_db()
    fields = []
    params = []
    if name is not None:
        fields.append("name = ?")
        params.append(name.strip())
    if weight_kg is not None:
        fields.append("weight_kg = ?")
        params.append(weight_kg)
    if height_cm is not None:
        fields.append("height_cm = ?")
        params.append(height_cm)
    if sex is not None:
        fields.append("sex = ?")
        params.append(sex)
    if birth_year is not None:
        fields.append("birth_year = ?")
        params.append(birth_year)
    if not fields:
        return
    params.append(person_id)
    db.execute(f"UPDATE people SET {', '.join(fields)} WHERE id = ?", params)
    db.commit()


def delete_person(person_id):
    """Delete a person. Returns True if deleted."""
    db = get_db()
    cursor = db.execute("DELETE FROM people WHERE id = ?", (person_id,))
    db.commit()
    return cursor.rowcount > 0



def update_activity_score(activity_id, score, weather_temp_c=None,
                          weather_humidity=None, weather_multiplier=None):
    """Update the score and weather data for an activity."""
    db = get_db()
    db.execute(
        """UPDATE activities SET score = ?, weather_temp_c = ?,
           weather_humidity = ?, weather_multiplier = ? WHERE id = ?""",
        (score, weather_temp_c, weather_humidity, weather_multiplier, activity_id),
    )
    db.commit()
