from datetime import date, timedelta

from flask import Blueprint, render_template, request

from ..models import get_daily_health_range, get_people, get_units

health_bp = Blueprint("health", __name__)


@health_bp.route("/health-dashboard")
def dashboard():
    """Health metrics dashboard with daily trends."""
    people = get_people()
    person = request.args.get("person", "").strip()
    weeks_param = request.args.get("weeks", "4")

    try:
        weeks_back = int(weeks_param)
    except ValueError:
        weeks_back = 4

    # Default to first person if none selected
    if not person and people:
        person = people[0]["name"]

    # Get date range
    end = date.today()
    start = end - timedelta(weeks=weeks_back)

    # Fetch health data
    records = []
    if person:
        records = get_daily_health_range(person, start.isoformat(), end.isoformat())

    # Prepare chart data
    chart_data = _prepare_chart_data(records)

    # Latest values for the summary cards
    latest = records[-1] if records else {}

    units = get_units()

    return render_template(
        "health_dashboard.html",
        people=people,
        current_person=person,
        current_weeks=weeks_param,
        chart_data=chart_data,
        latest=latest,
        units=units,
        record_count=len(records),
    )


def _prepare_chart_data(records):
    """Transform daily_health records into chart-ready data."""
    if not records:
        return {
            "labels": [],
            "steps": [],
            "weight": [],
        }

    labels = [r["date"] for r in records]
    return {
        "labels": labels,
        "steps": [r.get("steps") for r in records],
        "weight": [r.get("weight_kg") for r in records],
    }
