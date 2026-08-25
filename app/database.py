import os
import sqlite3
import sys

from flask import g, current_app


def get_db():
    """Get a database connection for the current request."""
    if "db" not in g:
        g.db = sqlite3.connect(
            current_app.config["DB_PATH"],
            detect_types=sqlite3.PARSE_DECLTYPES,
        )
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA journal_mode=WAL")
        g.db.execute("PRAGMA foreign_keys=ON")
    return g.db


def close_db(e=None):
    """Close the database connection at end of request."""
    db = g.pop("db", None)
    if db is not None:
        db.close()


def _ensure_data_dir(db_path):
    """Ensure the data directory exists and is writable."""
    data_dir = os.path.dirname(os.path.abspath(db_path))

    if not os.path.exists(data_dir):
        try:
            os.makedirs(data_dir, mode=0o755, exist_ok=True)
        except OSError as e:
            sys.exit(
                f"ERROR: Cannot create data directory '{data_dir}': {e}\n"
                f"Please create it manually with: mkdir -p {data_dir}"
            )

    if not os.access(data_dir, os.W_OK):
        sys.exit(
            f"ERROR: Data directory '{data_dir}' is not writable.\n"
            f"Fix with: chmod 755 {data_dir}\n"
            f"Or: sudo chown your_username {data_dir}"
        )


def init_db(app):
    """Initialize the database schema and seed data."""
    app.teardown_appcontext(close_db)

    db_path = app.config["DB_PATH"]
    _ensure_data_dir(db_path)

    db = sqlite3.connect(db_path)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA foreign_keys=ON")

    # Create tables
    db.executescript(SCHEMA_SQL)

    # Run migrations for existing databases
    _migrate(db)

    # Seed default exercise types if empty
    cursor = db.execute("SELECT COUNT(*) FROM exercise_types")
    if cursor.fetchone()[0] == 0:
        for et in DEFAULT_EXERCISE_TYPES:
            db.execute(
                "INSERT INTO exercise_types (name, category, fields, is_default) VALUES (?, ?, ?, 1)",
                (et["name"], et["category"], et["fields"]),
            )
        db.commit()

    # Seed default settings if empty
    cursor = db.execute("SELECT COUNT(*) FROM settings")
    if cursor.fetchone()[0] == 0:
        db.execute("INSERT INTO settings (key, value) VALUES ('units', 'metric')")
        db.commit()

    db.close()


def _migrate(db):
    """Add columns that may not exist in older databases."""
    # Get existing columns for the activities table
    cursor = db.execute("PRAGMA table_info(activities)")
    existing_cols = {row[1] for row in cursor.fetchall()}

    new_columns = [
        ("title", "TEXT"),
        ("avg_hr", "INTEGER"),
        ("max_hr", "INTEGER"),
        ("avg_pace_sec_per_km", "REAL"),
        ("best_pace_sec_per_km", "REAL"),
        ("total_ascent_m", "REAL"),
        ("total_descent_m", "REAL"),
        ("steps", "INTEGER"),
        ("elapsed_time_minutes", "REAL"),
        ("min_elevation_m", "REAL"),
        ("max_elevation_m", "REAL"),
        ("person", "TEXT"),
    ]

    for col_name, col_type in new_columns:
        if col_name not in existing_cols:
            db.execute(f"ALTER TABLE activities ADD COLUMN {col_name} {col_type}")

    # Create indexes for new columns (safe to run after columns exist)
    db.execute("CREATE INDEX IF NOT EXISTS idx_activities_person ON activities(person)")

    # Migrate activities table: add weather and person snapshot columns
    if "weather_temp_c" not in existing_cols:
        db.execute("ALTER TABLE activities ADD COLUMN weather_temp_c REAL")
    if "weather_humidity" not in existing_cols:
        db.execute("ALTER TABLE activities ADD COLUMN weather_humidity REAL")
    if "person_weight_kg" not in existing_cols:
        db.execute("ALTER TABLE activities ADD COLUMN person_weight_kg REAL")
    if "person_sex" not in existing_cols:
        db.execute("ALTER TABLE activities ADD COLUMN person_sex TEXT")
    if "person_birth_year" not in existing_cols:
        db.execute("ALTER TABLE activities ADD COLUMN person_birth_year INTEGER")
    # score and weather_multiplier kept for legacy but no longer written
    if "score" not in existing_cols:
        db.execute("ALTER TABLE activities ADD COLUMN score REAL")
    if "weather_multiplier" not in existing_cols:
        db.execute("ALTER TABLE activities ADD COLUMN weather_multiplier REAL")

    # Migrate people table: add profile columns
    people_cursor = db.execute("PRAGMA table_info(people)")
    people_cols = {row[1] for row in people_cursor.fetchall()}
    people_new_cols = [
        ("weight_kg", "REAL"),
        ("height_cm", "REAL"),
        ("sex", "TEXT"),
        ("birth_year", "INTEGER"),
    ]
    for col_name, col_type in people_new_cols:
        if col_name not in people_cols:
            db.execute(f"ALTER TABLE people ADD COLUMN {col_name} {col_type}")

    db.commit()


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS activities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    activity_date TEXT NOT NULL,
    activity_type TEXT NOT NULL,
    title TEXT,
    duration_minutes REAL,
    distance_km REAL,
    calories INTEGER,
    avg_hr INTEGER,
    max_hr INTEGER,
    avg_pace_sec_per_km REAL,
    best_pace_sec_per_km REAL,
    total_ascent_m REAL,
    total_descent_m REAL,
    steps INTEGER,
    elapsed_time_minutes REAL,
    min_elevation_m REAL,
    max_elevation_m REAL,
    notes TEXT,
    details TEXT DEFAULT '{}',
    person TEXT,
    person_weight_kg REAL,
    person_sex TEXT,
    person_birth_year INTEGER,
    weather_temp_c REAL,
    weather_humidity REAL,
    score REAL,
    weather_multiplier REAL
);

CREATE INDEX IF NOT EXISTS idx_activities_date ON activities(activity_date);
CREATE INDEX IF NOT EXISTS idx_activities_type ON activities(activity_type);

CREATE TABLE IF NOT EXISTS exercise_types (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    category TEXT NOT NULL,
    fields TEXT NOT NULL DEFAULT '[]',
    is_default INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS people (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    weight_kg REAL,
    height_cm REAL,
    sex TEXT,
    birth_year INTEGER
);

"""

DEFAULT_EXERCISE_TYPES = [
    {
        "name": "hike",
        "category": "outdoor",
        "fields": '["date","duration","distance","elevation_gain","notes"]',
    },
    {
        "name": "walk",
        "category": "outdoor",
        "fields": '["date","duration","distance","elevation_gain","notes"]',
    },
    {
        "name": "run",
        "category": "outdoor",
        "fields": '["date","duration","distance","elevation_gain","notes"]',
    },
    {
        "name": "cardio",
        "category": "cardio",
        "fields": '["date","duration","machine","calories","heart_rate","notes"]',
    },
    {
        "name": "strength",
        "category": "strength",
        "fields": '["date","duration","exercises","notes"]',
    },
]