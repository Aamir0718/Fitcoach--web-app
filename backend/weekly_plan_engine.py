from fitness_engine import (
    generate_weekly_plan as engine_generate_weekly_plan,
    get_todays_slot,
    plan_summary,
    swap_today,
    normalize_session_request,
    SESSION_ALIASES,
)


def generate_weekly_plan(uid, profile, select_exercises_fn=None):
    return engine_generate_weekly_plan(uid, profile, exercises_fn=select_exercises_fn)


def swap_today_workout(uid, plan, requested_muscle_label, profile, select_exercises_fn=None):
    return swap_today(plan, requested_muscle_label, profile, exercises_fn=select_exercises_fn)


def get_weekly_plan_summary(plan):
    return plan_summary(plan)


SWAP_TRIGGERS = [
    "don't want", "dont want", "skip", "not today", "instead", "replace",
    "change to", "switch", "switch to", "want", "make today", "training from home",
]


def detect_swap_intent(message):
    msg = (message or "").lower()
    has_trigger = any(trigger in msg for trigger in SWAP_TRIGGERS)
    matches = []
    for phrase, session in SESSION_ALIASES.items():
        pos = msg.rfind(phrase)
        if pos >= 0:
            matches.append((pos, len(phrase), session))
    requested = sorted(matches, key=lambda item: (item[0], item[1]))[-1][2] if matches else normalize_session_request(msg)
    if has_trigger and requested:
        return True, requested
    if requested and any(word in msg for word in ["today", "session", "workout"]):
        return True, requested
    return False, None
