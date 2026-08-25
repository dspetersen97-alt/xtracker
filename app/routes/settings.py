import json

from flask import Blueprint, flash, redirect, render_template, request, url_for

from ..importer import import_garmin_csv
from ..models import (
    create_exercise_type,
    delete_exercise_type,
    get_exercise_types,
    get_units,
    set_units,
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
    return render_template("settings.html", exercise_types=types, units=units)


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
    return render_template("settings_import.html")


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

    try:
        content = file.read().decode("utf-8")
        result = import_garmin_csv(content, source_units=source_units)

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