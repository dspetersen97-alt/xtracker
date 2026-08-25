"""Workout scoring system.

Calculates a score for running, walking, and hiking activities based on:
- Distance (km)
- Total ascent (meters)
- Duration (minutes)
- Sex (for max HR estimation)
- Weight (kg)
- Average heart rate (bpm)

Score formula:
    base_score = distance_km * 10 + (ascent_m / 10)
    speed_factor = distance_km / (duration_minutes / 60)  [km/h]
    hr_factor = avg_hr / estimated_max_hr  [0.0 - 1.0+]
    weight_factor = weight_kg / 70  [normalized to 70kg baseline]
    
    raw_score = base_score * (1 + speed_factor / 10) * (0.5 + hr_factor) * weight_factor
    
The weather multiplier is applied externally after this calculation.
"""

from datetime import date


def estimate_max_hr(age, sex):
    """Estimate maximum heart rate using age and sex.
    
    Uses the Tanaka formula (208 - 0.7 * age) as baseline.
    Female max HR is typically ~5-6 bpm lower in some models, 
    but Tanaka is considered sex-neutral. We use a small adjustment.
    """
    if age is None or age <= 0:
        age = 30  # default assumption
    max_hr = 208 - (0.7 * age)
    if sex == "female":
        max_hr -= 3  # slight physiological adjustment
    return max_hr


def calculate_score(distance_km, total_ascent_m, duration_minutes,
                    weight_kg, sex, avg_hr, age=None):
    """Calculate a workout score for running/walking/hiking.
    
    Args:
        distance_km: Distance in kilometers
        total_ascent_m: Total elevation gain in meters
        duration_minutes: Duration in minutes
        weight_kg: Person's weight in kg
        sex: 'male' or 'female' (for max HR estimation)
        avg_hr: Average heart rate during workout
        age: Person's age (if None, defaults to 30)
    
    Returns:
        float score, or None if insufficient data
    """
    # Need at minimum distance and duration to score
    if not distance_km or not duration_minutes or duration_minutes <= 0:
        return None
    
    # Default values for optional fields
    if total_ascent_m is None:
        total_ascent_m = 0
    if weight_kg is None:
        weight_kg = 70.0  # neutral baseline
    if sex is None:
        sex = "male"  # neutral default for max HR calc
    
    # Base score: distance contribution + elevation contribution
    # Every km = 10 points, every 10m of ascent = 1 point
    base_score = (distance_km * 10) + (total_ascent_m / 10)
    
    # Speed factor: reward faster pace
    # speed in km/h, divided by 10 gives a multiplier boost
    # e.g. 10 km/h running = 1.0 boost, 5 km/h walking = 0.5 boost
    duration_hours = duration_minutes / 60.0
    speed_kmh = distance_km / duration_hours
    speed_factor = 1 + (speed_kmh / 10)
    
    # Heart rate factor: reward higher effort
    # Expressed as fraction of estimated max HR
    # If no HR data, use neutral 0.7 (moderate effort assumed)
    if avg_hr and avg_hr > 0:
        max_hr = estimate_max_hr(age, sex)
        hr_intensity = avg_hr / max_hr
        # Clamp between 0.5 and 1.2 to avoid extreme values
        hr_intensity = max(0.5, min(1.2, hr_intensity))
        hr_factor = 0.5 + hr_intensity
    else:
        hr_factor = 1.2  # moderate default (0.5 + 0.7)
    
    # Weight factor: heavier person expends more energy
    # Normalized to 70kg baseline
    weight_factor = weight_kg / 70.0
    
    # Final score
    raw_score = base_score * speed_factor * hr_factor * weight_factor
    
    return round(raw_score, 1)


def calculate_weather_multiplier(temp_c, humidity):
    """Calculate a weather difficulty multiplier.
    
    Rewards exercising in extreme conditions:
    - Temperature: penalty/bonus outside 10-20C comfort zone
    - Humidity: penalty/bonus above 60%
    
    Args:
        temp_c: Temperature in Celsius
        humidity: Humidity percentage (0-100)
    
    Returns:
        float multiplier >= 1.0 (1.0 = no bonus, higher = harder conditions)
    """
    if temp_c is None and humidity is None:
        return 1.0
    
    multiplier = 1.0
    
    # Temperature factor
    # Comfort zone: 10-20C. Outside that, conditions get harder.
    if temp_c is not None:
        if temp_c > 30:
            # Hot: up to 15% bonus at 40C+
            multiplier += min(0.15, (temp_c - 30) * 0.015)
        elif temp_c > 20:
            # Warm: slight bonus
            multiplier += (temp_c - 20) * 0.005
        elif temp_c < 0:
            # Very cold: up to 15% bonus at -15C
            multiplier += min(0.15, abs(temp_c) * 0.01)
        elif temp_c < 10:
            # Cool: slight bonus
            multiplier += (10 - temp_c) * 0.005
    
    # Humidity factor
    # Above 60% makes exercise harder
    if humidity is not None:
        if humidity > 60:
            # Up to 10% bonus at 100% humidity
            multiplier += min(0.10, (humidity - 60) * 0.0025)
    
    # Combined extreme: hot + humid is especially hard
    if temp_c is not None and humidity is not None:
        if temp_c > 28 and humidity > 70:
            # Extra bonus for heat + humidity combo
            multiplier += 0.05
    
    return round(multiplier, 3)


def score_activity(activity, person_profile):
    """Score an activity using the person's profile.
    
    Args:
        activity: dict with activity fields (distance_km, total_ascent_m, 
                  duration_minutes, avg_hr, weather_temp_c, weather_humidity)
        person_profile: dict with person fields (weight_kg, sex, birth_year)
    
    Returns:
        dict with 'score', 'weather_multiplier', 'final_score'
        or None if activity type is not scoreable
    """
    activity_type = activity.get("activity_type", "")
    
    # Only score running, walking, hiking
    if activity_type not in ("run", "walk", "hike"):
        return None
    
    # Get person's age
    age = None
    if person_profile and person_profile.get("birth_year"):
        age = date.today().year - person_profile["birth_year"]
    
    weight_kg = person_profile.get("weight_kg") if person_profile else None
    sex = person_profile.get("sex") if person_profile else None
    
    # Calculate base score
    raw_score = calculate_score(
        distance_km=activity.get("distance_km"),
        total_ascent_m=activity.get("total_ascent_m"),
        duration_minutes=activity.get("duration_minutes"),
        weight_kg=weight_kg,
        sex=sex,
        avg_hr=activity.get("avg_hr"),
        age=age,
    )
    
    if raw_score is None:
        return None
    
    # Calculate weather multiplier
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
