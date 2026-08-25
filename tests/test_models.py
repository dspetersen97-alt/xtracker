import json

from app.models import (
    count_activities,
    create_activity,
    create_exercise_type,
    delete_activity,
    delete_exercise_type,
    get_activities,
    get_activity_by_id,
    get_exercise_type_by_name,
    get_exercise_types,
)


class TestActivityCRUD:
    def test_create_activity_basic(self, app_context):
        activity_id = create_activity(
            activity_date="2025-01-15",
            activity_type="run",
            duration_minutes=30,
            distance_km=5.0,
            notes="Morning run",
        )
        assert activity_id is not None
        assert activity_id > 0

    def test_create_and_get_by_id(self, app_context):
        activity_id = create_activity(
            activity_date="2025-01-15",
            activity_type="hike",
            duration_minutes=120,
            distance_km=8.5,
            calories=450,
            notes="Trail hike",
            details={"elevation_gain_m": 300, "trail": "Blue Ridge"},
        )
        activity = get_activity_by_id(activity_id)
        assert activity is not None
        assert activity["activity_type"] == "hike"
        assert activity["distance_km"] == 8.5
        assert activity["duration_minutes"] == 120
        assert activity["calories"] == 450
        assert activity["notes"] == "Trail hike"
        assert activity["details_parsed"]["elevation_gain_m"] == 300
        assert activity["details_parsed"]["trail"] == "Blue Ridge"

    def test_create_strength_activity(self, app_context):
        exercises = [
            {"name": "squat", "sets": 3, "reps": 10, "weight_kg": 60},
            {"name": "bench press", "sets": 3, "reps": 8, "weight_kg": 50},
        ]
        activity_id = create_activity(
            activity_date="2025-01-16",
            activity_type="strength",
            duration_minutes=45,
            details={"exercises": exercises},
        )
        activity = get_activity_by_id(activity_id)
        assert activity["activity_type"] == "strength"
        assert len(activity["details_parsed"]["exercises"]) == 2
        assert activity["details_parsed"]["exercises"][0]["name"] == "squat"

    def test_get_activity_not_found(self, app_context):
        assert get_activity_by_id(9999) is None

    def test_delete_activity(self, app_context):
        activity_id = create_activity(
            activity_date="2025-01-15",
            activity_type="walk",
            duration_minutes=20,
        )
        assert delete_activity(activity_id) is True
        assert get_activity_by_id(activity_id) is None

    def test_delete_activity_not_found(self, app_context):
        assert delete_activity(9999) is False


class TestActivityFiltering:
    def _seed_activities(self):
        create_activity("2025-01-10", "run", duration_minutes=30, distance_km=5.0)
        create_activity("2025-01-12", "hike", duration_minutes=120, distance_km=10.0)
        create_activity("2025-01-15", "run", duration_minutes=25, distance_km=4.0)
        create_activity("2025-01-18", "strength", duration_minutes=45)
        create_activity("2025-01-20", "cardio", duration_minutes=30, calories=250)

    def test_get_all_activities(self, app_context):
        self._seed_activities()
        activities = get_activities()
        assert len(activities) == 5

    def test_filter_by_type(self, app_context):
        self._seed_activities()
        runs = get_activities(activity_type="run")
        assert len(runs) == 2
        assert all(a["activity_type"] == "run" for a in runs)

    def test_filter_by_date_from(self, app_context):
        self._seed_activities()
        activities = get_activities(date_from="2025-01-15")
        assert len(activities) == 3

    def test_filter_by_date_to(self, app_context):
        self._seed_activities()
        activities = get_activities(date_to="2025-01-12")
        assert len(activities) == 2

    def test_filter_by_date_range(self, app_context):
        self._seed_activities()
        activities = get_activities(date_from="2025-01-12", date_to="2025-01-18")
        assert len(activities) == 3

    def test_filter_by_type_and_date(self, app_context):
        self._seed_activities()
        runs = get_activities(activity_type="run", date_from="2025-01-14")
        assert len(runs) == 1
        assert runs[0]["activity_date"] == "2025-01-15"

    def test_pagination_limit(self, app_context):
        self._seed_activities()
        activities = get_activities(limit=2)
        assert len(activities) == 2

    def test_pagination_offset(self, app_context):
        self._seed_activities()
        page1 = get_activities(limit=2, offset=0)
        page2 = get_activities(limit=2, offset=2)
        assert len(page1) == 2
        assert len(page2) == 2
        assert page1[0]["id"] != page2[0]["id"]

    def test_count_activities(self, app_context):
        self._seed_activities()
        assert count_activities() == 5
        assert count_activities(activity_type="run") == 2
        assert count_activities(date_from="2025-01-15") == 3

    def test_ordering_most_recent_first(self, app_context):
        self._seed_activities()
        activities = get_activities()
        dates = [a["activity_date"] for a in activities]
        assert dates == sorted(dates, reverse=True)


class TestExerciseTypes:
    def test_default_types_seeded(self, app_context):
        types = get_exercise_types()
        assert len(types) == 5
        names = [t["name"] for t in types]
        assert "hike" in names
        assert "walk" in names
        assert "run" in names
        assert "cardio" in names
        assert "strength" in names

    def test_get_type_by_name(self, app_context):
        et = get_exercise_type_by_name("strength")
        assert et is not None
        assert et["category"] == "strength"
        assert "exercises" in et["fields_parsed"]

    def test_get_type_not_found(self, app_context):
        assert get_exercise_type_by_name("swimming") is None

    def test_create_custom_type(self, app_context):
        type_id = create_exercise_type(
            name="Swimming",
            category="cardio",
            fields=["date", "duration", "distance", "notes"],
        )
        assert type_id is not None
        et = get_exercise_type_by_name("swimming")
        assert et is not None
        assert et["category"] == "cardio"
        assert et["is_default"] == 0

    def test_delete_custom_type(self, app_context):
        type_id = create_exercise_type("yoga", "cardio", ["date", "duration", "notes"])
        assert delete_exercise_type(type_id) is True
        assert get_exercise_type_by_name("yoga") is None

    def test_cannot_delete_default_type(self, app_context):
        et = get_exercise_type_by_name("run")
        assert delete_exercise_type(et["id"]) is False
        # Still exists
        assert get_exercise_type_by_name("run") is not None
