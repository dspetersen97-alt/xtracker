from flask import Blueprint, render_template, request

from ..stats import get_summary_stats, get_type_stats, strength_exercise_progression, weekly_health_averages
from ..models import get_people

progress_bp = Blueprint("progress", __name__)

RANGE_OPTIONS = {
    "4": 4,
    "12": 12,
    "26": 26,
}


@progress_bp.route("/progress")
def dashboard():
    """Main progress dashboard with summary charts."""
    weeks_param = request.args.get("weeks", "12")
    weeks_back = RANGE_OPTIONS.get(weeks_param, 12)
    person = request.args.get("person", "").strip()

    stats = get_summary_stats(weeks_back)
    health = weekly_health_averages(person=person or None, weeks_back=weeks_back)
    people = get_people()

    return render_template(
        "progress.html",
        stats=stats,
        health=health,
        people=people,
        current_person=person,
        weeks_back=weeks_back,
        current_weeks=weeks_param,
    )


@progress_bp.route("/progress/<activity_type>")
def type_detail(activity_type):
    """Per-type drill-down charts."""
    weeks_param = request.args.get("weeks", "12")
    weeks_back = RANGE_OPTIONS.get(weeks_param, 12)
    exercise_name = request.args.get("exercise", "")

    stats = get_type_stats(activity_type, weeks_back)

    # If strength and an exercise is selected, get its progression
    exercise_data = None
    if activity_type == "strength" and exercise_name:
        exercise_data = strength_exercise_progression(exercise_name, weeks_back)

    return render_template(
        "progress_type.html",
        activity_type=activity_type,
        stats=stats,
        current_weeks=weeks_param,
        exercise_name=exercise_name,
        exercise_data=exercise_data,
    )
