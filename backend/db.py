# db.py — FitCoach AI Database Layer v3.2 (+ weekly plans)

import sqlite3
from datetime import datetime, timedelta
import os, json

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# DB location: explicit DB_PATH wins; on Vercel the app dir is read-only so use /tmp;
# otherwise store next to the code for local/dev and traditional servers.
DB_NAME = os.environ.get("DB_PATH") or (
    "/tmp/users.db" if os.environ.get("VERCEL") else os.path.join(BASE_DIR, "users.db")
)

def get_connection():
    conn = sqlite3.connect(DB_NAME, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    # WAL mode: allows concurrent reads during writes — essential for multi-request servers
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=-8000")   # 8 MB page cache
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def init_db():
    conn = get_connection()
    c = conn.cursor()

    c.execute("""CREATE TABLE IF NOT EXISTS auth (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT UNIQUE NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        email_verified INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS otp_codes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT NOT NULL, code TEXT NOT NULL,
        purpose TEXT NOT NULL, expires_at TIMESTAMP NOT NULL,
        used INTEGER DEFAULT 0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        name TEXT, age INTEGER, gender TEXT,
        height REAL, weight REAL, goal TEXT,
        level TEXT, workout_place TEXT, injuries TEXT,
        days_per_week INTEGER, onboarded INTEGER DEFAULT 0,
        plays_sport INTEGER DEFAULT 0,
        sport TEXT,
        sport_profile TEXT
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS recovery_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        sleep_hours REAL,
        sleep_quality INTEGER,
        fatigue INTEGER,
        soreness INTEGER,
        prev_load INTEGER,
        recovery_score INTEGER,
        zone TEXT,
        date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS workouts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT, workout_day TEXT, muscle_group TEXT,
        exercises TEXT, duration_minutes INTEGER DEFAULT 0,
        completed INTEGER DEFAULT 0,
        workout_mode TEXT DEFAULT 'gym',
        sport TEXT,
        date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS weight_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT, weight REAL, date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS ai_memory (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT, date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        context TEXT, difficulty TEXT, notes TEXT, ai_summary TEXT
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS personal_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT, exercise TEXT, weight_kg REAL,
        reps INTEGER, date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS badges (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT, badge_name TEXT, badge_icon TEXT,
        earned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    # ── NEW: weekly plans ──────────────────────────────────────────────────────
    c.execute("""CREATE TABLE IF NOT EXISTS weekly_plans (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        week_start TEXT NOT NULL,
        plan_json TEXT NOT NULL,
        mode TEXT DEFAULT 'gym',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(user_id, week_start)
    )""")

    # Migrations for existing DBs
    for col, definition in [
        ("email_verified", "INTEGER DEFAULT 0"),
        ("plays_sport", "INTEGER DEFAULT 0"),
        ("sport", "TEXT"),
        ("sport_profile", "TEXT"),
    ]:
        try:
            c.execute(f"ALTER TABLE users ADD COLUMN {col} {definition}")
        except Exception:
            pass

    for col, definition in [
        ("workout_mode", "TEXT DEFAULT 'gym'"),
        ("sport", "TEXT"),
    ]:
        try:
            c.execute(f"ALTER TABLE workouts ADD COLUMN {col} {definition}")
        except Exception:
            pass

    c.execute("""CREATE TABLE IF NOT EXISTS planned_workouts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    date TEXT NOT NULL,
    workout_json TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, date)
)""")

    # Persistent session state — survives server restarts
    c.execute("""CREATE TABLE IF NOT EXISTS user_sessions (
        user_id TEXT PRIMARY KEY,
        session_json TEXT NOT NULL,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    # Performance indexes
    c.execute("CREATE INDEX IF NOT EXISTS idx_workouts_user_date ON workouts(user_id, date)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_recovery_user_date ON recovery_logs(user_id, date)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_otp_email_purpose ON otp_codes(email, purpose)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_weekly_plans_user ON weekly_plans(user_id, week_start)")

    conn.commit()
    conn.close()

# ─── SESSION STATE (persistent across restarts) ───────────────────────────────
def save_session_state(user_id: str, state: dict):
    conn = get_connection()
    c = conn.cursor()
    # Don't persist transient runtime objects — only serialisable fields
    safe = {k: v for k, v in state.items() if isinstance(v, (str, int, float, bool, type(None), list, dict))}
    c.execute("""INSERT INTO user_sessions (user_id, session_json, updated_at)
                 VALUES (?, ?, datetime('now'))
                 ON CONFLICT(user_id) DO UPDATE SET session_json=excluded.session_json, updated_at=excluded.updated_at""",
              (user_id, json.dumps(safe)))
    conn.commit()
    conn.close()

def load_session_state(user_id: str) -> dict:
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT session_json FROM user_sessions WHERE user_id=?", (user_id,))
    row = c.fetchone()
    conn.close()
    if row:
        try:
            return json.loads(row[0])
        except Exception:
            pass
    return {}

# ─── OTP ─────────────────────────────────────────────────────────────────────
def save_otp(email, code, purpose):
    conn = get_connection()
    c = conn.cursor()
    expires = (datetime.now() + timedelta(minutes=10)).isoformat()
    c.execute("UPDATE otp_codes SET used=1 WHERE email=? AND purpose=? AND used=0", (email, purpose))
    c.execute("INSERT INTO otp_codes (email, code, purpose, expires_at) VALUES (?,?,?,?)",
              (email, code, purpose, expires))
    conn.commit()
    conn.close()

def verify_otp(email, code, purpose):
    conn = get_connection()
    c = conn.cursor()
    c.execute("""SELECT id FROM otp_codes WHERE email=? AND code=? AND purpose=?
        AND used=0 AND expires_at > datetime('now') ORDER BY id DESC LIMIT 1""",
        (email, code, purpose))
    row = c.fetchone()
    if row:
        c.execute("UPDATE otp_codes SET used=1 WHERE id=?", (row["id"],))
        conn.commit()
    conn.close()
    return bool(row)

def mark_email_verified(email):
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE auth SET email_verified=1 WHERE email=?", (email,))
    conn.commit()
    conn.close()

# ─── AUTH ────────────────────────────────────────────────────────────────────
def create_auth(user_id, email, password_hash):
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute("INSERT INTO auth (user_id, email, password_hash) VALUES (?,?,?)",
                  (user_id, email, password_hash))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def get_auth_by_email(email):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM auth WHERE email=?", (email,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def get_auth_by_user_id(user_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM auth WHERE user_id=?", (user_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def update_password(email, new_hash):
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE auth SET password_hash=? WHERE email=?", (new_hash, email))
    conn.commit()
    conn.close()

# ─── USER ─────────────────────────────────────────────────────────────────────
def get_user(user_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE id=?", (user_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def save_user(user_id, profile):
    conn = get_connection()
    c = conn.cursor()
    if isinstance(profile, dict):
        p = profile
    else:
        p = profile.to_dict()
    sport_profile = p.get("sport_profile")
    if isinstance(sport_profile, dict):
        sport_profile = json.dumps(sport_profile)
    c.execute("""INSERT OR REPLACE INTO users
        (id,name,age,gender,height,weight,goal,level,workout_place,injuries,
         days_per_week,onboarded,plays_sport,sport,sport_profile)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,1,?,?,?)""",
        (user_id, p.get("name"), p.get("age"), p.get("gender"),
         p.get("height"), p.get("weight"), p.get("goal"), p.get("level"),
         p.get("workout_place"), p.get("injuries"), p.get("days_per_week"),
         int(p.get("plays_sport") or 0),
         p.get("sport"), sport_profile))
    conn.commit()
    conn.close()

def update_user_sport(user_id, sport, sport_profile):
    conn = get_connection()
    c = conn.cursor()
    sp = json.dumps(sport_profile) if isinstance(sport_profile, dict) else sport_profile
    c.execute("UPDATE users SET plays_sport=1, sport=?, sport_profile=? WHERE id=?",
              (sport, sp, user_id))
    conn.commit()
    conn.close()

def update_user_weight(user_id, new_weight):
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE users SET weight=? WHERE id=?", (new_weight, user_id))
    conn.commit()
    conn.close()

# ─── RECOVERY ─────────────────────────────────────────────────────────────────
def save_recovery_log(user_id, sleep_hours, sleep_quality, fatigue, soreness, prev_load, score, zone):
    conn = get_connection()
    c = conn.cursor()
    c.execute("""INSERT INTO recovery_logs
        (user_id,sleep_hours,sleep_quality,fatigue,soreness,prev_load,recovery_score,zone)
        VALUES (?,?,?,?,?,?,?,?)""",
        (user_id, sleep_hours, sleep_quality, fatigue, soreness, prev_load, score, zone))
    conn.commit()
    conn.close()

def get_latest_recovery(user_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM recovery_logs WHERE user_id=? ORDER BY date DESC LIMIT 1", (user_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

# ─── WORKOUTS ─────────────────────────────────────────────────────────────────
def log_workout(user_id, workout_day, muscle_group, completed=True, exercises="", duration=0, mode="gym", sport=None):
    conn = get_connection()
    c = conn.cursor()
    c.execute("""INSERT INTO workouts
        (user_id,workout_day,muscle_group,exercises,duration_minutes,completed,workout_mode,sport)
        VALUES (?,?,?,?,?,?,?,?)""",
        (user_id, workout_day, muscle_group, exercises, duration, int(completed), mode, sport))
    conn.commit()
    conn.close()
    check_and_award_badges(user_id)

def get_last_workout(user_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT muscle_group, date FROM workouts WHERE user_id=? ORDER BY date DESC LIMIT 1", (user_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def days_since_last_workout(user_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT date FROM workouts WHERE user_id=? AND completed=1 ORDER BY date DESC LIMIT 1", (user_id,))
    row = c.fetchone()
    conn.close()
    if not row:
        return None
    return (datetime.now() - datetime.fromisoformat(row["date"])).days

def workout_streak(user_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT date FROM workouts WHERE user_id=? AND completed=1 ORDER BY date DESC", (user_id,))
    rows = c.fetchall()
    conn.close()
    if not rows: return 0
    streak = 1
    prev = datetime.fromisoformat(rows[0]["date"]).date()
    for row in rows[1:]:
        curr = datetime.fromisoformat(row["date"]).date()
        if (prev - curr).days == 1:
            streak += 1
            prev = curr
        else:
            break
    return streak

def get_total_workouts(user_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) as cnt FROM workouts WHERE user_id=? AND completed=1", (user_id,))
    row = c.fetchone()
    conn.close()
    return row["cnt"] if row else 0

# ─── WEIGHT ───────────────────────────────────────────────────────────────────
def log_weight(user_id, weight):
    conn = get_connection()
    c = conn.cursor()
    c.execute("INSERT INTO weight_logs (user_id, weight) VALUES (?,?)", (user_id, weight))
    conn.commit()
    conn.close()

def get_weight_progress(user_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT date, weight FROM weight_logs WHERE user_id=? ORDER BY date ASC", (user_id,))
    rows = c.fetchall()
    conn.close()
    return [{"date": r["date"][:10], "weight": r["weight"]} for r in rows]

# ─── AI MEMORY ────────────────────────────────────────────────────────────────
def save_ai_memory(user_id, context, difficulty, notes, ai_summary):
    conn = get_connection()
    c = conn.cursor()
    c.execute("INSERT INTO ai_memory (user_id,context,difficulty,notes,ai_summary) VALUES (?,?,?,?,?)",
              (user_id, context, difficulty, notes, ai_summary))
    conn.commit()
    conn.close()

def get_recent_ai_memory(user_id, limit=5):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT context,difficulty,notes,ai_summary FROM ai_memory WHERE user_id=? ORDER BY date DESC LIMIT ?",
              (user_id, limit))
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]

# ─── BADGES ───────────────────────────────────────────────────────────────────
BADGE_RULES = [
    (1,"First Sweat","🥇"),(7,"Week Warrior","🔥"),
    (30,"Monthly Beast","💪"),(50,"Half Century","⚡"),(100,"Century Club","👑"),
]

def check_and_award_badges(user_id):
    total = get_total_workouts(user_id)
    conn = get_connection()
    c = conn.cursor()
    for count, name, icon in BADGE_RULES:
        if total >= count:
            c.execute("SELECT id FROM badges WHERE user_id=? AND badge_name=?", (user_id, name))
            if not c.fetchone():
                c.execute("INSERT INTO badges (user_id,badge_name,badge_icon) VALUES (?,?,?)",
                          (user_id, name, icon))
    conn.commit()
    conn.close()

def get_badges(user_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT badge_name,badge_icon,earned_at FROM badges WHERE user_id=? ORDER BY earned_at", (user_id,))
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]

# ─── ANALYTICS ────────────────────────────────────────────────────────────────
def get_workout_heatmap(user_id, days=90):
    conn = get_connection()
    c = conn.cursor()
    c.execute("""SELECT date(date) as day, COUNT(*) as count FROM workouts
        WHERE user_id=? AND completed=1 AND date >= date('now', ?) GROUP BY day""",
        (user_id, f'-{days} days'))
    rows = c.fetchall()
    conn.close()
    return {r["day"]: r["count"] for r in rows}

def get_muscle_group_distribution(user_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT muscle_group, COUNT(*) as count FROM workouts WHERE user_id=? AND completed=1 GROUP BY muscle_group",
              (user_id,))
    rows = c.fetchall()
    conn.close()
    return [{"muscle": r["muscle_group"], "count": r["count"]} for r in rows]

def get_weekly_workout_counts(user_id, weeks=8):
    conn = get_connection()
    c = conn.cursor()
    results = []
    for i in range(weeks-1, -1, -1):
        c.execute("""SELECT COUNT(*) as cnt FROM workouts WHERE user_id=? AND completed=1
            AND date >= date('now', ?) AND date < date('now', ?)""",
            (user_id, f'-{(i+1)*7} days', f'-{i*7} days'))
        row = c.fetchone()
        week_label = (datetime.now() - timedelta(weeks=i)).strftime("W%U")
        results.append({"week": week_label, "count": row["cnt"]})
    conn.close()
    return results

# ─── WEEKLY PLANS ─────────────────────────────────────────────────────────────
def get_week_start(dt=None):
    """Returns Monday of the current (or given) week as YYYY-MM-DD string."""
    d = (dt or datetime.now()).date()
    monday = d - timedelta(days=d.weekday())
    return monday.isoformat()

def save_weekly_plan(user_id, plan_list, mode="gym"):
    """
    plan_list: list of 7 dicts:
      { "day": "Mon", "day_index": 0, "muscle": "chest",
        "label": "Chest & Triceps", "exercises": [...], "rest": False }
    """
    conn = get_connection()
    c = conn.cursor()
    week_start = get_week_start()
    c.execute("""INSERT OR REPLACE INTO weekly_plans (user_id, week_start, plan_json, mode)
                 VALUES (?, ?, ?, ?)""",
              (user_id, week_start, json.dumps(plan_list), mode))
    conn.commit()
    conn.close()

def get_weekly_plan(user_id):
    """
    Returns this week's plan list, or None if not generated yet.
    """
    conn = get_connection()
    c = conn.cursor()
    week_start = get_week_start()
    c.execute("SELECT plan_json FROM weekly_plans WHERE user_id=? AND week_start=?",
              (user_id, week_start))
    row = c.fetchone()
    conn.close()
    if row:
        return json.loads(row["plan_json"])
    return None

def update_weekly_plan(user_id, plan_list):
    """Overwrite the current week's plan (used for swap/reschedule)."""
    conn = get_connection()
    c = conn.cursor()
    week_start = get_week_start()
    c.execute("UPDATE weekly_plans SET plan_json=? WHERE user_id=? AND week_start=?",
              (json.dumps(plan_list), user_id, week_start))
    conn.commit()
    conn.close()

def get_prev_week_muscles(user_id):
    """Returns set of muscles hit last week (for avoiding repeats in new plan)."""
    conn = get_connection()
    c = conn.cursor()
    prev_monday = get_week_start(datetime.now() - timedelta(weeks=1))
    c.execute("SELECT plan_json FROM weekly_plans WHERE user_id=? AND week_start=?",
              (user_id, prev_monday))
    row = c.fetchone()
    conn.close()
    if not row:
        return set()
    plan = json.loads(row["plan_json"])
    return {d["muscle"] for d in plan if not d.get("rest")}

def update_password(email, new_hash):
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE auth SET password_hash=? WHERE email=?", (new_hash, email))
    conn.commit()
    conn.close()

def save_recovery_log(user_id, sleep_hours, sleep_quality, fatigue, soreness, prev_load, score, zone):
    conn = get_connection()
    c = conn.cursor()
    c.execute("""INSERT INTO recovery_logs
        (user_id,sleep_hours,sleep_quality,fatigue,soreness,prev_load,recovery_score,zone)
        VALUES (?,?,?,?,?,?,?,?)""",
        (user_id, sleep_hours, sleep_quality, fatigue, soreness, prev_load, score, zone))
    conn.commit()
    conn.close()

def save_planned_workout(user_id, date, workout):
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        INSERT OR REPLACE INTO planned_workouts (user_id, date, workout_json)
        VALUES (?, ?, ?)
    """, (user_id, date, json.dumps(workout)))
    conn.commit()
    conn.close()


def get_planned_workout(user_id, date):
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        SELECT workout_json FROM planned_workouts
        WHERE user_id=? AND date=?
    """, (user_id, date))
    row = c.fetchone()
    conn.close()
    return json.loads(row["workout_json"]) if row else None