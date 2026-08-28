"""Workout scoring system.

Calculates XP for activities using type-specific formulas, calibrated so:
- 5k run (165 bpm, 50m ascent)          ~= 5,000 XP
- Marathon (42.2km, 160 bpm)            ~= 120,000 XP
- 30-min walk (~100 bpm)                ~= 5,000 XP
- 5mi/2hr/600ft hike                    ~= 12,000 XP
- All-day 15mi/8hr/4000ft hike          ~= 122,000 XP
- Cardio / strength: duration + intensity based
- Steps: tiered daily (handled in leveling.py)

Running scales super-linearly with distance (^1.5).
Walking scales super-linearly with time (^1.3).
Hiking scales with distance + time and an elevation multiplier.
Heart rate modulates all activities as an effort/intensity factor.

The weather multiplier is applied on top for outdoor activities.
"""

from datetime import date

# --- Calibration constants ---
RUN_K = 447.2              # 5k at effort 1.0 -> ~5,000 XP
RUN_DIST_EXP = 1.5         # super-linear distance scaling
RUN_REF_INTENSITY = 0.896  # HR intensity mapping to effort 1.0 (~165 bpm @ 34yo)

WALK_K = 58.6              # 30 min at pace 1.0 -> ~5,000 XP
WALK_TIME_EXP = 1.3        # super-linear time scaling

HIKE_DIST_A = 599.0        # per-km base contribution
HIKE_TIME_B = 2523.0       # per-hour base contribution
HIKE_ELEV_REF = 600.0      # elevation reference (meters)
HIKE_ELEV_EXP = 1.3        # elevation multiplier exponent

# Cardio / strength are duration+intensity based.
# Calibrated so a solid session lands in the low thousands (~5x prior output).
CARDIO_PER_MIN = 67.0
CARDIO_PER_KM = 50.0
STRENGTH_PER_MIN = 85.0


def estimate_max_hr(age, sex):
    """Estimate maximum heart rate using age and sex (Tanaka formula)."""
    if age is None or age <= 0:
        age = 30
    max_hr = 208 - (0.7 * age)
    if sex == "female":
        max_hr -= 3
    return max_hr


def _hr_effort_factor(avg_hr, age, sex, lo=0.6, hi=1.4, default=1.0):
    """Effort factor from HR intensity, normalized so the run reference
    intensity (~165 bpm) maps to 1.0. Clamped to avoid extremes.
    """
    if not avg_hr or avg_hr <= 0:
        return default
    max_hr = estimate_max_hr(age, sex)
    intensity = avg_hr / max_hr
    factor = intensity / RUN_REF_INTENSITY
    return max(lo, min(hi, factor))


def calculate_run_score(distance_km, duration_minutes, weight_kg, sex, avg_hr, age=None):
    """Score a run: distance-driven, super-linear, HR-modulated."""
    if not distance_km or distance_km <= 0:
        return None

    effort = _hr_effort_factor(avg_hr, age, sex)
    weight_factor = (weight_kg / 70.0) if weight_kg else 1.0

    raw = RUN_K * (distance_km ** RUN_DIST_EXP) * effort * weight_factor
    return round(raw, 1)


def calculate_walk_score(duration_minutes, weight_kg, sex, avg_hr, age=None):
    """Score a walk: time-driven, super-linear, mild pace/HR bonus."""
    if not duration_minutes or duration_minutes <= 0:
        return None

    # Mild pace factor: a normal walk (~100 bpm) = 1.0, brisk up to ~1.15
    if avg_hr and avg_hr > 0:
        max_hr = estimate_max_hr(age, sex)
        intensity = avg_hr / max_hr
        ref = 100.0 / max_hr
        pace = 1.0 + (intensity - ref) * 1.6
        pace = max(0.9, min(1.15, pace))
    else:
        pace = 1.0

    weight_factor = (weight_kg / 70.0) if weight_kg else 1.0

    raw = WALK_K * (duration_minutes ** WALK_TIME_EXP) * pace * weight_factor
    return round(raw, 1)


def calculate_hike_score(distance_km, duration_minutes, total_ascent_m,
                         weight_kg, sex, avg_hr, age=None):
    """Score a hike: distance + time base, elevation multiplier, HR nudge."""
    if (not distance_km or distance_km <= 0) and (not duration_minutes or duration_minutes <= 0):
        return None

    dist = distance_km or 0
    dur = duration_minutes or 0
    ascent = total_ascent_m or 0

    base = dist * HIKE_DIST_A + (dur / 60.0) * HIKE_TIME_B
    elev_mult = 1 + (ascent / HIKE_ELEV_REF) ** HIKE_ELEV_EXP

    # Mild HR effort nudge centered on a typical hiking HR (~120 bpm = 1.0),
    # kept gentle so terrain/distance dominate.
    if avg_hr and avg_hr > 0:
        max_hr = estimate_max_hr(age, sex)
        intensity = avg_hr / max_hr
        ref = 120.0 / max_hr
        effort = 1.0 + (intensity - ref) * 1.2
        effort = max(0.9, min(1.2, effort))
    else:
        effort = 1.0
    weight_factor = (weight_kg / 70.0) if weight_kg else 1.0

    raw = base * elev_mult * effort * weight_factor
    return round(raw, 1)


def calculate_cardio_score(duration_minutes, distance_km=None, calories=None,
                           weight_kg=None, sex=None, avg_hr=None, age=None):
    """Score cardio: duration + optional distance, HR-modulated."""
    if not duration_minutes or duration_minutes <= 0:
        return None

    if weight_kg is None:
        weight_kg = 70.0

    base_score = duration_minutes * CARDIO_PER_MIN
    if distance_km and distance_km > 0:
        base_score += distance_km * CARDIO_PER_KM

    if avg_hr and avg_hr > 0:
        max_hr = estimate_max_hr(age, sex)
        hr_intensity = max(0.5, min(1.2, avg_hr / max_hr))
        hr_factor = 0.5 + hr_intensity
    else:
        hr_factor = 1.2

    weight_factor = weight_kg / 70.0
    return round(base_score * hr_factor * weight_factor, 1)


def calculate_strength_score(duration_minutes, calories=None,
                             weight_kg=None, sex=None, avg_hr=None, age=None):
    """Score strength training: duration + intensity based."""
    if not duration_minutes or duration_minutes <= 0:
        return None

    if weight_kg is None:
        weight_kg = 70.0

    base_score = duration_minutes * STRENGTH_PER_MIN

    if avg_hr and avg_hr > 0:
        max_hr = estimate_max_hr(age, sex)
        hr_intensity = max(0.4, min(1.1, avg_hr / max_hr))
        hr_factor = 0.5 + hr_intensity
    else:
        hr_factor = 1.1

    weight_factor = weight_kg / 70.0
    return round(base_score * hr_factor * weight_factor, 1)


def calculate_generic_score(duration_minutes, distance_km=None, calories=None,
                            weight_kg=None, sex=None, avg_hr=None, age=None):
    """Generic duration + HR based score for types without a dedicated
    formula (hiit, yoga, pilates, and custom user-defined types).

    Mirrors the cardio formula: duration-driven with an optional distance
    contribution and HR intensity modulation.
    """
    if not duration_minutes or duration_minutes <= 0:
        return None

    if weight_kg is None:
        weight_kg = 70.0

    base_score = duration_minutes * CARDIO_PER_MIN
    if distance_km and distance_km > 0:
        base_score += distance_km * CARDIO_PER_KM

    if avg_hr and avg_hr > 0:
        max_hr = estimate_max_hr(age, sex)
        hr_intensity = max(0.5, min(1.2, avg_hr / max_hr))
        hr_factor = 0.5 + hr_intensity
    else:
        hr_factor = 1.2

    weight_factor = weight_kg / 70.0
    return round(base_score * hr_factor * weight_factor, 1)


def calculate_weather_multiplier(temp_c, humidity):
    """Weather difficulty multiplier (>= 1.0), rewarding extreme conditions."""
    if temp_c is None and humidity is None:
        return 1.0

    multiplier = 1.0

    if temp_c is not None:
        if temp_c > 30:
            multiplier += min(0.15, (temp_c - 30) * 0.015)
        elif temp_c > 20:
            multiplier += (temp_c - 20) * 0.005
        elif temp_c < 0:
            multiplier += min(0.15, abs(temp_c) * 0.01)
        elif temp_c < 10:
            multiplier += (10 - temp_c) * 0.005

    if humidity is not None:
        if humidity > 60:
            multiplier += min(0.10, (humidity - 60) * 0.0025)

    if temp_c is not None and humidity is not None:
        if temp_c > 28 and humidity > 70:
            multiplier += 0.05

    return round(multiplier, 3)


def score_activity(activity, person_profile):
    """Score an activity using the person's profile.

    Returns dict with 'score', 'weather_multiplier', 'final_score',
    or None if the activity type is not scoreable.
    """
    activity_type = activity.get("activity_type", "")

    age = None
    if person_profile and person_profile.get("birth_year"):
        age = date.today().year - person_profile["birth_year"]

    weight_kg = person_profile.get("weight_kg") if person_profile else None
    sex = person_profile.get("sex") if person_profile else None

    raw_score = None

    if activity_type == "run":
        raw_score = calculate_run_score(
            distance_km=activity.get("distance_km"),
            duration_minutes=activity.get("duration_minutes"),
            weight_kg=weight_kg, sex=sex,
            avg_hr=activity.get("avg_hr"), age=age,
        )
    elif activity_type == "walk":
        raw_score = calculate_walk_score(
            duration_minutes=activity.get("duration_minutes"),
            weight_kg=weight_kg, sex=sex,
            avg_hr=activity.get("avg_hr"), age=age,
        )
    elif activity_type == "hike":
        raw_score = calculate_hike_score(
            distance_km=activity.get("distance_km"),
            duration_minutes=activity.get("duration_minutes"),
            total_ascent_m=activity.get("total_ascent_m"),
            weight_kg=weight_kg, sex=sex,
            avg_hr=activity.get("avg_hr"), age=age,
        )
    elif activity_type == "cardio":
        raw_score = calculate_cardio_score(
            duration_minutes=activity.get("duration_minutes"),
            distance_km=activity.get("distance_km"),
            calories=activity.get("calories"),
            weight_kg=weight_kg, sex=sex,
            avg_hr=activity.get("avg_hr"), age=age,
        )
    elif activity_type == "strength":
        raw_score = calculate_strength_score(
            duration_minutes=activity.get("duration_minutes"),
            calories=activity.get("calories"),
            weight_kg=weight_kg, sex=sex,
            avg_hr=activity.get("avg_hr"), age=age,
        )
    else:
        # Generic duration + HR formula for all other types
        # (e.g. hiit, yoga, pilates, and custom user-defined types).
        raw_score = calculate_generic_score(
            duration_minutes=activity.get("duration_minutes"),
            distance_km=activity.get("distance_km"),
            weight_kg=weight_kg, sex=sex,
            avg_hr=activity.get("avg_hr"), age=age,
        )

    if raw_score is None:
        return None

    # Weather multiplier only for outdoor activities
    weather_mult = 1.0
    if activity_type in ("run", "walk", "hike"):
        weather_mult = calculate_weather_multiplier(
            temp_c=activity.get("weather_temp_c"),
            humidity=activity.get("weather_humidity"),
        )

    final_score = round(raw_score * weather_mult, 1)

    return {
        "score": raw_score,
        "weather_multiplier": weather_mult,
        "final_score": final_score,
    }
