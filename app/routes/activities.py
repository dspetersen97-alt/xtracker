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
    get_people,
    get_person_by_name,
    get_units,
    update_activity_score,
)
from ..scoring import score_activity
from ..units import convert_activity_for_display

activities_bp = Blueprint("activities", __name__)


@activities_bp.route("/log", methods=["GET"])
def log_workout():
    """Show the log workout form."""
    exercise_types = get_exercise_types()
    people = get_people()
    units = get_units()
    today = date.today().isoformat()
    units_label = "F" if units == "imperial" else "C"
    return render_template("log.html", exercise_types=exercise_types, people=people,
                           today=today, units=units, units_label=units_label)


@activities_bp.route("/log", methods=["POST"])
def log_workout_submit():
    """Process the log workout form submission."""
    exercise_types = get_exercise_types()
    today = date.today().isoformat()

    activity_type = request.form.get("activity_type", "").strip()
    activity_date = request.form.get("activity_date", "").strip()
    duration_minutes = request.form.get("duration_minutes", "").strip()
    distance_km = request.form.get("distance_km", "").strip()
    calories = request.form.get("calories", "").strip()
    notes = request.form.get("notes", "").strip()

    errors = []
    if not activity_type:
        errors.append("Activity type is required.")
    if not activity_date:
        errors.append("Date is required.")

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

    details = {}

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
        units = get_units()
        units_label = "F" if units == "imperial" else "C"
        return render_template(
            "log.html",
            exercise_types=exercise_types,
            people=get_people(),
            today=today,
            form=request.form,
            units=units,
            units_label=units_label,
        ), 422

    # Parse weather data
    weather_temp_raw = request.form.get("weather_temp", "").strip()
    weather_humidity_raw = request.form.get("weather_humidity", "").strip()

    weather_temp_c = None
    weather_humidity = None
    if weather_temp_raw:
        try:
            temp_val = float(weather_temp_raw)
            units = get_units()
            if units == "imperial":
                weather_temp_c = (temp_val - 32) * 5 / 9  # Convert F to C
            else:
                weather_temp_c = temp_val
        except ValueError:
            pass
    if weather_humidity_raw:
        try:
            weather_humidity = float(weather_humidity_raw)
        except ValueError:
            pass

    person_name = request.form.get("person", "").strip() or None
    activity_id = create_activity(
        activity_date=activity_date,
        activity_type=activity_type,
        duration_minutes=duration_val,
        distance_km=distance_val,
        calories=calories_val,
        notes=notes or None,
        details=details if details else None,
        person=person_name,
    )

    # Calculate and store score
    if activity_type in ("run", "walk", "hike") and activity_id:
        person_profile = get_person_by_name(person_name) if person_name else None
        activity_data = {
            "activity_type": activity_type,
            "distance_km": distance_val,
            "total_ascent_m": details.get("elevation_gain_m") if details else None,
            "duration_minutes": duration_val,
            "avg_hr": None,  # not captured in manual log form currently
            "weather_temp_c": weather_temp_c,
            "weather_humidity": weather_humidity,
        }
        result = score_activity(activity_data, person_profile)
        if result:
            update_activity_score(
                activity_id,
                score=result["final_score"],
                weather_temp_c=weather_temp_c,
                weather_humidity=weather_humidity,
                weather_multiplier=result["weather_multiplier"],
            )

    flash("Workout logged successfully!", "success")
    return redirect(url_for("activities.history"))


@activities_bp.route("/history")
def history():
    """Show workout history with filtering."""
    activity_type = request.args.get("type", "").strip()
    date_from = request.args.get("from", "").strip()
    date_to = request.args.get("to", "").strip()
    person = request.args.get("person", "").strip()
    page = request.args.get("page", 1, type=int)
    per_page = 20

    offset = (page - 1) * per_page
    activities = get_activities(
        activity_type=activity_type or None,
        date_from=date_from or None,
        date_to=date_to or None,
        person=person or None,
        limit=per_page,
        offset=offset,
    )

    total = count_activities(
        activity_type=activity_type or None,
        date_from=date_from or None,
        date_to=date_to or None,
        person=person or None,
    )

    total_pages = (total + per_page - 1) // per_page if total > 0 else 1
    exercise_types = get_exercise_types()
    units = get_units()

    # Convert activities for display
    display_activities = [convert_activity_for_display(a, units) for a in activities]

    people = get_people()
    return render_template(
        "history.html",
        activities=display_activities,
        exercise_types=exercise_types,
        people=people,
        current_type=activity_type,
        current_person=person,
        date_from=date_from,
        date_to=date_to,
        page=page,
        total_pages=total_pages,
        total=total,
        units=units,
    )


@activities_bp.route("/history/<int:activity_id>")
def activity_detail(activity_id):
    """Show detail view for a single activity."""
    activity = get_activity_by_id(activity_id)
    if activity is None:
        flash("Activity not found.", "error")
        return redirect(url_for("activities.history"))

    units = get_units()
    display = convert_activity_for_display(activity, units)
    return render_template("activity_detail.html", activity=display, units=units)


@activities_bp.route("/history/<int:activity_id>/delete", methods=["POST"])
def activity_delete(activity_id):
    """Delete an activity."""
    if delete_activity(activity_id):
        flash("Activity deleted.", "success")
    else:
        flash("Activity not found.", "error")
    return redirect(url_for("activities.history"))