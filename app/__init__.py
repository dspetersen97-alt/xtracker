import os
from flask import Flask, render_template

from .config import get_config


def create_app(config_overrides=None):
    app = Flask(__name__)

    # Load config from environment
    config = get_config()
    app.config.update(config)

    # Apply any overrides (useful for testing)
    if config_overrides:
        app.config.update(config_overrides)

    app.secret_key = app.config["SECRET_KEY"]

    # Exercise-type names are stored lowercase. Most display like a normal
    # capitalized word, but some are acronyms that should stay all-caps.
    EXERCISE_NAME_ACRONYMS = {"hiit": "HIIT"}

    @app.template_filter("exercise_name")
    def exercise_name_filter(name):
        """Format an exercise-type name for display, preserving acronyms."""
        if not name:
            return name
        key = str(name).strip().lower()
        if key in EXERCISE_NAME_ACRONYMS:
            return EXERCISE_NAME_ACRONYMS[key]
        return str(name).capitalize()

    # Initialize database (handles data dir creation and validation)
    from .database import init_db
    with app.app_context():
        init_db(app)

    # Register blueprints
    from .routes.main import main_bp
    from .routes.activities import activities_bp
    from .routes.progress import progress_bp
    from .routes.settings import settings_bp
    from .routes.health import health_bp
    from .routes.auth import auth_bp
    from .routes.profile import profile_bp
    app.register_blueprint(main_bp)
    app.register_blueprint(activities_bp)
    app.register_blueprint(progress_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(health_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(profile_bp)

    # Error handlers
    @app.errorhandler(404)
    def not_found(e):
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def server_error(e):
        return render_template("errors/500.html"), 500

    return app