import json

from flask import Blueprint, flash, redirect, render_template, request, url_for

from ..models import (
    create_exercise_type,
    delete_exercise_type,
    get_exercise_types,
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
    """List all exercise types."""
    types = get_exercise_types()
    return render_template("settings.html", exercise_types=types)


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

    # Validation
    errors = []
    if not name:
        errors.append("Name is required.")
    if not category:
        errors.append("Category is required.")
    if category and category not in [c[0] for c in CATEGORIES]:
        errors.append("Invalid category.")
    if not fields:
        errors.append("Select at least one field to track.")

    # Check for duplicate name
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

    # Always include date and notes
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
