"""CSV import for Garmin Connect exports."""
import csv
import io

from .database import get_db
from .units import (
    feet_to_meters,
    miles_to_km,
    pace_per_mile_to_per_km,
    parse_pace_string,
    parse_time_string,
)

# Map Garmin activity types to our internal types
GARMIN_TYPE_MAP = {
    "running": "run",
    "trail running": "run",
    "treadmill running": "run",
    "walking": "walk",
    "hiking": "hike",
    "cycling": "cardio",
    "indoor cycling": "cardio",
    "swimming": "cardio",
    "elliptical": "cardio",
    "cardio": "cardio",
    "strength training": "strength",
    "yoga": "cardio",
    "other": "cardio",
}


def _parse_float(value):
    """Parse a float value, returning None for empty or '--'."""
    if not value or value.strip() in ("--", ""):
        return None
    try:
        return float(value.strip().replace(",", ""))
    except ValueError:
        return None


def _parse_int(value):
    """Parse an int value, returning None for empty or '--'."""
    if not value or value.strip() in ("--", ""):
        return None
    try:
        return int(float(value.strip().replace(",", "")))
    except ValueError:
        return None


def import_garmin_csv(file_content, source_units="imperial"):
    """Import activities from a Garmin Connect CSV export.

    Args:
        file_content: String content of the CSV file.
        source_units: Unit system of the source data ('imperial' or 'metric').

    Returns:
        dict with 'imported' count, 'skipped' count, and 'errors' list.
    """
    db = get_db()
    reader = csv.DictReader(io.StringIO(file_content))

    imported = 0
    skipped = 0
    errors = []

    for i, row in enumerate(reader, start=2):
        try:
            result = _import_row(db, row, source_units)
            if result:
                imported += 1
            else:
                skipped += 1
        except Exception as e:
            errors.append(f"Row {i}: {str(e)}")
            skipped += 1

    db.commit()
    return {"imported": imported, "skipped": skipped, "errors": errors}


def _import_row(db, row, source_units):
    """Import a single CSV row. Returns True if imported, False if skipped."""
    # Activity type mapping
    raw_type = row.get("Activity Type", "").strip().lower()
    activity_type = GARMIN_TYPE_MAP.get(raw_type, raw_type)
    if not activity_type:
        return False

    # Date - extract just the date part from '2026-08-24 17:04:37'
    date_str = row.get("Date", "").strip()
    if not date_str:
        return False
    activity_date = date_str.split(" ")[0]

    # Title
    title = row.get("Title", "").strip() or None

    # Distance
    distance_raw = _parse_float(row.get("Distance", ""))
    if source_units == "imperial" and distance_raw is not None:
        distance_km = miles_to_km(distance_raw)
    else:
        distance_km = distance_raw

    # Calories
    calories = _parse_int(row.get("Calories", ""))

    # Time (moving time) -> duration_minutes
    time_str = row.get("Time", "").strip()
    duration_minutes = None
    if time_str and time_str != "--":
        parsed = parse_time_string(time_str)
        if parsed is not None:
            duration_minutes = round(parsed)

    # Elapsed Time
    elapsed_str = row.get("Elapsed Time", "").strip()
    elapsed_time_minutes = None
    if elapsed_str and elapsed_str != "--":
        elapsed_time_minutes = parse_time_string(elapsed_str)

    # Heart rate
    avg_hr = _parse_int(row.get("Avg HR", ""))
    max_hr = _parse_int(row.get("Max HR", ""))

    # Pace - stored as seconds per km internally
    avg_pace_str = row.get("Avg Pace", "").strip()
    best_pace_str = row.get("Best Pace", "").strip()

    avg_pace_sec = parse_pace_string(avg_pace_str)
    best_pace_sec = parse_pace_string(best_pace_str)

    if source_units == "imperial":
        avg_pace_sec_per_km = pace_per_mile_to_per_km(avg_pace_sec)
        best_pace_sec_per_km = pace_per_mile_to_per_km(best_pace_sec)
    else:
        avg_pace_sec_per_km = avg_pace_sec
        best_pace_sec_per_km = best_pace_sec

    # Elevation
    total_ascent_raw = _parse_float(row.get("Total Ascent", ""))
    total_descent_raw = _parse_float(row.get("Total Descent", ""))
    min_elevation_raw = _parse_float(row.get("Min Elevation", ""))
    max_elevation_raw = _parse_float(row.get("Max Elevation", ""))

    if source_units == "imperial":
        total_ascent_m = feet_to_meters(total_ascent_raw)
        total_descent_m = feet_to_meters(total_descent_raw)
        min_elevation_m = feet_to_meters(min_elevation_raw)
        max_elevation_m = feet_to_meters(max_elevation_raw)
    else:
        total_ascent_m = total_ascent_raw
        total_descent_m = total_descent_raw
        min_elevation_m = min_elevation_raw
        max_elevation_m = max_elevation_raw

    # Steps
    steps = _parse_int(row.get("Steps", ""))

    # Insert
    db.execute(
        """INSERT INTO activities (
            activity_date, activity_type, title, duration_minutes, distance_km,
            calories, avg_hr, max_hr, avg_pace_sec_per_km, best_pace_sec_per_km,
            total_ascent_m, total_descent_m, steps, elapsed_time_minutes,
            min_elevation_m, max_elevation_m, notes, details
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '{}')""",
        (activity_date, activity_type, title, duration_minutes, distance_km,
         calories, avg_hr, max_hr, avg_pace_sec_per_km, best_pace_sec_per_km,
         total_ascent_m, total_descent_m, steps, elapsed_time_minutes,
         min_elevation_m, max_elevation_m, None),
    )
    return True