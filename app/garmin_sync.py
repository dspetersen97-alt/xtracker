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
    "yoga": "yoga",
    "pilates": "pilates",
    "other": "cardio",
    "fitness_equipment": "cardio",
    "indoor_cardio": "cardio",
    "mountaineering": "hike",
    "rock_climbing": "strength",
}

# Keywords found in an activity Title that override the mapped type.
# Garmin often labels yoga/pilates sessions as generic cardio, so we
# recover the real type from the title text.
TITLE_TYPE_OVERRIDES = {
    "yoga": "yoga",
    "pilates": "pilates",
}


def resolve_activity_type(type_key, title):
    """Resolve the internal activity type from a Garmin type key and title.

    The title takes precedence for known keywords (e.g. a session titled
    "Yoga" becomes "yoga" even if Garmin categorized it as cardio).
    """
    if title:
        lowered = title.lower()
        for keyword, mapped in TITLE_TYPE_OVERRIDES.items():
            if keyword in lowered:
                return mapped
    return GARMIN_TYPE_MAP.get(type_key, "cardio")


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

            if _import_garmin_activity(db, activity, person_name, person_profile, garmin_id, garmin):
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


def _import_garmin_activity(db, activity, person_name, person_profile, garmin_id, garmin=None):
    """Import a single Garmin activity into the database.
    Returns True if imported, False if skipped.

    If a `garmin` client is provided, weather is fetched inline for outdoor
    activities (run/walk/hike) at import time.
    """
    import json

    # Title
    title = activity.get("activityName") or None

    # Map activity type (title can override the Garmin category)
    type_info = activity.get("activityType", {})
    type_key = type_info.get("typeKey", "other") if isinstance(type_info, dict) else "other"
    activity_type = resolve_activity_type(type_key, title)

    # Date/time
    start_time = activity.get("startTimeLocal", "")
    if not start_time:
        return False

    # Duration (seconds -> minutes), rounded to 2 decimals
    duration_sec = activity.get("duration")
    duration_minutes = round(duration_sec / 60.0, 2) if duration_sec else None

    # Elapsed time, rounded to 2 decimals
    elapsed_sec = activity.get("elapsedDuration") or activity.get("duration")
    elapsed_time_minutes = round(elapsed_sec / 60.0, 2) if elapsed_sec else None

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

    # GPS coordinates
    start_lat = activity.get("startLatitude")
    start_lng = activity.get("startLongitude")

    # Person snapshot
    p_weight = person_profile["weight_kg"] if person_profile else None
    p_sex = person_profile["sex"] if person_profile else None
    p_birth_year = person_profile["birth_year"] if person_profile else None

    # Store garmin_id in details for deduplication
    details = json.dumps({"garmin_id": garmin_id})

    # Weather (inline, for outdoor activities only)
    weather_temp_c = None
    weather_humidity = None
    if garmin is not None and activity_type in ("run", "walk", "hike"):
        weather_temp_c, weather_humidity = _fetch_activity_weather(garmin, garmin_id)

    # Compute the XP score now so it can be stored with the row (avoids a
    # separate recompute pass and per-request re-scoring later).
    score, weather_multiplier = _compute_import_score(
        activity_type, distance_km, total_ascent_m, duration_minutes,
        avg_hr, calories, weather_temp_c, weather_humidity,
        p_weight, p_sex, p_birth_year,
    )

    db.execute(
        """INSERT INTO activities (
            activity_date, activity_type, title, duration_minutes, distance_km,
            calories, avg_hr, max_hr, avg_pace_sec_per_km, best_pace_sec_per_km,
            total_ascent_m, total_descent_m, steps, elapsed_time_minutes,
            min_elevation_m, max_elevation_m, notes, details, person,
            person_weight_kg, person_sex, person_birth_year,
            start_latitude, start_longitude, weather_temp_c, weather_humidity,
            score, weather_multiplier
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (start_time, activity_type, title, duration_minutes, distance_km,
         calories, avg_hr, max_hr, avg_pace_sec_per_km, best_pace_sec_per_km,
         total_ascent_m, total_descent_m, steps, elapsed_time_minutes,
         None, None, None, details, person_name,
         p_weight, p_sex, p_birth_year,
         start_lat, start_lng, weather_temp_c, weather_humidity,
         score, weather_multiplier),
    )
    return True


def _compute_import_score(activity_type, distance_km, total_ascent_m,
                          duration_minutes, avg_hr, calories,
                          weather_temp_c, weather_humidity,
                          weight_kg, sex, birth_year):
    """Compute (score, weather_multiplier) for a row being imported.
    Returns (None, None) if the activity is not scoreable.
    """
    from .scoring import score_activity

    activity_data = {
        "activity_type": activity_type,
        "distance_km": distance_km,
        "total_ascent_m": total_ascent_m,
        "duration_minutes": duration_minutes,
        "avg_hr": avg_hr,
        "calories": calories,
        "weather_temp_c": weather_temp_c,
        "weather_humidity": weather_humidity,
    }
    person_profile = {"weight_kg": weight_kg, "sex": sex, "birth_year": birth_year}
    result = score_activity(activity_data, person_profile)
    if not result:
        return None, None
    return result["final_score"], result["weather_multiplier"]


def _fetch_activity_weather(garmin, garmin_id):
    """Fetch weather for a single activity. Returns (temp_c, humidity) or
    (None, None) on any failure. Temperatures that look like Fahrenheit are
    converted to Celsius.
    """
    try:
        weather = garmin.get_activity_weather(str(garmin_id))
    except Exception as e:
        logger.warning(f"Weather fetch failed for activity {garmin_id}: {e}")
        return None, None

    if not weather:
        return None, None

    temp = weather.get("temp")
    if temp is None:
        temp = weather.get("temperature")
    humidity = weather.get("relativeHumidity")
    if humidity is None:
        humidity = weather.get("humidity")

    temp_c = None
    if temp is not None:
        try:
            temp = float(temp)
            # Garmin returns temp in user display units. A value above 55 is
            # almost certainly Fahrenheit (reasonable outdoor C is -50..55).
            if temp > 55:
                temp = (temp - 32) * 5 / 9
            temp_c = round(temp, 1)
        except (ValueError, TypeError):
            temp_c = None

    humidity_val = None
    if humidity is not None:
        try:
            humidity_val = float(humidity)
        except (ValueError, TypeError):
            humidity_val = None

    return temp_c, humidity_val



def sync_daily_health(person_name, days_back=30):
    """Sync daily health metrics (steps and weight) from Garmin Connect.

    Uses range endpoints instead of per-day calls: steps and weight are each
    fetched for the whole window in a single library call (the steps endpoint
    internally chunks into 28-day windows), then merged by date. This replaces
    the old ~5-calls-per-day loop.

    Args:
        person_name: Name of the person to associate data with.
        days_back: How many days back to sync.

    Returns:
        dict with 'synced' (days count), 'errors' list.
    """
    from .models import upsert_daily_health

    email, password = get_garmin_credentials()
    if not email or not password:
        return {"synced": 0, "errors": ["No Garmin credentials configured."]}

    if not person_name:
        return {"synced": 0, "errors": ["Person name is required for health sync."]}

    try:
        from garminconnect import Garmin

        token_dir = _get_token_dir()
        garmin = Garmin(email=email, password=password)
        garmin.login(token_dir)

    except Exception as e:
        return {"synced": 0, "errors": [f"Connection failed: {str(e)}"]}

    end_date = date.today()
    start_date = end_date - timedelta(days=days_back)
    start_str = start_date.isoformat()
    end_str = end_date.isoformat()

    errors = []

    # Accumulate per-date data: {date_str: {"steps": ..., "weight_kg": ...}}
    by_date = {}

    # --- Steps for the whole range (one library call) ---
    _set_sync_status("Fetching steps...")
    try:
        steps_rows = garmin.get_daily_steps(start_str, end_str) or []
        for row in steps_rows:
            d = row.get("calendarDate") or row.get("date")
            steps = row.get("totalSteps")
            if d and steps is not None:
                by_date.setdefault(d, {})["steps"] = int(steps)
    except Exception as e:
        errors.append(f"Steps: {str(e)}")

    # --- Weight for the whole range (one library call) ---
    _set_sync_status("Fetching weight...")
    try:
        for d, weight_kg in _extract_weights(garmin.get_body_composition(start_str, end_str)).items():
            by_date.setdefault(d, {})["weight_kg"] = weight_kg
    except Exception as e:
        errors.append(f"Weight: {str(e)}")

    # --- Merge and upsert ---
    _set_sync_status("Saving health data...")
    synced = 0
    for date_str, fields in by_date.items():
        cleaned = {k: v for k, v in fields.items() if v is not None}
        if not cleaned:
            continue
        try:
            upsert_daily_health(date_str, person_name, **cleaned)
            synced += 1
        except Exception as e:
            errors.append(f"{date_str}: {str(e)}")

    return {"synced": synced, "errors": errors}


def _extract_weights(body):
    """Extract {calendarDate: weight_kg} from a body-composition range response.

    Garmin returns weight in grams within a 'dateWeightList' (or similar).
    When multiple weigh-ins exist for a day, the last one wins. Defensive
    about the exact response shape.
    """
    result = {}
    if not body:
        return result

    entries = []
    if isinstance(body, dict):
        entries = (
            body.get("dateWeightList")
            or body.get("weightList")
            or body.get("dailyWeightSummaries")
            or []
        )
    elif isinstance(body, list):
        entries = body

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        d = entry.get("calendarDate") or entry.get("date")
        weight_g = entry.get("weight")
        # Some payloads nest the weight under a summary object
        if weight_g is None and isinstance(entry.get("latestWeight"), dict):
            weight_g = entry["latestWeight"].get("weight")
            d = d or entry["latestWeight"].get("calendarDate")
        if d and weight_g and weight_g > 0:
            # Normalize a full timestamp date to YYYY-MM-DD
            d = str(d)[:10]
            result[d] = weight_g / 1000.0  # grams to kg

    return result



# --- Sync progress tracking ---


def _set_sync_status(message):
    """Update the current sync status message (for UI polling)."""
    try:
        set_setting("_sync_status", message)
    except Exception:
        pass


def get_sync_status():
    """Get the current sync status message."""
    return get_setting("_sync_status", "")


def clear_sync_status():
    """Clear the sync status."""
    try:
        set_setting("_sync_status", "")
    except Exception:
        pass


def sync_all(person_name=None, days_back=30):
    """Unified sync: activities + health + weather, with progress reporting.

    This is the main entry point called by the sync-all route.
    """
    results = {"messages": [], "errors": []}

    # Step 1: Verify credentials are configured (each sub-step logs in itself)
    _set_sync_status("Connecting to Garmin...")
    email, password = get_garmin_credentials()
    if not email or not password:
        results["errors"].append("No Garmin credentials configured.")
        clear_sync_status()
        return results

    # Step 2: Sync activities (weather is fetched inline per activity)
    _set_sync_status("Fetching activities from Garmin...")
    act_result = sync_activities(person_name=person_name, days_back=days_back)
    if act_result["imported"] > 0:
        results["messages"].append(f"Synced {act_result['imported']} new activities.")
    if act_result["errors"]:
        results["errors"].extend(act_result["errors"][:3])

    # Step 3: Sync health data
    if person_name:
        _set_sync_status("Syncing daily health data...")
        from .models import upsert_daily_health as _upsert  # ensure import
        health_result = sync_daily_health(person_name=person_name, days_back=days_back)
        if health_result["synced"] > 0:
            results["messages"].append(f"Health data synced for {health_result['synced']} days.")
        if health_result["errors"]:
            results["errors"].extend(health_result["errors"][:3])

    # Done
    set_last_sync_time()
    _set_sync_status("Sync complete!")

    return results
