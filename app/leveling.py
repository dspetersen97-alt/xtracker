"""Leveling system with a flattened power-curve progression.

XP curve: total XP to reach level L = C * (L-1)^2.2, calibrated so
level 99 requires ~13,034,431 XP (the same endpoint as the classic
RuneScape curve). Compared to RuneScape, this flattens the escalation:
lower levels cost relatively more and higher levels relatively less,
while still growing meaningfully as levels increase.

- Level 1:  0 XP
- Level 2:  ~542 XP
- Level 50: ~2,837,000 XP
- Level 99: ~13,034,431 XP
- Max level: 99

Skills (5 total):
- Cardio
- Flexibility
- Steps (daily step counts only)
- Endurance
- Strength

Each exercise type carries a skill % distribution (e.g. Run = 75% Cardio,
25% Endurance). An activity's score is split proportionally across those
skills. Steps is not assignable from workouts; it is derived from daily
step counts.
"""

import json

MAX_LEVEL = 99

# Curve parameters
_CURVE_EXPONENT = 2.2
_LEVEL_99_XP = 13_034_431  # keep the classic endpoint

# Pre-compute XP table (total XP needed to reach each level)
_XP_TABLE = [0] * (MAX_LEVEL + 1)


def _build_xp_table():
    """Build the XP table using a power curve: XP(L) = C * (L-1)^exponent.

    C is calibrated so that reaching MAX_LEVEL costs exactly _LEVEL_99_XP.
    """
    c = _LEVEL_99_XP / ((MAX_LEVEL - 1) ** _CURVE_EXPONENT)
    _XP_TABLE[1] = 0  # Level 1 starts at 0 XP
    for level in range(2, MAX_LEVEL + 1):
        _XP_TABLE[level] = round(c * ((level - 1) ** _CURVE_EXPONENT))


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


# The five skills. "steps" is derived from daily step counts only and is not
# assignable via workout skill distributions (the other four are).
SKILLS = ["cardio", "flexibility", "steps", "endurance", "strength"]
WORKOUT_SKILLS = ["cardio", "flexibility", "endurance", "strength"]


def get_skill_distribution(activity_type, db):
    """Get the skill % distribution for an exercise type as a normalized
    dict of {skill: fraction}, where fractions sum to 1.0.

    Returns an empty dict if the type is unknown or has no distribution.
    """
    if not activity_type:
        return {}
    row = db.execute(
        "SELECT skills FROM exercise_types WHERE name = ?",
        (activity_type,),
    ).fetchone()
    if row is None:
        return {}
    try:
        raw = json.loads(row["skills"] or "{}")
    except (ValueError, TypeError):
        return {}

    # Keep only valid workout skills with positive weight
    weights = {
        k: float(v)
        for k, v in raw.items()
        if k in WORKOUT_SKILLS and _is_positive_number(v)
    }
    total = sum(weights.values())
    if total <= 0:
        return {}
    return {k: v / total for k, v in weights.items()}


def _is_positive_number(v):
    try:
        return float(v) > 0
    except (ValueError, TypeError):
        return False


# Steps skill: three-tier daily rates (per step)
XP_PER_STEP_TIER1 = 500 / 1000.0     # steps 1-5,000:      500 XP / 1000
XP_PER_STEP_TIER2 = 1000 / 1000.0    # steps 5,000-10,000: 1000 XP / 1000
XP_PER_STEP_TIER3 = 2000 / 1000.0    # steps 10,000+:      2000 XP / 1000
STEP_TIER1_CAP = 5000
STEP_TIER2_CAP = 10000


def steps_xp_for_day(steps):
    """Compute Steps XP for a single day's step count, with three tiers.

    Steps 1-5,000       earn 500 XP per 1,000.
    Steps 5,000-10,000  earn 1,000 XP per 1,000.
    Steps 10,000+       earn 2,000 XP per 1,000.
    """
    if not steps or steps <= 0:
        return 0.0

    tier1 = min(steps, STEP_TIER1_CAP)
    tier2 = min(max(steps - STEP_TIER1_CAP, 0), STEP_TIER2_CAP - STEP_TIER1_CAP)
    tier3 = max(steps - STEP_TIER2_CAP, 0)

    return (
        tier1 * XP_PER_STEP_TIER1
        + tier2 * XP_PER_STEP_TIER2
        + tier3 * XP_PER_STEP_TIER3
    )


def get_steps_xp(person, db):
    """Get total Steps-skill XP from daily step counts.
    Three-tier per day: 500 / 1000 / 2000 XP per 1000 steps.
    Applied per day so the thresholds reset each day.
    """
    rows = db.execute(
        "SELECT steps FROM daily_health WHERE person = ? AND steps IS NOT NULL",
        (person,),
    ).fetchall()

    total_xp = sum(steps_xp_for_day(row["steps"]) for row in rows if row["steps"])
    return round(total_xp)


def get_skill_xp(person, db):
    """Get total XP for each skill for a person.

    Each activity's score is split across the skills its exercise type is
    assigned to (per that type's % distribution). Steps XP is added from
    daily health data.

    Returns dict with 'cardio', 'flexibility', 'endurance', 'strength',
    and 'steps' XP totals.
    """
    skills = {s: 0.0 for s in WORKOUT_SKILLS}

    # Read the pre-computed score stored on each activity and split it across
    # the exercise type's skills. Scores are persisted at write time
    # (create/edit/import) and via the refresh_xp script, so no re-scoring
    # happens on read.
    rows = db.execute(
        "SELECT activity_type, score FROM activities WHERE person = ? AND score IS NOT NULL",
        (person,),
    ).fetchall()

    for row in rows:
        score = row["score"]
        if not score:
            continue
        distribution = get_skill_distribution(row["activity_type"], db)
        if not distribution:
            continue
        for skill, fraction in distribution.items():
            skills[skill] += score * fraction

    # Round activity-based totals
    result = {k: round(v) for k, v in skills.items()}
    # Add steps skill XP from daily health data
    result["steps"] = get_steps_xp(person, db)
    return result


def get_profile_data(person, db):
    """Get full leveling profile for a person.

    Returns dict with skill data for cardio, flexibility, endurance,
    strength, and steps, plus a combined 'total' level.
    """
    skill_xp = get_skill_xp(person, db)

    profile = {}
    total_xp = 0

    for skill in SKILLS:
        xp = skill_xp[skill]
        total_xp += xp
        profile[skill] = xp_progress(xp)

    profile["total"] = xp_progress(total_xp)

    return profile
