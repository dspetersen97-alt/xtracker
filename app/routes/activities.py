import json
from datetime import date

from flask import Blueprint, flash, redirect, render_template, request, url_for

from ..models import (
    count_activities,
    create_activity,
    delete_activity,
    get_activities,
    get_activity_by_id,
    get_exercise_types,
)

activities_bp = Blueprint("activities", __name__)


@activities_bp.route("/log", methods=["GET"])
def log_workout():
    """Show the log workout form."""
    exercise_types = get_exercise_types()
    today = date.today().isoformat()
    return render_template("log.html", exercise_types=exercise_types, today=today)


@activities_bp.route("/log", methods=["POST"])
def log_workout_submit():
    """Process the log workout form submission."""
    exercise_types = get_exercise_types()
    today = date.today().isoformat()

    # Extract common fields
    activity_type = request.form.get("activity_type", "").strip()
    activity_date = request.form.get("activity_date", "").strip()
    duration_minutes = request.form.get("duration_minutes", "").strip()
    distance_km = request.form.get("distance_km", "").strip()
    calories = request.form.get("calories", "").strip()
    notes = request.form.get("notes", "").strip()

    # Validation
    errors = []
    if not activity_type:
        errors.append("Activity type is required.")
    if not activity_date:
        errors.append("Date is required.")

    # Parse numeric fields
    duration_val = None
    if duration_minutes:
        try:
            duration_val = int(duration_minutes)
            if duration_val < 0:
                errors.append("Duration must be positive.")
        except ValueError:
            errors.append("Duration must be a whole number.")

    distance_val = None
    if distance_km:
        try:
            distance_val = float(distance_km)
            if distance_val < 0:
                errors.append("Distance must be positive.")
        except ValueError:
            errors.append("Distance must be a number.")

    calories_val = None
    if calories:
        try:
            calories_val = int(calories)
            if calories_val < 0:
                errors.append("Calories must be positive.")
        except ValueError:
            errors.append("Calories must be a whole number.")

    # Build details JSON based on activity type
    details = {}

    # Type-specific fields
    if activity_type in ("hike", "walk", "run"):
        elevation_gain = request.form.get("elevation_gain", "").strip()
        if elevation_gain:
            try:
                details["elevation_gain_m"] = float(elevation_gain)
            except ValueError:
                errors.append("Elevation gain must be a number.")

    elif activity_type == "cardio":
        machine = request.form.get("machine", "").strip()
        heart_rate = request.form.get("heart_rate", "").strip()
        if machine:
            details["machine"] = machine
        if heart_rate:
            try:
                details["heart_rate_avg"] = int(heart_rate)
            except ValueError:
                errors.append("Heart rate must be a whole number.")

    elif activity_type == "strength":
        # Parse exercise rows
        exercises = []
        exercise_names = request.form.getlist("exercise_name[]")
        exercise_sets = request.form.getlist("exercise_sets[]")
        exercise_reps = request.form.getlist("exercise_reps[]")
        exercise_weights = request.form.getlist("exercise_weight[]")

        for i, name in enumerate(exercise_names):
            name = name.strip()
            if not name:
                continue
            exercise = {"name": name}
            try:
                if i < len(exercise_sets) and exercise_sets[i].strip():
                    exercise["sets"] = int(exercise_sets[i])
                if i < len(exercise_reps) and exercise_reps[i].strip():
                    exercise["reps"] = int(exercise_reps[i])
                if i < len(exercise_weights) and exercise_weights[i].strip():
                    exercise["weight_kg"] = float(exercise_weights[i])
            except ValueError:
                errors.append(f"Invalid number in exercise row {i + 1}.")
            exercises.append(exercise)

        if not exercises:
            errors.append("At least one exercise is required for strength training.")
        details["exercises"] = exercises

    else:
        # Custom type — store any extra fields generically
        elevation_gain = request.form.get("elevation_gain", "").strip()
        machine = request.form.get("machine", "").strip()
        heart_rate = request.form.get("heart_rate", "").strip()
        if elevation_gain:
            try:
                details["elevation_gain_m"] = float(elevation_gain)
            except ValueError:
                pass
        if machine:
            details["machine"] = machine
        if heart_rate:
            try:
                details["heart_rate_avg"] = int(heart_rate)
            except ValueError:
                pass

    if errors:
        for error in errors:
            flash(error, "error")
        return render_template(
            "log.html",
            exercise_types=exercise_types,
            today=today,
            form=request.form,
        ), 422

    # Create the activity
    activity_id = create_activity(
        activity_date=activity_date,
        activity_type=activity_type,
        duration_minutes=duration_val,
        distance_km=distance_val,
        calories=calories_val,
        notes=notes or None,
        details=details if details else None,
    )

    flash(f"Workout logged successfully!", "success")
    return redirect(url_for("activities.history"))


@activities_bp.route("/history")
def history():
    """Show workout history with filtering."""
    # Get filter params
    activity_type = request.args.get("type", "").strip()
    date_from = request.args.get("from", "").strip()
    date_to = request.args.get("to", "").strip()
    page = request.args.get("page", 1, type=int)
    per_page = 20

    # Get filtered activities
    offset = (page - 1) * per_page
    activities = get_activities(
        activity_type=activity_type or None,
        date_from=date_from or None,
        date_to=date_to or None,
        limit=per_page,
        offset=offset,
    )

    total = count_activities(
        activity_type=activity_type or None,
        date_from=date_from or None,
        date_to=date_to or None,
    )

    total_pages = (total + per_page - 1) // per_page if total > 0 else 1
    exercise_types = get_exercise_types()

    return render_template(
        "history.html",
        activities=activities,
        exercise_types=exercise_types,
        current_type=activity_type,
        date_from=date_from,
        date_to=date_to,
        page=page,
        total_pages=total_pages,
        total=total,
    )


@activities_bp.route("/history/<int:activity_id>")
def activity_detail(activity_id):
    """Show detail view for a single activity."""
    activity = get_activity_by_id(activity_id)
    if activity is None:
        flash("Activity not found.", "error")
        return redirect(url_for("activities.history"))
    return render_template("activity_detail.html", activity=activity)


@activities_bp.route("/history/<int:activity_id>/delete", methods=["POST"])
def activity_delete(activity_id):
    """Delete an activity."""
    if delete_activity(activity_id):
        flash("Activity deleted.", "success")
    else:
        flash("Activity not found.", "error")
    return redirect(url_for("activities.history"))
