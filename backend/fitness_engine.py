from copy import deepcopy
from datetime import date
import re

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

HOME_EQUIPMENT = {"none", "bodyweight", "mat", "resistance_band", "mini_band", "chair", "jump_rope"}
GYM_EQUIPMENT = {"barbell", "dumbbell", "cable", "machine", "bench", "medicine_ball", "kettlebell", "trap_bar"}

GOAL_ALIASES = {
    "weight_loss": "fat_loss",
    "fat loss": "fat_loss",
    "lose weight": "fat_loss",
    "lean": "lean_physique",
    "tone": "toning",
    "toned": "toning",
    "bulk": "muscle_gain",
    "hypertrophy": "muscle_gain",
}

SESSION_ALIASES = {
    "legs": "legs",
    "leg": "legs",
    "lower": "lower_body",
    "lower body": "lower_body",
    "glute": "glutes",
    "glutes": "glutes",
    "chest": "push",
    "push": "push",
    "back": "pull",
    "pull": "pull",
    "arms": "upper_body",
    "shoulder": "upper_body",
    "upper": "upper_body",
    "upper body": "upper_body",
    "core": "core_cardio",
    "abs": "core_cardio",
    "cardio": "cardio",
    "hiit": "hiit",
    "full": "full_body",
    "full body": "full_body",
    "mobility": "mobility",
    "recovery": "recovery",
    "power": "power",
    "explosive": "power",
    "strength": "strength",
    "agility": "agility",
    "speed": "agility",
    "conditioning": "conditioning",
    "endurance": "endurance",
    "drills": "drills",
}

INJURY_RULES = {
    "knee": {
        "avoid_tags": {"jump", "deep_knee", "lunge_dynamic", "plyometric"},
        "prefer_tags": {"knee_friendly", "hinge", "glute", "mobility"},
    },
    "shoulder": {
        "avoid_tags": {"overhead", "heavy_press", "dip", "throw"},
        "prefer_tags": {"shoulder_friendly", "row", "mobility"},
    },
    "back": {
        "avoid_tags": {"spinal_load", "heavy_hinge", "jump"},
        "prefer_tags": {"core_stability", "supported", "mobility"},
    },
    "wrist": {
        "avoid_tags": {"wrist_loaded", "pushup", "plank"},
        "prefer_tags": {"neutral_grip", "mobility"},
    },
    "ankle": {
        "avoid_tags": {"jump", "sprint", "plyometric"},
        "prefer_tags": {"balance", "mobility", "calf"},
    },
}

WEEKLY_TEMPLATES = {
    ("gym", "male", "muscle_gain"): ["push", "pull", "legs", "upper_body", "push_volume", "pull_volume", "recovery"],
    ("gym", "male", "strength"): ["push_strength", "pull_strength", "legs_strength", "recovery", "upper_body", "lower_body", "recovery"],
    ("gym", "male", "aesthetics"): ["push", "pull", "legs", "shoulders_arms", "upper_body", "lower_body", "recovery"],
    ("gym", "male", "fat_loss"): ["full_body", "cardio", "upper_body", "legs", "hiit", "core_cardio", "recovery"],
    ("gym", "female", "lean_physique"): ["lower_body", "core_cardio", "glutes", "hiit", "full_body", "cardio", "recovery"],
    ("gym", "female", "glute_focus"): ["glutes", "upper_body", "glutes_hamstrings", "core_cardio", "glutes", "full_body", "recovery"],
    ("gym", "female", "toning"): ["full_body", "lower_body", "upper_body", "core_cardio", "full_body", "cardio", "recovery"],
    ("gym", "female", "endurance"): ["cardio", "lower_body", "core_cardio", "full_body", "cardio", "mobility", "recovery"],
    ("gym", "female", "fat_loss"): ["hiit", "lower_body", "core_cardio", "full_body", "cardio", "hiit", "recovery"],
    ("home", "male", "muscle_gain"): ["upper_body", "lower_body", "push", "pull", "legs", "full_body", "recovery"],
    ("home", "male", "strength"): ["lower_body", "upper_body", "core_cardio", "legs", "push", "full_body", "recovery"],
    ("home", "male", "fat_loss"): ["hiit", "core_cardio", "lower_body", "cardio", "full_body", "hiit", "recovery"],
    ("home", "female", "lean_physique"): ["lower_body", "core_cardio", "glutes", "hiit", "full_body", "cardio", "recovery"],
    ("home", "female", "glute_focus"): ["glutes", "core_cardio", "glutes_hamstrings", "upper_body", "glutes", "cardio", "recovery"],
    ("home", "female", "toning"): ["full_body", "core_cardio", "lower_body", "upper_body", "hiit", "cardio", "recovery"],
    ("home", "female", "endurance"): ["cardio", "core_cardio", "lower_body", "hiit", "full_body", "mobility", "recovery"],
    ("home", "female", "fat_loss"): ["hiit", "core_cardio", "lower_body", "cardio", "full_body", "hiit", "recovery"],
    ("sport", "any", "cricket"): ["power", "mobility", "strength", "conditioning", "rotational_power", "reaction_speed", "recovery"],
    ("sport", "any", "football"): ["power", "conditioning", "lower_strength", "agility", "endurance", "match_prep", "recovery"],
    ("sport", "any", "running"): ["endurance", "drills", "lower_strength", "mobility", "knee_stability", "tempo", "recovery"],
}

SESSION_LABELS = {
    "push": "Chest + Triceps",
    "push_volume": "Push Volume",
    "push_strength": "Heavy Push Strength",
    "pull": "Back + Biceps",
    "pull_volume": "Pull Volume",
    "pull_strength": "Heavy Pull Strength",
    "legs": "Legs",
    "legs_strength": "Lower Strength",
    "lower_body": "Lower Body",
    "lower_strength": "Lower Strength",
    "glutes": "Glute Focus",
    "glutes_hamstrings": "Glutes + Hamstrings",
    "upper_body": "Upper Body",
    "shoulders_arms": "Shoulders + Arms",
    "core_cardio": "Core + Cardio",
    "full_body": "Full Body",
    "hiit": "HIIT",
    "cardio": "Cardio",
    "mobility": "Mobility",
    "recovery": "Recovery",
    "power": "Explosive Power",
    "rotational_power": "Rotational Strength",
    "conditioning": "Sprint Conditioning",
    "agility": "Agility + Speed",
    "endurance": "Endurance",
    "reaction_speed": "Reaction Speed",
    "match_prep": "Match Prep",
    "drills": "Running Drills",
    "knee_stability": "Knee Stability",
    "tempo": "Tempo Run",
    "strength": "Strength",
}

EXERCISES = [
    # Gym strength and hypertrophy
    {"name": "Barbell Bench Press", "sessions": ["push", "push_strength"], "modes": ["gym"], "goals": ["muscle_gain", "strength", "aesthetics"], "gender": ["male", "any"], "equipment": ["barbell", "bench"], "muscles": ["chest", "triceps"], "tags": ["heavy_press"], "level": "intermediate", "sets": 4, "reps": "6-8", "rest": "90s", "weight_guide": "Moderate-heavy barbell", "form_key": "pushup"},
    {"name": "Incline Dumbbell Press", "sessions": ["push", "upper_body"], "modes": ["gym"], "goals": ["muscle_gain", "aesthetics", "toning"], "gender": ["any"], "equipment": ["dumbbell", "bench"], "muscles": ["upper chest"], "tags": ["press"], "level": "beginner", "sets": 3, "reps": "8-12", "rest": "75s", "weight_guide": "Controlled dumbbells", "form_key": "pushup"},
    {"name": "Cable Chest Fly", "sessions": ["push", "push_volume"], "modes": ["gym"], "goals": ["muscle_gain", "aesthetics"], "gender": ["male", "any"], "equipment": ["cable"], "muscles": ["chest"], "tags": ["isolation"], "level": "beginner", "sets": 3, "reps": "12-15", "rest": "60s", "weight_guide": "Light cable", "form_key": "pushup"},
    {"name": "Lat Pulldown", "sessions": ["pull", "upper_body"], "modes": ["gym"], "goals": ["muscle_gain", "strength", "toning"], "gender": ["any"], "equipment": ["machine"], "muscles": ["lats", "biceps"], "tags": ["row", "shoulder_friendly"], "level": "beginner", "sets": 3, "reps": "10-12", "rest": "75s", "weight_guide": "Smooth machine load", "form_key": "biceps"},
    {"name": "Seated Cable Row", "sessions": ["pull", "pull_volume", "upper_body"], "modes": ["gym"], "goals": ["muscle_gain", "strength", "toning"], "gender": ["any"], "equipment": ["cable"], "muscles": ["back"], "tags": ["row", "supported", "shoulder_friendly"], "level": "beginner", "sets": 3, "reps": "10-12", "rest": "75s", "weight_guide": "Controlled cable", "form_key": "biceps"},
    {"name": "Romanian Deadlift", "sessions": ["legs", "lower_body", "glutes_hamstrings", "lower_strength"], "modes": ["gym"], "goals": ["muscle_gain", "strength", "glute_focus", "lean_physique"], "gender": ["any"], "equipment": ["barbell", "dumbbell"], "muscles": ["hamstrings", "glutes"], "tags": ["hinge", "heavy_hinge"], "level": "intermediate", "sets": 4, "reps": "8-10", "rest": "90s", "weight_guide": "Moderate hinge load", "form_key": "squat"},
    {"name": "Leg Press", "sessions": ["legs", "legs_strength", "lower_body"], "modes": ["gym"], "goals": ["muscle_gain", "strength"], "gender": ["male", "any"], "equipment": ["machine"], "muscles": ["quads"], "tags": ["deep_knee"], "level": "beginner", "sets": 3, "reps": "10-12", "rest": "90s", "weight_guide": "Machine load", "form_key": "squat"},
    {"name": "Hip Thrust", "sessions": ["glutes", "glutes_hamstrings", "lower_body", "legs"], "modes": ["gym"], "goals": ["glute_focus", "lean_physique", "muscle_gain"], "gender": ["female", "any"], "equipment": ["barbell", "bench"], "muscles": ["glutes"], "tags": ["glute", "knee_friendly"], "level": "beginner", "sets": 4, "reps": "10-12", "rest": "75s", "weight_guide": "Barbell or machine", "form_key": "squat"},
    {"name": "Goblet Squat", "sessions": ["legs", "lower_body", "full_body"], "modes": ["gym", "home"], "goals": ["lean_physique", "toning", "fat_loss", "muscle_gain"], "gender": ["any"], "equipment": ["dumbbell", "kettlebell"], "muscles": ["quads", "glutes"], "tags": ["deep_knee"], "level": "beginner", "sets": 3, "reps": "12-15", "rest": "60s", "weight_guide": "Light-moderate weight", "form_key": "squat"},
    {"name": "Cable Glute Kickback", "sessions": ["glutes", "glutes_hamstrings"], "modes": ["gym"], "goals": ["glute_focus", "lean_physique"], "gender": ["female", "any"], "equipment": ["cable"], "muscles": ["glutes"], "tags": ["glute", "knee_friendly"], "level": "beginner", "sets": 3, "reps": "12-15 each", "rest": "45s", "weight_guide": "Light cable", "form_key": "squat"},
    {"name": "Face Pull", "sessions": ["pull", "upper_body", "mobility"], "modes": ["gym", "home"], "goals": ["aesthetics", "toning", "lean_physique"], "gender": ["any"], "equipment": ["cable", "resistance_band"], "muscles": ["rear delts"], "tags": ["shoulder_friendly", "row"], "level": "beginner", "sets": 3, "reps": "15-20", "rest": "45s", "weight_guide": "Cable or band", "form_key": "biceps"},
    # Home and lean conditioning
    {"name": "Glute Bridge", "sessions": ["glutes", "lower_body", "glutes_hamstrings", "full_body"], "modes": ["home", "gym"], "goals": ["lean_physique", "glute_focus", "toning", "fat_loss"], "gender": ["female", "any"], "equipment": ["bodyweight", "mat", "resistance_band"], "muscles": ["glutes"], "tags": ["glute", "knee_friendly"], "level": "beginner", "sets": 3, "reps": "18-22", "rest": "45s", "weight_guide": "Bodyweight or band", "form_key": "squat"},
    {"name": "Single-Leg Glute Bridge", "sessions": ["glutes", "glutes_hamstrings", "lower_body"], "modes": ["home", "gym"], "goals": ["lean_physique", "glute_focus", "toning"], "gender": ["female", "any"], "equipment": ["bodyweight", "mat"], "muscles": ["glutes", "hamstrings"], "tags": ["glute", "knee_friendly"], "level": "beginner", "sets": 3, "reps": "10-12 each", "rest": "45s", "weight_guide": "Bodyweight", "form_key": "squat"},
    {"name": "Banded Lateral Walk", "sessions": ["glutes", "lower_body", "glutes_hamstrings"], "modes": ["home", "gym"], "goals": ["lean_physique", "glute_focus", "toning", "fat_loss"], "gender": ["female", "any"], "equipment": ["mini_band", "resistance_band"], "muscles": ["glute medius"], "tags": ["glute", "knee_friendly"], "level": "beginner", "sets": 3, "reps": "12 steps each", "rest": "35s", "weight_guide": "Mini band", "form_key": "squat"},
    {"name": "Frog Pumps", "sessions": ["glutes", "glutes_hamstrings"], "modes": ["home", "gym"], "goals": ["lean_physique", "glute_focus", "toning"], "gender": ["female", "any"], "equipment": ["mat", "bodyweight"], "muscles": ["glutes"], "tags": ["glute", "knee_friendly"], "level": "beginner", "sets": 3, "reps": "20-25", "rest": "35s", "weight_guide": "Bodyweight", "form_key": "squat"},
    {"name": "Reverse Lunge to Knee Drive", "sessions": ["lower_body", "glutes", "full_body"], "modes": ["home", "gym"], "goals": ["lean_physique", "toning", "fat_loss", "glute_focus"], "gender": ["female", "any"], "equipment": ["bodyweight"], "muscles": ["glutes", "quads", "balance"], "tags": ["glute", "balance"], "level": "beginner", "sets": 3, "reps": "10 each", "rest": "45s", "weight_guide": "Bodyweight", "form_key": "squat"},
    {"name": "Band Romanian Deadlift", "sessions": ["lower_body", "glutes_hamstrings", "full_body"], "modes": ["home"], "goals": ["lean_physique", "glute_focus", "toning"], "gender": ["female", "any"], "equipment": ["resistance_band"], "muscles": ["hamstrings", "glutes"], "tags": ["hinge", "knee_friendly"], "level": "beginner", "sets": 3, "reps": "12-15", "rest": "60s", "weight_guide": "Resistance band", "form_key": "squat"},
    {"name": "Bodyweight Squat to Chair", "sessions": ["legs", "lower_body", "full_body"], "modes": ["home"], "goals": ["lean_physique", "toning", "fat_loss"], "gender": ["any"], "equipment": ["bodyweight", "chair"], "muscles": ["quads", "glutes"], "tags": ["knee_friendly"], "level": "beginner", "sets": 3, "reps": "12-15", "rest": "60s", "weight_guide": "Bodyweight", "form_key": "squat"},
    {"name": "Dead Bug", "sessions": ["core_cardio", "mobility", "recovery"], "modes": ["home", "gym"], "goals": ["lean_physique", "toning", "fat_loss", "endurance"], "gender": ["any"], "equipment": ["mat", "bodyweight"], "muscles": ["core"], "tags": ["core_stability", "back_friendly"], "level": "beginner", "sets": 3, "reps": "10 each", "rest": "30s", "weight_guide": "Bodyweight", "form_key": "biceps"},
    {"name": "Forearm Plank", "sessions": ["core_cardio", "full_body"], "modes": ["home", "gym"], "goals": ["lean_physique", "toning", "fat_loss"], "gender": ["any"], "equipment": ["mat", "bodyweight"], "muscles": ["core"], "tags": ["core_stability"], "level": "beginner", "sets": 3, "reps": "30-45s", "rest": "30s", "weight_guide": "Bodyweight", "form_key": "pushup"},
    {"name": "Side Plank Reach", "sessions": ["core_cardio", "full_body"], "modes": ["home", "gym"], "goals": ["lean_physique", "toning", "fat_loss"], "gender": ["female", "any"], "equipment": ["mat", "bodyweight"], "muscles": ["obliques", "core"], "tags": ["core_stability"], "level": "beginner", "sets": 3, "reps": "8 each", "rest": "30s", "weight_guide": "Bodyweight", "form_key": "pushup"},
    {"name": "Standing Cross-Body Crunch", "sessions": ["core_cardio", "cardio"], "modes": ["home", "gym"], "goals": ["lean_physique", "toning", "fat_loss", "endurance"], "gender": ["female", "any"], "equipment": ["bodyweight"], "muscles": ["core", "cardio"], "tags": ["knee_friendly", "core_stability"], "level": "beginner", "sets": 3, "reps": "35s", "rest": "25s", "weight_guide": "Bodyweight", "form_key": "squat"},
    {"name": "Step Jacks", "sessions": ["cardio", "hiit", "core_cardio"], "modes": ["home", "gym"], "goals": ["fat_loss", "lean_physique", "endurance", "toning"], "gender": ["female", "any"], "equipment": ["bodyweight"], "muscles": ["cardio"], "tags": ["knee_friendly"], "level": "beginner", "sets": 4, "reps": "35s", "rest": "25s", "weight_guide": "Bodyweight", "form_key": "squat"},
    {"name": "Mountain Climbers", "sessions": ["core_cardio", "hiit", "cardio"], "modes": ["home", "gym"], "goals": ["fat_loss", "lean_physique", "endurance"], "gender": ["any"], "equipment": ["bodyweight", "mat"], "muscles": ["core", "cardio"], "tags": ["wrist_loaded", "plank"], "level": "beginner", "sets": 3, "reps": "30s", "rest": "30s", "weight_guide": "Bodyweight", "form_key": "pushup"},
    {"name": "Low Impact High Knees", "sessions": ["cardio", "hiit", "core_cardio"], "modes": ["home", "gym"], "goals": ["fat_loss", "lean_physique", "endurance"], "gender": ["any"], "equipment": ["bodyweight"], "muscles": ["cardio"], "tags": ["knee_friendly"], "level": "beginner", "sets": 4, "reps": "30s", "rest": "30s", "weight_guide": "Bodyweight", "form_key": "squat"},
    {"name": "Band Row", "sessions": ["upper_body", "pull", "full_body"], "modes": ["home"], "goals": ["lean_physique", "toning", "fat_loss"], "gender": ["any"], "equipment": ["resistance_band"], "muscles": ["back"], "tags": ["row", "shoulder_friendly"], "level": "beginner", "sets": 3, "reps": "15", "rest": "45s", "weight_guide": "Resistance band", "form_key": "biceps"},
    {"name": "Incline Push-up", "sessions": ["upper_body", "push", "full_body"], "modes": ["home"], "goals": ["toning", "fat_loss", "lean_physique"], "gender": ["any"], "equipment": ["bodyweight", "chair"], "muscles": ["chest", "triceps"], "tags": ["pushup", "wrist_loaded"], "level": "beginner", "sets": 3, "reps": "8-12", "rest": "60s", "weight_guide": "Bodyweight", "form_key": "pushup"},
    {"name": "Standing Band Pallof Press", "sessions": ["core_cardio", "full_body"], "modes": ["home", "gym"], "goals": ["lean_physique", "toning", "fat_loss"], "gender": ["any"], "equipment": ["resistance_band", "cable"], "muscles": ["core"], "tags": ["core_stability", "knee_friendly"], "level": "beginner", "sets": 3, "reps": "12 each", "rest": "45s", "weight_guide": "Band or cable", "form_key": "biceps"},
    {"name": "Cat-Cow to Child Pose", "sessions": ["mobility", "recovery"], "modes": ["home", "gym"], "goals": ["any"], "gender": ["any"], "equipment": ["mat", "bodyweight"], "muscles": ["spine"], "tags": ["mobility", "back_friendly"], "level": "beginner", "sets": 2, "reps": "60s", "rest": "20s", "weight_guide": "Bodyweight", "form_key": "squat"},
    # Sport
    {"name": "Medicine Ball Rotational Throw", "sessions": ["power", "rotational_power"], "modes": ["sport", "gym"], "sports": ["cricket"], "goals": ["any"], "gender": ["any"], "equipment": ["medicine_ball"], "muscles": ["core", "shoulder"], "tags": ["throw", "rotational"], "level": "intermediate", "sets": 4, "reps": "6 each", "rest": "90s", "weight_guide": "Light medicine ball", "form_key": "biceps"},
    {"name": "Band External Rotation", "sessions": ["mobility", "rotational_power", "recovery"], "modes": ["sport", "home", "gym"], "sports": ["cricket"], "goals": ["any"], "gender": ["any"], "equipment": ["resistance_band"], "muscles": ["rotator cuff"], "tags": ["shoulder_friendly", "mobility"], "level": "beginner", "sets": 3, "reps": "15 each", "rest": "30s", "weight_guide": "Light band", "form_key": "biceps"},
    {"name": "Wrist Pronation Supination", "sessions": ["reaction_speed", "mobility"], "modes": ["sport", "home", "gym"], "sports": ["cricket"], "goals": ["any"], "gender": ["any"], "equipment": ["dumbbell", "bodyweight"], "muscles": ["forearms"], "tags": ["wrist_strength"], "level": "beginner", "sets": 3, "reps": "12 each", "rest": "30s", "weight_guide": "Light dumbbell", "form_key": "biceps"},
    {"name": "Lateral Shuffle", "sessions": ["conditioning", "agility", "reaction_speed"], "modes": ["sport", "home", "gym"], "sports": ["cricket", "football"], "goals": ["any"], "gender": ["any"], "equipment": ["bodyweight"], "muscles": ["agility"], "tags": ["knee_friendly"], "level": "beginner", "sets": 4, "reps": "20s", "rest": "45s", "weight_guide": "Bodyweight", "form_key": "squat"},
    {"name": "Acceleration Sprints", "sessions": ["conditioning", "power", "match_prep"], "modes": ["sport"], "sports": ["football", "cricket"], "goals": ["any"], "gender": ["any"], "equipment": ["bodyweight"], "muscles": ["speed"], "tags": ["sprint"], "level": "intermediate", "sets": 6, "reps": "15m", "rest": "75s", "weight_guide": "Bodyweight", "form_key": "squat"},
    {"name": "Skater Step", "sessions": ["agility", "power"], "modes": ["sport", "home"], "sports": ["football"], "goals": ["any"], "gender": ["any"], "equipment": ["bodyweight"], "muscles": ["glutes", "balance"], "tags": ["balance", "knee_friendly"], "level": "beginner", "sets": 3, "reps": "10 each", "rest": "45s", "weight_guide": "Bodyweight", "form_key": "squat"},
    {"name": "Copenhagen Plank", "sessions": ["lower_strength", "knee_stability"], "modes": ["sport", "gym", "home"], "sports": ["football", "running"], "goals": ["any"], "gender": ["any"], "equipment": ["bodyweight", "bench"], "muscles": ["adductors", "core"], "tags": ["core_stability"], "level": "intermediate", "sets": 3, "reps": "25s each", "rest": "45s", "weight_guide": "Bodyweight", "form_key": "pushup"},
    {"name": "Tempo Run", "sessions": ["endurance", "tempo"], "modes": ["sport"], "sports": ["running"], "goals": ["any"], "gender": ["any"], "equipment": ["bodyweight"], "muscles": ["endurance"], "tags": ["run"], "level": "beginner", "sets": 1, "reps": "20-30 min", "rest": "0", "weight_guide": "Conversational pace", "form_key": "squat"},
    {"name": "A-Skip Drill", "sessions": ["drills"], "modes": ["sport"], "sports": ["running"], "goals": ["any"], "gender": ["any"], "equipment": ["bodyweight"], "muscles": ["running mechanics"], "tags": ["drill"], "level": "beginner", "sets": 3, "reps": "20m", "rest": "45s", "weight_guide": "Bodyweight", "form_key": "squat"},
    {"name": "Tibialis Raise", "sessions": ["knee_stability", "lower_strength"], "modes": ["sport", "home", "gym"], "sports": ["running"], "goals": ["any"], "gender": ["any"], "equipment": ["bodyweight"], "muscles": ["shins"], "tags": ["knee_friendly", "calf"], "level": "beginner", "sets": 3, "reps": "18-20", "rest": "30s", "weight_guide": "Bodyweight", "form_key": "squat"},
    {"name": "Calf Raise Iso Hold", "sessions": ["knee_stability", "lower_strength", "endurance"], "modes": ["sport", "home", "gym"], "sports": ["running", "football"], "goals": ["any"], "gender": ["any"], "equipment": ["bodyweight"], "muscles": ["calves"], "tags": ["calf", "knee_friendly"], "level": "beginner", "sets": 3, "reps": "30s", "rest": "30s", "weight_guide": "Bodyweight", "form_key": "squat"},
]


def normalize_goal(goal):
    raw = (goal or "fat_loss").strip().lower().replace("-", "_")
    raw = raw.replace(" ", "_")
    return GOAL_ALIASES.get(raw, raw)


def normalize_mode(profile, requested_mode=None):
    requested = (requested_mode or "").lower()
    if requested in {"sport", "cricket", "football", "running"} and profile.get("sport"):
        return "sport"
    place = (profile.get("workout_place") or profile.get("mode") or "gym").lower()
    if place in {"sport", "cricket", "football", "running"} and profile.get("sport"):
        return "sport"
    if "home" in requested or "home" in place:
        return "home"
    return "gym"


def parse_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v).strip().lower() for v in value if str(v).strip()]
    return [v.strip().lower() for v in re.split(r"[,/|]+", str(value)) if v.strip()]


def injuries(profile):
    values = parse_list(profile.get("injuries"))
    sport_profile = profile.get("sport_profile") or {}
    if isinstance(sport_profile, str):
        try:
            import json
            sport_profile = json.loads(sport_profile)
        except Exception:
            sport_profile = {}
    values += parse_list(sport_profile.get("sport_injuries"))
    return [v for v in values if v not in {"none", "no", "n/a", "na"}]


def equipment(profile, mode):
    values = set(parse_list(profile.get("equipment")))
    if mode == "home":
        return values or {"bodyweight", "mat", "resistance_band", "chair"}
    if mode == "gym":
        return values or (HOME_EQUIPMENT | GYM_EQUIPMENT)
    return values or (HOME_EQUIPMENT | {"medicine_ball", "dumbbell", "bench"})


def template_for(profile, requested_mode=None):
    gender = (profile.get("gender") or "any").lower()
    if gender not in {"male", "female"}:
        gender = "male"
    mode = normalize_mode(profile, requested_mode)
    if mode == "sport" and profile.get("sport"):
        return WEEKLY_TEMPLATES.get(("sport", "any", str(profile.get("sport")).lower())), mode
    goal = normalize_goal(profile.get("goal"))
    key = (mode, gender, goal)
    if key not in WEEKLY_TEMPLATES:
        key = (mode, gender, "fat_loss" if "loss" in goal or "fat" in goal else "lean_physique" if gender == "female" else "muscle_gain")
    return WEEKLY_TEMPLATES.get(key, WEEKLY_TEMPLATES[("home", "female", "lean_physique")]), mode


def apply_training_days(sessions, days_per_week):
    days = max(1, min(7, int(days_per_week or 5)))
    sessions = list(sessions[:7])
    if days >= 7:
        return sessions
    protected = {6}
    if days <= 5:
        protected.add(3)
    if days <= 4:
        protected.add(5)
    if days <= 3:
        protected.add(1)
    for idx in sorted(protected, reverse=True):
        if len([s for s in sessions if s != "recovery"]) > days:
            sessions[idx] = "recovery"
    return sessions


def generate_weekly_plan(uid, profile, requested_mode=None, recovery_zone="green", exercises_fn=None):
    template, mode = template_for(profile, requested_mode)
    sessions = apply_training_days(template, profile.get("days_per_week"))
    plan = []
    for idx, session in enumerate(sessions):
        rest = session == "recovery"
        if rest:
            exercises = []
        elif exercises_fn:
            exercises = exercises_fn(session, profile, mode, recovery_zone, 6)
        else:
            exercises = select_exercises(session, profile, mode, recovery_zone, count=6)
        plan.append({
            "day": DAYS[idx],
            "day_index": idx,
            "muscle": session,
            "label": SESSION_LABELS.get(session, session.replace("_", " ").title()),
            "db_key": session,
            "rest": rest,
            "sport_type": mode == "sport",
            "mode": mode,
            "exercises": exercises,
        })
    return plan


MUSCLE_FAMILIES = {
    "legs": "lower",
    "legs_strength": "lower",
    "lower_body": "lower",
    "lower_strength": "lower",
    "glutes": "lower",
    "glutes_hamstrings": "lower",
    "push": "push",
    "push_volume": "push",
    "push_strength": "push",
    "shoulders_arms": "push",
    "pull": "pull",
    "pull_volume": "pull",
    "pull_strength": "pull",
    "upper_body": "upper",
    "core_cardio": "core",
    "full_body": "full",
    "hiit": "conditioning",
    "cardio": "conditioning",
    "conditioning": "conditioning",
    "endurance": "conditioning",
    "mobility": "recovery",
    "recovery": "recovery",
    "power": "power",
    "rotational_power": "power",
    "agility": "agility",
    "reaction_speed": "agility",
    "match_prep": "conditioning",
    "drills": "conditioning",
    "knee_stability": "lower",
    "tempo": "conditioning",
    "strength": "strength",
}


def session_family(session_or_label):
    value = (session_or_label or "").lower().replace("+", " ").replace("-", " ")
    normalized = normalize_session_request(value) or value.replace(" ", "_")
    if normalized in MUSCLE_FAMILIES:
        return MUSCLE_FAMILIES[normalized]
    if any(term in value for term in ["leg", "lower", "glute", "hamstring"]):
        return "lower"
    if any(term in value for term in ["chest", "tricep", "push", "shoulder"]):
        return "push"
    if any(term in value for term in ["back", "bicep", "pull"]):
        return "pull"
    if any(term in value for term in ["core", "abs"]):
        return "core"
    if any(term in value for term in ["cardio", "hiit", "conditioning", "endurance"]):
        return "conditioning"
    if any(term in value for term in ["recovery", "mobility", "restore"]):
        return "recovery"
    return normalized or "general"


def today_index():
    return date.today().weekday()


def get_todays_slot(plan):
    if not plan:
        return {}
    return plan[min(today_index(), len(plan) - 1)]


def normalize_session_request(text):
    msg = (text or "").lower()
    for phrase, session in sorted(SESSION_ALIASES.items(), key=lambda item: len(item[0]), reverse=True):
        if phrase in msg:
            return session
    return None


def swap_today(plan, requested, profile, requested_mode=None, recovery_zone="green", exercises_fn=None):
    req = normalize_session_request(requested) or requested
    idx = today_index()
    updated = deepcopy(plan)
    displaced = deepcopy(updated[idx])
    target_idx = None
    for i, slot in enumerate(updated):
        if i == idx:
            continue
        haystack = " ".join([str(slot.get("muscle", "")), str(slot.get("label", "")), str(slot.get("db_key", ""))]).lower()
        if req and (req in haystack or req.replace("_", " ") in haystack):
            target_idx = i
            break
    if target_idx is not None:
        updated[idx], updated[target_idx] = updated[target_idx], updated[idx]
        moved_to = DAYS[target_idx]
    else:
        _, mode = template_for(profile, requested_mode)
        new_exercises = (
            exercises_fn(req, profile, mode, recovery_zone, 6)
            if exercises_fn
            else select_exercises(req, profile, mode, recovery_zone, count=6)
        )
        updated[idx] = {
            "day": DAYS[idx],
            "day_index": idx,
            "muscle": req,
            "label": SESSION_LABELS.get(req, req.replace("_", " ").title()),
            "db_key": req,
            "rest": False,
            "sport_type": mode == "sport",
            "mode": mode,
            "exercises": new_exercises,
        }
        moved_to = "next recovery slot"
        for i in range(idx + 1, 7):
            if updated[i].get("rest"):
                updated[i] = displaced
                moved_to = DAYS[i]
                break
    for i, slot in enumerate(updated):
        slot["day"] = DAYS[i]
        slot["day_index"] = i
    return updated, displaced.get("label", "Today"), moved_to


def exercise_score(ex, session, profile, mode, available, injury_names, recovery_zone):
    gender = (profile.get("gender") or "any").lower()
    goal = normalize_goal(profile.get("goal"))
    sport = (profile.get("sport") or "").lower()
    score = 0
    if session in ex.get("sessions", []):
        score += 40
    if mode in ex.get("modes", []):
        score += 30
    if sport and sport in ex.get("sports", []):
        score += 25
    goals = ex.get("goals", [])
    if goal in goals or "any" in goals:
        score += 15
    genders = ex.get("gender", ["any"])
    if gender in genders or "any" in genders:
        score += 8
    if set(ex.get("equipment", [])) & available or "bodyweight" in ex.get("equipment", []):
        score += 10
    if mode == "home" and gender == "female" and goal in {"lean_physique", "toning", "fat_loss", "glute_focus"}:
        if {"heavy_press", "heavy_hinge", "isolation", "wrist_strength"} & set(ex.get("tags", [])):
            score -= 45
        if {"glute", "core_stability", "knee_friendly", "mobility"} & set(ex.get("tags", [])):
            score += 16
    avoid = set()
    prefer = set()
    for injury in injury_names:
        for key, rule in INJURY_RULES.items():
            if key in injury:
                avoid |= rule["avoid_tags"]
                prefer |= rule["prefer_tags"]
    tags = set(ex.get("tags", []))
    if tags & avoid:
        return -999
    score += len(tags & prefer) * 10
    if recovery_zone == "red":
        if {"mobility", "core_stability", "knee_friendly", "shoulder_friendly"} & tags:
            score += 20
        if {"heavy_press", "heavy_hinge", "sprint", "jump"} & tags:
            score -= 35
    elif recovery_zone == "yellow":
        if {"heavy_press", "heavy_hinge", "sprint", "jump"} & tags:
            score -= 10
    return score


def select_exercises(session, profile, mode=None, recovery_zone="green", count=6):
    mode = mode or normalize_mode(profile)
    available = equipment(profile, mode)
    injury_names = injuries(profile)
    sport = (profile.get("sport") or "").lower()
    session = normalize_session_request(session) or (session or "full_body")
    pool = []
    for ex in EXERCISES:
        ex_sports = ex.get("sports", [])
        if ex_sports and sport not in ex_sports:
            continue
        ex_sessions = set(ex.get("sessions", []))
        if session != "recovery" and session not in ex_sessions:
            continue
        if session == "recovery":
            ex_tags = set(ex.get("tags", []))
            if not ({"recovery", "mobility"} & ex_sessions or "mobility" in ex_tags):
                continue
        if mode == "home" and any(eq in GYM_EQUIPMENT for eq in ex.get("equipment", [])):
            if not (set(ex.get("equipment", [])) & available):
                continue
        if mode not in ex.get("modes", []):
            continue
        score = exercise_score(ex, session, profile, mode, available, injury_names, recovery_zone)
        if score > 0:
            pool.append((score, ex["name"], ex))
    if not pool and recovery_zone != "red":
        return select_exercises("full_body", profile, mode, "yellow", count)
    if not pool:
        pool = [(1, ex["name"], ex) for ex in EXERCISES if "recovery" in ex.get("sessions", []) and mode in ex.get("modes", [])]
    pool.sort(key=lambda item: (-item[0], item[1]))
    selected = [format_exercise(item[2], recovery_zone) for item in pool[:count]]
    return selected


def format_exercise(ex, recovery_zone):
    item = deepcopy(ex)
    if recovery_zone == "red":
        item["sets"] = max(1, min(int(item.get("sets", 3)), 2))
        item["rest"] = "45s"
        item["intensity"] = "recovery"
    elif recovery_zone == "yellow":
        item["sets"] = max(2, int(item.get("sets", 3)) - 1)
        item["intensity"] = "moderate"
    else:
        item["intensity"] = "full"
    item["muscle"] = ", ".join(item.pop("muscles", []))
    item["category"] = item.get("sessions", ["general"])[0]
    item["progression"] = progression_for(item)
    item["injury_compatible"] = True
    item["home_compatible"] = "home" in item.get("modes", [])
    item["gym_compatible"] = "gym" in item.get("modes", [])
    item["posture_config"] = {
        "form_key": item.get("form_key", "squat"),
        "rep_target": parse_rep_target(item.get("reps", "10")),
    }
    item["demo_url"] = "https://www.youtube.com/results?search_query=" + item["name"].replace(" ", "+") + "+form"
    return item


def parse_rep_target(reps):
    match = re.search(r"\d+", str(reps))
    return int(match.group(0)) if match else 12


def progression_for(ex):
    tags = set(ex.get("tags", []))
    if "heavy_press" in tags or "heavy_hinge" in tags:
        return ["add 2.5kg when all reps are clean", "keep 1-2 reps in reserve"]
    if "sprint" in tags:
        return ["add one sprint next week", "keep full rest for speed quality"]
    if "mobility" in tags:
        return ["increase range slowly", "hold end positions longer"]
    return ["add 1-2 reps per set", "increase band or load after clean completion"]


def build_workout(uid, profile, requested_mode=None, recovery_zone="green", plan=None):
    if plan is None:
        plan = generate_weekly_plan(uid, profile, requested_mode, recovery_zone)
    slot = get_todays_slot(plan)
    if slot.get("rest") or recovery_zone == "red":
        session = "recovery" if recovery_zone == "red" else slot.get("db_key", "recovery")
    else:
        session = slot.get("db_key") or slot.get("muscle") or "full_body"
    mode = slot.get("mode") or normalize_mode(profile, requested_mode)
    exercises = slot.get("exercises") or select_exercises(session, profile, mode, recovery_zone, count=6)
    label = SESSION_LABELS.get(session, slot.get("label", session.replace("_", " ").title()))
    return {
        "muscle_group": label,
        "exercises": exercises,
        "zone": recovery_zone,
        "mode": mode,
        "sport": profile.get("sport") if mode == "sport" else None,
        "session_type": session,
        "planner_slot": slot,
    }


def plan_summary(plan):
    idx = today_index()
    lines = []
    for slot in plan:
        marker = " <- today" if slot.get("day_index") == idx else ""
        label = "Recovery" if slot.get("rest") else slot.get("label", "Workout")
        lines.append(f"**{slot.get('day')}** - {label}{marker}")
    return "\n".join(lines)


def coach_preview(profile, workout, plan=None):
    goal = normalize_goal(profile.get("goal")).replace("_", " ")
    zone = workout.get("zone", "green")
    opener = f"{workout['muscle_group']} loaded for {goal}."
    if zone == "red":
        opener = "Recovery-safe session loaded."
    elif workout.get("mode") == "sport":
        opener = f"{workout['muscle_group']} sport block loaded."
    lines = [opener, ""]
    for ex in workout["exercises"]:
        lines.append(f"**{ex['name']}** - {ex['sets']} x {ex['reps']} | {ex.get('rest', '60s')}")
    lines.append("")
    lines.append("Ready? Tap **Start Workout** to begin!")
    if plan:
        lines.append("")
        lines.append("**This week:**")
        lines.append(plan_summary(plan))
    return "\n".join(lines)


def contextual_greeting(profile, workout, recovery_zone="green"):
    name = profile.get("name") or "Athlete"
    muscle = workout.get("muscle_group", "training")
    family = session_family(workout.get("session_type") or muscle)
    if recovery_zone == "red":
        return f"Mobility focus today for optimal recovery, {name}."
    if recovery_zone == "yellow":
        return f"{muscle} loaded at controlled intensity, {name}."
    if workout.get("mode") == "sport":
        return f"Explosive {muscle.lower()} block ready, {name}."
    if family == "lower":
        return f"Explosive lower-body block ready, {name}."
    if family in {"push", "pull", "upper"}:
        return f"Upper-body hypertrophy session loaded, {name}."
    if family == "conditioning":
        return f"Metabolic conditioning console is live, {name}."
    if family == "core":
        return f"Core stability and athletic engine work is ready, {name}."
    return f"Recovery looks strong today. {muscle} is loaded, {name}."
