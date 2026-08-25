"""Unit conversion utilities.

All data is stored internally in metric (km, meters, sec/km).
This module provides conversion to/from imperial (miles, feet, sec/mile).
"""

# Distance
KM_PER_MILE = 1.609344
MILES_PER_KM = 1 / KM_PER_MILE

# Elevation
METERS_PER_FOOT = 0.3048
FEET_PER_METER = 1 / METERS_PER_FOOT


def miles_to_km(miles):
    if miles is None:
        return None
    return miles * KM_PER_MILE


def km_to_miles(km):
    if km is None:
        return None
    return km * MILES_PER_KM


def feet_to_meters(feet):
    if feet is None:
        return None
    return feet * METERS_PER_FOOT


def meters_to_feet(meters):
    if meters is None:
        return None
    return meters * FEET_PER_METER


def pace_per_mile_to_per_km(pace_sec_per_mile):
    if pace_sec_per_mile is None:
        return None
    return pace_sec_per_mile / KM_PER_MILE


def pace_per_km_to_per_mile(pace_sec_per_km):
    if pace_sec_per_km is None:
        return None
    return pace_sec_per_km * KM_PER_MILE


def parse_pace_string(pace_str):
    """Parse a pace string like '14:00' or '5:25' into total seconds."""
    if not pace_str or pace_str == "--":
        return None
    try:
        parts = pace_str.strip().split(":")
        if len(parts) == 2:
            minutes = int(parts[0])
            seconds = int(parts[1])
            return minutes * 60 + seconds
        elif len(parts) == 3:
            hours = int(parts[0])
            minutes = int(parts[1])
            seconds = int(parts[2])
            return hours * 3600 + minutes * 60 + seconds
    except (ValueError, IndexError):
        return None
    return None


def parse_time_string(time_str):
    """Parse a time string like '00:33:56' into total minutes (float)."""
    if not time_str or time_str == "--":
        return None
    try:
        parts = time_str.strip().split(":")
        if len(parts) == 3:
            hours = int(parts[0])
            minutes = int(parts[1])
            seconds = int(parts[2])
            return hours * 60 + minutes + seconds / 60.0
        elif len(parts) == 2:
            minutes = int(parts[0])
            seconds = int(parts[1])
            return minutes + seconds / 60.0
    except (ValueError, IndexError):
        return None
    return None


def format_pace(sec_per_unit):
    """Format pace in seconds per unit to MM:SS string."""
    if sec_per_unit is None:
        return "--"
    total_sec = int(round(sec_per_unit))
    minutes = total_sec // 60
    seconds = total_sec % 60
    return f"{minutes}:{seconds:02d}"


def format_duration(minutes):
    """Format duration in minutes to H:MM:SS or MM:SS string."""
    if minutes is None:
        return "--"
    total_sec = int(round(minutes * 60))
    hours = total_sec // 3600
    mins = (total_sec % 3600) // 60
    secs = total_sec % 60
    if hours > 0:
        return f"{hours}:{mins:02d}:{secs:02d}"
    return f"{mins}:{secs:02d}"

def convert_activity_for_display(activity, units="metric"):
    """Convert an activity dict values for display in the given unit system.
    Does NOT modify the original dict. Returns a new one.
    """
    a = dict(activity)

    if units == "imperial":
        if a.get("distance_km") is not None:
            a["distance_display"] = round(km_to_miles(a["distance_km"]), 2)
            a["distance_unit"] = "mi"
        else:
            a["distance_display"] = None
            a["distance_unit"] = "mi"

        for field in ("total_ascent_m", "total_descent_m", "min_elevation_m", "max_elevation_m"):
            if a.get(field) is not None:
                a[field.replace("_m", "_display")] = int(round(meters_to_feet(a[field])))
            else:
                a[field.replace("_m", "_display")] = None
        a["elevation_unit"] = "ft"

        if a.get("avg_pace_sec_per_km") is not None:
            a["avg_pace_display"] = format_pace(pace_per_km_to_per_mile(a["avg_pace_sec_per_km"]))
        else:
            a["avg_pace_display"] = "--"
        if a.get("best_pace_sec_per_km") is not None:
            a["best_pace_display"] = format_pace(pace_per_km_to_per_mile(a["best_pace_sec_per_km"]))
        else:
            a["best_pace_display"] = "--"
        a["pace_unit"] = "/mi"

    else:
        if a.get("distance_km") is not None:
            a["distance_display"] = round(a["distance_km"], 2)
            a["distance_unit"] = "km"
        else:
            a["distance_display"] = None
            a["distance_unit"] = "km"

        for field in ("total_ascent_m", "total_descent_m", "min_elevation_m", "max_elevation_m"):
            if a.get(field) is not None:
                a[field.replace("_m", "_display")] = int(round(a[field]))
            else:
                a[field.replace("_m", "_display")] = None
        a["elevation_unit"] = "m"

        if a.get("avg_pace_sec_per_km") is not None:
            a["avg_pace_display"] = format_pace(a["avg_pace_sec_per_km"])
        else:
            a["avg_pace_display"] = "--"
        if a.get("best_pace_sec_per_km") is not None:
            a["best_pace_display"] = format_pace(a["best_pace_sec_per_km"])
        else:
            a["best_pace_display"] = "--"
        a["pace_unit"] = "/km"

    if a.get("duration_minutes") is not None:
        a["duration_display"] = format_duration(a["duration_minutes"])
    else:
        a["duration_display"] = "--"

    if a.get("elapsed_time_minutes") is not None:
        a["elapsed_time_display"] = format_duration(a["elapsed_time_minutes"])
    else:
        a["elapsed_time_display"] = "--"

    return a
