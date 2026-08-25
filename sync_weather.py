"""CLI: Re-fetch weather data for all activities missing it."""
from app import create_app

app = create_app()

with app.app_context():
    from app.garmin_sync import backfill_all_weather, _set_sync_status, get_sync_status

    print("Fetching weather data from Garmin for activities without weather...")
    filled = backfill_all_weather()

    if filled > 0:
        print(f"Done. Weather added for {filled} activities.")
    else:
        print("No activities need weather data (all filled or no Garmin credentials).")
