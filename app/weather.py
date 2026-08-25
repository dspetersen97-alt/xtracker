"""Weather lookup using Open-Meteo Historical Weather API.

Fetches historical temperature and humidity for a given GPS coordinate and datetime.
Uses the free Open-Meteo archive API — no API key required.

API docs: https://open-meteo.com/en/docs/historical-weather-api
"""

import json
import logging
import urllib.request
import urllib.error
from datetime import datetime

logger = logging.getLogger(__name__)

OPEN_METEO_URL = "https://archive-api.open-meteo.com/v1/archive"


def get_historical_weather(latitude, longitude, dt):
    """Fetch historical temperature and humidity for a location and time.

    Args:
        latitude: GPS latitude (float)
        longitude: GPS longitude (float)
        dt: datetime object or ISO string (e.g., '2026-08-24 17:04:37')

    Returns:
        dict with 'temperature_c' and 'humidity' (percentage),
        or None if lookup fails.
    """
    if latitude is None or longitude is None:
        return None

    # Parse datetime if string
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt.replace(" ", "T"))
        except ValueError:
            # Try just the date part
            try:
                dt = datetime.fromisoformat(dt.split(" ")[0])
            except ValueError:
                return None

    date_str = dt.strftime("%Y-%m-%d")
    hour = dt.hour

    # Build API request
    params = (
        f"?latitude={latitude}"
        f"&longitude={longitude}"
        f"&start_date={date_str}"
        f"&end_date={date_str}"
        f"&hourly=temperature_2m,relative_humidity_2m"
    )

    url = OPEN_METEO_URL + params

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "xtracker/1.0"})
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError) as e:
        logger.warning(f"Weather API request failed: {e}")
        return None
    except Exception as e:
        logger.warning(f"Weather lookup error: {e}")
        return None

    # Parse response - hourly data arrays indexed by hour (0-23)
    hourly = data.get("hourly", {})
    temps = hourly.get("temperature_2m", [])
    humidity = hourly.get("relative_humidity_2m", [])

    if not temps or not humidity:
        return None

    # Get the value for the specific hour (or closest available)
    if hour < len(temps) and hour < len(humidity):
        temp_c = temps[hour]
        humid = humidity[hour]
    elif temps and humidity:
        # Fallback to the last available hour
        temp_c = temps[-1]
        humid = humidity[-1]
    else:
        return None

    if temp_c is None or humid is None:
        return None

    return {
        "temperature_c": round(float(temp_c), 1),
        "humidity": round(float(humid), 0),
    }


def backfill_weather_for_activity(activity):
    """Look up weather for an activity using its GPS coords and start time.

    Args:
        activity: dict with 'start_latitude', 'start_longitude', 'activity_date'

    Returns:
        dict with 'temperature_c' and 'humidity', or None if unavailable.
    """
    lat = activity.get("start_latitude")
    lng = activity.get("start_longitude")
    dt_str = activity.get("activity_date")

    if not lat or not lng or not dt_str:
        return None

    return get_historical_weather(lat, lng, dt_str)
