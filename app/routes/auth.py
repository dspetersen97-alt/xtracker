"""Authentication routes (placeholder - no logic yet)."""
from flask import Blueprint, render_template

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    """Login page."""
    return render_template("auth/login.html")


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    """Registration page."""
    return render_template("auth/register.html")


@auth_bp.route("/change-password", methods=["GET", "POST"])
def change_password():
    """Change password page."""
    return render_template("auth/change_password.html")
