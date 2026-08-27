"""Profile route - shows leveling/XP progress, personal info, and Garmin connection."""
from flask import Blueprint, render_template, request

from ..database import get_db
from ..garmin_sync import get_garmin_credentials, get_last_sync_time
from ..leveling import get_profile_data
from ..models import get_people, get_person_by_name, get_units

profile_bp = Blueprint("profile", __name__)


@profile_bp.route("/profile")
def profile():
    """Show the user's leveling profile, personal info, and Garmin connection."""
    people = get_people()
    person = request.args.get("person", "").strip()

    # Default to first person if none selected
    if not person and people:
        person = people[0]["name"]

    # Get leveling data
    profile_data = None
    total_level = 3  # minimum (all level 1)
    person_info = None
    if person:
        db = get_db()
        profile_data = get_profile_data(person, db)
        person_info = get_person_by_name(person)
        if profile_data:
            total_level = (
                profile_data["outdoor"]["level"] +
                profile_data["cardio"]["level"] +
                profile_data["strength"]["level"]
            )

    # Garmin connection info
    garmin_email, _ = get_garmin_credentials()
    garmin_connected = garmin_email is not None
    garmin_last_sync = get_last_sync_time()

    # Units
    units = get_units()

    return render_template(
        "profile.html",
        people=people,
        current_person=person,
        person_info=person_info,
        profile=profile_data,
        total_level=total_level,
        garmin_connected=garmin_connected,
        garmin_email=garmin_email,
        garmin_last_sync=garmin_last_sync,
        units=units,
    )
