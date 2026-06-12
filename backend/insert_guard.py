new_block = '''
    # -- SPORT MODE GUARD --------------------------------------------------
    if active_mode == "sport" and not (profile.get("plays_sport") and profile.get("sport")):
        name = profile.get("name", "Athlete")
        return jsonify({
            "reply": f"Hey {name}! Sport Mode needs your sport profile first. Let me set that up for you!",
            "type": "sport_onboarding_prompt",
            "start_sport_onboard": True,
        })

    # -- INITIAL GREETING (coach tab opens with no message) ----------------
    if not user_message and session_state[uid].get("mode", "idle") in ("idle", "planning", "greeted"):
        h = datetime.now().hour
        tod = "morning" if h < 12 else ("afternoon" if h < 17 else "evening")
        name = profile.get("name", "Athlete")
        streak = workout_streak(uid)
        rec = get_latest_recovery(uid)
        zone = rec["zone"] if rec else "green"
        zone_labels = {"green": "Fully recovered", "yellow": "Moderate recovery", "red": "Light day recommended"}
        plan = get_weekly_plan(uid)
        if plan_needs_refresh(plan, active_mode):
            plan = generate_weekly_plan(uid, profile, _get_rich_exercises)
            save_weekly_plan(uid, plan, mode=active_mode)
        today_slot = get_todays_slot(plan) if plan else {}
        is_rest = today_slot.get("rest", False) if today_slot else True
        today_muscle = "Rest Day" if is_rest else today_slot.get("label", "Full Body")
        exercises = (today_slot.get("exercises") or []) if today_slot else []
        if not exercises and not is_rest and today_slot:
            exercises = _get_rich_exercises(
                today_slot.get("db_key") or today_slot.get("muscle", "full_body"),
                profile, active_mode, zone, 6
            )
        planned = {
            "muscle_group": today_muscle,
            "exercises": exercises,
            "zone": zone,
            "mode": active_mode,
            "sport": profile.get("sport") if active_mode == "sport" else None,
            "session_type": (today_slot.get("db_key") or today_slot.get("muscle")) if today_slot else "full_body",
        }
        session_state[uid]["planned_workout"] = planned
        if not is_rest:
            save_planned_workout(uid, date.today().isoformat(), planned)
        session_state[uid]["mode"] = "greeted"
        streak_txt = f"{streak} day streak" if streak > 0 else "Start your streak today!"
        greeting_reply = (
            f"Good {tod}, {name}!\\n\\n"
            f"Today\'s Focus: **{today_muscle}**\\n"
            f"Recovery: **{zone.upper()}** - {zone_labels.get(zone, \'\')}\\n"
            f"Streak: {streak_txt}"
        )
        return jsonify({
            "reply": greeting_reply,
            "type": "daily_greeting",
            "streak": streak,
            "today_muscle": today_muscle,
            "exercises": exercises,
            "zone": zone,
            "workout_mode": active_mode,
            "weekly_plan": plan,
        })

'''

with open(r'C:\Users\aamir\Fitcoach\backend\app.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Insert before line 1564 (the WEIGHT LOG comment)
lines.insert(1564, new_block)

with open(r'C:\Users\aamir\Fitcoach\backend\app.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)

# Verify
with open(r'C:\Users\aamir\Fitcoach\backend\app.py', 'r', encoding='utf-8') as f:
    content = f.read()
print("Sport guard present:", "SPORT MODE GUARD" in content)
print("Greeting present:", "INITIAL GREETING" in content)
print("Total lines:", content.count('\n'))
