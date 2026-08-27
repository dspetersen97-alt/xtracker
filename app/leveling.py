"""RuneScape-style leveling system.

XP formula matches RuneScape's level progression:
- Level 1->2: 83 XP
- Level 98->99: 1,228,825 XP
- Max level: 99

Three skills based on activity categories:
- Strength (strength activities)
- Cardio (cardio activities)
- Outdoor (hike, walk, run)

Activity scores are converted directly to XP for the appropriate skill.
"""

import math

MAX_LEVEL = 99

# Pre-compute XP table (total XP needed to reach each level)
_XP_TABLE = [0] * (MAX_LEVEL + 1)


def _build_xp_table():
    """Build the XP-per-level table using the RuneScape formula.
    
    Total XP for level L = floor(sum for x=1 to L-1 of floor(x + 300 * 2^(x/7)) / 4)
    """
    _XP_TABLE[1] = 0  # Level 1 starts at 0 XP
    total = 0
    for x in range(1, MAX_LEVEL):
        total += math.floor(x + 300 * (2 ** (x / 7)))
        _XP_TABLE[x + 1] = math.floor(total / 4)


_build_xp_table()


def xp_for_level(level):
    """Get the total XP required to reach a given level (1-99)."""
    if level < 1:
        return 0
    if level > MAX_LEVEL:
        return _XP_TABLE[MAX_LEVEL]
    return _XP_TABLE[level]


def level_for_xp(xp):
    """Get the level for a given amount of total XP."""
    if xp < 0:
        return 1
    for level in range(MAX_LEVEL, 0, -1):
        if xp >= _XP_TABLE[level]:
            return level
    return 1


def xp_progress(xp):
    """Get detailed progress info for a given XP amount.
    
    Returns dict with:
        level: current level (1-99)
        xp_total: total XP accumulated
        xp_current_level: XP needed to reach current level
        xp_next_level: XP needed to reach next level (None if max)
        xp_into_level: XP earned past current level threshold
        xp_for_next: XP still needed for next level
        progress_pct: percentage progress toward next level (0-100)
    """
    level = level_for_xp(xp)
    xp_current = xp_for_level(level)
    
    if level >= MAX_LEVEL:
        return {
            "level": MAX_LEVEL,
            "xp_total": xp,
            "xp_current_level": xp_current,
            "xp_next_level": None,
            "xp_into_level": xp - xp_current,
            "xp_for_next": 0,
            "progress_pct": 100,
        }
    
    xp_next = xp_for_level(level + 1)
    xp_into = xp - xp_current
    xp_needed = xp_next - xp_current
    progress = (xp_into / xp_needed * 100) if xp_needed > 0 else 0
    
    return {
        "level": level,
        "xp_total": xp,
        "xp_current_level": xp_current,
        "xp_next_level": xp_next,
        "xp_into_level": xp_into,
        "xp_for_next": xp_next - xp,
        "progress_pct": min(100, round(progress, 1)),
    }


# Skill category mapping
SKILL_CATEGORIES = {
    "strength": "strength",
    "cardio": "cardio",
    "outdoor": "outdoor",
}

# Map activity types to skills
ACTIVITY_TYPE_TO_SKILL = {
    "run": "outdoor",
    "walk": "outdoor",
    "hike": "outdoor",
    "cardio": "cardio",
    "strength": "strength",
}


def get_skill_for_activity(activity_type):
    """Get the skill category for a given activity type."""
    return ACTIVITY_TYPE_TO_SKILL.get(activity_type)


def get_skill_xp(person, db):
    """Get total XP for each skill for a person.
    
    Sums all activity scores grouped by skill category.
    Returns dict with 'strength', 'cardio', 'outdoor' XP totals.
    """
    skills = {"strength": 0, "cardio": 0, "outdoor": 0}
    
    rows = db.execute(
        """SELECT activity_type, distance_km, total_ascent_m, duration_minutes,
                  avg_hr, calories, person_weight_kg, person_sex, person_birth_year,
                  weather_temp_c, weather_humidity
           FROM activities
           WHERE person = ? AND activity_type IN ('run', 'walk', 'hike', 'cardio', 'strength')""",
        (person,),
    ).fetchall()
    
    from .scoring import score_activity
    
    for row in rows:
        activity_type = row["activity_type"]
        skill = get_skill_for_activity(activity_type)
        if not skill:
            continue
        
        # Compute score dynamically (same as display)
        activity_data = {
            "activity_type": activity_type,
            "distance_km": row["distance_km"],
            "total_ascent_m": row["total_ascent_m"],
            "duration_minutes": row["duration_minutes"],
            "avg_hr": row["avg_hr"],
            "calories": row["calories"],
            "weather_temp_c": row["weather_temp_c"],
            "weather_humidity": row["weather_humidity"],
        }
        person_profile = {
            "weight_kg": row["person_weight_kg"],
            "sex": row["person_sex"],
            "birth_year": row["person_birth_year"],
        }
        
        result = score_activity(activity_data, person_profile)
        if result and result["final_score"]:
            skills[skill] += result["final_score"]
    
    # Round totals
    return {k: round(v) for k, v in skills.items()}


def get_profile_data(person, db):
    """Get full leveling profile for a person.
    
    Returns dict with skill data for strength, cardio, outdoor,
    plus a combined 'total' level.
    """
    skill_xp = get_skill_xp(person, db)
    
    profile = {}
    total_xp = 0
    
    for skill in ("strength", "cardio", "outdoor"):
        xp = skill_xp[skill]
        total_xp += xp
        profile[skill] = xp_progress(xp)
    
    profile["total"] = xp_progress(total_xp)
    
    return profile
