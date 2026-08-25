"""Garmin Connect sync module.

Authenticates with Garmin Connect using the garminconnect library,
fetches activities, and imports them into xtracker.

Credentials are stored encrypted in the database.
OAuth tokens are cached in the data directory for session reuse.
"""

import logging
import os
from datetime import date, datetime, timedelta

from .crypto import decrypt, encrypt
from .database import get_db
from .models import get_person_by_name, get_setting, set_setting

logger = logging.getLogger(__name__)

# Reuse the type mapping from the CSV importer
GARMIN_TYPE_MAP = {
    "running": "run",
    "trail_running": "run",
    "treadmill_running": "run",
    "walking": "walk",
    "hiking": "hike",
    "cycling": "cardio",
    "indoor_cycling": "cardio",
    "swimming": "cardio",
    "lap_swimming": "cardio",
    "open_water_swimming": "cardio",
    "elliptical": "cardio",
    "cardio": "cardio",
    "strength_training": "strength",
    "yoga": "cardio",
    "pilates": "cardio",
    "other": "cardio",
    "fitness_equipment": "cardio",
    "indoor_cardio": "cardio",
    "mountaineering": "hike",
    "rock_climbing": "strength",
}


def save_garmin_credentials(email, password):
    """Save Garmin credentials encrypted in the settings table."""
    set_setting("garmin_email", encrypt(email))
    set_setting("garmin_password", encrypt(password))


def get_garmin_credentials():
    """Retrieve and decrypt Garmin credentials.
    Returns (email, password) tuple, or (None, None) if not configured.
    """
    enc_email = get_setting("garmin_email")
    enc_password = get_setting("garmin_password")

    if not enc_email or not enc_password:
        return None, None

    email = decrypt(enc_email)
    password = decrypt(enc_password)

    if not email or not password:
        return None, None

    return email, password


def clear_garmin_credentials():
    """Remove stored Garmin credentials."""
    db = get_db()
    db.execute("DELETE FROM settings WHERE key IN ('garmin_email', 'garmin_password')")
    db.commit()


def get_last_sync_time():
    """Get the timestamp of the last successful sync."""
    val = get_setting("garmin_last_sync")
    if val:
        try:
            return datetime.fromisoformat(val)
        except ValueError:
            return None
    return None


def set_last_sync_time(dt=None):
    """Record the current time as last sync time."""
    if dt is None:
        dt = datetime.now()
    set_setting("garmin_last_sync", dt.isoformat())


def _get_token_dir():
    """Get the directory for storing Garmin OAuth tokens."""
    from flask import current_app
    token_dir = os.path.join(current_app.config["DATA_DIR"], ".garmin_tokens")
    os.makedirs(token_dir, exist_ok=True)
    return token_dir


def test_connection():
    """Test the Garmin connection with stored credentials.
    Returns (success: bool, message: str).
    """
    email, password = get_garmin_credentials()
    if not email or not password:
        return False, "No Garmin credentials configured."

    try:
        from garminconnect import (
            Garmin,
            GarminConnectAuthenticationError,
            GarminConnectConnectionError,
        )

        token_dir = _get_token_dir()
        garmin = Garmin(email=email, password=password)
        garmin.login(token_dir)

        # Quick test: fetch today's summary
        today = date.today().isoformat()
        garmin.get_user_summary(today)

        return True, "Connection successful."

    except GarminConnectAuthenticationError:
        return False, "Authentication failed. Check your email and password."
    except GarminConnectConnectionError as e:
        return False, f"Connection error: {str(e)}"
    except Exception as e:
        return False, f"Unexpected error: {str(e)}"


def sync_activities(person_name=None, days_back=30):
    """Sync activities from Garmin Connect.

    Args:
        person_name: Name of the person to associate activities with.
        days_back: How many days back to look for activities (default 30).

    Returns:
        dict with 'imported', 'skipped', 'errors' counts and list.
    """
    email, password = get_garmin_credentials()
    if not email or not password:
        return {"imported": 0, "skipped": 0, "errors": ["No Garmin credentials configured."]}

    try:
        from garminconnect import (
            Garmin,
            GarminConnectAuthenticationError,
            GarminConnectConnectionError,
        )

        token_dir = _get_token_dir()
        garmin = Garmin(email=email, password=password)
        garmin.login(token_dir)

    except GarminConnectAuthenticationError:
        return {"imported": 0, "skipped": 0, "errors": ["Authentication failed."]}
    except Exception as e:
        return {"imported": 0, "skipped": 0, "errors": [f"Connection failed: {str(e)}"]}

    # Determine date range
    end_date = date.today()
    start_date = end_date - timedelta(days=days_back)

    # Fetch activities from Garmin
    try:
        activities = garmin.get_activities_by_date(
            start_date.isoformat(), end_date.isoformat()
        )
    except Exception as e:
        return {"imported": 0, "skipped": 0, "errors": [f"Failed to fetch activities: {str(e)}"]}

    if not activities:
        return {"imported": 0, "skipped": 0, "errors": []}

    # Get person profile for snapshot
    person_profile = None
    if person_name:
        person_profile = get_person_by_name(person_name)

    # Get existing activity IDs to avoid duplicates
    db = get_db()
    existing_ids = _get_existing_garmin_ids(db)

    imported = 0
    skipped = 0
    errors = []

    for activity in activities:
        try:
            garmin_id = str(activity.get("activityId", ""))
            if garmin_id in existing_ids:
                skipped += 1
                continue

            if _import_garmin_activity(db, activity, person_name, person_profile, garmin_id):
                imported += 1
            else:
                skipped += 1
        except Exception as e:
            errors.append(f"Activity {activity.get('activityName', '?')}: {str(e)}")
            skipped += 1

    db.commit()
    set_last_sync_time()

    return {"imported": imported, "skipped": skipped, "errors": errors}


def _get_existing_garmin_ids(db):
    """Get set of Garmin activity IDs already in our database.
    Stored in the details JSON as 'garmin_id'.
    """
    rows = db.execute(
        "SELECT details FROM activities WHERE details LIKE '%garmin_id%'"
    ).fetchall()

    ids = set()
    import json
    for row in rows:
        try:
            details = json.loads(row["details"] or "{}")
            gid = details.get("garmin_id")
            if gid:
                ids.add(str(gid))
        except (json.JSONDecodeError, TypeError):
            continue
    return ids


def _import_garmin_activity(db, activity, person_name, person_profile, garmin_id):
    """Import a single Garmin activity into the database.
    Returns True if imported, False if skipped.
    """
    import json

    # Map activity type
    type_info = activity.get("activityType", {})
    type_key = type_info.get("typeKey", "other") if isinstance(type_info, dict) else "other"
    activity_type = GARMIN_TYPE_MAP.get(type_key, "cardio")

    # Date/time
    start_time = activity.get("startTimeLocal", "")
    if not start_time:
        return False

    # Title
    title = activity.get("activityName") or None

    # Duration (seconds -> minutes)
    duration_sec = activity.get("duration")
    duration_minutes = duration_sec / 60.0 if duration_sec else None

    # Elapsed time
    elapsed_sec = activity.get("elapsedDuration") or activity.get("duration")
    elapsed_time_minutes = elapsed_sec / 60.0 if elapsed_sec else None

    # Distance (meters -> km)
    distance_m = activity.get("distance")
    distance_km = distance_m / 1000.0 if distance_m else None

    # Calories
    calories = activity.get("calories")
    if calories:
        calories = int(calories)

    # Heart rate
    avg_hr = activity.get("averageHR")
    max_hr = activity.get("maxHR")
    if avg_hr:
        avg_hr = int(avg_hr)
    if max_hr:
        max_hr = int(max_hr)

    # Elevation
    elevation_gain = activity.get("elevationGain")
    elevation_loss = activity.get("elevationLoss")
    total_ascent_m = float(elevation_gain) if elevation_gain else None
    total_descent_m = float(elevation_loss) if elevation_loss else None

    # Pace (computed from distance and duration if available)
    avg_pace_sec_per_km = None
    if distance_km and distance_km > 0 and duration_minutes and duration_minutes > 0:
        avg_pace_sec_per_km = (duration_minutes * 60) / distance_km

    # Best pace from Garmin (maxSpeed is m/s)
    best_pace_sec_per_km = None
    max_speed = activity.get("maxSpeed")
    if max_speed and max_speed > 0:
        best_pace_sec_per_km = 1000.0 / max_speed  # seconds per km

    # Steps
    steps = activity.get("steps")
    if steps:
        steps = int(steps)

    # Person snapshot
    p_weight = person_profile["weight_kg"] if person_profile else None
    p_sex = person_profile["sex"] if person_profile else None
    p_birth_year = person_profile["birth_year"] if person_profile else None

    # Store garmin_id in details for deduplication
    details = json.dumps({"garmin_id": garmin_id})

    db.execute(
        """INSERT INTO activities (
            activity_date, activity_type, title, duration_minutes, distance_km,
            calories, avg_hr, max_hr, avg_pace_sec_per_km, best_pace_sec_per_km,
            total_ascent_m, total_descent_m, steps, elapsed_time_minutes,
            min_elevation_m, max_elevation_m, notes, details, person,
            person_weight_kg, person_sex, person_birth_year
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (start_time, activity_type, title, duration_minutes, distance_km,
         calories, avg_hr, max_hr, avg_pace_sec_per_km, best_pace_sec_per_km,
         total_ascent_m, total_descent_m, steps, elapsed_time_minutes,
         None, None, None, details, person_name,
         p_weight, p_sex, p_birth_year),
    )
    return True
