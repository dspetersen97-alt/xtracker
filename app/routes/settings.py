import json

from flask import Blueprint, flash, redirect, render_template, request, url_for

from ..garmin_sync import (
    clear_garmin_credentials,
    get_garmin_credentials,
    get_last_sync_time,
    save_garmin_credentials,
    sync_activities,
    test_connection as garmin_test_connection,
)
from ..importer import import_garmin_csv
from ..models import (
    create_exercise_type,
    create_person,
    delete_exercise_type,
    delete_person,
    get_exercise_types,
    get_people,
    get_units,
    set_units,
    update_person,
)

settings_bp = Blueprint("settings", __name__)

AVAILABLE_FIELDS = [
    ("date", "Date"),
    ("duration", "Duration"),
    ("distance", "Distance"),
    ("elevation_gain", "Elevation Gain"),
    ("calories", "Calories"),
    ("machine", "Machine / Equipment"),
    ("heart_rate", "Heart Rate"),
    ("exercises", "Exercises (sets/reps/weight)"),
    ("notes", "Notes"),
]

CATEGORIES = [
    ("outdoor", "Outdoor"),
    ("cardio", "Cardio"),
    ("strength", "Strength"),
]


@settings_bp.route("/settings")
def exercise_types():
    """List all exercise types and app settings."""
    types = get_exercise_types()
    units = get_units()
    people = get_people()

    # Garmin status
    garmin_email, _ = get_garmin_credentials()
    garmin_connected = garmin_email is not None
    garmin_last_sync = get_last_sync_time()

    return render_template(
        "settings.html",
        exercise_types=types,
        units=units,
        people=people,
        garmin_connected=garmin_connected,
        garmin_email=garmin_email,
        garmin_last_sync=garmin_last_sync,
    )


@settings_bp.route("/settings/types/new")
def new_exercise_type():
    """Show form to create a new exercise type."""
    return render_template(
        "settings_new_type.html",
        available_fields=AVAILABLE_FIELDS,
        categories=CATEGORIES,
    )


@settings_bp.route("/settings/types", methods=["POST"])
def create_type():
    """Create a new custom exercise type."""
    name = request.form.get("name", "").strip()
    category = request.form.get("category", "").strip()
    fields = request.form.getlist("fields")

    errors = []
    if not name:
        errors.append("Name is required.")
    if not category:
        errors.append("Category is required.")
    if category and category not in [c[0] for c in CATEGORIES]:
        errors.append("Invalid category.")
    if not fields:
        errors.append("Select at least one field to track.")

    existing_types = get_exercise_types()
    existing_names = [t["name"] for t in existing_types]
    if name.lower() in existing_names:
        errors.append(f"An exercise type named '{name}' already exists.")

    if errors:
        for error in errors:
            flash(error, "error")
        return render_template(
            "settings_new_type.html",
            available_fields=AVAILABLE_FIELDS,
            categories=CATEGORIES,
            form=request.form,
        ), 422

    if "date" not in fields:
        fields.insert(0, "date")
    if "notes" not in fields:
        fields.append("notes")

    create_exercise_type(name=name, category=category, fields=fields)
    flash(f"Exercise type '{name}' created successfully!", "success")
    return redirect(url_for("settings.exercise_types"))


@settings_bp.route("/settings/types/<int:type_id>/delete", methods=["POST"])
def delete_type(type_id):
    """Delete a custom exercise type."""
    if delete_exercise_type(type_id):
        flash("Exercise type deleted.", "success")
    else:
        flash("Cannot delete default exercise types.", "error")
    return redirect(url_for("settings.exercise_types"))


@settings_bp.route("/settings/units", methods=["POST"])
def toggle_units():
    """Toggle between metric and imperial units."""
    units = request.form.get("units", "metric")
    if units in ("metric", "imperial"):
        set_units(units)
        flash(f"Units switched to {units}.", "success")
    else:
        flash("Invalid unit selection.", "error")
    return redirect(url_for("settings.exercise_types"))


@settings_bp.route("/settings/import", methods=["GET"])
def import_page():
    """Show the CSV import form."""
    people = get_people()
    return render_template("settings_import.html", people=people)


@settings_bp.route("/settings/import", methods=["POST"])
def import_csv():
    """Process a CSV file upload."""
    if "csv_file" not in request.files:
        flash("No file selected.", "error")
        return redirect(url_for("settings.import_page"))

    file = request.files["csv_file"]
    if file.filename == "":
        flash("No file selected.", "error")
        return redirect(url_for("settings.import_page"))

    if not file.filename.lower().endswith(".csv"):
        flash("Please upload a CSV file.", "error")
        return redirect(url_for("settings.import_page"))

    source_units = request.form.get("source_units", "imperial")
    person = request.form.get("person", "").strip() or None

    try:
        content = file.read().decode("utf-8")
        result = import_garmin_csv(content, source_units=source_units, person=person)

        if result["imported"] > 0:
            flash(f"Successfully imported {result['imported']} activities.", "success")
        if result["skipped"] > 0:
            flash(f"Skipped {result['skipped']} rows.", "error")
        if result["errors"]:
            for err in result["errors"][:5]:
                flash(err, "error")

    except Exception as e:
        flash(f"Import failed: {str(e)}", "error")

    return redirect(url_for("settings.exercise_types"))

@settings_bp.route("/settings/people", methods=["POST"])
def add_person():
    """Add a new person with profile."""
    name = request.form.get("name", "").strip()
    if not name:
        flash("Name is required.", "error")
        return redirect(url_for("settings.exercise_types"))

    weight_raw = request.form.get("weight", "").strip()
    height_raw = request.form.get("height", "").strip()
    sex = request.form.get("sex", "").strip()
    birth_year = request.form.get("birth_year", "").strip()

    units = get_units()
    weight_kg = None
    height_cm = None
    if weight_raw:
        w = float(weight_raw)
        weight_kg = w / 2.20462 if units == "imperial" else w
    if height_raw:
        h = float(height_raw)
        height_cm = h * 2.54 if units == "imperial" else h

    create_person(
        name=name,
        weight_kg=round(weight_kg, 1) if weight_kg else None,
        height_cm=round(height_cm, 1) if height_cm else None,
        sex=sex if sex in ("male", "female") else None,
        birth_year=int(birth_year) if birth_year else None,
    )
    flash(f"Person '{name}' added.", "success")
    return redirect(url_for("settings.exercise_types"))


@settings_bp.route("/settings/people/<int:person_id>/edit", methods=["POST"])
def edit_person(person_id):
    """Update a person's profile."""
    name = request.form.get("name", "").strip()
    weight_raw = request.form.get("weight", "").strip()
    height_raw = request.form.get("height", "").strip()
    sex = request.form.get("sex", "").strip()
    birth_year = request.form.get("birth_year", "").strip()

    units = get_units()
    weight_kg = None
    height_cm = None
    if weight_raw:
        w = float(weight_raw)
        weight_kg = round(w / 2.20462, 1) if units == "imperial" else w
    if height_raw:
        h = float(height_raw)
        height_cm = round(h * 2.54, 1) if units == "imperial" else h

    update_person(
        person_id,
        name=name if name else None,
        weight_kg=weight_kg,
        height_cm=height_cm,
        sex=sex if sex in ("male", "female") else None,
        birth_year=int(birth_year) if birth_year else None,
    )
    flash("Profile updated.", "success")
    return redirect(url_for("settings.exercise_types"))


@settings_bp.route("/settings/people/<int:person_id>/delete", methods=["POST"])
def remove_person(person_id):
    """Delete a person."""
    if delete_person(person_id):
        flash("Person removed.", "success")
    else:
        flash("Person not found.", "error")
    return redirect(url_for("settings.exercise_types"))



# --- Garmin Connect ---


@settings_bp.route("/settings/garmin/connect", methods=["POST"])
def garmin_connect():
    """Save Garmin credentials and test the connection."""
    email = request.form.get("garmin_email", "").strip()
    password = request.form.get("garmin_password", "").strip()

    if not email or not password:
        flash("Email and password are required.", "error")
        return redirect(url_for("settings.exercise_types"))

    # Save credentials (encrypted)
    save_garmin_credentials(email, password)

    # Test the connection
    success, message = garmin_test_connection()
    if success:
        flash(f"Garmin Connect linked successfully ({email}).", "success")
    else:
        # Remove credentials if connection failed
        clear_garmin_credentials()
        flash(f"Connection failed: {message}", "error")

    return redirect(url_for("settings.exercise_types"))


@settings_bp.route("/settings/garmin/disconnect", methods=["POST"])
def garmin_disconnect():
    """Remove stored Garmin credentials."""
    clear_garmin_credentials()
    flash("Garmin Connect disconnected.", "success")
    return redirect(url_for("settings.exercise_types"))


@settings_bp.route("/settings/garmin/test", methods=["POST"])
def garmin_test():
    """Test the Garmin connection."""
    success, message = garmin_test_connection()
    if success:
        flash("Garmin connection is working.", "success")
    else:
        flash(f"Connection test failed: {message}", "error")
    return redirect(url_for("settings.exercise_types"))


@settings_bp.route("/settings/garmin/sync", methods=["POST"])
def garmin_sync():
    """Sync activities from Garmin Connect."""
    person = request.form.get("person", "").strip() or None
    days_back = request.form.get("days_back", "30").strip()

    try:
        days = int(days_back)
    except ValueError:
        days = 30

    result = sync_activities(person_name=person, days_back=days)

    if result["imported"] > 0:
        flash(f"Synced {result['imported']} new activities from Garmin.", "success")
    elif not result["errors"]:
        flash("No new activities to sync.", "success")

    if result["skipped"] > 0 and result["imported"] == 0 and not result["errors"]:
        flash(f"{result['skipped']} activities already imported (skipped).", "success")

    for err in result["errors"][:5]:
        flash(err, "error")

    return redirect(url_for("settings.exercise_types"))
