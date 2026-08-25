"""DEV ONLY: Clear all activities and health data, keeping people and exercise types."""
import os
import sqlite3
import sys

# Resolve DB path same way the app does
base_dir = os.path.dirname(os.path.abspath(__file__))
data_dir = os.environ.get("DATA_DIR", os.path.join(base_dir, "data"))
db_path = os.path.join(data_dir, "xtracker.db")

if not os.path.exists(db_path):
    print(f"No database found at {db_path}")
    sys.exit(1)

db = sqlite3.connect(db_path)

activities = db.execute("SELECT COUNT(*) FROM activities").fetchone()[0]
health = db.execute("SELECT COUNT(*) FROM daily_health").fetchone()[0]

print(f"Database: {db_path}")
print(f"  Activities to delete: {activities}")
print(f"  Daily health records to delete: {health}")
print()

confirm = input("Are you sure? (yes/no): ").strip().lower()
if confirm != "yes":
    print("Aborted.")
    sys.exit(0)

db.execute("DELETE FROM activities")
db.execute("DELETE FROM daily_health")
db.execute("DELETE FROM settings WHERE key = 'garmin_last_sync'")
db.commit()
db.close()

print(f"Cleared {activities} activities and {health} health records.")
print("People, exercise types, and Garmin credentials kept.")
