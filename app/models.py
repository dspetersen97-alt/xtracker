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
                    max_elevation_m=None, person=None,
                    person_weight_kg=None, person_sex=None, person_birth_year=None,
                    weather_temp_c=None, weather_humidity=None):
    """Create a new activity record. Returns the new activity's ID."""
    db = get_db()
    details_json = json.dumps(details) if details else "{}"
    cursor = db.execute(
        """INSERT INTO activities (activity_date, activity_type, title,
           duration_minutes, distance_km, calories, avg_hr, max_hr,
           avg_pace_sec_per_km, best_pace_sec_per_km, total_ascent_m,
           total_descent_m, steps, elapsed_time_minutes, min_elevation_m,
           max_elevation_m, notes, details, person,
           person_weight_kg, person_sex, person_birth_year,
           weather_temp_c, weather_humidity)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (activity_date, activity_type, title, duration_minutes, distance_km,
         calories, avg_hr, max_hr, avg_pace_sec_per_km, best_pace_sec_per_km,
         total_ascent_m, total_descent_m, steps, elapsed_time_minutes,
         min_elevation_m, max_elevation_m, notes, details_json, person,
         person_weight_kg, person_sex, person_birth_year,
         weather_temp_c, weather_humidity),
    )
    db.commit()
    activity_id = cursor.lastrowid

    # Compute and persist the XP score now so views can read it directly.
    recompute_activity_score(activity_id)
    return activity_id


def _score_fields_from_row(row):
    """Build the (activity_data, person_profile) inputs that score_activity
    needs from a stored activity row (dict or sqlite3.Row)."""
    get = row.get if isinstance(row, dict) else (lambda k: row[k])
    activity_data = {
        "activity_type": get("activity_type"),
        "distance_km": get("distance_km"),
        "total_ascent_m": get("total_ascent_m"),
        "duration_minutes": get("duration_minutes"),
        "avg_hr": get("avg_hr"),
        "calories": get("calories"),
        "weather_temp_c": get("weather_temp_c"),
        "weather_humidity": get("weather_humidity"),
    }
    person_profile = {
        "weight_kg": get("person_weight_kg"),
        "sex": get("person_sex"),
        "birth_year": get("person_birth_year"),
    }
    return activity_data, person_profile


def set_activity_score(activity_id, score, weather_multiplier):
    """Persist a computed score and weather multiplier onto an activity row."""
    db = get_db()
    db.execute(
        "UPDATE activities SET score = ?, weather_multiplier = ? WHERE id = ?",
        (score, weather_multiplier, activity_id),
    )
    db.commit()


def recompute_activity_score(activity_id):
    """Recompute and persist an activity's score from its stored snapshot.

    Returns the final score (or None if the activity is not scoreable /
    not found).
    """
    from .scoring import score_activity

    db = get_db()
    row = db.execute("SELECT * FROM activities WHERE id = ?", (activity_id,)).fetchone()
    if row is None:
        return None

    activity_data, person_profile = _score_fields_from_row(row)
    result = score_activity(activity_data, person_profile)

    score = result["final_score"] if result else None
    weather_mult = result["weather_multiplier"] if result else None
    set_activity_score(activity_id, score, weather_mult)
    return score


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


def _parse_exercise_type(row):
    """Convert an exercise_types Row into a dict with parsed skills/fields."""
    result = dict(row)
    result["skills_parsed"] = json.loads(result.get("skills") or "{}")
    result["fields_parsed"] = json.loads(result.get("fields") or "[]")
    return result


def get_exercise_types():
    """Get all exercise types, ordered: defaults first, then custom alphabetically."""
    db = get_db()
    rows = db.execute(
        "SELECT * FROM exercise_types ORDER BY is_default DESC, name ASC"
    ).fetchall()
    return [_parse_exercise_type(row) for row in rows]


def get_exercise_type_by_name(name):
    """Get a single exercise type by name."""
    db = get_db()
    row = db.execute(
        "SELECT * FROM exercise_types WHERE name = ?", (name,)
    ).fetchone()
    if row is None:
        return None
    return _parse_exercise_type(row)


def create_exercise_type(name, skills, fields):
    """Create a custom exercise type. Returns the new ID.

    `skills` is a dict mapping skill name -> percentage (e.g.
    {"cardio": 75, "endurance": 25}). It is stored as JSON.
    """
    db = get_db()
    fields_json = json.dumps(fields) if isinstance(fields, list) else fields
    skills_json = json.dumps(skills) if isinstance(skills, dict) else skills
    cursor = db.execute(
        "INSERT INTO exercise_types (name, skills, fields, is_default) VALUES (?, ?, ?, 0)",
        (name.lower().strip(), skills_json, fields_json),
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



def update_activity(activity_id, **kwargs):
    """Update an activity's fields. Pass column=value pairs as kwargs."""
    db = get_db()
    allowed = {
        "activity_date", "activity_type", "title", "duration_minutes",
        "distance_km", "calories", "avg_hr", "max_hr",
        "avg_pace_sec_per_km", "best_pace_sec_per_km",
        "total_ascent_m", "total_descent_m", "steps",
        "elapsed_time_minutes", "min_elevation_m", "max_elevation_m",
        "notes", "details", "person",
        "person_weight_kg", "person_sex", "person_birth_year",
        "weather_temp_c", "weather_humidity",
    }
    fields = []
    params = []
    for key, value in kwargs.items():
        if key in allowed:
            fields.append(f"{key} = ?")
            params.append(value)
    if not fields:
        return
    params.append(activity_id)
    db.execute(f"UPDATE activities SET {', '.join(fields)} WHERE id = ?", params)
    db.commit()

    # Any scoring-relevant field may have changed; recompute the stored score.
    recompute_activity_score(activity_id)



# --- Daily Health ---


def upsert_daily_health(date_str, person, **kwargs):
    """Insert or update a daily health record.
    Uses UPSERT (INSERT OR REPLACE) keyed on (date, person).
    """
    db = get_db()
    # Only steps and weight are synced. Other daily_health columns remain in
    # the schema for backward compatibility but are no longer written.
    allowed = {"steps", "weight_kg"}

    # Get existing record to preserve fields not being updated
    existing = get_daily_health(date_str, person)

    fields = {"date": date_str, "person": person}
    for key, value in kwargs.items():
        if key in allowed:
            fields[key] = value

    # Merge with existing data (don't overwrite with None)
    if existing:
        for key in allowed:
            if key not in fields or fields.get(key) is None:
                fields[key] = existing.get(key)

    columns = list(fields.keys())
    placeholders = ", ".join(["?"] * len(columns))
    col_names = ", ".join(columns)

    db.execute(
        f"INSERT OR REPLACE INTO daily_health ({col_names}) VALUES ({placeholders})",
        [fields[c] for c in columns],
    )
    db.commit()


def get_daily_health(date_str, person):
    """Get a single daily health record. Returns dict or None."""
    db = get_db()
    row = db.execute(
        "SELECT * FROM daily_health WHERE date = ? AND person = ?",
        (date_str, person),
    ).fetchone()
    if row is None:
        return None
    return dict(row)


def get_daily_health_range(person, date_from, date_to):
    """Get daily health records for a person within a date range."""
    db = get_db()
    rows = db.execute(
        """SELECT * FROM daily_health
           WHERE person = ? AND date >= ? AND date <= ?
           ORDER BY date ASC""",
        (person, date_from, date_to),
    ).fetchall()
    return [dict(row) for row in rows]


def get_latest_weight(person):
    """Get the most recent weight entry for a person from daily_health."""
    db = get_db()
    row = db.execute(
        """SELECT weight_kg FROM daily_health
           WHERE person = ? AND weight_kg IS NOT NULL
           ORDER BY date DESC LIMIT 1""",
        (person,),
    ).fetchone()
    if row:
        return row["weight_kg"]
    return None
