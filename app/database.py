import os
import sqlite3
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


def init_db(app):
    """Initialize the database schema and seed data."""
    app.teardown_appcontext(close_db)

    # Ensure the directory for the DB file exists
    db_path = app.config["DB_PATH"]
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)

    db = sqlite3.connect(db_path)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA foreign_keys=ON")

    # Create tables
    db.executescript(SCHEMA_SQL)

    # Seed default exercise types if empty
    cursor = db.execute("SELECT COUNT(*) FROM exercise_types")
    if cursor.fetchone()[0] == 0:
        for et in DEFAULT_EXERCISE_TYPES:
            db.execute(
                "INSERT INTO exercise_types (name, category, fields, is_default) VALUES (?, ?, ?, 1)",
                (et["name"], et["category"], et["fields"]),
            )
        db.commit()

    db.close()


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS activities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    activity_date TEXT NOT NULL,
    activity_type TEXT NOT NULL,
    duration_minutes INTEGER,
    distance_km REAL,
    calories INTEGER,
    notes TEXT,
    details TEXT DEFAULT '{}'
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
