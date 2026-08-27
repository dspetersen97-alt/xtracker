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
    update_activity,
)
import json
from ..units import convert_activity_for_display


def _compute_score(activity, profile=None):
    """Attach display XP fields to an activity using its stored score.

    Reads the pre-computed 'score' column (persisted at write time) rather
    than re-scoring on every view. Splits that score across the exercise
    type's skills for display.

    `profile` is the person's leveling profile (from get_profile_data). Pass
    it in so callers can compute it once per request instead of once per row.

    Adds to the activity dict:
      - 'computed_score': total workout XP (before splitting)
      - 'weather_multiplier_computed'
      - 'skill_breakdown': list of {skill, xp, pct, level} the XP is split into
      - 'steps_xp' / 'steps_level'
      - 'combined_xp': workout XP + steps XP
      - 'total_fitness_level': sum of all skill levels
    """
    from ..database import get_db
    from ..leveling import SKILLS, get_skill_distribution, steps_xp_for_day

    db = get_db()

    # Use the stored score (computed at write time / by refresh_xp).
    total_score = activity.get("score") or 0
    activity["computed_score"] = activity.get("score")
    activity["weather_multiplier_computed"] = activity.get("weather_multiplier")

    # Split the workout XP across the exercise type's assigned skills
    distribution = get_skill_distribution(activity.get("activity_type"), db)
    breakdown = []
    for skill, fraction in sorted(distribution.items(), key=lambda kv: -kv[1]):
        breakdown.append({
            "skill": skill,
            "xp": round(total_score * fraction),
            "pct": round(fraction * 100),
            "level": None,
        })
    activity["skill_breakdown"] = breakdown

    # Steps XP for this activity (three-tier: 500/1000/2000 per 1000 steps)
    steps = activity.get("steps")
    activity["steps_xp"] = round(steps_xp_for_day(steps)) if steps else 0

    # Combined preview total: workout XP + steps XP
    activity["combined_xp"] = round(total_score) + activity["steps_xp"]

    # Attach skill levels and total fitness level from the precomputed profile
    activity["steps_level"] = None
    activity["total_fitness_level"] = None
    if profile:
        for item in breakdown:
            if item["skill"] in profile:
                item["level"] = profile[item["skill"]]["level"]
        activity["steps_level"] = profile["steps"]["level"]
        activity["total_fitness_level"] = sum(profile[s]["level"] for s in SKILLS)

    return activity


def _profiles_for_activities(activities, db):
    """Compute each distinct person's leveling profile once. Returns
    {person_name: profile} so per-row rendering can look levels up cheaply.
    """
    from ..leveling import get_profile_data

    profiles = {}
    for a in activities:
        person = a.get("person")
        if person and person not in profiles:
            try:
                profiles[person] = get_profile_data(person, db)
            except Exception:
                profiles[person] = None
    return profiles

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

    # Snapshot person profile at time of logging
    person_profile = get_person_by_name(person_name) if person_name else None
    person_weight_kg = person_profile["weight_kg"] if person_profile else None
    person_sex = person_profile["sex"] if person_profile else None
    person_birth_year = person_profile["birth_year"] if person_profile else None

    activity_id = create_activity(
        activity_date=activity_date,
        activity_type=activity_type,
        duration_minutes=duration_val,
        distance_km=distance_val,
        calories=calories_val,
        notes=notes or None,
        details=details if details else None,
        person=person_name,
        person_weight_kg=person_weight_kg,
        person_sex=person_sex,
        person_birth_year=person_birth_year,
        weather_temp_c=weather_temp_c,
        weather_humidity=weather_humidity,
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

    # Compute each person's leveling profile once, then attach display XP
    # fields to each activity from the stored score.
    from ..database import get_db
    profiles = _profiles_for_activities(activities, get_db())
    display_activities = [
        _compute_score(convert_activity_for_display(a, units), profiles.get(a.get("person")))
        for a in activities
    ]

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
    profile = None
    if activity.get("person"):
        from ..database import get_db
        from ..leveling import get_profile_data
        try:
            profile = get_profile_data(activity["person"], get_db())
        except Exception:
            profile = None
    display = _compute_score(convert_activity_for_display(activity, units), profile)
    return render_template("activity_detail.html", activity=display, units=units)


@activities_bp.route("/history/<int:activity_id>/delete", methods=["POST"])
def activity_delete(activity_id):
    """Delete an activity."""
    if delete_activity(activity_id):
        flash("Activity deleted.", "success")
    else:
        flash("Activity not found.", "error")
    return redirect(url_for("activities.history"))


@activities_bp.route("/history/<int:activity_id>/edit", methods=["GET"])
def activity_edit(activity_id):
    """Show the edit form for an activity."""
    activity = get_activity_by_id(activity_id)
    if activity is None:
        flash("Activity not found.", "error")
        return redirect(url_for("activities.history"))

    exercise_types = get_exercise_types()
    people = get_people()
    units = get_units()
    units_label = "F" if units == "imperial" else "C"
    return render_template(
        "activity_edit.html",
        activity=activity,
        exercise_types=exercise_types,
        people=people,
        units=units,
        units_label=units_label,
    )


@activities_bp.route("/history/<int:activity_id>/edit", methods=["POST"])
def activity_edit_submit(activity_id):
    """Process the edit form."""
    activity = get_activity_by_id(activity_id)
    if activity is None:
        flash("Activity not found.", "error")
        return redirect(url_for("activities.history"))

    # Parse all fields from form
    updates = {}

    activity_type = request.form.get("activity_type", "").strip()
    if activity_type:
        updates["activity_type"] = activity_type

    activity_date = request.form.get("activity_date", "").strip()
    if activity_date:
        updates["activity_date"] = activity_date

    title = request.form.get("title", "").strip()
    updates["title"] = title or None

    person_name = request.form.get("person", "").strip()
    updates["person"] = person_name or None

    # Update person snapshot if person changed
    if person_name:
        person_profile = get_person_by_name(person_name)
        if person_profile:
            updates["person_weight_kg"] = person_profile["weight_kg"]
            updates["person_sex"] = person_profile["sex"]
            updates["person_birth_year"] = person_profile["birth_year"]

    # Numeric fields
    duration = request.form.get("duration_minutes", "").strip()
    updates["duration_minutes"] = float(duration) if duration else None

    distance = request.form.get("distance_km", "").strip()
    updates["distance_km"] = float(distance) if distance else None

    calories = request.form.get("calories", "").strip()
    updates["calories"] = int(calories) if calories else None

    avg_hr = request.form.get("avg_hr", "").strip()
    updates["avg_hr"] = int(avg_hr) if avg_hr else None

    max_hr = request.form.get("max_hr", "").strip()
    updates["max_hr"] = int(max_hr) if max_hr else None

    total_ascent = request.form.get("total_ascent_m", "").strip()
    updates["total_ascent_m"] = float(total_ascent) if total_ascent else None

    total_descent = request.form.get("total_descent_m", "").strip()
    updates["total_descent_m"] = float(total_descent) if total_descent else None

    steps = request.form.get("steps", "").strip()
    updates["steps"] = int(steps) if steps else None

    min_elev = request.form.get("min_elevation_m", "").strip()
    updates["min_elevation_m"] = float(min_elev) if min_elev else None

    max_elev = request.form.get("max_elevation_m", "").strip()
    updates["max_elevation_m"] = float(max_elev) if max_elev else None

    notes = request.form.get("notes", "").strip()
    updates["notes"] = notes or None

    # Weather
    units = get_units()
    weather_temp_raw = request.form.get("weather_temp", "").strip()
    weather_humidity_raw = request.form.get("weather_humidity", "").strip()

    if weather_temp_raw:
        temp_val = float(weather_temp_raw)
        if units == "imperial":
            updates["weather_temp_c"] = (temp_val - 32) * 5 / 9
        else:
            updates["weather_temp_c"] = temp_val
    else:
        updates["weather_temp_c"] = None

    updates["weather_humidity"] = float(weather_humidity_raw) if weather_humidity_raw else None

    # Strength exercises (stored in details JSON)
    if activity_type == "strength":
        exercise_names = request.form.getlist("exercise_name[]")
        exercise_sets = request.form.getlist("exercise_sets[]")
        exercise_reps = request.form.getlist("exercise_reps[]")
        exercise_weights = request.form.getlist("exercise_weight[]")
        exercises = []
        for i, name in enumerate(exercise_names):
            name = name.strip()
            if not name:
                continue
            ex = {"name": name}
            if i < len(exercise_sets) and exercise_sets[i].strip():
                ex["sets"] = int(exercise_sets[i])
            if i < len(exercise_reps) and exercise_reps[i].strip():
                ex["reps"] = int(exercise_reps[i])
            if i < len(exercise_weights) and exercise_weights[i].strip():
                ex["weight_kg"] = float(exercise_weights[i])
            exercises.append(ex)
        import json as json_mod
        updates["details"] = json_mod.dumps({"exercises": exercises})

    update_activity(activity_id, **updates)
    flash("Workout updated.", "success")
    return redirect(url_for("activities.history"))
    #return redirect(url_for("activities.activity_detail", activity_id=activity_id))