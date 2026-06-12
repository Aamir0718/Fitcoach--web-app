# app.py " FitCoach AI Backend v5.1 (Chat'Workout Fix)
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
from datetime import date, datetime, timedelta
import os, sys, uuid, re, random, smtplib, json, hashlib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from groq import Groq

# Make local modules importable regardless of how the app is launched
# (python app.py locally, gunicorn, or Vercel's serverless entrypoint).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from db import (
    init_db, get_user, save_user, log_workout, get_last_workout,
    days_since_last_workout, workout_streak, save_ai_memory,
    get_recent_ai_memory, log_weight, get_weight_progress,
    get_badges, get_workout_heatmap, get_muscle_group_distribution,
    get_weekly_workout_counts, get_total_workouts,
    create_auth, get_auth_by_email, get_auth_by_user_id,
    update_user_weight, update_password, update_user_sport,
    save_otp, verify_otp, mark_email_verified,
    save_recovery_log, get_latest_recovery,
    save_weekly_plan, get_weekly_plan, update_weekly_plan,
    save_planned_workout, get_planned_workout,
    save_session_state, load_session_state,
)
 
from weekly_plan_engine import (
    generate_weekly_plan, get_todays_slot, swap_today_workout,
    get_weekly_plan_summary, detect_swap_intent,
)
from fitness_engine import (
    build_workout as engine_build_workout,
    coach_preview as engine_coach_preview,
    contextual_greeting as engine_contextual_greeting,
    normalize_session_request as engine_normalize_session_request,
    select_exercises as engine_select_exercises,
    session_family as engine_session_family,
    SESSION_LABELS,
    parse_rep_target as engine_parse_rep_target,
)
from models import UserProfile

load_dotenv()
init_db()

app = Flask(__name__)

#  CORS -- restrict to allowed origins (set ALLOWED_ORIGINS in .env for prod) 
_raw_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:5000,http://127.0.0.1:5000")
_allowed_origins = [o.strip() for o in _raw_origins.split(",") if o.strip()]
CORS(app, supports_credentials=True, origins=_allowed_origins)

#  JWT -- no fallback; raise immediately if secret is missing 
_jwt_secret = os.getenv("JWT_SECRET")
if not _jwt_secret:
    raise RuntimeError(
        "JWT_SECRET environment variable is not set. "
        "Add it to your .env file before starting the server."
    )
app.config["JWT_SECRET_KEY"] = _jwt_secret
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(days=30)
jwt = JWTManager(app)

#  Rate limiter 
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=[],          # No global limit -- apply per-route only
    storage_uri="memory://",
)

groq_client = Groq(api_key=os.getenv("GROQ_API_KEY", ""))

MOJIBAKE_REPLACEMENTS = {
    # These are the only replacements that matter before ASCII encoding strips the rest
    "\u2714": "OK",   # checkmark
    "\u2705": "OK",   # check box
    "\u2013": "-",    # en dash
    "\u2014": "--",   # em dash
    "\u2022": "-",    # bullet
    "\u2018": "'",    # left single quote
    "\u2019": "'",    # right single quote
    "\u201c": '"',    # left double quote
    "\u201d": '"',    # right double quote
    "\u2192": "->",   # right arrow
    "\u00d7": "x",    # multiplication sign
    "\u2026": "...",  # ellipsis
}

def clean_text(value):
    if not isinstance(value, str):
        return value
    text = value
    for bad, good in MOJIBAKE_REPLACEMENTS.items():
        text = text.replace(bad, good)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    return text.strip()

def clean_json_payload(value):
    if isinstance(value, dict):
        return {key: clean_json_payload(item) for key, item in value.items()}
    if isinstance(value, list):
        return [clean_json_payload(item) for item in value]
    if isinstance(value, str):
        return clean_text(value)
    return value

@app.after_request
def sanitize_json_response(response):
    if response.content_type and response.content_type.startswith("application/json"):
        try:
            payload = response.get_json(silent=True)
            if payload is not None:
                response.set_data(json.dumps(clean_json_payload(payload), ensure_ascii=False))
                response.headers["Content-Length"] = str(len(response.get_data()))
        except Exception:
            pass
    return response

# Session state -- in-memory cache backed by SQLite for restart safety
class PersistentSessionState:
    def __init__(self):
        self._cache = {}

    def _defaults(self):
        return {'mode': 'idle', 'workout_mode': 'gym'}

    def __contains__(self, uid):
        return uid in self._cache or bool(load_session_state(uid))

    def __getitem__(self, uid):
        if uid not in self._cache:
            stored = load_session_state(uid)
            self._cache[uid] = {**self._defaults(), **stored}
        return self._cache[uid]

    def __setitem__(self, uid, value):
        self._cache[uid] = value
        save_session_state(uid, value)

    def get(self, uid, default=None):
        try:
            return self[uid]
        except Exception:
            return default

    def setdefault(self, uid, default):
        if uid not in self._cache:
            stored = load_session_state(uid)
            if stored:
                self._cache[uid] = {**self._defaults(), **stored}
            else:
                self._cache[uid] = default
                save_session_state(uid, default)
        return self._cache[uid]

    def _write(self, uid):
        if uid in self._cache:
            save_session_state(uid, self._cache[uid])

onboarding_state = {}    # ephemeral -- OK to lose on restart
sport_ob_state   = {}    # ephemeral
workout_state    = {}    # ephemeral
recovery_state   = {}    # ephemeral
session_state    = PersistentSessionState()


# ------------------------------------------------------------------------------
# EMAIL
# ------------------------------------------------------------------------------
def send_email(to_email, subject, html_body):
    sender = os.getenv("MAIL_FROM", "infoatfitcoachai@gmail.com")

    # Preferred path (works on serverless / Vercel, where outbound SMTP is blocked):
    # Brevo's transactional HTTP API — just an HTTPS request, no SMTP ports.
    brevo_key = os.getenv("BREVO_API_KEY", "")
    if brevo_key:
        try:
            import requests
            r = requests.post(
                "https://api.brevo.com/v3/smtp/email",
                headers={"api-key": brevo_key, "Content-Type": "application/json"},
                json={
                    "sender":      {"name": "FitCoach", "email": sender},
                    "to":          [{"email": to_email}],
                    "subject":     subject,
                    "htmlContent": html_body,
                },
                timeout=15,
            )
            if r.status_code in (200, 201):
                return True
            print(f"Brevo API error {r.status_code}: {r.text[:200]}")
        except Exception as e:
            print(f"Brevo API exception: {e}")
        # fall through to SMTP if the API call failed

    # Fallback: SMTP (local dev / traditional servers)
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_pass = os.getenv("SMTP_PASS", "")
    if not smtp_user:
        print(f"[DEV EMAIL] To:{to_email}\n{html_body}")
        return True
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject; msg["From"] = f"FitCoach <{sender}>"; msg["To"] = to_email
        msg.attach(MIMEText(html_body, "html"))
        with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as s:
            s.starttls(); s.login(smtp_user, smtp_pass); s.sendmail(sender, to_email, msg.as_string())
        return True
    except Exception as e:
        print(f"Email error: {e}"); return False

def generate_otp(): return str(random.randint(100000,999999))

def otp_email_html(otp, purpose):
    t = {"verify":"Email Verification","login":"Login OTP","reset":"Password Reset"}.get(purpose,"OTP")
    return (
        f'<div style="font-family:Arial;max-width:480px;margin:auto;background:#0f0f1a;padding:40px;border-radius:16px;">'
        f'<h1 style="color:#a78bfa;text-align:center"> FitCoach AI</h1>'
        f'<div style="background:#14141f;border-radius:12px;padding:32px;text-align:center;">'
        f'<div style="font-size:48px;font-weight:900;color:#a78bfa;letter-spacing:8px">{otp}</div>'
        f'<p style="color:#64748b;font-size:13px">Valid 10 minutes</p></div></div>'
    )

# ------------------------------------------------------------------------------
# RECOVERY
# ------------------------------------------------------------------------------
def calculate_recovery_score(sleep_hours, sleep_quality, fatigue, soreness, prev_load):
    sleep_score  = min(5, max(1, (sleep_hours / 8.0) * 5))
    fatigue_inv  = 6 - fatigue
    soreness_inv = 6 - soreness
    load_inv     = 6 - prev_load
    raw   = (sleep_score*30 + sleep_quality*20 + fatigue_inv*25 + soreness_inv*15 + load_inv*10) / 5
    score = int(min(100, max(0, raw)))
    zone  = "green" if score >= 80 else ("yellow" if score >= 60 else "red")
    return score, zone

def get_volume_modifier(zone):
    if zone == "green":  return 1.0, "Full intensity"
    if zone == "yellow": return 0.75, "Moderate intensity"
    return 0.5, "Recovery session"

# ------------------------------------------------------------------------------
# DATE SEED
# ------------------------------------------------------------------------------
def get_day_seed(uid: str) -> int:
    today = datetime.now().strftime("%Y-%m-%d")
    return int(hashlib.md5(f"{uid}-{today}".encode()).hexdigest(), 16) % 10000

# ------------------------------------------------------------------------------
# EXERCISE DATABASES (unchanged from your v5)
# ------------------------------------------------------------------------------
MALE_GYM_DB = {
    "push": [
        {"name":"Barbell Bench Press",     "sets":4,"reps":"6-8",  "rest":"90s","muscle":"Chest",        "weight_guide":"70-110kg",         "equipment_required":True, "demo_url":"https://www.youtube.com/results?search_query=bench+press+form"},
        {"name":"Incline Dumbbell Press",  "sets":4,"reps":"8-10", "rest":"75s","muscle":"Upper Chest",   "weight_guide":"22-36kg/hand",     "equipment_required":True, "demo_url":"https://www.youtube.com/results?search_query=incline+dumbbell+press"},
        {"name":"Overhead Barbell Press",  "sets":4,"reps":"6-8",  "rest":"90s","muscle":"Shoulders",     "weight_guide":"40-70kg",          "equipment_required":True, "demo_url":"https://www.youtube.com/results?search_query=overhead+press+form"},
        {"name":"Dumbbell Shoulder Press", "sets":3,"reps":"10-12","rest":"75s","muscle":"Shoulders",     "weight_guide":"18-30kg/hand",     "equipment_required":True, "demo_url":"https://www.youtube.com/results?search_query=dumbbell+shoulder+press"},
        {"name":"Lateral Raises",          "sets":4,"reps":"12-15","rest":"60s","muscle":"Side Delts",    "weight_guide":"8-15kg/hand",      "equipment_required":True, "demo_url":"https://www.youtube.com/results?search_query=lateral+raise"},
        {"name":"Cable Lateral Raise",     "sets":3,"reps":"15",   "rest":"45s","muscle":"Side Delts",    "weight_guide":"5-10kg cable",     "equipment_required":True, "demo_url":"https://www.youtube.com/results?search_query=cable+lateral+raise"},
        {"name":"Triceps Pushdown",        "sets":3,"reps":"12-15","rest":"60s","muscle":"Triceps",       "weight_guide":"20-40kg cable",    "equipment_required":True, "demo_url":"https://www.youtube.com/results?search_query=tricep+pushdown"},
        {"name":"Skull Crushers",          "sets":3,"reps":"10-12","rest":"60s","muscle":"Triceps",       "weight_guide":"30-50kg bar",      "equipment_required":True, "demo_url":"https://www.youtube.com/results?search_query=skull+crusher"},
        {"name":"Cable Chest Flye",        "sets":3,"reps":"12",   "rest":"60s","muscle":"Chest",         "weight_guide":"15-25kg/side",     "equipment_required":True, "demo_url":"https://www.youtube.com/results?search_query=cable+chest+fly"},
        {"name":"Close-Grip Bench Press",  "sets":3,"reps":"10",   "rest":"75s","muscle":"Triceps/Chest", "weight_guide":"60-90kg",          "equipment_required":True, "demo_url":"https://www.youtube.com/results?search_query=close+grip+bench+press"},
        {"name":"Arnold Press",            "sets":3,"reps":"10-12","rest":"75s","muscle":"Shoulders",     "weight_guide":"16-26kg/hand",     "equipment_required":True, "demo_url":"https://www.youtube.com/results?search_query=arnold+press"},
        {"name":"Decline Bench Press",     "sets":3,"reps":"8-10", "rest":"90s","muscle":"Lower Chest",   "weight_guide":"65-100kg",         "equipment_required":True, "demo_url":"https://www.youtube.com/results?search_query=decline+bench+press"},
    ],
    "pull": [
        {"name":"Weighted Pull-Ups",          "sets":4,"reps":"5-8",  "rest":"90s","muscle":"Lats",       "weight_guide":"BW or +5-20kg",    "equipment_required":True, "demo_url":"https://www.youtube.com/results?search_query=pull+up+form"},
        {"name":"Barbell Bent-Over Row",      "sets":4,"reps":"6-8",  "rest":"90s","muscle":"Back",       "weight_guide":"70-110kg",         "equipment_required":True, "demo_url":"https://www.youtube.com/results?search_query=bent+over+row"},
        {"name":"Seated Cable Row",           "sets":3,"reps":"10-12","rest":"75s","muscle":"Mid Back",   "weight_guide":"50-80kg cable",    "equipment_required":True, "demo_url":"https://www.youtube.com/results?search_query=seated+cable+row"},
        {"name":"Chest-Supported Row",        "sets":3,"reps":"10-12","rest":"75s","muscle":"Rhomboids",  "weight_guide":"20-35kg/hand DB",  "equipment_required":True, "demo_url":"https://www.youtube.com/results?search_query=chest+supported+row"},
        {"name":"Face Pulls",                 "sets":3,"reps":"15-20","rest":"60s","muscle":"Rear Delts", "weight_guide":"15-30kg cable",    "equipment_required":True, "demo_url":"https://www.youtube.com/results?search_query=face+pull+exercise"},
        {"name":"Barbell Bicep Curls",        "sets":3,"reps":"10-12","rest":"60s","muscle":"Biceps",     "weight_guide":"30-50kg",          "equipment_required":True, "demo_url":"https://www.youtube.com/results?search_query=barbell+curl"},
        {"name":"Incline Dumbbell Curl",      "sets":3,"reps":"10-12","rest":"60s","muscle":"Biceps",     "weight_guide":"12-20kg/hand",     "equipment_required":True, "demo_url":"https://www.youtube.com/results?search_query=incline+dumbbell+curl"},
        {"name":"Lat Pulldown",               "sets":4,"reps":"8-10", "rest":"75s","muscle":"Lats",       "weight_guide":"50-80kg cable",    "equipment_required":True, "demo_url":"https://www.youtube.com/results?search_query=lat+pulldown"},
        {"name":"Single-Arm DB Row",          "sets":3,"reps":"10 ea","rest":"75s","muscle":"Back",       "weight_guide":"30-50kg/hand",     "equipment_required":True, "demo_url":"https://www.youtube.com/results?search_query=single+arm+dumbbell+row"},
        {"name":"Hammer Curls",               "sets":3,"reps":"10-12","rest":"60s","muscle":"Brachialis", "weight_guide":"16-26kg/hand",     "equipment_required":True, "demo_url":"https://www.youtube.com/results?search_query=hammer+curl"},
        {"name":"Cable Straight-Arm Pulldown","sets":3,"reps":"12",   "rest":"60s","muscle":"Lats",       "weight_guide":"25-40kg cable",    "equipment_required":True, "demo_url":"https://www.youtube.com/results?search_query=straight+arm+pulldown"},
    ],
    "legs": [
        {"name":"Barbell Back Squat",      "sets":4,"reps":"5-6",  "rest":"120s","muscle":"Quads",         "weight_guide":"90-150kg",         "equipment_required":True, "demo_url":"https://www.youtube.com/results?search_query=barbell+squat+form"},
        {"name":"Romanian Deadlift",       "sets":4,"reps":"8-10", "rest":"90s", "muscle":"Hamstrings",    "weight_guide":"70-110kg",         "equipment_required":True, "demo_url":"https://www.youtube.com/results?search_query=romanian+deadlift"},
        {"name":"Leg Press",               "sets":3,"reps":"10-12","rest":"90s", "muscle":"Quads",         "weight_guide":"160-260kg machine","equipment_required":True, "demo_url":"https://www.youtube.com/results?search_query=leg+press"},
        {"name":"Bulgarian Split Squat",   "sets":3,"reps":"8 ea", "rest":"75s", "muscle":"Quads/Glutes",  "weight_guide":"20-35kg/hand",     "equipment_required":True, "demo_url":"https://www.youtube.com/results?search_query=bulgarian+split+squat"},
        {"name":"Hack Squat",              "sets":3,"reps":"10-12","rest":"90s", "muscle":"Quads",         "weight_guide":"80-150kg machine", "equipment_required":True, "demo_url":"https://www.youtube.com/results?search_query=hack+squat"},
        {"name":"Seated Leg Curl",         "sets":3,"reps":"12-15","rest":"60s", "muscle":"Hamstrings",    "weight_guide":"40-70kg machine",  "equipment_required":True, "demo_url":"https://www.youtube.com/results?search_query=seated+leg+curl"},
        {"name":"Leg Extension",           "sets":3,"reps":"12-15","rest":"60s", "muscle":"Quads",         "weight_guide":"40-70kg machine",  "equipment_required":True, "demo_url":"https://www.youtube.com/results?search_query=leg+extension"},
        {"name":"Hip Thrust",              "sets":3,"reps":"10-12","rest":"75s", "muscle":"Glutes",        "weight_guide":"80-130kg barbell", "equipment_required":True, "demo_url":"https://www.youtube.com/results?search_query=hip+thrust"},
        {"name":"Standing Calf Raises",    "sets":4,"reps":"15-20","rest":"45s", "muscle":"Calves",        "weight_guide":"BW or 30-60kg",    "equipment_required":True, "demo_url":"https://www.youtube.com/results?search_query=calf+raise"},
        {"name":"Barbell Deadlift",        "sets":4,"reps":"4-5",  "rest":"120s","muscle":"Full Posterior","weight_guide":"100-180kg",        "equipment_required":True, "demo_url":"https://www.youtube.com/results?search_query=deadlift+form"},
        {"name":"Nordic Hamstring Curl",   "sets":3,"reps":"5-6",  "rest":"90s", "muscle":"Hamstrings",    "weight_guide":"Bodyweight",       "equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=nordic+hamstring+curl"},
        {"name":"Dumbbell Walking Lunges", "sets":3,"reps":"10 ea","rest":"75s", "muscle":"Quads/Glutes",  "weight_guide":"18-28kg/hand",     "equipment_required":True, "demo_url":"https://www.youtube.com/results?search_query=dumbbell+walking+lunges"},
    ],
    "upper": [
        {"name":"Flat Dumbbell Press",       "sets":4,"reps":"8-10","rest":"75s","muscle":"Chest",       "weight_guide":"26-42kg/hand",     "equipment_required":True,"demo_url":"https://www.youtube.com/results?search_query=dumbbell+bench+press"},
        {"name":"Dumbbell Row",              "sets":4,"reps":"8-10","rest":"75s","muscle":"Back",        "weight_guide":"32-52kg/hand",     "equipment_required":True,"demo_url":"https://www.youtube.com/results?search_query=dumbbell+row"},
        {"name":"Dumbbell Shoulder Press",   "sets":3,"reps":"10",  "rest":"75s","muscle":"Shoulders",   "weight_guide":"20-35kg/hand",     "equipment_required":True,"demo_url":"https://www.youtube.com/results?search_query=dumbbell+shoulder+press"},
        {"name":"Lat Pulldown",              "sets":3,"reps":"10",  "rest":"75s","muscle":"Lats",        "weight_guide":"55-85kg cable",    "equipment_required":True,"demo_url":"https://www.youtube.com/results?search_query=lat+pulldown"},
        {"name":"Hammer Curls",              "sets":3,"reps":"12",  "rest":"60s","muscle":"Biceps",      "weight_guide":"16-26kg/hand",     "equipment_required":True,"demo_url":"https://www.youtube.com/results?search_query=hammer+curl"},
        {"name":"Overhead Tricep Extension", "sets":3,"reps":"12",  "rest":"60s","muscle":"Triceps",     "weight_guide":"26-42kg dumbbell", "equipment_required":True,"demo_url":"https://www.youtube.com/results?search_query=overhead+tricep+extension"},
        {"name":"Face Pulls",                "sets":3,"reps":"15",  "rest":"60s","muscle":"Rear Delts",  "weight_guide":"15-30kg cable",    "equipment_required":True,"demo_url":"https://www.youtube.com/results?search_query=face+pull"},
        {"name":"Barbell Bicep Curl",        "sets":3,"reps":"10",  "rest":"60s","muscle":"Biceps",      "weight_guide":"30-50kg",          "equipment_required":True,"demo_url":"https://www.youtube.com/results?search_query=barbell+curl"},
    ],
    "lower": [
        {"name":"Hack Squat",            "sets":4,"reps":"8-10", "rest":"90s","muscle":"Quads",        "weight_guide":"80-150kg machine","equipment_required":True,"demo_url":"https://www.youtube.com/results?search_query=hack+squat"},
        {"name":"Dumbbell Lunges",       "sets":3,"reps":"10 ea","rest":"75s","muscle":"Quads",        "weight_guide":"20-35kg/hand",    "equipment_required":True,"demo_url":"https://www.youtube.com/results?search_query=dumbbell+lunges"},
        {"name":"Hip Thrust",            "sets":4,"reps":"10-12","rest":"75s","muscle":"Glutes",       "weight_guide":"70-130kg barbell","equipment_required":True,"demo_url":"https://www.youtube.com/results?search_query=hip+thrust"},
        {"name":"Seated Leg Curl",       "sets":3,"reps":"12-15","rest":"60s","muscle":"Hamstrings",   "weight_guide":"40-70kg machine", "equipment_required":True,"demo_url":"https://www.youtube.com/results?search_query=leg+curl"},
        {"name":"Leg Extension",         "sets":3,"reps":"12-15","rest":"60s","muscle":"Quads",        "weight_guide":"40-70kg machine", "equipment_required":True,"demo_url":"https://www.youtube.com/results?search_query=leg+extension"},
        {"name":"Seated Calf Raise",     "sets":4,"reps":"15-20","rest":"45s","muscle":"Calves",       "weight_guide":"30-60kg",         "equipment_required":True,"demo_url":"https://www.youtube.com/results?search_query=seated+calf+raise"},
        {"name":"Romanian Deadlift",     "sets":3,"reps":"10",   "rest":"90s","muscle":"Hamstrings",   "weight_guide":"70-110kg",        "equipment_required":True,"demo_url":"https://www.youtube.com/results?search_query=romanian+deadlift"},
        {"name":"Bulgarian Split Squat", "sets":3,"reps":"8 ea", "rest":"75s","muscle":"Quads/Glutes","weight_guide":"20-35kg/hand",    "equipment_required":True,"demo_url":"https://www.youtube.com/results?search_query=bulgarian+split+squat"},
    ],
    "full body": [
        {"name":"Barbell Deadlift",    "sets":3,"reps":"5",    "rest":"120s","muscle":"Full Body","weight_guide":"90-170kg",      "equipment_required":True,"demo_url":"https://www.youtube.com/results?search_query=deadlift+form"},
        {"name":"Bench Press",         "sets":3,"reps":"8",    "rest":"90s", "muscle":"Chest",    "weight_guide":"65-105kg",      "equipment_required":True,"demo_url":"https://www.youtube.com/results?search_query=bench+press"},
        {"name":"Barbell Squat",       "sets":3,"reps":"8",    "rest":"90s", "muscle":"Legs",     "weight_guide":"75-130kg",      "equipment_required":True,"demo_url":"https://www.youtube.com/results?search_query=squat+form"},
        {"name":"Pull-Ups",            "sets":3,"reps":"8-10", "rest":"90s", "muscle":"Back",     "weight_guide":"Bodyweight",    "equipment_required":True,"demo_url":"https://www.youtube.com/results?search_query=pull+up"},
        {"name":"Overhead Press",      "sets":3,"reps":"8",    "rest":"90s", "muscle":"Shoulders","weight_guide":"42-65kg",       "equipment_required":True,"demo_url":"https://www.youtube.com/results?search_query=overhead+press"},
        {"name":"Romanian Deadlift",   "sets":3,"reps":"10",   "rest":"90s", "muscle":"Hamstrings","weight_guide":"70-110kg",     "equipment_required":True,"demo_url":"https://www.youtube.com/results?search_query=romanian+deadlift"},
        {"name":"Barbell Row",         "sets":3,"reps":"8",    "rest":"90s", "muscle":"Back",     "weight_guide":"65-100kg",      "equipment_required":True,"demo_url":"https://www.youtube.com/results?search_query=barbell+row"},
        {"name":"Dumbbell Lunges",     "sets":3,"reps":"10 ea","rest":"75s", "muscle":"Legs",     "weight_guide":"20-32kg/hand",  "equipment_required":True,"demo_url":"https://www.youtube.com/results?search_query=dumbbell+lunges"},
    ],
}

FEMALE_GYM_DB = {
    "glute & legs": [
        {"name":"Hip Thrust",              "sets":4,"reps":"10-15","rest":"75s","muscle":"Glutes",        "weight_guide":"40-90kg barbell",  "equipment_required":True,"demo_url":"https://www.youtube.com/results?search_query=hip+thrust+women"},
        {"name":"Bulgarian Split Squat",   "sets":3,"reps":"10 ea","rest":"75s","muscle":"Glutes/Quads",  "weight_guide":"10-22kg/hand",     "equipment_required":True,"demo_url":"https://www.youtube.com/results?search_query=bulgarian+split+squat"},
        {"name":"Sumo Deadlift",           "sets":3,"reps":"8-10", "rest":"90s","muscle":"Glutes/Hamstrings","weight_guide":"40-90kg",       "equipment_required":True,"demo_url":"https://www.youtube.com/results?search_query=sumo+deadlift+women"},
        {"name":"Cable Kickback",          "sets":3,"reps":"15 ea","rest":"60s","muscle":"Glutes",        "weight_guide":"10-22kg cable",    "equipment_required":True,"demo_url":"https://www.youtube.com/results?search_query=cable+kickback"},
        {"name":"Leg Press (wide stance)", "sets":3,"reps":"12-15","rest":"75s","muscle":"Glutes/Quads",  "weight_guide":"80-160kg",         "equipment_required":True,"demo_url":"https://www.youtube.com/results?search_query=wide+stance+leg+press"},
        {"name":"Romanian Deadlift",       "sets":3,"reps":"10-12","rest":"90s","muscle":"Hamstrings",    "weight_guide":"40-80kg",          "equipment_required":True,"demo_url":"https://www.youtube.com/results?search_query=romanian+deadlift+women"},
        {"name":"Abductor Machine",        "sets":3,"reps":"15-20","rest":"60s","muscle":"Hip Abductors", "weight_guide":"40-70kg machine",  "equipment_required":True,"demo_url":"https://www.youtube.com/results?search_query=abductor+machine"},
        {"name":"Leg Curl",                "sets":3,"reps":"12-15","rest":"60s","muscle":"Hamstrings",    "weight_guide":"30-55kg machine",  "equipment_required":True,"demo_url":"https://www.youtube.com/results?search_query=leg+curl+women"},
        {"name":"Barbell Squat",           "sets":4,"reps":"8-10", "rest":"90s","muscle":"Quads/Glutes",  "weight_guide":"40-80kg",          "equipment_required":True,"demo_url":"https://www.youtube.com/results?search_query=squat+women"},
        {"name":"Seated Calf Raise",       "sets":3,"reps":"15-20","rest":"45s","muscle":"Calves",        "weight_guide":"20-50kg",          "equipment_required":True,"demo_url":"https://www.youtube.com/results?search_query=seated+calf+raise"},
    ],
    "upper toning": [
        {"name":"Lat Pulldown",            "sets":3,"reps":"12-15","rest":"75s","muscle":"Back",      "weight_guide":"25-50kg cable",   "equipment_required":True,"demo_url":"https://www.youtube.com/results?search_query=lat+pulldown+women"},
        {"name":"Seated Cable Row",        "sets":3,"reps":"12",   "rest":"75s","muscle":"Back",      "weight_guide":"25-45kg cable",   "equipment_required":True,"demo_url":"https://www.youtube.com/results?search_query=seated+cable+row+women"},
        {"name":"Dumbbell Shoulder Press", "sets":3,"reps":"12",   "rest":"60s","muscle":"Shoulders", "weight_guide":"8-16kg/hand",     "equipment_required":True,"demo_url":"https://www.youtube.com/results?search_query=shoulder+press+women"},
        {"name":"Tricep Pushdown",         "sets":3,"reps":"15",   "rest":"60s","muscle":"Triceps",   "weight_guide":"10-22kg cable",   "equipment_required":True,"demo_url":"https://www.youtube.com/results?search_query=tricep+pushdown+women"},
        {"name":"Dumbbell Row",            "sets":3,"reps":"12",   "rest":"60s","muscle":"Back",      "weight_guide":"10-22kg/hand",    "equipment_required":True,"demo_url":"https://www.youtube.com/results?search_query=dumbbell+row+women"},
        {"name":"Lateral Raises",          "sets":3,"reps":"15",   "rest":"45s","muscle":"Shoulders", "weight_guide":"5-12kg/hand",     "equipment_required":True,"demo_url":"https://www.youtube.com/results?search_query=lateral+raise"},
        {"name":"Incline Dumbbell Press",  "sets":3,"reps":"12",   "rest":"75s","muscle":"Upper Chest","weight_guide":"10-18kg/hand",   "equipment_required":True,"demo_url":"https://www.youtube.com/results?search_query=incline+dumbbell+press+women"},
        {"name":"Cable Bicep Curl",        "sets":3,"reps":"12-15","rest":"45s","muscle":"Biceps",    "weight_guide":"10-20kg cable",   "equipment_required":True,"demo_url":"https://www.youtube.com/results?search_query=cable+curl+women"},
        {"name":"Face Pulls",              "sets":3,"reps":"15",   "rest":"45s","muscle":"Rear Delts","weight_guide":"10-20kg cable",   "equipment_required":True,"demo_url":"https://www.youtube.com/results?search_query=face+pull"},
    ],
    "core & cardio": [
        {"name":"Cable Crunch",        "sets":3,"reps":"15-20","rest":"45s","muscle":"Core",    "weight_guide":"15-35kg cable","equipment_required":True, "demo_url":"https://www.youtube.com/results?search_query=cable+crunch"},
        {"name":"Hanging Leg Raise",   "sets":3,"reps":"12",   "rest":"45s","muscle":"Core",    "weight_guide":"Bodyweight",   "equipment_required":True, "demo_url":"https://www.youtube.com/results?search_query=hanging+leg+raise"},
        {"name":"Plank",               "sets":3,"reps":"45-60s","rest":"45s","muscle":"Core",   "weight_guide":"Bodyweight",   "equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=plank+form"},
        {"name":"Russian Twists",      "sets":3,"reps":"20",   "rest":"45s","muscle":"Obliques","weight_guide":"5-12kg plate", "equipment_required":True, "demo_url":"https://www.youtube.com/results?search_query=russian+twist"},
        {"name":"Ab Rollout",          "sets":3,"reps":"10-12","rest":"60s","muscle":"Core",    "weight_guide":"Ab wheel",     "equipment_required":True, "demo_url":"https://www.youtube.com/results?search_query=ab+rollout"},
        {"name":"Stairmaster",         "sets":1,"reps":"20 min","rest":"0", "muscle":"Cardio",  "weight_guide":"Level 8-12",   "equipment_required":True, "demo_url":"https://www.youtube.com/results?search_query=stairmaster+workout"},
        {"name":"Treadmill Intervals", "sets":6,"reps":"1 min fast / 1 min slow","rest":"0","muscle":"Cardio","weight_guide":"Own pace","equipment_required":True,"demo_url":"https://www.youtube.com/results?search_query=treadmill+interval+workout"},
        {"name":"Bicycle Crunches",    "sets":3,"reps":"20",   "rest":"45s","muscle":"Obliques","weight_guide":"Bodyweight",   "equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=bicycle+crunch"},
    ],
    "full body": [
        {"name":"Hip Thrust",              "sets":3,"reps":"12-15","rest":"75s","muscle":"Glutes",      "weight_guide":"40-70kg barbell","equipment_required":True,"demo_url":"https://www.youtube.com/results?search_query=hip+thrust+women"},
        {"name":"Lat Pulldown",            "sets":3,"reps":"12",   "rest":"75s","muscle":"Back",        "weight_guide":"25-45kg",        "equipment_required":True,"demo_url":"https://www.youtube.com/results?search_query=lat+pulldown"},
        {"name":"Leg Press",               "sets":3,"reps":"12-15","rest":"75s","muscle":"Quads/Glutes","weight_guide":"80-140kg",        "equipment_required":True,"demo_url":"https://www.youtube.com/results?search_query=leg+press"},
        {"name":"Dumbbell Shoulder Press", "sets":3,"reps":"12",   "rest":"60s","muscle":"Shoulders",   "weight_guide":"8-14kg/hand",    "equipment_required":True,"demo_url":"https://www.youtube.com/results?search_query=shoulder+press"},
        {"name":"Cable Kickback",          "sets":3,"reps":"15 ea","rest":"60s","muscle":"Glutes",      "weight_guide":"10-18kg",        "equipment_required":True,"demo_url":"https://www.youtube.com/results?search_query=cable+kickback"},
        {"name":"Seated Cable Row",        "sets":3,"reps":"12",   "rest":"75s","muscle":"Back",        "weight_guide":"25-45kg",        "equipment_required":True,"demo_url":"https://www.youtube.com/results?search_query=seated+cable+row"},
        {"name":"Leg Curl",                "sets":3,"reps":"15",   "rest":"60s","muscle":"Hamstrings",  "weight_guide":"25-45kg",        "equipment_required":True,"demo_url":"https://www.youtube.com/results?search_query=leg+curl"},
    ],
}

MALE_HOME_DB = {
    "push": [
        {"name":"Push-Ups",                "sets":4,"reps":"15-20","rest":"60s","muscle":"Chest",          "weight_guide":"Bodyweight","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=push+up+form"},
        {"name":"Pike Push-Ups",           "sets":3,"reps":"12-15","rest":"60s","muscle":"Shoulders",      "weight_guide":"Bodyweight","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=pike+push+up"},
        {"name":"Diamond Push-Ups",        "sets":3,"reps":"12",   "rest":"60s","muscle":"Triceps",        "weight_guide":"Bodyweight","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=diamond+push+up"},
        {"name":"Decline Push-Ups",        "sets":3,"reps":"15",   "rest":"60s","muscle":"Upper Chest",    "weight_guide":"Bodyweight","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=decline+push+up"},
        {"name":"Wide Push-Ups",           "sets":3,"reps":"15",   "rest":"60s","muscle":"Chest",          "weight_guide":"Bodyweight","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=wide+push+up"},
        {"name":"Dips (chair)",            "sets":3,"reps":"15",   "rest":"60s","muscle":"Triceps",        "weight_guide":"Bodyweight","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=chair+dips"},
        {"name":"Archer Push-Ups",         "sets":3,"reps":"8 ea", "rest":"75s","muscle":"Chest",          "weight_guide":"Bodyweight","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=archer+push+up"},
        {"name":"Explosive Push-Ups",      "sets":3,"reps":"10",   "rest":"75s","muscle":"Chest/Power",    "weight_guide":"Bodyweight","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=explosive+push+up"},
        {"name":"Incline Push-Ups",        "sets":3,"reps":"20",   "rest":"60s","muscle":"Lower Chest",    "weight_guide":"Bodyweight","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=incline+push+up"},
    ],
    "pull": [
        {"name":"Superman Hold",           "sets":3,"reps":"12",   "rest":"45s","muscle":"Lower Back",     "weight_guide":"Bodyweight","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=superman+hold"},
        {"name":"Doorframe Row",           "sets":4,"reps":"12-15","rest":"60s","muscle":"Back",            "weight_guide":"Bodyweight","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=doorframe+row"},
        {"name":"Towel Row",               "sets":3,"reps":"12",   "rest":"60s","muscle":"Back",            "weight_guide":"Bodyweight","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=towel+row+home"},
        {"name":"Reverse Snow Angel",      "sets":3,"reps":"15",   "rest":"45s","muscle":"Rear Delts",      "weight_guide":"Bodyweight","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=reverse+snow+angel"},
        {"name":"Band Bicep Curl",         "sets":3,"reps":"15",   "rest":"45s","muscle":"Biceps",          "weight_guide":"Resistance band","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=resistance+band+curl"},
        {"name":"Inverted Row (table)",    "sets":3,"reps":"12",   "rest":"60s","muscle":"Back",            "weight_guide":"Bodyweight","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=inverted+row+table"},
        {"name":"Band Pull-Apart",         "sets":3,"reps":"20",   "rest":"45s","muscle":"Rear Delts",      "weight_guide":"Light band","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=band+pull+apart"},
        {"name":"Resistance Band Row",     "sets":3,"reps":"15",   "rest":"60s","muscle":"Back",            "weight_guide":"Medium band","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=resistance+band+row"},
        {"name":"Face Pull (band)",        "sets":3,"reps":"15",   "rest":"45s","muscle":"Rear Delts",      "weight_guide":"Light band","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=band+face+pull"},
    ],
    "legs": [
        {"name":"Bodyweight Squats",       "sets":4,"reps":"20-25","rest":"60s","muscle":"Quads",           "weight_guide":"Bodyweight","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=squat+form"},
        {"name":"Jump Squats",             "sets":3,"reps":"15",   "rest":"75s","muscle":"Quads/Power",     "weight_guide":"Bodyweight","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=jump+squat"},
        {"name":"Reverse Lunges",          "sets":3,"reps":"12 ea","rest":"60s","muscle":"Quads",           "weight_guide":"Bodyweight","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=reverse+lunge"},
        {"name":"Glute Bridge",            "sets":4,"reps":"20",   "rest":"60s","muscle":"Glutes",          "weight_guide":"Bodyweight","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=glute+bridge"},
        {"name":"Single-Leg Deadlift",     "sets":3,"reps":"10 ea","rest":"60s","muscle":"Hamstrings",      "weight_guide":"Bodyweight","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=single+leg+deadlift+bodyweight"},
        {"name":"Calf Raises",             "sets":4,"reps":"25",   "rest":"45s","muscle":"Calves",          "weight_guide":"Bodyweight","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=calf+raise"},
        {"name":"Wall Sit",                "sets":3,"reps":"45-60s","rest":"60s","muscle":"Quads",          "weight_guide":"Bodyweight","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=wall+sit"},
        {"name":"Nordic Curl (assisted)",  "sets":3,"reps":"5-8",  "rest":"90s","muscle":"Hamstrings",      "weight_guide":"Bodyweight","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=nordic+curl"},
        {"name":"Step-Ups (chair)",        "sets":3,"reps":"12 ea","rest":"60s","muscle":"Quads/Glutes",    "weight_guide":"Bodyweight","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=step+up+exercise"},
    ],
    "full body": [
        {"name":"Burpees",            "sets":3,"reps":"12",  "rest":"75s","muscle":"Full Body",   "weight_guide":"Bodyweight","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=burpee+form"},
        {"name":"Mountain Climbers",  "sets":3,"reps":"30s", "rest":"45s","muscle":"Core/Cardio", "weight_guide":"Bodyweight","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=mountain+climber"},
        {"name":"Push-Ups",           "sets":3,"reps":"15",  "rest":"60s","muscle":"Chest",       "weight_guide":"Bodyweight","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=push+up"},
        {"name":"Bodyweight Squats",  "sets":3,"reps":"20",  "rest":"60s","muscle":"Legs",        "weight_guide":"Bodyweight","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=squat"},
        {"name":"Plank",              "sets":3,"reps":"45s", "rest":"45s","muscle":"Core",        "weight_guide":"Bodyweight","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=plank"},
        {"name":"Glute Bridge",       "sets":3,"reps":"20",  "rest":"60s","muscle":"Glutes",      "weight_guide":"Bodyweight","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=glute+bridge"},
        {"name":"Pike Push-Ups",      "sets":3,"reps":"10",  "rest":"60s","muscle":"Shoulders",   "weight_guide":"Bodyweight","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=pike+push+up"},
        {"name":"Jumping Jacks",      "sets":3,"reps":"30",  "rest":"30s","muscle":"Cardio",      "weight_guide":"Bodyweight","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=jumping+jacks"},
    ],
}

FEMALE_HOME_DB = {
    "glute & legs": [
        {"name":"Glute Bridge",            "sets":4,"reps":"20",   "rest":"60s","muscle":"Glutes",        "weight_guide":"Bodyweight","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=glute+bridge+women"},
        {"name":"Donkey Kicks",            "sets":3,"reps":"20 ea","rest":"45s","muscle":"Glutes",        "weight_guide":"Bodyweight","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=donkey+kick"},
        {"name":"Sumo Squats",             "sets":4,"reps":"20",   "rest":"60s","muscle":"Glutes/Quads",  "weight_guide":"Bodyweight","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=sumo+squat"},
        {"name":"Fire Hydrants",           "sets":3,"reps":"20 ea","rest":"45s","muscle":"Glutes",        "weight_guide":"Bodyweight","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=fire+hydrant+exercise"},
        {"name":"Curtsy Lunges",           "sets":3,"reps":"15 ea","rest":"60s","muscle":"Glutes",        "weight_guide":"Bodyweight","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=curtsy+lunge"},
        {"name":"Single-Leg Glute Bridge", "sets":3,"reps":"15 ea","rest":"60s","muscle":"Glutes",        "weight_guide":"Bodyweight","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=single+leg+glute+bridge"},
        {"name":"Hip Circles",             "sets":3,"reps":"15 ea","rest":"30s","muscle":"Hip Abductors", "weight_guide":"Bodyweight","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=hip+circles+exercise"},
        {"name":"Reverse Lunges",          "sets":3,"reps":"12 ea","rest":"60s","muscle":"Quads/Glutes",  "weight_guide":"Bodyweight","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=reverse+lunge+women"},
        {"name":"Calf Raises",             "sets":3,"reps":"20",   "rest":"45s","muscle":"Calves",        "weight_guide":"Bodyweight","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=calf+raise"},
        {"name":"Jump Squats",             "sets":3,"reps":"12",   "rest":"75s","muscle":"Quads/Power",   "weight_guide":"Bodyweight","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=jump+squat+women"},
    ],
    "upper toning": [
        {"name":"Push-Ups",           "sets":3,"reps":"12-15","rest":"60s","muscle":"Chest",     "weight_guide":"Bodyweight",     "equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=push+up+women"},
        {"name":"Band Lateral Raise", "sets":3,"reps":"15",   "rest":"45s","muscle":"Shoulders", "weight_guide":"Light band",     "equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=band+lateral+raise"},
        {"name":"Tricep Dips (chair)","sets":3,"reps":"12",   "rest":"60s","muscle":"Triceps",   "weight_guide":"Bodyweight",     "equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=tricep+dip+chair"},
        {"name":"Band Rows",          "sets":3,"reps":"15",   "rest":"60s","muscle":"Back",      "weight_guide":"Resistance band","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=resistance+band+row"},
        {"name":"Band Bicep Curl",    "sets":3,"reps":"15",   "rest":"45s","muscle":"Biceps",    "weight_guide":"Light band",     "equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=band+bicep+curl"},
        {"name":"Pike Push-Ups",      "sets":3,"reps":"10",   "rest":"60s","muscle":"Shoulders", "weight_guide":"Bodyweight",     "equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=pike+push+up+women"},
        {"name":"Inverted Row (table)","sets":3,"reps":"10",  "rest":"60s","muscle":"Back",      "weight_guide":"Bodyweight",     "equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=inverted+row+table"},
        {"name":"Band Pull-Apart",    "sets":3,"reps":"20",   "rest":"45s","muscle":"Rear Delts","weight_guide":"Light band",     "equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=band+pull+apart"},
        {"name":"Diamond Push-Ups",   "sets":3,"reps":"8-10", "rest":"60s","muscle":"Triceps",   "weight_guide":"Bodyweight",     "equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=diamond+push+up"},
    ],
    "core & cardio": [
        {"name":"Crunches",          "sets":3,"reps":"20",    "rest":"45s","muscle":"Core",    "weight_guide":"Bodyweight","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=crunch+form"},
        {"name":"Plank",             "sets":3,"reps":"45-60s","rest":"45s","muscle":"Core",    "weight_guide":"Bodyweight","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=plank"},
        {"name":"High Knees",        "sets":3,"reps":"30s",   "rest":"30s","muscle":"Cardio",  "weight_guide":"Bodyweight","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=high+knees"},
        {"name":"Russian Twists",    "sets":3,"reps":"20",    "rest":"45s","muscle":"Obliques","weight_guide":"Bodyweight","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=russian+twist"},
        {"name":"Jumping Jacks",     "sets":3,"reps":"30",    "rest":"30s","muscle":"Cardio",  "weight_guide":"Bodyweight","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=jumping+jacks"},
        {"name":"Bicycle Crunches",  "sets":3,"reps":"20",    "rest":"45s","muscle":"Obliques","weight_guide":"Bodyweight","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=bicycle+crunch"},
        {"name":"Leg Raises",        "sets":3,"reps":"15",    "rest":"45s","muscle":"Lower Core","weight_guide":"Bodyweight","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=leg+raise"},
        {"name":"Burpees",           "sets":3,"reps":"10",    "rest":"60s","muscle":"Full Body","weight_guide":"Bodyweight","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=burpee"},
    ],
    "full body": [
        {"name":"Glute Bridge",      "sets":3,"reps":"20",   "rest":"60s","muscle":"Glutes",      "weight_guide":"Bodyweight",     "equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=glute+bridge"},
        {"name":"Push-Ups",          "sets":3,"reps":"12",   "rest":"60s","muscle":"Chest",       "weight_guide":"Bodyweight",     "equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=push+up"},
        {"name":"Sumo Squats",       "sets":3,"reps":"20",   "rest":"60s","muscle":"Legs",        "weight_guide":"Bodyweight",     "equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=sumo+squat"},
        {"name":"Plank",             "sets":3,"reps":"45s",  "rest":"45s","muscle":"Core",        "weight_guide":"Bodyweight",     "equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=plank"},
        {"name":"Donkey Kicks",      "sets":3,"reps":"15 ea","rest":"45s","muscle":"Glutes",      "weight_guide":"Bodyweight",     "equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=donkey+kick"},
        {"name":"Band Rows",         "sets":3,"reps":"15",   "rest":"60s","muscle":"Back",        "weight_guide":"Light band",     "equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=resistance+band+row"},
        {"name":"Mountain Climbers", "sets":3,"reps":"30s",  "rest":"45s","muscle":"Core/Cardio", "weight_guide":"Bodyweight",     "equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=mountain+climber"},
    ],
}

INJURY_SAFE_DB = {
    "upper": [
        {"name":"Seated Dumbbell Press", "sets":3,"reps":"12",   "rest":"75s","muscle":"Shoulders", "weight_guide":"5-14kg",    "equipment_required":True, "demo_url":"https://www.youtube.com/results?search_query=seated+dumbbell+press"},
        {"name":"Cable Lat Pulldown",    "sets":3,"reps":"12",   "rest":"75s","muscle":"Back",      "weight_guide":"20-45kg",   "equipment_required":True, "demo_url":"https://www.youtube.com/results?search_query=lat+pulldown"},
        {"name":"Band Pull-Apart",       "sets":3,"reps":"20",   "rest":"45s","muscle":"Rear Delts","weight_guide":"Light band","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=band+pull+apart"},
        {"name":"Seated Cable Row",      "sets":3,"reps":"12",   "rest":"75s","muscle":"Back",      "weight_guide":"25-50kg",   "equipment_required":True, "demo_url":"https://www.youtube.com/results?search_query=seated+cable+row"},
        {"name":"Wrist Curl",            "sets":3,"reps":"15",   "rest":"45s","muscle":"Forearms",  "weight_guide":"5-12kg",    "equipment_required":True, "demo_url":"https://www.youtube.com/results?search_query=wrist+curl"},
    ],
    "lower": [
        {"name":"Leg Press (shallow)", "sets":3,"reps":"15",   "rest":"75s","muscle":"Quads",    "weight_guide":"60-110kg", "equipment_required":True, "demo_url":"https://www.youtube.com/results?search_query=shallow+leg+press"},
        {"name":"Seated Leg Curl",     "sets":3,"reps":"15",   "rest":"60s","muscle":"Hamstrings","weight_guide":"25-50kg",  "equipment_required":True, "demo_url":"https://www.youtube.com/results?search_query=seated+leg+curl"},
        {"name":"Calf Raises",         "sets":4,"reps":"20",   "rest":"45s","muscle":"Calves",    "weight_guide":"Bodyweight","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=calf+raise"},
        {"name":"Hip Thrust (light)",  "sets":3,"reps":"15",   "rest":"60s","muscle":"Glutes",    "weight_guide":"BW-40kg",  "equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=hip+thrust"},
        {"name":"Wall Sit",            "sets":3,"reps":"45s",  "rest":"60s","muscle":"Quads",     "weight_guide":"Bodyweight","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=wall+sit"},
    ],
    "full body": [
        {"name":"Seated Band Row",     "sets":3,"reps":"15",   "rest":"60s","muscle":"Back",      "weight_guide":"Light band","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=resistance+band+row"},
        {"name":"Lying Hip Abduction", "sets":3,"reps":"15 ea","rest":"45s","muscle":"Hips",      "weight_guide":"Bodyweight","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=hip+abduction"},
        {"name":"Seated Shoulder Press","sets":3,"reps":"12",  "rest":"60s","muscle":"Shoulders", "weight_guide":"8-16kg",   "equipment_required":True, "demo_url":"https://www.youtube.com/results?search_query=seated+shoulder+press"},
        {"name":"Calf Raises",         "sets":3,"reps":"20",   "rest":"45s","muscle":"Calves",    "weight_guide":"Bodyweight","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=calf+raise"},
        {"name":"Band Pull-Apart",     "sets":3,"reps":"20",   "rest":"45s","muscle":"Rear Delts","weight_guide":"Light band","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=band+pull+apart"},
    ],
}


# -- RICH DB ROUTING ---------------------------------------------------------
# Maps abstract weekly-plan session types to keys inside the gender/mode DBs
_MALE_GYM_MAP = {
    "push": "push", "push_volume": "push", "push_strength": "push",
    "pull": "pull", "pull_volume": "pull", "pull_strength": "pull",
    "legs": "legs", "legs_strength": "legs",
    "upper_body": "upper", "shoulders_arms": "upper", "strength": "upper",
    "lower_body": "lower", "lower_strength": "lower",
    "full_body": "full body",
}
_FEMALE_GYM_MAP = {
    "lower_body": "glute & legs", "glutes": "glute & legs",
    "glutes_hamstrings": "glute & legs", "legs": "glute & legs",
    "legs_strength": "glute & legs", "strength": "glute & legs",
    "upper_body": "upper toning",
    "core_cardio": "core & cardio", "hiit": "core & cardio", "cardio": "core & cardio",
    "full_body": "full body",
}
_MALE_HOME_MAP = {
    "push": "push", "upper_body": "push", "shoulders_arms": "push",
    "pull": "pull",
    "legs": "legs", "lower_body": "legs", "lower_strength": "legs",
    "full_body": "full body", "hiit": "full body",
    "core_cardio": "full body", "cardio": "full body",
}
_FEMALE_HOME_MAP = {
    "lower_body": "glute & legs", "glutes": "glute & legs",
    "glutes_hamstrings": "glute & legs", "legs": "glute & legs",
    "upper_body": "upper toning",
    "core_cardio": "core & cardio", "hiit": "core & cardio", "cardio": "core & cardio",
    "full_body": "full body",
}
_RICH_DBS = {
    ("male", "gym"): MALE_GYM_DB, ("female", "gym"): FEMALE_GYM_DB,
    ("male", "home"): MALE_HOME_DB, ("female", "home"): FEMALE_HOME_DB,
}
_GENDER_SESSION_MAP = {
    ("male", "gym"): _MALE_GYM_MAP, ("female", "gym"): _FEMALE_GYM_MAP,
    ("male", "home"): _MALE_HOME_MAP, ("female", "home"): _FEMALE_HOME_MAP,
}


def _format_rich_ex(ex, zone="green"):
    "Add workout-UI required fields to a rich-DB exercise dict."
    item = dict(ex)
    if zone == "red":
        item["sets"] = max(1, min(item.get("sets", 3), 2))
        item["rest"] = "45s"
        item["intensity"] = "recovery"
    elif zone == "yellow":
        item["sets"] = max(2, item.get("sets", 3) - 1)
        item["intensity"] = "moderate"
    else:
        item["intensity"] = "full"
    reps_str = str(item.get("reps", "10"))
    item["posture_config"] = {
        "form_key": item.get("form_key", "squat"),
        "rep_target": engine_parse_rep_target(reps_str),
    }
    item.setdefault("weight_guide", "Appropriate weight")
    item.setdefault("progression", ["add reps or load each week", "keep form strict"])
    item["injury_compatible"] = True
    item["home_compatible"] = not item.get("equipment_required", True)
    item["gym_compatible"] = bool(item.get("equipment_required", True))
    item.setdefault(
        "demo_url",
        "https://www.youtube.com/results?search_query="
        + item["name"].replace(" ", "+") + "+form",
    )
    return item


def _get_rich_exercises(session, profile, mode, recovery_zone="green", count=6):
    """
    Route exercise selection to the correct gender/mode-specific rich DB.
    Signature matches exercises_fn protocol: (session, profile, mode, zone, count).
    Falls back to fitness_engine for sessions not covered by the rich DBs.
    """
    p      = profile if isinstance(profile, dict) else profile.to_dict()
    gender = (p.get("gender") or "male").lower()
    if gender not in ("male", "female"):
        gender = "male"
    sport = (p.get("sport") or "").lower()

    # Sport mode: delegate to SPORT_EXERCISES
    if mode == "sport" and sport:
        raw = get_sport_exercises(sport, session, recovery_zone, p)
        return [_format_rich_ex(e, recovery_zone) for e in raw[:count]]

    # Recovery / mobility: engine handles these lightweight sessions
    if session in ("recovery", "mobility"):
        return engine_select_exercises(session, p, mode, recovery_zone, count)

    # Try the rich gender/mode DB
    key_map   = _GENDER_SESSION_MAP.get((gender, mode), {})
    db_key    = key_map.get(session)
    if db_key:
        db        = _RICH_DBS.get((gender, mode), {})
        exercises = db.get(db_key, [])
        if exercises:
            return [_format_rich_ex(e, recovery_zone) for e in exercises[:count]]

    # Final fallback: fitness_engine small-pool selector
    return engine_select_exercises(session, p, mode, recovery_zone, count)

# ------------------------------------------------------------------------------
# SPORT EXERCISE DATABASE
# ------------------------------------------------------------------------------
SPORT_EXERCISES = {
    "cricket": {
        "power": [
            {"name":"Medicine Ball Rotational Throw","sets":4,"reps":"8 ea","rest":"90s","muscle":"Core/Power","weight_guide":"4-8kg ball","equipment_required":True,"demo_url":"https://www.youtube.com/results?search_query=medicine+ball+rotational+throw"},
            {"name":"Cable Wood Chop",               "sets":3,"reps":"12 ea","rest":"75s","muscle":"Obliques","weight_guide":"20-35kg cable","equipment_required":True,"demo_url":"https://www.youtube.com/results?search_query=cable+wood+chop"},
            {"name":"Landmine Rotation",             "sets":3,"reps":"10 ea","rest":"75s","muscle":"Rotational Power","weight_guide":"20-40kg","equipment_required":True,"demo_url":"https://www.youtube.com/results?search_query=landmine+rotation"},
            {"name":"Box Jump",                      "sets":4,"reps":"6","rest":"90s","muscle":"Explosive Power","weight_guide":"Bodyweight","equipment_required":True,"demo_url":"https://www.youtube.com/results?search_query=box+jump+form"},
            {"name":"Romanian Deadlift",             "sets":3,"reps":"8","rest":"90s","muscle":"Hamstrings","weight_guide":"60-100kg","equipment_required":True,"demo_url":"https://www.youtube.com/results?search_query=romanian+deadlift"},
            {"name":"Pallof Press",                  "sets":3,"reps":"12 ea","rest":"60s","muscle":"Anti-Rotation Core","weight_guide":"15-30kg","equipment_required":True,"demo_url":"https://www.youtube.com/results?search_query=pallof+press"},
            {"name":"Single-Leg Bound",              "sets":3,"reps":"6 ea","rest":"90s","muscle":"Explosive Legs","weight_guide":"Bodyweight","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=single+leg+bound"},
            {"name":"Trap Bar Deadlift",             "sets":3,"reps":"5","rest":"120s","muscle":"Full Body Power","weight_guide":"80-140kg","equipment_required":True,"demo_url":"https://www.youtube.com/results?search_query=trap+bar+deadlift"},
        ],
        "mobility": [
            {"name":"Hip 90/90 Stretch",         "sets":3,"reps":"60s ea","rest":"30s","muscle":"Hips","weight_guide":"Bodyweight","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=90+90+hip+stretch"},
            {"name":"Thoracic Rotation",         "sets":3,"reps":"10 ea","rest":"30s","muscle":"Thoracic","weight_guide":"Bodyweight","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=thoracic+rotation+stretch"},
            {"name":"Shoulder Band Distraction", "sets":3,"reps":"60s ea","rest":"30s","muscle":"Shoulder","weight_guide":"Light band","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=shoulder+band+distraction"},
            {"name":"Wrist Circles",             "sets":3,"reps":"15 ea","rest":"20s","muscle":"Wrists","weight_guide":"Bodyweight","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=wrist+mobility"},
            {"name":"Cat-Cow Stretch",           "sets":3,"reps":"12","rest":"20s","muscle":"Spine","weight_guide":"Bodyweight","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=cat+cow+stretch"},
            {"name":"World's Greatest Stretch",  "sets":3,"reps":"5 ea","rest":"30s","muscle":"Full Body Mobility","weight_guide":"Bodyweight","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=worlds+greatest+stretch"},
            {"name":"Pigeon Pose",               "sets":3,"reps":"60s ea","rest":"0","muscle":"Hip Flexors","weight_guide":"Bodyweight","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=pigeon+pose"},
        ],
        "strength": [
            {"name":"Barbell Squat",           "sets":4,"reps":"6","rest":"120s","muscle":"Legs","weight_guide":"80-130kg","equipment_required":True,"demo_url":"https://www.youtube.com/results?search_query=barbell+squat"},
            {"name":"Single-Arm Dumbbell Row", "sets":3,"reps":"8 ea","rest":"75s","muscle":"Back","weight_guide":"30-50kg","equipment_required":True,"demo_url":"https://www.youtube.com/results?search_query=single+arm+row"},
            {"name":"Pallof Press",            "sets":3,"reps":"12 ea","rest":"60s","muscle":"Core Stability","weight_guide":"15-30kg","equipment_required":True,"demo_url":"https://www.youtube.com/results?search_query=pallof+press"},
            {"name":"Nordic Hamstring Curl",   "sets":3,"reps":"6","rest":"90s","muscle":"Hamstrings","weight_guide":"Bodyweight","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=nordic+hamstring+curl"},
            {"name":"Face Pulls",              "sets":3,"reps":"15","rest":"60s","muscle":"Shoulder Health","weight_guide":"15-25kg","equipment_required":True,"demo_url":"https://www.youtube.com/results?search_query=face+pull"},
            {"name":"Bulgarian Split Squat",   "sets":3,"reps":"8 ea","rest":"90s","muscle":"Single-Leg Strength","weight_guide":"20-35kg/hand","equipment_required":True,"demo_url":"https://www.youtube.com/results?search_query=bulgarian+split+squat"},
            {"name":"Hip Thrust",              "sets":3,"reps":"8","rest":"90s","muscle":"Glutes/Drive","weight_guide":"80-120kg","equipment_required":True,"demo_url":"https://www.youtube.com/results?search_query=hip+thrust"},
        ],
        "conditioning": [
            {"name":"Sprint Intervals (20m)", "sets":6,"reps":"20m sprint","rest":"60s","muscle":"Speed","weight_guide":"Bodyweight","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=sprint+training"},
            {"name":"Lateral Shuffle",        "sets":4,"reps":"10m ea","rest":"45s","muscle":"Agility","weight_guide":"Bodyweight","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=lateral+shuffle+drill"},
            {"name":"Skater Jumps",           "sets":3,"reps":"12 ea","rest":"60s","muscle":"Lateral Power","weight_guide":"Bodyweight","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=skater+jump"},
            {"name":"Reaction Ball Drill",    "sets":3,"reps":"2 min","rest":"60s","muscle":"Reflexes","weight_guide":"Reaction ball","equipment_required":True,"demo_url":"https://www.youtube.com/results?search_query=reaction+ball+drill"},
            {"name":"Jump Rope",              "sets":3,"reps":"2 min","rest":"60s","muscle":"Cardio/Footwork","weight_guide":"Jump rope","equipment_required":True,"demo_url":"https://www.youtube.com/results?search_query=jump+rope+workout"},
            {"name":"Agility Ladder Drills",  "sets":4,"reps":"30s","rest":"45s","muscle":"Footwork/Speed","weight_guide":"Ladder","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=agility+ladder+drills"},
        ],
        "recovery": [
            {"name":"Foam Roll Thoracic Spine","sets":1,"reps":"2 min","rest":"0","muscle":"Thoracic","weight_guide":"Foam roller","equipment_required":True,"demo_url":"https://www.youtube.com/results?search_query=foam+roll+thoracic"},
            {"name":"Hip Flexor Stretch",      "sets":3,"reps":"60s ea","rest":"0","muscle":"Hip Flexors","weight_guide":"Bodyweight","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=hip+flexor+stretch"},
            {"name":"Shoulder Sleeper Stretch","sets":3,"reps":"60s ea","rest":"0","muscle":"Shoulder","weight_guide":"Bodyweight","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=sleeper+stretch+shoulder"},
            {"name":"Child's Pose",            "sets":3,"reps":"60s","rest":"0","muscle":"Spine","weight_guide":"Bodyweight","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=childs+pose"},
            {"name":"Ice Bath / Cold Shower",  "sets":1,"reps":"10 min","rest":"0","muscle":"Full Recovery","weight_guide":"Cold water","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=ice+bath+benefits"},
        ],
    },
    "football": {
        "power": [
            {"name":"Power Clean",         "sets":4,"reps":"5","rest":"120s","muscle":"Full Body Power","weight_guide":"50-80kg","equipment_required":True,"demo_url":"https://www.youtube.com/results?search_query=power+clean+form"},
            {"name":"Trap Bar Deadlift",   "sets":4,"reps":"5","rest":"120s","muscle":"Posterior Chain","weight_guide":"80-140kg","equipment_required":True,"demo_url":"https://www.youtube.com/results?search_query=trap+bar+deadlift"},
            {"name":"Depth Jump",          "sets":4,"reps":"5","rest":"90s","muscle":"Reactive Power","weight_guide":"Bodyweight","equipment_required":True,"demo_url":"https://www.youtube.com/results?search_query=depth+jump+plyometric"},
            {"name":"Bulgarian Split Squat","sets":3,"reps":"8 ea","rest":"90s","muscle":"Single-Leg Strength","weight_guide":"20-40kg/hand","equipment_required":True,"demo_url":"https://www.youtube.com/results?search_query=bulgarian+split+squat"},
            {"name":"Hip Thrust",          "sets":4,"reps":"8","rest":"90s","muscle":"Glutes/Sprint Power","weight_guide":"80-120kg","equipment_required":True,"demo_url":"https://www.youtube.com/results?search_query=hip+thrust+sports"},
            {"name":"Band Resisted Sprint", "sets":5,"reps":"15m","rest":"90s","muscle":"Sprint Power","weight_guide":"Resistance band","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=band+resisted+sprint"},
        ],
        "agility": [
            {"name":"Cone Drills (T-Drill)","sets":4,"reps":"1 run","rest":"60s","muscle":"Agility","weight_guide":"Bodyweight","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=t+drill+agility"},
            {"name":"Ladder Drills",        "sets":4,"reps":"2 min","rest":"60s","muscle":"Footwork","weight_guide":"Agility ladder","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=agility+ladder+drills"},
            {"name":"Box Shuffle",          "sets":3,"reps":"30s","rest":"45s","muscle":"Lateral Speed","weight_guide":"Bodyweight","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=box+shuffle+drill"},
            {"name":"180 Jump Turn",       "sets":3,"reps":"8","rest":"60s","muscle":"Change of Direction","weight_guide":"Bodyweight","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=180+jump+turn"},
            {"name":"Reactive Sprint",      "sets":5,"reps":"10m","rest":"60s","muscle":"Sprint Reaction","weight_guide":"Bodyweight","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=reactive+sprint+drill"},
            {"name":"5-10-5 Shuttle",       "sets":4,"reps":"1 run","rest":"60s","muscle":"Change of Direction","weight_guide":"Bodyweight","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=5+10+5+shuttle+drill"},
        ],
        "strength": [
            {"name":"Barbell Squat",    "sets":4,"reps":"5","rest":"120s","muscle":"Legs","weight_guide":"80-140kg","equipment_required":True,"demo_url":"https://www.youtube.com/results?search_query=barbell+squat"},
            {"name":"Bench Press",      "sets":4,"reps":"6","rest":"90s","muscle":"Chest","weight_guide":"70-110kg","equipment_required":True,"demo_url":"https://www.youtube.com/results?search_query=bench+press"},
            {"name":"Pull-Ups",         "sets":4,"reps":"8","rest":"75s","muscle":"Back","weight_guide":"BW +weight","equipment_required":True,"demo_url":"https://www.youtube.com/results?search_query=pull+up"},
            {"name":"RDL",              "sets":3,"reps":"8","rest":"90s","muscle":"Hamstrings","weight_guide":"60-100kg","equipment_required":True,"demo_url":"https://www.youtube.com/results?search_query=romanian+deadlift"},
            {"name":"Copenhagen Plank", "sets":3,"reps":"30s ea","rest":"60s","muscle":"Adductors","weight_guide":"Bodyweight","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=copenhagen+plank"},
            {"name":"Single-Leg RDL",   "sets":3,"reps":"8 ea","rest":"75s","muscle":"Hamstrings/Balance","weight_guide":"20-35kg/hand","equipment_required":True,"demo_url":"https://www.youtube.com/results?search_query=single+leg+romanian+deadlift"},
        ],
        "conditioning": [
            {"name":"Interval Runs (40m)","sets":8,"reps":"40m sprint","rest":"45s","muscle":"Speed/Conditioning","weight_guide":"Bodyweight","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=40m+sprint+training"},
            {"name":"Yo-Yo Test Drills",  "sets":1,"reps":"10 min","rest":"0","muscle":"Aerobic Capacity","weight_guide":"Bodyweight","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=yo+yo+test+training"},
            {"name":"Slalom Runs",        "sets":4,"reps":"30s","rest":"45s","muscle":"Agility/Cardio","weight_guide":"Cones","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=slalom+run+drill"},
            {"name":"Bear Crawl",         "sets":3,"reps":"20m","rest":"60s","muscle":"Full Body","weight_guide":"Bodyweight","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=bear+crawl"},
            {"name":"Shuttle Runs",       "sets":6,"reps":"20m","rest":"45s","muscle":"Speed/Endurance","weight_guide":"Bodyweight","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=shuttle+run+drill"},
        ],
        "recovery": [
            {"name":"Hip Flexor Stretch",      "sets":3,"reps":"60s ea","rest":"0","muscle":"Hip Flexors","weight_guide":"Bodyweight","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=hip+flexor+stretch"},
            {"name":"Foam Roll Quads",         "sets":1,"reps":"2 min ea","rest":"0","muscle":"Quads","weight_guide":"Foam roller","equipment_required":True,"demo_url":"https://www.youtube.com/results?search_query=foam+roll+quads"},
            {"name":"Calf Stretch",            "sets":3,"reps":"60s ea","rest":"0","muscle":"Calves","weight_guide":"Bodyweight","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=calf+stretch"},
            {"name":"Hamstring Stretch",       "sets":3,"reps":"60s ea","rest":"0","muscle":"Hamstrings","weight_guide":"Bodyweight","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=hamstring+stretch"},
            {"name":"Diaphragmatic Breathing", "sets":1,"reps":"5 min","rest":"0","muscle":"Recovery","weight_guide":"None","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=diaphragmatic+breathing"},
        ],
    },
    "running": {
        "strength": [
            {"name":"Single-Leg Deadlift",  "sets":3,"reps":"8 ea","rest":"75s","muscle":"Posterior Chain","weight_guide":"20-40kg/hand","equipment_required":True,"demo_url":"https://www.youtube.com/results?search_query=single+leg+deadlift"},
            {"name":"Bulgarian Split Squat","sets":3,"reps":"10 ea","rest":"75s","muscle":"Single-Leg Power","weight_guide":"15-30kg/hand","equipment_required":True,"demo_url":"https://www.youtube.com/results?search_query=bulgarian+split+squat"},
            {"name":"Hip Thrust",           "sets":3,"reps":"12","rest":"75s","muscle":"Glutes/Drive","weight_guide":"60-100kg","equipment_required":True,"demo_url":"https://www.youtube.com/results?search_query=hip+thrust+running"},
            {"name":"Calf Raises (weighted)","sets":4,"reps":"15","rest":"45s","muscle":"Calves","weight_guide":"BW+weight","equipment_required":True,"demo_url":"https://www.youtube.com/results?search_query=weighted+calf+raise"},
            {"name":"Nordic Hamstring Curl","sets":3,"reps":"6","rest":"90s","muscle":"Hamstrings","weight_guide":"Bodyweight","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=nordic+hamstring+curl"},
            {"name":"Step-Ups",             "sets":3,"reps":"10 ea","rest":"75s","muscle":"Single-Leg Quads","weight_guide":"16-28kg/hand","equipment_required":True,"demo_url":"https://www.youtube.com/results?search_query=step+up+exercise"},
        ],
        "drills": [
            {"name":"A-Skip Drill","sets":3,"reps":"20m","rest":"45s","muscle":"Running Mechanics","weight_guide":"Bodyweight","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=a+skip+running+drill"},
            {"name":"B-Skip Drill","sets":3,"reps":"20m","rest":"45s","muscle":"Running Mechanics","weight_guide":"Bodyweight","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=b+skip+running+drill"},
            {"name":"High Knees",  "sets":3,"reps":"20m","rest":"45s","muscle":"Cadence","weight_guide":"Bodyweight","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=high+knees+running+drill"},
            {"name":"Butt Kicks",  "sets":3,"reps":"20m","rest":"45s","muscle":"Hamstrings/Cadence","weight_guide":"Bodyweight","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=butt+kicks+drill"},
            {"name":"Bounding",    "sets":3,"reps":"30m","rest":"60s","muscle":"Power/Stride Length","weight_guide":"Bodyweight","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=bounding+running+drill"},
            {"name":"Strides",     "sets":6,"reps":"100m","rest":"60s","muscle":"Speed/Form","weight_guide":"Bodyweight","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=running+strides"},
        ],
        "endurance": [
            {"name":"Tempo Run",     "sets":1,"reps":"20-30 min","rest":"0","muscle":"Aerobic Engine","weight_guide":"Own pace","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=tempo+run+training"},
            {"name":"Fartlek Run",   "sets":1,"reps":"25 min","rest":"0","muscle":"Speed Endurance","weight_guide":"Own pace","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=fartlek+run"},
            {"name":"Hill Repeats",  "sets":6,"reps":"30s hard","rest":"90s","muscle":"Power Endurance","weight_guide":"Bodyweight","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=hill+repeats+running"},
            {"name":"Easy Long Run", "sets":1,"reps":"45-60 min","rest":"0","muscle":"Base Fitness","weight_guide":"Easy pace","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=easy+long+run"},
            {"name":"800m Repeats",  "sets":4,"reps":"800m","rest":"90s","muscle":"VO2 Max","weight_guide":"Race pace","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=800m+repeat+workout"},
        ],
        "injury_prevention": [
            {"name":"Clamshells",          "sets":3,"reps":"20 ea","rest":"30s","muscle":"Hip Abductors","weight_guide":"Light band","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=clamshell+exercise"},
            {"name":"Ankle Circles",       "sets":3,"reps":"15 ea","rest":"20s","muscle":"Ankles","weight_guide":"Bodyweight","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=ankle+circles"},
            {"name":"Tibialis Raises",     "sets":3,"reps":"20","rest":"45s","muscle":"Shin Splints Prevention","weight_guide":"Bodyweight","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=tibialis+raise"},
            {"name":"IT Band Foam Roll",   "sets":1,"reps":"2 min ea","rest":"0","muscle":"IT Band","weight_guide":"Foam roller","equipment_required":True,"demo_url":"https://www.youtube.com/results?search_query=it+band+foam+roll"},
            {"name":"Foot Doming",         "sets":3,"reps":"15","rest":"30s","muscle":"Foot Arch","weight_guide":"Bodyweight","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=foot+doming+exercise"},
            {"name":"Single-Leg Balance",  "sets":3,"reps":"45s ea","rest":"30s","muscle":"Ankle Stability","weight_guide":"Bodyweight","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=single+leg+balance"},
        ],
        "recovery": [
            {"name":"Static Calf Stretch",     "sets":3,"reps":"60s ea","rest":"0","muscle":"Calves","weight_guide":"Bodyweight","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=calf+stretch"},
            {"name":"Pigeon Pose",             "sets":3,"reps":"90s ea","rest":"0","muscle":"Hip Flexors","weight_guide":"Bodyweight","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=pigeon+pose"},
            {"name":"Foam Roll Calves",        "sets":1,"reps":"2 min","rest":"0","muscle":"Calves","weight_guide":"Foam roller","equipment_required":True,"demo_url":"https://www.youtube.com/results?search_query=foam+roll+calves"},
            {"name":"Legs Up the Wall",        "sets":1,"reps":"10 min","rest":"0","muscle":"Recovery/Blood Flow","weight_guide":"Bodyweight","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=legs+up+wall+yoga"},
            {"name":"Diaphragmatic Breathing", "sets":1,"reps":"5 min","rest":"0","muscle":"Recovery","weight_guide":"None","equipment_required":False,"demo_url":"https://www.youtube.com/results?search_query=diaphragmatic+breathing"},
        ],
    },
}

# ------------------------------------------------------------------------------
# SPORT WORKOUT GENERATION
# ------------------------------------------------------------------------------
SPORT_SPLITS = {
    "cricket":  {3:["power","mobility","strength"],4:["power","strength","conditioning","mobility"],5:["power","strength","conditioning","mobility","strength"],6:["power","strength","conditioning","mobility","strength","conditioning"]},
    "football": {3:["power","strength","agility"],4:["power","strength","agility","conditioning"],5:["power","strength","agility","conditioning","strength"],6:["power","strength","agility","conditioning","strength","agility"]},
    "running":  {3:["strength","drills","endurance"],4:["strength","drills","endurance","injury_prevention"],5:["strength","drills","endurance","injury_prevention","drills"],6:["strength","drills","endurance","injury_prevention","drills","endurance"]},
}

def get_sport_exercises(sport, session_type, zone, profile):
    sport_db  = SPORT_EXERCISES.get(sport, {})
    if zone == "red":
        return sport_db.get("recovery", [])
    exercises = list(sport_db.get(session_type, []))
    inj = (profile.get("injuries") or "").lower()
    if inj and inj not in ["none","no",""]:
        exercises = [e for e in exercises
                     if "sprint" not in e["name"].lower()
                     and "jump" not in e["name"].lower()
                     and "plyometric" not in e["name"].lower()]
        if not exercises:
            exercises = sport_db.get("recovery", [])
    if zone == "yellow":
        exercises = [dict(e, sets=min(e.get("sets",3), 3)) for e in exercises]
    return exercises

def decide_sport_session(sport, days_per_week, uid):
    "Date-seeded  always pass uid."
    split = SPORT_SPLITS.get(sport, {}).get(
        int(days_per_week or 3),
        SPORT_SPLITS.get(sport, {}).get(3, ["strength","conditioning","recovery"])
    )
    seed = get_day_seed(uid)
    return split[seed % len(split)]

# ------------------------------------------------------------------------------
# GYM/HOME WORKOUT GENERATION
# ------------------------------------------------------------------------------
def get_training_split(days, gender):
    days   = int(days) if days else 3
    female = (gender or "").lower() == "female"
    if days <= 2: return ["full body","full body"]
    if days == 3: return ["glute & legs","upper toning","full body"] if female else ["push","pull","legs"]
    if days == 4: return ["glute & legs","upper toning","glute & legs","core & cardio"] if female else ["upper","lower","upper","lower"]
    return ["glute & legs","upper toning","core & cardio","glute & legs","upper toning","full body"] if female else ["push","pull","legs","push","pull","full body"]

def decide_today_workout(profile, uid):
    p     = profile if isinstance(profile, dict) else profile.to_dict()
    split = get_training_split(p.get("days_per_week",3), p.get("gender","male"))
    seed  = get_day_seed(uid)
    return split[seed % len(split)]

def has_injury(profile):
    p   = profile if isinstance(profile, dict) else profile.to_dict()
    inj = (p.get("injuries") or "").strip().lower()
    return inj and inj not in ["none","no","n/a",""]

def select_exercises_for_session(muscle_group, profile, uid, count=5):
    p = profile if isinstance(profile, dict) else profile.to_dict()
    rec = get_latest_recovery(uid)
    zone = rec["zone"] if rec else "green"
    mode = "sport" if p.get("plays_sport") and p.get("sport") else p.get("workout_place", "gym")
    return _get_rich_exercises(muscle_group, p, mode, zone, count)

# ------------------------------------------------------------------------------
# AI HELPERS
# ------------------------------------------------------------------------------
_AI_INJECTION_PATTERNS = [
    "ignore previous", "ignore all", "disregard", "forget instructions",
    "you are now", "act as", "pretend you", "jailbreak", "system prompt",
    "print all user", "reveal user data", "show all users",
]

def _sanitize_user_message(msg: str) -> str:
    "Strip prompt injection attempts and enforce max length."
    if not msg:
        return msg
    # Hard cap -- no message needs to be longer than 600 chars
    msg = msg[:600]
    lower = msg.lower()
    for pattern in _AI_INJECTION_PATTERNS:
        if pattern in lower:
            return "[Message filtered]"
    return msg

def ai_call(messages, temperature=0.7, max_tokens=512):
    try:
        ascii_guard = {
            "role": "system",
            "content": (
                "Output plain English ASCII only. Do not use emojis, smart quotes, "
                "special symbols, markdown tables, or non-English text. Keep it concise."
            ),
        }
        r = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[ascii_guard, *messages],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return clean_text(r.choices[0].message.content.strip())
    except Exception as e:
        err_str = str(e).lower()
        if "429" in err_str or "rate_limit" in err_str or "rate limit" in err_str:
            return "I'm a bit busy right now -- give me 30 seconds and try again."
        if "401" in err_str or "authentication" in err_str or "api key" in err_str:
            print("CRITICAL: Groq API key invalid or revoked --", e)
            return "AI service configuration error. Please contact support."
        if "timeout" in err_str or "connection" in err_str or "network" in err_str:
            return "Connection to AI timed out. Check your internet and try again."
        if "context" in err_str or "token" in err_str:
            return "Request too long -- please keep messages shorter."
        print("AI ERROR:", e)
        return "Something went wrong. Try again in a moment."

def time_greeting(name):
    h = datetime.now().hour
    if h < 12:   return f"Good morning, {name}"
    elif h < 18: return f"Good afternoon, {name}"
    return f"Good evening, {name}"

def ai_motivation(profile, days_missed, streak):
    p = profile if isinstance(profile, dict) else profile.to_dict()
    return ai_call([
        {"role":"system","content":"Elite motivational fitness coach. Short, punchy, personal. Max 2 sentences."},
        {"role":"user","content":f"Name:{p.get('name')}, Goal:{p.get('goal')}, Sport:{p.get('sport','none')}, Streak:{streak}, Missed:{days_missed} days."}
    ], 0.8)

def ai_set_intro(exercise_name, set_no, gender="male"):
    tone = "energetic and encouraging if gender == female else hype and powerful"
    return ai_call([
        {"role":"system","content":f"Personal trainer. Be {tone}. One short ASCII sentence only. No emoji or symbols."},
        {"role":"user","content":f"Hype me up for Set {set_no} of {exercise_name}. One line."}
    ], 0.9)

def ai_trainer_chat(profile, user_message, memory=None):
    """
    Pure conversational AI -- no JSON embedding.
    Workout planning is handled separately by the deterministic engine.
    """
    p = profile if isinstance(profile, dict) else profile.to_dict()
    sp = p.get("sport_profile") or {}
    if isinstance(sp, str):
        try: sp = json.loads(sp)
        except: sp = {}

    # Sanitize user input against prompt injection
    safe_message = _sanitize_user_message(user_message or "")

    # Limit memory to last 3 entries to save tokens
    mem = "\n".join(
        f"- {m.get('ai_summary','')}" for m in (memory or [])[-3:] if m.get('ai_summary')
    )

    # Sport context -- truncated to session names only (not full exercise list) to save tokens
    sport_ctx = ""
    if p.get("sport"):
        sport      = p.get("sport")
        session_types = list(SPORT_EXERCISES.get(sport, {}).keys())
        weekly_split  = SPORT_SPLITS.get(sport, {}).get(int(p.get("days_per_week") or 3), [])
        sport_ctx = (
            f"\nSport: {sport}, Position: {sp.get('position','')}, "
            f"Focus: {sp.get('primary_focus','')}, "
            f"Weekly split: {weekly_split}, "
            f"Available sessions: {', '.join(session_types)}"
        )

    system_prompt = (
        f"Elite AI personal trainer. Answer fitness, recovery, nutrition, and sport questions concisely.\n"
        f"User: {p.get('name')}, {p.get('age')}y, {p.get('gender')}, "
        f"{p.get('height')}cm, {p.get('weight')}kg, "
        f"Goal: {p.get('goal')}, Level: {p.get('level')}, "
        f"Place: {p.get('workout_place')}, Injuries: {p.get('injuries') or 'none'}"
        f"{sport_ctx}\n"
        f"Memory: {mem or 'None'}\n"
        "To change workout type, user can type the session name (e.g. 'strength', 'agility'). "
        "Keep responses under 120 words."
    )

    return ai_call([
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": safe_message},
    ], 0.7, max_tokens=300)

def ai_generate_todays_split(profile, exercises, muscle_group, zone, uid, sport=None, session_type=None):
    p0 = profile if isinstance(profile, dict) else profile.to_dict()
    return engine_coach_preview(p0, {
        "muscle_group": muscle_group,
        "exercises": exercises,
        "zone": zone,
        "mode": "sport" if sport else p0.get("workout_place", "gym"),
        "sport": sport,
        "session_type": session_type,
    })
    for key, item in FOOD_NUTRITION_DB.items():
        food_name = item.get("name")
        if key in text and food_name not in seen_foods:
            matches.append(item)
            seen_foods.add(food_name)
    if not matches:
        return {
            "name": "Mixed Meal",
            "category": "Estimated Meal",
            "portion": "1 plate",
            "calories": 430,
            "protein": 22,
            "carbs": 48,
            "fats": 15,
            "fiber": 6,
            "sugar": 6,
            "quality": "Good",
            "density": "Medium",
            "tags": ["lean_physique", "performance"],
        }
    if len(matches) == 1:
        return matches[0]
    total = {"name": "Mixed Plate", "category": "Mixed Meal", "portion": "Estimated combined serving", "calories": 0, "protein": 0, "carbs": 0, "fats": 0, "fiber": 0, "sugar": 0, "quality": "Good", "density": "Medium", "tags": []}
    names = []
    tags = set()
    for item in matches[:4]:
        names.append(item["name"])
        for key in ["calories", "protein", "carbs", "fats", "fiber", "sugar"]:
            total[key] += item.get(key, 0)
        tags.update(item.get("tags", []))
    total["name"] = " + ".join(names[:3])
    total["tags"] = list(tags)
    if total["calories"] > 650: total["density"] = "High"
    if total["protein"] >= 30: total["quality"] = "Great"
    return total

def _extract_json_object(text):
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        pass
    match = re.search(r"\{.*\}", text, flags=re.S)
    if match:
        try:
            return json.loads(match.group(0))
        except Exception:
            return None
    return None

def _coerce_ai_nutrition(raw, fallback_item, source, goal):
    data = raw if isinstance(raw, dict) else {}
    macros = data.get("macros") or {}
    def macro_num(*values):
        for value in values:
            if value is None or value == "":
                continue
            if isinstance(value, (int, float)):
                return int(round(value))
            match = re.search(r"-?\d+(\.\d+)?", str(value))
            if match:
                return int(round(float(match.group(0))))
        return 0
    item = {
        "name": data.get("detected_food") or data.get("food") or fallback_item.get("name"),
        "category": data.get("category") or fallback_item.get("category"),
        "portion": data.get("portion_size") or data.get("portion") or fallback_item.get("portion"),
        "calories": macro_num(macros.get("calories"), data.get("calories"), fallback_item.get("calories", 0)),
        "protein": macro_num(macros.get("protein"), data.get("protein"), fallback_item.get("protein", 0)),
        "carbs": macro_num(macros.get("carbs"), data.get("carbs"), fallback_item.get("carbs", 0)),
        "fats": macro_num(macros.get("fats"), macros.get("fat"), data.get("fats"), fallback_item.get("fats", 0)),
        "fiber": macro_num(macros.get("fiber"), data.get("fiber"), fallback_item.get("fiber", 0)),
        "sugar": macro_num(macros.get("sugar"), data.get("sugar"), fallback_item.get("sugar", 0)),
        "quality": data.get("meal_quality") or data.get("quality") or fallback_item.get("quality"),
        "density": data.get("calorie_density") or data.get("density") or fallback_item.get("density"),
        "tags": fallback_item.get("tags", []),
    }
    payload = _build_nutrition_payload(item, source=source, confidence=data.get("confidence"), goal=goal)
    if isinstance(data.get("recommendation"), dict):
        payload["recommendation"].update({k: str(v) for k, v in data[recommendation].items() if v})
    if isinstance(data.get("items"), list) and data["items"]:
        payload["items"] = data[items][:5]
    return payload

def ai_analyze_nutrition(food="", image_data=None, goal=""):
    fallback_item = _fallback_food_from_text(food or "")
    source = "vision if image_data else text"
    if image_data and not image_data.startswith("data:image/"):
        image_data = None
        source = "text"
    try:
        if image_data:
            model = os.getenv("GROQ_VISION_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct")
            prompt = (
                "You are FitCoach AI Nutrition Vision. Analyze the food image. "
                "Return ONLY valid JSON with keys: detected_food, confidence, category, portion_size, "
                "meal_quality, calorie_density, macros {calories, protein, carbs, fats, fiber, sugar}, "
                "items [{name, portion, calories}], recommendation {summary, timing, recovery}. "
                "Estimate common foods, Indian meals, fast foods, snacks, eggs, chicken, rice, oats, fruit, and protein foods. "
                "Never say you cannot analyze images. If uncertain, provide the best visual estimate."
            )
            r = groq_client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": image_data}},
                ]}],
                temperature=0.15,
            )
            raw = _extract_json_object(r.choices[0].message.content)
            return _coerce_ai_nutrition(raw, fallback_item, "vision", goal)
        raw_text = ai_call([
            {"role": "system", "content": (
                "You are FitCoach AI Nutrition. Return ONLY valid JSON with keys: detected_food, confidence, "
                "category, portion_size, meal_quality, calorie_density, macros {calories, protein, carbs, fats, fiber, sugar}, "
                "items [{name, portion, calories}], recommendation {summary, timing, recovery}. "
                "Estimate nutrition for common foods and Indian meals. Never apologize."
            )},
            {"role": "user", "content": f"Food: {food}. User goal: {goal or 'balanced fitness'}."}
        ], 0.2)
        raw = _extract_json_object(raw_text)
        return _coerce_ai_nutrition(raw, fallback_item, "text", goal)
    except Exception as e:
        print("NUTRITION AI ERROR:", e)
        return _build_nutrition_payload(fallback_item, source=source, confidence=68 if image_data else 82, goal=goal)

def ai_analyze_calories(food):
    payload = ai_analyze_nutrition(food=food)
    macros = payload["macros"]
    return (
        f"{payload['detected_food']} detected\n"
        f"Calories: {macros['calories']} kcal\n"
        f"Protein: {macros['protein']}g\n"
        f"Carbs: {macros['carbs']}g\n"
        f"Fats: {macros['fats']}g\n"
        f"Fiber: {macros['fiber']}g\n"
        f"Tip: {payload['recommendation']['summary']}"
    )

def normalize_command(text):
    t = text.strip().lower()
    mapping = {
        "start":["start","begin","let's go","lets go","go","workout"],
        "next": ["next","done set","next set","finished set","ok","...","next set done"],
        "done": ["done","complete","finished","end","finish","log","log workout"],
        "easy": ["easy","too easy","felt easy"],
        "hard": ["hard","too hard","tough","difficult","felt hard"],
    }
    for cmd, variants in mapping.items():
        if t in variants: return cmd
    # "" SESSION TYPE SWITCH " user types a sport session name """"""
    sport_sessions = ["power","strength","agility","conditioning","recovery","mobility","drills","endurance","injury_prevention"]
    if t in sport_sessions:
        return f"switch:{t}"
    return t

# ------------------------------------------------------------------------------
# ONBOARDING DEFINITIONS
# ------------------------------------------------------------------------------
GENERAL_FIELD_ORDER = ["name","dob","gender","height","weight","goal","level","workout_place","days_per_week","injuries","plays_sport"]
GENERAL_QUESTIONS = {
    "name":          {"reply":"Hey! ' What should I call you?",                        "input_type":"text"},
    "dob":           {"reply":"What's your date of birth?",                             "input_type":"dob"},
    "gender":        {"reply":"What's your gender?",                                    "input_type":"gender"},
    "height":        {"reply":"What's your height?",                                    "input_type":"height"},
    "weight":        {"reply":"What's your current weight?",                            "input_type":"weight"},
    "goal":          {"reply":"What's your primary fitness goal?",                      "input_type":"goal"},
    "level":         {"reply":"What's your fitness experience level?",                  "input_type":"level"},
    "workout_place": {"reply":"Where do you prefer to work out?",                       "input_type":"place"},
    "days_per_week": {"reply":"How many days per week can you train?",                  "input_type":"days"},
    "injuries":      {"reply":"Any injuries or pain I should know about?",              "input_type":"injuries"},
    "plays_sport":   {"reply":"Do you play any sport competitively or recreationally?", "input_type":"plays_sport"},
}

SPORT_FIELD_ORDERS = {
    "cricket":  ["sport_select","role","bowling_type","match_frequency","primary_focus","sport_injuries"],
    "football": ["sport_select","position","match_frequency","primary_focus","sport_injuries"],
    "running":  ["sport_select","distance_type","weekly_mileage","primary_focus","sport_injuries"],
}
SPORT_QUESTIONS = {
    "sport_select":    {"reply":"Which sport do you play?",              "input_type":"sport_select"},
    "role":            {"reply":"What's your role in cricket?",          "input_type":"cricket_role"},
    "bowling_type":    {"reply":"What type of bowler are you?",          "input_type":"bowling_type"},
    "match_frequency": {"reply":"How often do you play matches?",        "input_type":"match_frequency"},
    "primary_focus":   {"reply":"What's your primary training focus?",   "input_type":"primary_focus"},
    "sport_injuries":  {"reply":"Any sport-related injuries?",           "input_type":"sport_injuries"},
    "position":        {"reply":"What position do you play in football?","input_type":"football_position"},
    "distance_type":   {"reply":"What type of running do you do?",       "input_type":"distance_type"},
    "weekly_mileage":  {"reply":"What's your current weekly mileage?",   "input_type":"weekly_mileage"},
}

# ------------------------------------------------------------------------------
# AUTH ROUTES
# ------------------------------------------------------------------------------
#  Server-side reset tokens (email -> token, expires) 
# Stored in memory; survives the reset flow which is a single browser session.
_reset_tokens: dict = {}   # email -> {"token": str, "expires": datetime}

def _issue_reset_token(email: str) -> str:
    token = hashlib.sha256(os.urandom(32)).hexdigest()
    _reset_tokens[email] = {"token": token, "expires": datetime.now() + timedelta(minutes=15)}
    return token

def _consume_reset_token(email: str, token: str) -> bool:
    entry = _reset_tokens.get(email)
    if not entry:
        return False
    if datetime.now() > entry["expires"]:
        _reset_tokens.pop(email, None)
        return False
    if entry["token"] != token:
        return False
    _reset_tokens.pop(email, None)
    return True

@app.route("/api/send-otp", methods=["POST"])
@limiter.limit("20 per minute; 100 per hour")
def send_otp_route():
    data    = request.get_json() or {}
    email   = data.get("email","").strip().lower()
    purpose = data.get("purpose","verify")
    if not email: return jsonify({"error":"Email required"}),400
    if purpose in ["login","reset"]:
        if not get_auth_by_email(email): return jsonify({"error":"No account with that email"}),404
    otp = generate_otp()
    save_otp(email, otp, purpose)
    subjects = {"verify":"Verify your FitCoach account","login":"Your FitCoach login code","reset":"Reset FitCoach password"}
    sent = send_email(email, subjects.get(purpose,"FitCoach OTP"), otp_email_html(otp, purpose))
    if not sent:
        return jsonify({"error":"Could not send the OTP email right now. Please try again."}), 502
    return jsonify({"message":f"OTP sent to {email}"})

@app.route("/api/verify-otp", methods=["POST"])
@limiter.limit("10 per minute")
def verify_otp_route():
    data    = request.get_json() or {}
    email   = data.get("email","").strip().lower()
    code    = data.get("code","").strip()
    purpose = data.get("purpose","verify")
    if not verify_otp(email, code, purpose): return jsonify({"error":"Invalid or expired OTP"}),400
    if purpose == "verify":
        mark_email_verified(email)
        return jsonify({"verified":True})
    if purpose == "login":
        auth  = get_auth_by_email(email)
        if not auth: return jsonify({"error":"User not found"}),404
        user  = get_user(auth["user_id"])
        token = create_access_token(identity=auth["user_id"])
        return jsonify({"token":token,"user_id":auth["user_id"],"onboarded":bool(user and user.get("onboarded"))})
    if purpose == "reset":
        # Issue a short-lived reset token -- required to call /api/reset-password
        reset_token = _issue_reset_token(email)
        return jsonify({"verified":True, "reset_token": reset_token})
    return jsonify({"verified":True})

@app.route("/api/reset-password", methods=["POST"])
@limiter.limit("5 per minute")
def reset_password():
    data        = request.get_json() or {}
    email       = data.get("email","").strip().lower()
    new_pass    = data.get("new_password","")
    reset_token = data.get("reset_token","").strip()
    if not reset_token:
        return jsonify({"error":"Reset token required. Complete OTP verification first."}),400
    if not _consume_reset_token(email, reset_token):
        return jsonify({"error":"Invalid or expired reset token. Request a new OTP."}),400
    if len(new_pass) < 6: return jsonify({"error":"Min 6 characters"}),400
    auth = get_auth_by_email(email)
    if not auth: return jsonify({"error":"User not found"}),404
    update_password(email, generate_password_hash(new_pass))
    return jsonify({"message":"Password updated successfully"})

@app.route("/api/signup", methods=["POST"])
@limiter.limit("10 per hour")
def signup():
    data     = request.get_json() or {}
    email    = data.get("email","").strip().lower()
    password = data.get("password","")
    if not email or not password: return jsonify({"error":"Email and password required"}),400
    if len(password) < 6: return jsonify({"error":"Min 6 characters"}),400
    if get_auth_by_email(email): return jsonify({"error":"Email already registered"}),409
    user_id = str(uuid.uuid4())
    if not create_auth(user_id, email, generate_password_hash(password)):
        return jsonify({"error":"Signup failed"}),500
    token = create_access_token(identity=user_id)
    return jsonify({"token":token,"user_id":user_id,"onboarded":False}),201

@app.route("/api/login", methods=["POST"])
@limiter.limit("10 per minute; 50 per hour")
def login():
    data     = request.get_json() or {}
    email    = data.get("email","").strip().lower()
    password = data.get("password","")
    auth     = get_auth_by_email(email)
    if not auth or not check_password_hash(auth["password_hash"],password):
        return jsonify({"error":"Invalid email or password"}),401
    user  = get_user(auth["user_id"])
    token = create_access_token(identity=auth["user_id"])
    return jsonify({"token":token,"user_id":auth["user_id"],
                    "onboarded":bool(user and user.get("onboarded")),
                    "name":user.get("name") if user else None})

@app.route("/api/me", methods=["GET"])
@jwt_required()
def get_me():
    uid  = get_jwt_identity()
    user = get_user(uid)
    if not user: return jsonify({"onboarded":False})
    return jsonify({"onboarded":bool(user.get("onboarded")),"profile":dict(user)})

# ------------------------------------------------------------------------------
# RECOVERY API
# ------------------------------------------------------------------------------
def _safe_float(val, default, lo=None, hi=None):
    try:
        v = float(val)
        if lo is not None and v < lo: v = lo
        if hi is not None and v > hi: v = hi
        return v
    except (TypeError, ValueError):
        return default

def _safe_int(val, default, lo=None, hi=None):
    try:
        v = int(float(val))
        if lo is not None and v < lo: v = lo
        if hi is not None and v > hi: v = hi
        return v
    except (TypeError, ValueError):
        return default

@app.route("/api/recovery", methods=["POST"])
@jwt_required()
def log_recovery():
    uid           = get_jwt_identity()
    data          = request.get_json() or {}
    sleep_hours   = _safe_float(data.get("sleep_hours"),   7,   lo=0, hi=24)
    sleep_quality = _safe_int(data.get("sleep_quality"),   3,   lo=1, hi=5)
    fatigue       = _safe_int(data.get("fatigue"),         2,   lo=1, hi=5)
    soreness      = _safe_int(data.get("soreness"),        2,   lo=1, hi=5)
    prev_load     = _safe_int(data.get("prev_load"),       2,   lo=1, hi=5)
    score, zone   = calculate_recovery_score(sleep_hours, sleep_quality, fatigue, soreness, prev_load)
    save_recovery_log(uid, sleep_hours, sleep_quality, fatigue, soreness, prev_load, score, zone)
    zone_msgs = {
        "green":  "You are fully recovered - Go all out today.",
        "yellow": "Moderate recovery - Good session ahead, pace yourself.",
        "red":    "Low recovery detected - Today is a light/recovery session.",
    }
    return jsonify({"score":score,"zone":zone,"message":zone_msgs[zone]})

@app.route("/api/recovery/latest", methods=["GET"])
@jwt_required()
def get_recovery():
    uid = get_jwt_identity()
    rec = get_latest_recovery(uid)
    if not rec: return jsonify({"score":80,"zone":"green","message":"No recovery data yet."})
    return jsonify(dict(rec))

# ------------------------------------------------------------------------------
# SPORT ONBOARDING
# ------------------------------------------------------------------------------
@app.route("/api/sport-onboard", methods=["POST"])
@jwt_required()
def sport_onboard():
    uid     = get_jwt_identity()
    data    = request.get_json()
    sport   = (data.get("sport") or "").strip().lower()
    profile = data.get("profile", {})
    if not sport or sport not in ["cricket","football","running"]:
        return jsonify({"error":"Unknown sport"}), 400
    update_user_sport(uid, sport, profile)
    return jsonify({
        "reply": f" **{sport.capitalize()} Mode** activated!\n\nYour training will now be built around your sport.\n\nSwitch to Sport Mode and tap **Start Workout** to begin! ",
        "type": "sport_onboarding_complete",
        "sport": sport,
        "sport_profile": profile
    })

# ------------------------------------------------------------------------------
# CALORIES
# ------------------------------------------------------------------------------
@app.route("/api/calories", methods=["POST"])
@jwt_required()
def calorie_counter():
    uid = get_jwt_identity()
    user = get_user(uid) or {}
    data = request.get_json() or {}
    food = data.get("food","").strip()
    image_data = data.get("image_data") or data.get("image")
    if not food and not image_data:
        return jsonify({"error":"No food description or image"}),400
    goal = user.get("goal") or data.get("goal") or ""
    nutrition = ai_analyze_nutrition(food=food, image_data=image_data, goal=goal)
    macros = nutrition["macros"]
    analysis = (
        f"{nutrition['detected_food']} detected\n"
        f"Calories: {macros['calories']} kcal\n"
        f"Protein: {macros['protein']}g\n"
        f"Carbs: {macros['carbs']}g\n"
        f"Fats: {macros['fats']}g\n"
        f"Fiber: {macros['fiber']}g\n"
        f"Meal quality: {nutrition['meal_quality']}\n"
        f"AI tip: {nutrition['recommendation']['summary']}"
    )
    return jsonify({"analysis": analysis, "nutrition": nutrition})

# ------------------------------------------------------------------------------
# HELPER " build a workout plan deterministically and store it in session
# ------------------------------------------------------------------------------
def _build_and_store_plan(uid, profile, active_mode, zone):
    """
    Single source of truth for building today's workout.
    Always stores the result in session_state[uid]['planned_workout'].
    Returns (muscle_group, exercises, wmode, sport, session_type).
    """
    if uid not in session_state:
        session_state[uid] = {"mode":"idle","workout_mode":"gym"}
    if active_mode == "sport" and profile.get("sport"):
        profile = dict(profile)
        profile["workout_place"] = "sport"
    plan = get_weekly_plan(uid)
    if plan_needs_refresh(plan, active_mode):
        plan = generate_weekly_plan(uid, profile, _get_rich_exercises)
        save_weekly_plan(uid, plan, mode=active_mode)
    workout = engine_build_workout(uid, profile, active_mode, zone, plan)
    session_state[uid]["planned_workout"] = workout
    save_planned_workout(uid, date.today().isoformat(), workout)
    return (
        workout["muscle_group"],
        workout["exercises"],
        workout["mode"],
        workout.get("sport"),
        workout.get("session_type"),
    )

# ------------------------------------------------------------------------------
# MAIN CHAT ROUTE
# ------------------------------------------------------------------------------
def plan_needs_refresh(plan, active_mode):
    if not plan:
        return True
    for slot in plan:
        if slot.get("rest"):
            continue
        if not slot.get("mode"):
            return True
        if active_mode in ["home", "gym", "sport"] and slot.get("mode") != active_mode:
            return True
        exercises = slot.get("exercises") or []
        if exercises and not exercises[0].get("posture_config"):
            return True
    return False

def session_key_from_slot(slot):
    return (slot or {}).get("db_key") or (slot or {}).get("muscle") or (slot or {}).get("label") or ""

def rotate_plan_after_completion(uid, profile, completed_muscle, active_mode):
    plan = get_weekly_plan(uid)
    if plan_needs_refresh(plan, active_mode):
        plan = generate_weekly_plan(uid, profile, _get_rich_exercises)
        save_weekly_plan(uid, plan, mode=active_mode)
    if not plan:
        return None, None

    today_idx = date.today().weekday()
    next_idx = today_idx + 1
    completed_family = engine_session_family(completed_muscle)
    next_session = None

    if next_idx < len(plan):
        tomorrow = plan[next_idx]
        tomorrow_family = engine_session_family(session_key_from_slot(tomorrow))
        if not tomorrow.get("rest") and tomorrow_family == completed_family:
            swap_idx = None
            for idx in range(next_idx + 1, len(plan)):
                candidate = plan[idx]
                if candidate.get("rest"):
                    continue
                if engine_session_family(session_key_from_slot(candidate)) != completed_family:
                    swap_idx = idx
                    break
            if swap_idx is not None:
                plan[next_idx], plan[swap_idx] = plan[swap_idx], plan[next_idx]
            else:
                plan[next_idx] = {
                    "day": plan[next_idx].get("day"),
                    "day_index": next_idx,
                    "muscle": "recovery",
                    "label": "Recovery",
                    "db_key": "recovery",
                    "rest": True,
                    "sport_type": active_mode == "sport",
                    "mode": active_mode,
                    "exercises": [],
                }
        for idx, slot in enumerate(plan):
            slot["day_index"] = idx
        update_weekly_plan(uid, plan)
        next_session = plan[next_idx].get("label") if next_idx < len(plan) else None
    return plan, next_session

def focus_options_for(profile, active_mode, plan):
    preferred = []
    for slot in plan or []:
        session = slot.get("db_key") or slot.get("muscle")
        if session and session != "recovery" and session not in preferred:
            preferred.append(session)

    gender = (profile.get("gender") or "").lower()
    goal = (profile.get("goal") or "").lower()
    injuries_text = (profile.get("injuries") or "").lower()
    last_workout = get_last_workout(profile.get("id", "")) if profile.get("id") else None
    blocked_family = engine_session_family(last_workout.get("muscle_group")) if last_workout else None

    if "shoulder" in injuries_text or "neck" in injuries_text or "cervical" in injuries_text:
        preferred = ["lower_body", "legs", "core_cardio", "cardio", "mobility"] + preferred
    elif active_mode == "home":
        preferred = ["lower_body", "core_cardio", "glutes", "hiit", "full_body", "mobility"] + preferred
    elif active_mode == "sport":
        preferred = ["power", "conditioning", "agility", "endurance", "mobility"] + preferred
    elif gender == "female" or "lean" in goal or "glute" in goal:
        preferred = ["lower_body", "glutes", "core_cardio", "full_body", "cardio"] + preferred
    else:
        preferred = ["push", "pull", "legs", "upper_body", "core_cardio"] + preferred

    seen = set()
    options = []
    for session in preferred:
        if session in seen or session == "recovery":
            continue
        if blocked_family and engine_session_family(session) == blocked_family:
            continue
        seen.add(session)
        options.append({
            "label": SESSION_LABELS.get(session, session.replace("_", " ").title()),
            "command": f"start {session.replace('_', ' ')}",
            "session": session,
        })
        if len(options) >= 5:
            break
    options.append({"label": "Recovery", "command": "start recovery", "session": "recovery"})
    return options

def build_focus_workout(uid, profile, active_mode, zone, requested_focus):
    session = engine_normalize_session_request(requested_focus) or requested_focus or "full_body"
    mode = "sport" if active_mode == "sport" and profile.get("sport") else active_mode
    if mode not in ["home", "gym", "sport"]:
        mode = "home" if "home" in (profile.get("workout_place") or "").lower() else "gym"
    exercises = _get_rich_exercises(session, profile, mode, zone, 6)
    workout = {
        "muscle_group": SESSION_LABELS.get(session, session.replace("_", " ").title()),
        "exercises": exercises,
        "zone": zone,
        "mode": mode,
        "sport": profile.get("sport") if mode == "sport" else None,
        "session_type": session,
        "planner_slot": {"manual": True, "db_key": session, "label": SESSION_LABELS.get(session, session)},
    }
    session_state[uid]["planned_workout"] = workout
    save_planned_workout(uid, date.today().isoformat(), workout)
    return workout

@app.route("/api/chat", methods=["POST"])
@jwt_required()
def chat():
    uid          = get_jwt_identity()
    data         = request.get_json() or {}
    user_message = _sanitize_user_message((data.get("message") or "").strip())

    if uid not in session_state:
        session_state[uid] = {"mode":"idle","workout_mode":"gym"}

    # "" GENERAL ONBOARDING """"""""""""""""""""""""""""""""""""""""""
    user = get_user(uid)
    if not user or not user.get("onboarded"):
        if uid not in onboarding_state:
            onboarding_state[uid] = {"profile":{},"current_field":"name"}
            q = GENERAL_QUESTIONS["name"]
            return jsonify({"reply":q["reply"],"type":"onboarding","field":"name","input_type":q["input_type"],"gender":""})

        state         = onboarding_state[uid]
        profile_ob    = state["profile"]
        current_field = state["current_field"]

        if user_message and current_field:
            profile_ob[current_field] = user_message
            if current_field == "dob":
                try:
                    dob = datetime.strptime(user_message,"%Y-%m-%d")
                    profile_ob["age"] = (datetime.now()-dob).days // 365
                except:
                    profile_ob["age"] = 25

        if not user_message:
            q = GENERAL_QUESTIONS.get(current_field, GENERAL_QUESTIONS["name"])
            return jsonify({"reply":q["reply"],"type":"onboarding","field":current_field,
                            "input_type":q["input_type"],"gender":profile_ob.get("gender","")})

        next_field = next((f for f in GENERAL_FIELD_ORDER if f not in profile_ob), None)

        if not next_field:
            plays = profile_ob.get("plays_sport","no").lower() in ["yes","true","1"]
            up    = UserProfile(
                name=profile_ob.get("name"), age=profile_ob.get("age",25),
                gender=profile_ob.get("gender"),
                height=float(profile_ob.get("height",170)),
                weight=float(profile_ob.get("weight",70)),
                goal=profile_ob.get("goal"), level=profile_ob.get("level"),
                workout_place=profile_ob.get("workout_place"),
                injuries=profile_ob.get("injuries"),
                days_per_week=int(profile_ob.get("days_per_week",3)),
                plays_sport=plays
            )
            save_user(uid, up)
            try: log_weight(uid, float(profile_ob.get("weight",70)))
            except: pass
            del onboarding_state[uid]
            if plays:
                return jsonify({"reply":f" Welcome, {up.name}!\n\nNow let's set up your **Sport Mode**.","type":"onboarding_complete_sport","profile":up.to_dict(),"start_sport_onboard":True})
            return jsonify({"reply":f" Welcome to FitCoach, {up.name}!\n\nYour profile is set. Tap **Start Workout** to begin! '","type":"onboarding_complete","profile":up.to_dict()})

        state["current_field"] = next_field
        q = GENERAL_QUESTIONS[next_field]
        return jsonify({"reply":q["reply"],"type":"onboarding","field":next_field,
                        "input_type":q["input_type"],"gender":profile_ob.get("gender","")})

    # "" LOAD PROFILE """"""""""""""""""""""""""""""""""""""""""""""""
    profile     = user
    command     = normalize_command(user_message)
    gender      = (profile.get("gender") or "male").lower()
    active_mode = data.get("mode", session_state[uid].get("workout_mode","gym"))
    lower_message = user_message.lower()
    requested_start_focus = None
    if lower_message.startswith(("start ", "begin ", "load ", "do ")):
        requested_start_focus = engine_normalize_session_request(lower_message)
        if requested_start_focus:
            command = "start"
    if "home today" in lower_message or "from home" in lower_message or "train at home" in lower_message:
        profile = dict(profile)
        profile["workout_place"] = "home"
        active_mode = "home"
        session_state[uid]["workout_mode"] = "home"
        session_state._write(uid)
    elif "gym today" in lower_message or "at the gym" in lower_message:
        profile = dict(profile)
        profile["workout_place"] = "gym"
        active_mode = "gym"
        session_state[uid]["workout_mode"] = "gym"
        session_state._write(uid)
    elif active_mode == "sport" and profile.get("sport"):
        profile = dict(profile)
        profile["workout_place"] = "sport"


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
        session_state._write(uid)
        streak_txt = f"{streak} day streak if streak > 0 else Start your streak today!"
        greeting_reply = (
            f"Good {tod}, {name}!\n\n"
            f"Today's Focus: **{today_muscle}**\n"
            f"Recovery: **{zone.upper()}** - {zone_labels.get(zone, '')}\n"
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

    # "" WEIGHT LOG """"""""""""""""""""""""""""""""""""""""""""""""""
    if "weight" in user_message.lower() and any(c.isdigit() for c in user_message):
        nums = re.findall(r'\d+\.?\d*', user_message)
        if nums:
            w = float(nums[0])
            log_weight(uid, w); update_user_weight(uid, w)
            return jsonify({"reply":f"... Weight logged: **{w} kg** ","type":"weight_logged","weight":w})

    if any(t in lower_message for t in ["make today lighter", "lighter today", "easy today", "low recovery"]):
        plan = generate_weekly_plan(uid, profile, _get_rich_exercises)
        save_weekly_plan(uid, plan, mode=active_mode)
        workout = engine_build_workout(uid, profile, active_mode, "red", plan)
        session_state[uid]["planned_workout"] = workout
        save_planned_workout(uid, date.today().isoformat(), workout)
        return jsonify({
            "reply": engine_coach_preview(profile, workout, plan),
            "type": "daily_plan",
            "today_muscle": workout["muscle_group"],
            "exercises": workout["exercises"],
            "zone": "red",
            "workout_mode": workout["mode"],
            "weekly_plan": plan,
        })

    # "" SESSION TYPE SWITCH (e.g. user types "agility" or "strength") ""
    if command.startswith("switch:"):
        requested = command.split(":",1)[1]
        sport     = profile.get("sport") if active_mode == "sport" else None
        if sport and requested in SPORT_EXERCISES.get(sport, {}):
            session_state[uid]["session_override"] = requested
            rec  = get_latest_recovery(uid)
            zone = rec["zone"] if rec else "green"
            _, intensity = get_volume_modifier(zone)
            mg, exercises, wmode, sport_arg, stype = _build_and_store_plan(uid, profile, active_mode, zone)
            ai_preview = ai_generate_todays_split(profile, exercises, mg, zone, uid, sport_arg, stype)
            return jsonify({
                "reply":        f"... Switched to **{requested.upper()}** session!\n\n{ai_preview}",
                "type":         "daily_plan",
                "today_muscle": mg,
                "exercises":    exercises,
                "zone":         zone,
                "workout_mode": wmode,
            })
        else:
            # Not a valid session type for this sport " fall through to AI chat
            pass

    # "" LOAD OR CREATE WEEKLY PLAN """""""""""""""""""""""""""""""""""""""""""
    plan = get_weekly_plan(uid)
    if plan_needs_refresh(plan, active_mode):
        plan = generate_weekly_plan(uid, profile, _get_rich_exercises)
        save_weekly_plan(uid, plan, mode=active_mode)
 
    today_slot = get_todays_slot(plan)
 
    # "" SWAP INTENT " "skip chest, do legs" """"""""""""""""""""""""""""""""""
    is_swap, requested_muscle = detect_swap_intent(user_message)
    if is_swap and requested_muscle:
        updated_plan, displaced_label, new_day = swap_today_workout(
            uid, plan, requested_muscle, profile, _get_rich_exercises
        )
        update_weekly_plan(uid, updated_plan)
        today_slot = get_todays_slot(updated_plan)
 
        # Rebuild session plan
        exercises = today_slot.get("exercises") or select_exercises_for_session(
            today_slot.get("db_key","full body"), profile, uid)
        session_state[uid]["planned_workout"] = {
            "muscle_group": today_slot["label"],
            "exercises":    exercises,
            "zone":         "green",
            "mode":         active_mode,
            "sport":        profile.get("sport"),
            "session_type": today_slot.get("muscle"),
        }
        save_planned_workout(uid, date.today().isoformat(), session_state[uid]["planned_workout"])
 
        week_summary = get_weekly_plan_summary(updated_plan)
        return jsonify({
            "reply": (
                f"... Done! Swapped to **{today_slot['label']}** today.\n"
                f"**{displaced_label}** has been moved to **{new_day}**.\n\n"
                f"**This week:**\n{week_summary}\n\n"
                f"Ready? Tap **Start Workout** to begin! '"
            ),
            "type":          "daily_plan",
            "today_muscle":  today_slot["label"],
            "exercises":     exercises,
            "zone":          "green",
            "workout_mode":  active_mode,
            "weekly_plan":   updated_plan,
        })
 
    # "" PLAN TRIGGERS " "what's today?", "show my workout", etc. """""""""""""
    plan_triggers = [
        "plan","today's workout","what's today","show split","show my workout",
        "my workout","what workout","workout plan","today workout","plan my workout",
        # NEW chat phrases that AI used to handle but now go through deterministic engine:
        "what should i do","what's my workout","todays session","today session",
        "give me a workout","what am i doing","whats today","show weekly",
        "weekly plan","this week","week plan",
    ]
    wants_plan = any(t in user_message.lower() for t in plan_triggers)
 
    if wants_plan or (not user_message and session_state[uid]["mode"] == "idle"):
        rec          = get_latest_recovery(uid)
        zone         = rec["zone"] if rec else "green"
        _, intensity = get_volume_modifier(zone)
        streak       = workout_streak(uid)
 
        # Use today's slot from the weekly plan
        exercises = today_slot.get("exercises")
        if not exercises:
            db_key    = today_slot.get("db_key","full body")
            exercises = select_exercises_for_session(db_key, profile, uid)
 
        muscle_group = today_slot.get("label", today_slot.get("muscle", "Full Body"))
        wmode        = today_slot.get("mode") or ("sport" if today_slot.get("sport_type") else active_mode)
        sport_arg    = profile.get("sport") if wmode == "sport" else None
        stype        = today_slot.get("muscle") if wmode == "sport" else None
 
        # Store so Start Workout uses the SAME workout
        session_state[uid]["planned_workout"] = {
            "muscle_group": muscle_group,
            "exercises":    exercises,
            "zone":         zone,
            "mode":         wmode,
            "sport":        sport_arg,
            "session_type": stype,
        }
        save_planned_workout(uid, date.today().isoformat(), session_state[uid]["planned_workout"])
        session_state[uid]["mode"] = "planning"
        session_state._write(uid)
 
        workout_for_greeting = {
            "muscle_group": muscle_group,
            "exercises": exercises,
            "zone": zone,
            "mode": wmode,
            "sport": sport_arg,
            "session_type": stype,
        }
        ai_preview   = ai_generate_todays_split(profile, exercises, muscle_group, zone, uid, sport_arg, stype)
        greeting     = engine_contextual_greeting(profile, workout_for_greeting, zone)
        rec_badge    = f" Recovery: **{zone.upper()}**  {intensity}\n\n if rec else "
        week_summary = get_weekly_plan_summary(plan)
 
        return jsonify({
            "reply":        f"{greeting}\n\n{rec_badge}{ai_preview}\n\n**This week:**\n{week_summary}",
            "type":         "daily_plan",
            "today_muscle": muscle_group,
            "exercises":    exercises,
            "streak":       streak,
            "zone":         zone,
            "workout_mode": wmode,
            "weekly_plan":  plan,
        })
 

    # "" START WORKOUT " always uses the stored plan """"""""""""""""""
    if command == "start":
        rec  = get_latest_recovery(uid)
        zone = rec["zone"] if rec else "green"
        _, intensity_label = get_volume_modifier(zone)
        today = date.today().isoformat()

        plan = get_weekly_plan(uid)
        if plan_needs_refresh(plan, active_mode):
            plan = generate_weekly_plan(uid, profile, _get_rich_exercises)
            save_weekly_plan(uid, plan, mode=active_mode)
        today_slot = get_todays_slot(plan)

        if requested_start_focus:
            planned = build_focus_workout(uid, profile, active_mode, zone, requested_start_focus)
        else:
            planned = get_planned_workout(uid, today) or session_state[uid].get("planned_workout")
            if planned and planned.get("exercises") and not planned["exercises"][0].get("posture_config"):
                planned = None
            planned_is_recovery = (
                (planned or {}).get("session_type") == "recovery" or
                (planned or {}).get("muscle_group", "").lower() == "recovery"
            )
            today_is_recovery = today_slot.get("rest") or today_slot.get("db_key") == "recovery"
            if zone != "red" and (today_is_recovery or planned_is_recovery):
                options = focus_options_for(profile, active_mode, plan)
                return jsonify({
                    "reply": (
                        "Today is scheduled as recovery, but your recovery score is green.\n\n"
                        "Choose what you want to train now:"
                    ),
                    "type": "focus_picker",
                    "options": options,
                    "zone": zone,
                    "workout_mode": active_mode,
                })

        if not planned:
            _build_and_store_plan(uid, profile, active_mode, zone)
            planned = session_state[uid].get("planned_workout")

        exercises    = planned.get("exercises", []) if planned else []
        muscle_group = planned.get("muscle_group", "Full Body") if planned else "Full Body"
        wmode        = planned.get("mode", active_mode) if planned else active_mode

        if not exercises:
            planned = engine_build_workout(uid, profile, active_mode, zone)
            exercises = planned["exercises"]
            muscle_group = planned["muscle_group"]
            wmode = planned["mode"]
            save_planned_workout(uid, today, planned)

        workout_state[uid] = {
            "muscle_group": muscle_group,
            "exercises": exercises,
            "current_index": 0,
            "current_set": 1,
            "start_time": datetime.now().isoformat(),
            "completed_exercises": [],
            "zone": zone,
            "mode": wmode,
            "sport": planned.get("sport") or profile.get("sport"),
            "session_type": planned.get("session_type"),
        }
        session_state[uid]["mode"] = "workout"
        session_state._write(uid)
        session_state[uid]["workout_mode"] = wmode
        session_state[uid]["planned_workout"] = planned

        ex = exercises[0]
        intro = ai_set_intro(ex["name"], 1, gender)
        rec_msg = f"\n\nRecovery: **{zone.upper()}** — {intensity_label}" if rec else ""
        return jsonify({
            "reply": f"Today: **{muscle_group}**.{rec_msg}\n\n{intro}\n\n**{ex['name']}** — {ex.get('weight_guide', '')}",
            "type": "workout_start",
            "muscle_group": muscle_group,
            "exercises": exercises,
            "current_exercise": ex,
            "current_exercise_index": 0,
            "current_set": 1,
            "total_exercises": len(exercises),
            "zone": zone,
            "workout_mode": wmode,
            "ghost_trainer": {
                "exercise_order": [e.get("name") for e in exercises],
                "posture_configs": [e.get("posture_config", {}) for e in exercises],
                "rep_targets": [e.get("posture_config", {}).get("rep_target", 12) for e in exercises],
            },
        })
    if command == "next" and uid in workout_state:
        state = workout_state[uid]
        ex    = state["exercises"][state["current_index"]]
        state["current_set"] += 1

        if state["current_set"] > ex["sets"]:
            state["completed_exercises"].append(ex["name"])
            state["current_index"] += 1
            state["current_set"]    = 1

            if state["current_index"] >= len(state["exercises"]):
                session_state[uid]["mode"] = "feedback"
                return jsonify({"reply":"🎉 **All exercises done!**\n\nHow did that feel?","type":"workout_all_done"})

            next_ex = state["exercises"][state["current_index"]]
            intro   = ai_set_intro(next_ex["name"], 1, gender)
            return jsonify({
                "reply":                  f"➡️ Next up!\n\n{intro}\n\n**{next_ex['name']}** — {next_ex.get('weight_guide','')}",
                "type":                   "workout_next_exercise",
                "current_exercise":       next_ex,
                "current_exercise_index": state["current_index"],
                "current_set":            1,
                "total_exercises":        len(state["exercises"]),
            })

        intro = ai_set_intro(ex["name"], state["current_set"], gender)
        return jsonify({
            "reply":                  f"Set {state['current_set']}/{ex['sets']}\n\n{intro}\n\n**{ex['name']}**  {ex['weight_guide']}",
            "type":                   "workout_next_set",
            "current_exercise":       ex,
            "current_exercise_index": state["current_index"],
            "current_set":            state["current_set"],
            "total_exercises":        len(state["exercises"]),
        })

    # "" FEEDBACK """"""""""""""""""""""""""""""""""""""""""""""""""""
    if command in ["easy","hard"] and session_state[uid].get("mode") == "feedback":
        if uid in workout_state:
            mg = workout_state[uid]["muscle_group"]
            save_ai_memory(uid, mg, command, "", f"{mg} felt {command}")
            msg = "🔥 Beast mode! I'll push harder next session." if command == "easy" else "💪 Smart recovery choice. Rest is growth."
            return jsonify({"reply":f"{msg}\n\nTap **Log Workout** to save.","type":"feedback_received"})

    # "" DONE """"""""""""""""""""""""""""""""""""""""""""""""""""""""
    if command == "done":
        if uid in workout_state:
            state    = workout_state[uid]
            start    = datetime.fromisoformat(state["start_time"])
            duration = int((datetime.now()-start).total_seconds()/60)
            log_workout(uid,"Day",state["muscle_group"],True,
                        ", ".join(state.get("completed_exercises",[])),
                        duration, state.get("mode","gym"), state.get("sport"))
            updated_plan, next_session = rotate_plan_after_completion(uid, profile, state["muscle_group"], state.get("mode","gym"))
            badges    = get_badges(uid)
            total     = get_total_workouts(uid)
            streak    = workout_streak(uid)
            new_badge = badges[-1] if badges else None
            del workout_state[uid]
            session_state[uid]["mode"] = "post_workout"
            badge_msg = f"\n\n Badge: {new_badge['badge_icon']} **{new_badge['badge_name']}**!" if new_badge and total<=1 else ""
            next_msg = f"\nNext session: **{next_session}**." if next_session else ""
            return jsonify({
                "reply":         f"Ã¢Å“â€¦ **Workout logged!** {duration} mins\nStreak: {streak} days{badge_msg}{next_msg}\n\nRest, hydrate, recover!",
                "type":          "workout_logged",
                "duration":      duration,
                "streak":        streak,
                "total_workouts":total,
                "new_badge":     new_badge,
                "next_session":  next_session,
                "weekly_plan":   updated_plan,
            })

    # "" AI FALLBACK """"""""""""""""""""""""""""""""""""""""""""""""""""""""""
    # If user is asking about their workout in a conversational way,
    # route through the deterministic engine instead of plain AI.
    workout_chat_triggers = [
        "what workout", "today's workout", "what should i do", "what's my workout",
        "give me a workout", "todays session", "what am i doing today",
        "my plan", "plan for today",
    ]
    if any(t in user_message.lower() for t in workout_chat_triggers):
        # Re-use the plan we already built at the top of this request
        exercises    = today_slot.get("exercises") or \
                       select_exercises_for_session(today_slot.get("db_key","full body"), profile, uid)
        muscle_group = today_slot.get("label", "Full Body")
        rec          = get_latest_recovery(uid)
        zone         = rec["zone"] if rec else "green"
        wmode        = "sport" if today_slot.get("sport_type") else "gym"
        sport_arg    = profile.get("sport") if wmode == "sport" else None
        stype        = today_slot.get("muscle") if wmode == "sport" else None
 
        # Store it so Start Workout is consistent
        session_state[uid]["planned_workout"] = {
            "muscle_group": muscle_group,
            "exercises":    exercises,
            "zone":         zone,
            "mode":         wmode,
            "sport":        sport_arg,
            "session_type": stype,
        }
 
        ai_preview = ai_generate_todays_split(profile, exercises, muscle_group, zone, uid, sport_arg, stype)
        return jsonify({
            "reply":        ai_preview,
            "type":         "daily_plan",
            "today_muscle": muscle_group,
            "exercises":    exercises,
            "zone":         zone,
            "workout_mode": wmode,
            "weekly_plan":  plan,
        })
 
    memory = get_recent_ai_memory(uid)
    reply  = ai_trainer_chat(profile, user_message, memory)
    return jsonify({"reply": reply, "type": "chat"})
# ------------------------------------------------------------------------------
# PROGRESS + PROFILE
# ------------------------------------------------------------------------------
@app.route("/api/progress", methods=["GET"])
@jwt_required()
def progress():
    uid  = get_jwt_identity()
    user = get_user(uid)
    if not user: return jsonify({"error":"Not found"}),404
    weight_data = get_weight_progress(uid)
    weekly_data = get_weekly_workout_counts(uid)
    muscle_dist = get_muscle_group_distribution(uid)
    heatmap     = get_workout_heatmap(uid)
    badges      = get_badges(uid)
    streak      = workout_streak(uid)
    total       = get_total_workouts(uid)
    weight_lost = None
    if len(weight_data) >= 2:
        weight_lost = round(weight_data[0]["weight"] - weight_data[-1]["weight"], 1)
    return jsonify({
        "total_weight_lost":weight_lost,"total_workouts":total,"current_streak":streak,
        "badges":badges,
        "weight":{"labels":[w["date"] for w in weight_data],"values":[w["weight"] for w in weight_data]},
        "weekly_workouts":{"labels":[w["week"] for w in weekly_data],"values":[w["count"] for w in weekly_data]},
        "muscle_distribution":muscle_dist,"heatmap":heatmap,
    })

@app.route("/api/profile", methods=["GET"])
@jwt_required()
def get_profile():
    uid  = get_jwt_identity()
    user = get_user(uid)
    if not user: return jsonify({"error":"Not found"}),404
    return jsonify(dict(user))

@app.route("/api/profile", methods=["PUT"])
@jwt_required()
def update_profile():
    uid  = get_jwt_identity()
    data = request.get_json()
    user = get_user(uid)
    if not user: return jsonify({"error":"Not found"}),404
    up = UserProfile(
        name=data.get("name",user["name"]),
        age=data.get("age",user["age"]),
        gender=data.get("gender",user["gender"]),
        height=data.get("height",user["height"]),
        weight=data.get("weight",user["weight"]),
        goal=data.get("goal",user["goal"]),
        level=data.get("level",user["level"]),
        workout_place=data.get("workout_place",user["workout_place"]),
        injuries=data.get("injuries",user["injuries"]),
        days_per_week=data.get("days_per_week",user["days_per_week"]),
        plays_sport=user.get("plays_sport",False),
        sport=user.get("sport"),
        sport_profile=user.get("sport_profile"),
    )
    save_user(uid, up)
    if data.get("weight"): log_weight(uid, float(data["weight"]))
    return jsonify({"message":"Profile updated ..."})

@app.route("/")
def index():
    return render_template("index.html", initial_tab="home")

@app.route("/trainer")
@app.route("/ghost-trainer")
def trainer_page():
    return render_template("index.html", initial_tab="trainer")

@app.route("/health")
def health():
    return jsonify({"status":"ok","version":"5.1"})

@app.route("/api/weekly-plan", methods=["GET"])
@jwt_required()
def get_weekly_plan_route():
    "Returns (or generates) this week's plan for the frontend to display."
    uid     = get_jwt_identity()
    profile = get_user(uid)
    if not profile:
        return jsonify({"error": "Not found"}), 404
 
    plan = get_weekly_plan(uid)
    active_mode = "sport" if profile.get("plays_sport") and profile.get("sport") else profile.get("workout_place", "gym")
    if plan_needs_refresh(plan, active_mode):
        plan = generate_weekly_plan(uid, profile, _get_rich_exercises)
        save_weekly_plan(uid, plan, mode=active_mode)
 
    today_slot   = get_todays_slot(plan)
    week_summary = get_weekly_plan_summary(plan)
 
    return jsonify({
        "weekly_plan":  plan,
        "today":        today_slot,
        "summary":      week_summary,
    })
 
 
@app.route("/api/weekly-plan/swap", methods=["POST"])
@jwt_required()
def swap_workout_route():
    """
    POST body: { "requested_muscle": "legs" }
    Swaps today's workout with the requested muscle.
    """
    uid     = get_jwt_identity()
    profile = get_user(uid)
    if not profile:
        return jsonify({"error": "Not found"}), 404
 
    data             = request.get_json()
    requested_muscle = data.get("requested_muscle", "").strip().lower()
    if not requested_muscle:
        return jsonify({"error": "requested_muscle required"}), 400
 
    plan = get_weekly_plan(uid)
    active_mode = "sport" if profile.get("plays_sport") and profile.get("sport") else profile.get("workout_place", "gym")
    if plan_needs_refresh(plan, active_mode):
        plan = generate_weekly_plan(uid, profile, _get_rich_exercises)
 
    updated_plan, displaced_label, new_day = swap_today_workout(
        uid, plan, requested_muscle, profile, _get_rich_exercises
    )
    update_weekly_plan(uid, updated_plan)

    today_slot = get_todays_slot(updated_plan)
    exercises  = today_slot.get("exercises") or \
                 select_exercises_for_session(today_slot.get("db_key","full body"), profile, uid)
 
    # Update session so Start Workout is consistent
    if uid not in session_state:
        session_state[uid] = {"mode":"idle","workout_mode":"gym"}
    session_state[uid]["planned_workout"] = {
        "muscle_group": today_slot["label"],
        "exercises":    exercises,
        "zone":         "green",
        "mode":         "gym",
        "sport":        profile.get("sport"),
        "session_type": today_slot.get("muscle"),
    }
    save_planned_workout(uid, date.today().isoformat(), session_state[uid]["planned_workout"])
 
    week_summary = get_weekly_plan_summary(updated_plan)
    return jsonify({
        "weekly_plan":   updated_plan,
        "today":         today_slot,
        "exercises":     exercises,
        "displaced":     displaced_label,
        "moved_to":      new_day,
        "summary":       week_summary,
        "message":       f"... Swapped to {today_slot['label']}. {displaced_label} moved to {new_day}.",
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", debug=True, use_reloader=False, port=5000)

