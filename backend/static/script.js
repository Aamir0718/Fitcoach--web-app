// ================================================
// FITCOACH AI — script.js v4.0
// Sport Mode + Recovery Intelligence
// ================================================
const API = "";
let authToken    = localStorage.getItem("fc_token") || null;
let currentUser  = null;
let workoutMode  = localStorage.getItem("fc_workout_mode") || "gym";
let voiceRec     = null;
let isListening  = false;
let restInterval = null;
let chartInst    = {};
let workoutActive  = false;
let feedbackMode   = false;
let onboardingField     = null;
let onboardingInputType = null;
let onboardingGender    = "male";
let sportObField        = null;
let sportObInputType    = null;
let sportObSport        = null;
let recoveryInputs      = {};
let foodPhotoBase64 = null;
let homeCountRaf = {};

const ATHLETE_THEMES = {
  galaxy: { label: "Galaxy Purple" },
  carbon: { label: "Carbon Black" },
  cyan: { label: "Neon Cyan" },
  gold: { label: "Elite Gold" },
  ice: { label: "Ice White" },
};
const AUTO_THEME_BY_TAB = {
  home: "galaxy",
  chat: "galaxy",
  trainer: "carbon",
  recovery: "ice",
  progress: "gold",
  calories: "cyan",
  profile: "carbon",
  visualos: "galaxy",
};

function applyAthleteTheme(theme, options = {}) {
  const nextTheme = ATHLETE_THEMES[theme] ? theme : "galaxy";
  document.documentElement.setAttribute("data-theme", nextTheme);
  document.documentElement.classList.add("theme-is-switching");
  window.clearTimeout(applyAthleteTheme._timer);
  applyAthleteTheme._timer = window.setTimeout(() => {
    document.documentElement.classList.remove("theme-is-switching");
  }, 520);
  if (!options.previewOnly) {
    localStorage.setItem("fc_athlete_theme", nextTheme);
  }
  updateThemeSwitcher(nextTheme);
}

function updateThemeSwitcher(activeTheme) {
  document.querySelectorAll("[data-theme-option]").forEach((chip) => {
    chip.classList.toggle("active", chip.dataset.themeOption === activeTheme);
  });
  const autoEnabled = localStorage.getItem("fc_theme_auto") === "1";
  document.documentElement.toggleAttribute("data-theme-auto", autoEnabled);
  const autoBtn = document.getElementById("theme-auto-btn");
  if (autoBtn) {
    autoBtn.classList.toggle("active", autoEnabled);
    autoBtn.setAttribute("aria-pressed", autoEnabled ? "true" : "false");
  }
}

function setAthleteTheme(theme) {
  localStorage.setItem("fc_theme_auto", "0");
  applyAthleteTheme(theme);
  showToast(`Visual OS: ${ATHLETE_THEMES[theme]?.label || "Galaxy Purple"}`);
}

function toggleAutoTheme() {
  const enabled = localStorage.getItem("fc_theme_auto") === "1";
  localStorage.setItem("fc_theme_auto", enabled ? "0" : "1");
  if (!enabled) {
    const activeTab = document.querySelector(".tab-content.active")?.id?.replace("tab-", "") || "home";
    applyAthleteTheme(AUTO_THEME_BY_TAB[activeTab] || "galaxy", { previewOnly: true });
    showToast("Auto AI theme mode enabled");
  } else {
    applyAthleteTheme(localStorage.getItem("fc_athlete_theme") || "galaxy");
    showToast("Auto AI theme mode disabled");
  }
}

function initThemeEngine() {
  const savedTheme = localStorage.getItem("fc_athlete_theme") || document.documentElement.dataset.theme || "galaxy";
  applyAthleteTheme(savedTheme);
  document.querySelectorAll("[data-theme-option]").forEach((chip) => {
    chip.addEventListener("mouseenter", () => {
      if (localStorage.getItem("fc_theme_auto") === "1") return;
      applyAthleteTheme(chip.dataset.themeOption, { previewOnly: true });
    });
    chip.addEventListener("mouseleave", () => {
      if (localStorage.getItem("fc_theme_auto") === "1") return;
      applyAthleteTheme(localStorage.getItem("fc_athlete_theme") || savedTheme, { previewOnly: true });
    });
  });
}

// ── HOME SCREEN ───────────────────────────────────────────────────────
 
const HOME_QUOTES = [
  { text: "The body achieves what the mind believes.", author: "FitCoach AI" },
  { text: "Hard work beats talent when talent doesn't work hard.", author: "Tim Notke" },
  { text: "Don't count the days. Make the days count.", author: "Muhammad Ali" },
  { text: "I've failed over and over and over again. That is why I succeed.", author: "Michael Jordan" },
  { text: "The most important thing is to try and inspire people.", author: "Kobe Bryant" },
  { text: "I am not a perfectionist, but I like to feel that things are done well.", author: "Cristiano Ronaldo" },
  { text: "The last three or four reps is what makes the muscle grow.", author: "Arnold Schwarzenegger" },
  { text: "Champions train differently.", author: "FitCoach AI" },
  { text: "Discipline creates freedom.", author: "FitCoach AI" },
  { text: "Pressure creates diamonds.", author: "FitCoach AI" },
];
 
function timeGreeting() {
  const h = new Date().getHours();
  if (h < 12) return "Good morning";
  if (h < 17) return "Good afternoon";
  return "Good evening";
}
 
function getTodayCTAMessage(profile, recoveryZone) {
  const goal = profile?.goal?.toLowerCase() || "";
  if (recoveryZone === "red") {
    return { icon: "🌿", title: "Recovery Day", sub: "Your body needs rest — tap for a light session" };
  }
  if (recoveryZone === "yellow") {
    return { icon: "⚡", title: "Moderate Session", sub: "70% intensity today — tap to start" };
  }
  if (goal.includes("weight") || goal.includes("fat")) {
    return { icon: "🔥", title: "Burn Session Ready", sub: "Tap to begin today's fat-loss workout" };
  }
  if (goal.includes("muscle") || goal.includes("bulk") || goal.includes("strength")) {
    return { icon: "💪", title: "Strength Day", sub: "Let's build. Tap to start your session" };
  }
  return { icon: "🏋️", title: "Start Today's Workout", sub: "Tap to begin your AI-guided session" };
}
 
function setTxt(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = val;
}

function animateTextNumber(id, value, suffix = "") {
  const el = document.getElementById(id);
  if (!el) return;
  const number = Number(value);
  if (!Number.isFinite(number)) {
    el.textContent = value || "—";
    return;
  }
  cancelAnimationFrame(homeCountRaf[id]);
  const start = performance.now();
  const duration = 720;
  const from = Number(el.dataset.value || 0);
  const ease = (t) => 1 - Math.pow(1 - t, 3);
  const tick = (now) => {
    const t = Math.min(1, (now - start) / duration);
    const current = Math.round(from + (number - from) * ease(t));
    el.textContent = current + suffix;
    if (t < 1) homeCountRaf[id] = requestAnimationFrame(tick);
    else el.dataset.value = number;
  };
  homeCountRaf[id] = requestAnimationFrame(tick);
}

async function loadHome() {
  try {
    // 1. Greeting
    const hour = new Date().getHours();
    document.getElementById("home-greeting").textContent = timeGreeting();
 
    // 2. User name
    const name = currentUser?.name || "Athlete";
    document.getElementById("home-name").textContent = name;
 
    // 3. Random quote (changes daily)
    const dayIndex = new Date().getDate() % HOME_QUOTES.length;
    const q = HOME_QUOTES[dayIndex];
    document.getElementById("home-quote-text").textContent = q.text;
    document.getElementById("home-quote-author").textContent = "— " + q.author;
 
    // 4. Load progress stats
    try {
      const data = await apiFetch("/api/progress");
      const workouts = data.total_workouts || 0;
      const streak   = data.current_streak || 0;
      const badges   = data.badges?.length || 0;
      const lastWeight = data.weight?.values?.slice(-1)[0] || null;
 
      animateTextNumber("hs-workouts", workouts);
      animateTextNumber("hs-streak", streak);
      animateTextNumber("hs-badges", badges);
      document.getElementById("hs-weight").textContent   = lastWeight ? lastWeight + "kg" : "—";
      animateTextNumber("home-streak-count", streak);
      animateTextNumber("home-footer-streak", streak);
      setTxt("home-perf-calories", workouts ? `${workouts * 280} kcal` : "Scan");
      setTxt("home-perf-consistency", workouts ? `${workouts}` : "Start");
 
      // Weekly heatmap strip (last 7 days)
      renderHomeWeek(data.heatmap);
    } catch(e) {}
 
    // 5. Recovery banner
    try {
      const rec = await apiFetch("/api/recovery/latest");
      const bar  = document.getElementById("home-recovery-bar");
      const dot  = document.getElementById("home-recovery-dot");
      const txt  = document.getElementById("home-recovery-text");
 
      if (rec && rec.zone) {
        bar.style.display = "flex";
        dot.className     = "hrb-dot " + rec.zone;
        const zoneLabel   = { green:"Full intensity 🟢", yellow:"Moderate day 🟡", red:"Rest day 🔴" };
        txt.textContent   = "Recovery: " + (zoneLabel[rec.zone] || rec.zone) + " (score " + rec.score + ")";
        const focusReadiness = document.getElementById("home-focus-readiness");
        focusReadiness?.style.setProperty("--home-ready", rec.score || 75);
        focusReadiness?.querySelector("strong") && (focusReadiness.querySelector("strong").textContent = rec.score || 75);
        setTxt("home-recovery-score-big", rec.score || "--");
        setTxt("home-footer-recovery", rec.zone || "--");
        setTxt("home-perf-recovery", rec.zone === "green" ? "Rising" : rec.zone === "yellow" ? "Stable" : "Restore");
        setTxt("home-muscle-fatigue", rec.zone === "green" ? "Low" : rec.zone === "yellow" ? "Moderate" : "High");
        setTxt("home-insight-recovery", rec.zone === "green"
          ? "Your recovery is high today. Push quality work while keeping technique sharp."
          : rec.zone === "yellow"
            ? "Recovery is moderate. Train productively, but cap intensity before form breaks."
            : "Recovery is low. Restoration work will compound better than max effort today.");
        // Update CTA based on recovery zone
        const cta = getTodayCTAMessage(currentUser, rec.zone);
        document.getElementById("home-cta-icon").textContent  = cta.icon;
        document.getElementById("home-cta-title").textContent = cta.title;
        document.getElementById("home-cta-sub").textContent   = cta.sub;
      } else {
        // No recovery logged today — nudge them
        bar.style.display = "flex";
        document.getElementById("home-recovery-dot").className = "hrb-dot yellow";
        document.getElementById("home-recovery-text").textContent = "Log your recovery to get personalised intensity";
      }
    } catch(e) {
      // Recovery not available — show default CTA
      const cta = getTodayCTAMessage(currentUser, null);
      document.getElementById("home-cta-icon").textContent  = cta.icon;
      document.getElementById("home-cta-title").textContent = cta.title;
      document.getElementById("home-cta-sub").textContent   = cta.sub;
    }
 
  } catch(e) {
    console.log("Home load error:", e);
  }
}
 
function renderHomeWeek(heatmap) {
  const container = document.getElementById("home-week-row");
  if (!container) return;
 
  const days = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"];
  const today = new Date();
  // Build last 7 days as YYYY-MM-DD strings
  const last7 = Array.from({length:7}, (_,i) => {
    const d = new Date(today);
    d.setDate(today.getDate() - (6 - i));
    return d.toISOString().split("T")[0];
  });
 
  // Build a set of workout dates from heatmap
  const workoutDates = new Set();
  if (heatmap && Array.isArray(heatmap)) {
    heatmap.forEach(entry => {
      if (entry.date) workoutDates.add(entry.date.split("T")[0]);
    });
  }
 
  const todayStr = today.toISOString().split("T")[0];
 
  container.innerHTML = last7.map((dateStr, i) => {
    const worked = workoutDates.has(dateStr);
    const isToday = dateStr === todayStr;
    const dayLabel = days[new Date(dateStr).getDay() === 0 ? 6 : new Date(dateStr).getDay() - 1];
    const barClass = isToday ? "week-bar today" : worked ? "week-bar done" : "week-bar empty";
    const barHeight = worked || isToday ? "32px" : "16px";
    const checkmark = worked ? '<div class="week-check">✓</div>' : "";
    return `<div class="week-day">
      ${checkmark}
      <div class="${barClass}" style="height:${barHeight}"></div>
      <div class="week-label">${dayLabel}</div>
    </div>`;
  }).join("");
}

// ── SPORT ONBOARDING DEFINITIONS ──────────────────────────────────────
const SPORT_FIELD_ORDERS = {
  cricket:  ["sport_select","role","bowling_type","match_frequency","primary_focus","sport_injuries"],
  football: ["sport_select","position","match_frequency","primary_focus","sport_injuries"],
  running:  ["sport_select","distance_type","weekly_mileage","primary_focus","sport_injuries"],
  default:  ["sport_select","primary_focus","sport_injuries"],
};

const SPORT_QUESTIONS = {
  sport_select:    {reply:"Which sport do you play?",                     input_type:"sport_select"},
  role:            {reply:"What's your role in cricket?",                 input_type:"cricket_role"},
  bowling_type:    {reply:"What type of bowler are you?",                 input_type:"bowling_type"},
  match_frequency: {reply:"How often do you play matches?",               input_type:"match_frequency"},
  primary_focus:   {reply:"What's your primary training focus?",          input_type:"primary_focus"},
  sport_injuries:  {reply:"Any sport-specific injuries or areas to protect?", input_type:"sport_injuries"},
  position:        {reply:"What position do you play?",                   input_type:"football_position"},
  distance_type:   {reply:"What type of running do you focus on?",        input_type:"distance_type"},
  weekly_mileage:  {reply:"What's your current weekly mileage / running volume?", input_type:"weekly_mileage"},
};

// ── INIT ──────────────────────────────────────────────────────────────
window.onload = async () => {
  initThemeEngine();
  if (authToken) {
    try {
      const res = await apiFetch("/api/me");
      if (res.onboarded) {
        currentUser = res.profile;
        showApp();
        switchTab(window.FC_INITIAL_TAB || 'home');
        loadRecoveryBanner();
      } else {
        showApp();
        loadChat(); // will trigger onboarding
      }
    } catch {
      authToken = null;
      localStorage.removeItem("fc_token");
      showAuth();
    }
  } else {
    showAuth();
  }
  initVoiceInput();
  updateModeUI();
  updateThemeSwitcher(document.documentElement.getAttribute("data-theme") || "galaxy");
};

// ── SCREENS ───────────────────────────────────────────────────────────
function showAuth() {
  document.getElementById("auth-screen").classList.add("active");
  document.getElementById("app-screen").classList.remove("active");
}
function showApp() {
  document.getElementById("auth-screen").classList.remove("active");
  document.getElementById("app-screen").classList.add("active");
}

// ── AUTH TABS ─────────────────────────────────────────────────────────
function switchAuthTab(tab) {
  document.querySelectorAll(".auth-tab").forEach((t,i) => {
    t.classList.toggle("active",(i===0&&tab==="login")||(i===1&&tab==="signup"));
  });
  document.getElementById("login-form").classList.toggle("hidden",tab!=="login");
  document.getElementById("signup-form").classList.toggle("hidden",tab!=="signup");
  document.getElementById("forgot-form").classList.add("hidden");
  document.getElementById("auth-error").classList.add("hidden");
  const hl = document.getElementById("auth-headline");
  const sl = document.getElementById("auth-subline");
  if (hl && sl) {
    if (tab === "signup") {
      hl.innerHTML = 'Start your <span>journey</span>';
      sl.textContent = "Create your free account in seconds";
    } else {
      hl.innerHTML = 'Welcome <span>back</span>';
      sl.textContent = "Sign in to continue your training";
    }
  }
}
function switchLoginMethod(m) {
  document.getElementById("method-password-btn").classList.toggle("active",m==="password");
  document.getElementById("method-otp-btn").classList.toggle("active",m==="otp");
  document.getElementById("login-password-section").classList.toggle("hidden",m!=="password");
  document.getElementById("login-otp-section").classList.toggle("hidden",m!=="otp");
}
function showForgotPassword() {
  document.getElementById("login-form").classList.add("hidden");
  document.getElementById("forgot-form").classList.remove("hidden");
  document.getElementById("auth-error").classList.add("hidden");
}
function showLoginForm() {
  document.getElementById("forgot-form").classList.add("hidden");
  document.getElementById("login-form").classList.remove("hidden");
}

// ── OTP FLOWS ─────────────────────────────────────────────────────────
async function sendSignupOTP() {
  const email = document.getElementById("signup-email").value.trim();
  if (!email) return showAuthError("Enter your email first");
  try {
    const res = await fetch(`${API}/api/send-otp`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({email,purpose:"verify"})});
    const d = await res.json();
    if (!res.ok) return showAuthError(d.error || "Failed");
    document.getElementById("signup-otp-section").classList.remove("hidden");
    document.getElementById("signup-send-otp-btn").textContent = "✅ OTP Sent";
    showToast("📧 OTP sent to "+email);
  } catch { showAuthError("Connection error"); }
}
async function sendLoginOTP() {
  const email = document.getElementById("login-email").value.trim();
  if (!email) return showAuthError("Enter your email");
  try {
    const res = await fetch(`${API}/api/send-otp`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({email,purpose:"login"})});
    const d = await res.json();
    if (!res.ok) return showAuthError(d.error || "Failed");
    document.getElementById("login-otp-input-wrap").classList.remove("hidden");
    showToast("📧 OTP sent to "+email);
  } catch { showAuthError("Connection error"); }
}
async function doLoginOTP() {
  const email = document.getElementById("login-email").value.trim();
  const code  = document.getElementById("login-otp-code").value.trim();
  if (!code) return showAuthError("Enter the OTP");
  try {
    const res = await fetch(`${API}/api/verify-otp`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({email,code,purpose:"login"})});
    const d = await res.json();
    if (!res.ok) return showAuthError(d.error || "Invalid OTP");
    authToken = d.token; localStorage.setItem("fc_token",authToken);
    showApp(); loadChat();
  } catch { showAuthError("Connection error"); }
}
async function sendResetOTP() {
  const email = document.getElementById("forgot-email").value.trim();
  if (!email) return showAuthError("Enter your email");
  try {
    const res = await fetch(`${API}/api/send-otp`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({email,purpose:"reset"})});
    if (!res.ok) return showAuthError("Failed to send OTP");
    document.getElementById("forgot-step1").classList.add("hidden");
    document.getElementById("forgot-step2").classList.remove("hidden");
    showToast("📧 Reset code sent");
  } catch { showAuthError("Connection error"); }
}
async function doResetPassword() {
  const email   = document.getElementById("forgot-email").value.trim();
  const otp     = document.getElementById("forgot-otp").value.trim();
  const newPass = document.getElementById("forgot-newpass").value;
  if (!otp || !newPass) return showAuthError("Fill all fields");
  if (newPass.length < 6) return showAuthError("Min 6 characters");
  try {
    // Step 1: verify OTP — backend returns a short-lived reset_token
    const vRes  = await fetch(`${API}/api/verify-otp`, {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({email,code:otp,purpose:"reset"})});
    const vData = await vRes.json();
    if (!vRes.ok) return showAuthError(vData.error || "Invalid OTP");
    const resetToken = vData.reset_token;
    if (!resetToken) return showAuthError("OTP verification failed — try again");

    // Step 2: reset password using the token (server verifies it server-side)
    const rRes  = await fetch(`${API}/api/reset-password`, {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({email, new_password:newPass, reset_token:resetToken})});
    const rData = await rRes.json();
    if (!rRes.ok) return showAuthError(rData.error || "Reset failed");
    showToast("Password reset! Sign in now.");
    showLoginForm();
  } catch { showAuthError("Connection error"); }
}
async function doLogin() {
  const email    = document.getElementById("login-email").value.trim();
  const password = document.getElementById("login-password").value;
  if (!email||!password) return showAuthError("Fill in all fields");
  _btnLock("login-btn", true);
  try {
    const res = await fetch(`${API}/api/login`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({email,password})});
    const d = await res.json();
    if (!res.ok) { _btnLock("login-btn", false); return showAuthError(d.error||"Login failed"); }
    authToken = d.token; localStorage.setItem("fc_token",authToken);
    currentUser = d; showApp(); loadChat();
  } catch (e) { _btnLock("login-btn", false); showAuthError("Connection error"); }
}
async function doSignup() {
  const email    = document.getElementById("signup-email").value.trim();
  const password = document.getElementById("signup-password").value;
  const otp      = document.getElementById("signup-otp-code").value.trim();
  if (!email||!password) return showAuthError("Fill all fields");
  if (!otp) return showAuthError("Verify email with OTP first");
  _btnLock("signup-btn", true);
  try {
    const vRes = await fetch(`${API}/api/verify-otp`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({email,code:otp,purpose:"verify"})});
    if (!vRes.ok) { _btnLock("signup-btn", false); return showAuthError("Invalid OTP"); }
    const res = await fetch(`${API}/api/signup`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({email,password})});
    const d = await res.json();
    if (!res.ok) { _btnLock("signup-btn", false); return showAuthError(d.error||"Signup failed"); }
    authToken = d.token; localStorage.setItem("fc_token",authToken);
    showApp(); loadChat();
  } catch (e) { _btnLock("signup-btn", false); showAuthError("Connection error"); }
}
function doLogout() {
  authToken = null; currentUser = null;
  localStorage.removeItem("fc_token");
  document.getElementById("chat-box").innerHTML = "";
  workoutActive = false; feedbackMode = false;
  showAuth();
}
function showAuthError(msg) {
  const el = document.getElementById("auth-error");
  if (!msg){el.classList.add("hidden");return;}
  el.textContent = msg; el.classList.remove("hidden");
}

// ── API ───────────────────────────────────────────────────────────────
async function apiFetch(url, options={}) {
  let res;
  try {
    res = await fetch(`${API}${url}`, {
      ...options,
      headers:{"Content-Type":"application/json","Authorization":`Bearer ${authToken}`,...(options.headers||{})}
    });
  } catch (networkErr) {
    showToast("Connection error — check your internet.");
    throw networkErr;
  }
  if (res.status === 401) { doLogout(); throw new Error("Unauthorized"); }
  if (res.status === 429) {
    showToast("Too many requests — slow down a moment.");
    throw new Error("Rate limited");
  }
  if (res.status >= 500) {
    showToast("Server error — try again in a moment.");
    throw new Error(`Server error ${res.status}`);
  }
  const ct = res.headers.get("content-type") || "";
  if (!ct.includes("application/json")) {
    throw new Error("Unexpected response from server");
  }
  return res.json();
}

function _btnLock(btnId, loading=true) {
  const btn = document.getElementById(btnId);
  if (!btn) return;
  btn.disabled = loading;
  btn._origText = btn._origText || btn.textContent;
  btn.textContent = loading ? "Please wait..." : btn._origText;
}

// ── WORKOUT MODE ──────────────────────────────────────────────────────
function setWorkoutMode(mode) {
  // Guard: sport mode requires sport profile
  if (mode === "sport" && !(currentUser?.plays_sport && currentUser?.sport)) {
    showToast("Complete sport setup first!");
    setTimeout(() => startSportOnboarding(), 300);
    return;
  }
  workoutMode = mode;
  localStorage.setItem("fc_workout_mode", mode);
  updateModeUI();
  const modeLabel = mode === "sport" ? "Sport Mode 🏆" : "Gym Mode 🏋️";
  showToast(`Switched to ${modeLabel}`);
}
function updateModeUI() {
  const isSport = workoutMode === "sport";
  // Sidebar
  document.getElementById("mode-gym-btn")?.classList.toggle("active",  !isSport);
  document.getElementById("mode-sport-btn")?.classList.toggle("active", isSport);
  // Mobile compact
  document.getElementById("mp-gym")?.classList.toggle("active",   !isSport);
  document.getElementById("mp-sport")?.classList.toggle("active",  isSport);
  // Header label
  const lbl = document.getElementById("coach-mode-label");
  if (lbl) lbl.textContent = isSport ? "Sport Mode 🏆" : "Gym Mode 🏋️";
  const sidebarMode = document.getElementById("sidebar-mode-readout");
  if (sidebarMode) sidebarMode.textContent = isSport ? "Sport" : "Gym";
  const protocolChip = document.getElementById("coach-protocol-chip");
  if (protocolChip) protocolChip.textContent = isSport ? "Sport focus" : "Strength focus";
  const currentSplit = document.getElementById("coach-current-split");
  if (currentSplit) currentSplit.textContent = isSport ? "Sport Mode" : "Gym Mode";
  // Avatar
  const av = document.getElementById("coach-avatar");
  if (av) av.textContent = isSport ? "🏆" : "⚡";
}

// ── TABS ──────────────────────────────────────────────────────────────
function switchTab(tab) {
  document.querySelectorAll(".tab-content").forEach(t=>t.classList.remove("active"));
  document.querySelectorAll(".nav-btn,.bnav-btn").forEach(b=>{
    b.classList.toggle("active",b.dataset.tab===tab);
  });
  const target = document.getElementById(`tab-${tab}`);
  if (!target) return;
  target.classList.add("active");
  if (localStorage.getItem("fc_theme_auto") === "1") {
    applyAthleteTheme(AUTO_THEME_BY_TAB[tab] || "galaxy", { previewOnly: true });
  }
  if (tab==="progress") loadProgress();
  if (tab==="profile")  loadProfile();
  if (tab==="recovery") loadRecoveryLatest();
  if (tab==="home") loadHome();
  if (tab==="chat") {
    const chatBox = document.getElementById("chat-box");
    if (chatBox && chatBox.children.length === 0) loadChat();
  }
  if (tab==="trainer") window.fitCoachGhostTrainer?.init();
  if (tab!=="trainer") window.fitCoachGhostTrainer?.stop();
}

// ── CHAT ──────────────────────────────────────────────────────────────
function loadChat() {
  document.getElementById("chat-box").innerHTML = "";
  callServer(""); // triggers greeting or onboarding
}

function cleanDisplayText(text) {
  return String(text || "")
    .replace(/âœ…|âœ“/g, "OK")
    .replace(/â€”|â€“/g, "-")
    .replace(/Ã—/g, "x")
    .replace(/â†’/g, "->")
    .replace(/ðŸ”¥|ðŸ’ª|ðŸŒ¿|ðŸ“Š|ðŸ|ðŸ†|ðŸŽ‰|ðŸ‘‹|âš¡|â˜€ï¸|ðŸŒ¤ï¸|ðŸŒ™/g, "")
    .replace(/[^\x09\x0A\x0D\x20-\x7E]/g, "")
    .replace(/[ \t]{2,}/g, " ")
    .trim();
}

function addMessage(text, sender) {
  const chatBox = document.getElementById("chat-box");
  const msg = document.createElement("div");
  msg.className = `message ${sender}`;
  msg.innerHTML = cleanDisplayText(text)
    .replace(/\*\*(.*?)\*\*/g,"<strong>$1</strong>")
    .replace(/_(.*?)_/g,"<em>$1</em>")
    .replace(/\n/g,"<br>");
  chatBox.appendChild(msg);
  msg.scrollIntoView({behavior:"smooth",block:"nearest"});
  return msg;
}

function escapeHtml(value) {
  return cleanDisplayText(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function titleCase(value) {
  return cleanDisplayText(value || "")
    .replace(/[_-]/g, " ")
    .replace(/\w\S*/g, (txt) => txt.charAt(0).toUpperCase() + txt.slice(1).toLowerCase());
}

function estimateCalories(exercises, duration) {
  const count = Array.isArray(exercises) ? exercises.length : 0;
  const mins = Number(duration) || Math.max(28, count * 8);
  return Math.round(mins * 7.2 / 10) * 10;
}

function extractInsightLines(reply, max = 4) {
  const text = cleanDisplayText(reply);
  return text
    .split(/\n+/)
    .map((line) => line.replace(/^[-*\d.\s]+/, "").trim())
    .filter((line) => line && !/^today:|^ready\?|^this week:/i.test(line))
    .slice(0, max);
}

function exerciseIcon(exercise) {
  const hay = `${exercise?.name || ""} ${exercise?.muscle || ""} ${exercise?.category || ""}`.toLowerCase();
  if (hay.includes("run") || hay.includes("sprint")) return "RUN";
  if (hay.includes("press") || hay.includes("push") || hay.includes("chest")) return "PRS";
  if (hay.includes("squat") || hay.includes("leg") || hay.includes("lunge")) return "LEG";
  if (hay.includes("row") || hay.includes("pull") || hay.includes("back")) return "PULL";
  if (hay.includes("core") || hay.includes("plank") || hay.includes("abs")) return "CORE";
  if (hay.includes("mobility") || hay.includes("stretch")) return "REC";
  return "AI";
}

function renderCoachResponse(data) {
  const chatBox = document.getElementById("chat-box");
  const panel = document.createElement("section");
  panel.className = `coach-dashboard-response ${data.type || "chat"}`;
  panel.innerHTML = buildCoachDashboardHtml(data);
  chatBox.appendChild(panel);
  wireCoachDashboard(panel);
  panel.scrollIntoView({behavior:"smooth",block:"start"});
  return panel;
}

function buildCoachDashboardHtml(data) {
  if (["daily_plan", "workout_start", "workout_next_set", "workout_next_exercise"].includes(data.type)) {
    return buildWorkoutDashboard(data);
  }
  if (data.type === "workout_all_done") return buildCompletionDashboard(data, false);
  if (data.type === "feedback_received") return buildCompletionDashboard(data, true);
  if (data.type === "workout_logged") return buildLoggedDashboard(data);
  if (data.type === "daily_greeting") return buildGreetingDashboard(data);
  if ((data.reply || "").toLowerCase().includes("protein") || (data.reply || "").toLowerCase().includes("calorie") || (data.reply || "").toLowerCase().includes("nutrition") || (data.reply || "").toLowerCase().includes("meal")) {
    return buildNutritionDashboard(data);
  }
  return buildInsightDashboard(data);
}

function buildWorkoutDashboard(data) {
  const exercises = data.exercises || (data.current_exercise ? [data.current_exercise] : []);
  const currentIdx = data.current_exercise_index ?? 0;
  const total = data.total_exercises || exercises.length || 1;
  const currentSet = data.current_set || 1;
  const active = data.current_exercise || exercises[currentIdx] || exercises[0] || {};
  const muscle = data.muscle_group || data.today_muscle || active.muscle || "AI Workout";
  const zone = data.zone || "green";
  const duration = Math.max(30, exercises.length * 8 + 8);
  const pct = data.type === "daily_plan" ? 0 : Math.min(96, Math.round(((currentIdx + (currentSet - 1) / Math.max(active.sets || 3, 1)) / total) * 100));
  const focus = data.workout_mode === "sport" ? "Sport Performance" : "Strength + Hypertrophy";
  const heroTitle = titleCase(muscle);
  const insightLines = extractInsightLines(data.reply, 3);
  const exerciseCards = exercises.map((ex, idx) => buildExerciseCard(ex, idx, currentIdx, data.type)).join("");
  const weekly = buildWeeklyPlanner(data.weekly_plan);
  const splitIntel = buildSplitIntelligence(data, exercises, currentIdx, pct);

  return `
    <div class="coach-hero-card zone-${escapeHtml(zone)}">
      <div class="coach-hero-copy">
        <div class="coach-kicker">AI Workout OS</div>
        <h3>${heroTitle}</h3>
        <p>${escapeHtml(focus)} - ${zone === "red" ? "Recovery optimized" : zone === "yellow" ? "Intensity moderated" : "Recovery optimized"}</p>
      </div>
      <div class="coach-hero-metrics">
        <div><strong>${duration}</strong><span>min</span></div>
        <div><strong>${estimateCalories(exercises, duration)}</strong><span>kcal</span></div>
        <div><strong>${escapeHtml(zone.toUpperCase())}</strong><span>readiness</span></div>
      </div>
      <div class="coach-orbit-meter" style="--progress:${pct}%"><span>${pct}%</span></div>
    </div>
    <div class="coach-insight-strip">
      ${insightLines.map((line, i) => `<div class="ai-insight-card"><span>${["AI","PWR","REC","FOC"][i] || "AI"}</span>${escapeHtml(line)}</div>`).join("") || `<div class="ai-insight-card"><span>AI</span>Session loaded and ready.</div>`}
    </div>
    ${splitIntel}
    <div class="coach-section">
      <button class="coach-section-toggle" type="button" data-toggle-section>
        <span>Exercise Stack</span><small>${currentIdx + 1}/${total} active</small>
      </button>
      <div class="exercise-card-grid">${exerciseCards}</div>
    </div>
    ${weekly}
  `;
}

function buildSplitIntelligence(data, exercises, currentIdx, pct) {
  const zone = data.zone || "green";
  const session = data.muscle_group || data.today_muscle || "Workout";
  const families = new Set(exercises.map((ex) => (ex.category || ex.muscle || "").toLowerCase().split(/[,+/]/)[0]).filter(Boolean));
  const load = zone === "red" ? 38 : zone === "yellow" ? 68 : 88;
  const timeline = exercises.slice(0, 5).map((ex, idx) => `
    <div class="session-timeline-step ${idx < currentIdx ? "done" : idx === currentIdx && data.type !== "daily_plan" ? "active" : ""}">
      <span></span><strong>${escapeHtml(ex.name || `Block ${idx + 1}`)}</strong>
    </div>
  `).join("");
  return `
    <div class="ai-workspace-grid">
      <div class="readiness-widget" style="--readiness:${load}%">
        <div class="readiness-ring"><strong>${load}</strong><span>readiness</span></div>
        <p>${zone === "red" ? "Recovery-biased session selected." : zone === "yellow" ? "Load moderated for clean output." : "High-output training window detected."}</p>
      </div>
      <div class="muscle-heat-widget">
        <div class="panel-title-row"><span>Muscle Heat</span><small>${escapeHtml(families.size || 1)} zones</small></div>
        <div class="muscle-heat-bars">
          ${["lower","push","pull","core","engine"].map((name, idx) => `<div><span>${name}</span><i style="--heat:${Math.max(18, Math.min(96, pct + 18 - idx * 9))}%"></i></div>`).join("")}
        </div>
      </div>
      <div class="session-timeline-card">
        <div class="panel-title-row"><span>Session Timeline</span><small>${escapeHtml(session)}</small></div>
        <div class="session-timeline">${timeline}</div>
      </div>
    </div>
  `;
}

function buildExerciseCard(ex, idx, activeIdx, responseType) {
  const isActive = idx === activeIdx && responseType !== "daily_plan";
  const isDone = responseType !== "daily_plan" && idx < activeIdx;
  const sets = ex?.sets || 3;
  const reps = ex?.reps || "10";
  const muscle = ex?.muscle || ex?.category || "Full body";
  const difficulty = ex?.intensity || ex?.difficulty || "guided";
  const equipment = Array.isArray(ex?.equipment) ? ex.equipment.join(", ") : (ex?.equipment || ex?.weight_guide || "Body control");
  const tip = Array.isArray(ex?.progression) ? ex.progression[0] : (ex?.weight_guide || "Move with clean control and own every rep.");
  return `
    <article class="exercise-ai-card ${isActive ? "active" : ""} ${isDone ? "complete" : ""}" draggable="true">
      <div class="exercise-visual"><span>${exerciseIcon(ex)}</span></div>
      <div class="exercise-card-main">
        <div class="exercise-topline">
          <h4>${escapeHtml(ex?.name || "Exercise")}</h4>
          <span class="exercise-state">${isDone ? "Done" : isActive ? "Live" : `#${idx + 1}`}</span>
        </div>
        <div class="exercise-prescription">
          <span>${escapeHtml(sets)} sets</span><span>${escapeHtml(reps)} reps</span><span>${escapeHtml(ex?.rest || "60s")}</span>
        </div>
        <div class="exercise-tags">
          <span>${escapeHtml(muscle)}</span><span>${escapeHtml(difficulty)}</span><span>${escapeHtml(equipment)}</span>
        </div>
        <p>${escapeHtml(tip)}</p>
        <div class="exercise-actions">
          <button type="button" data-command="${isActive ? "next" : "start"}">${isActive ? "Complete Set" : "Start"}</button>
          <button type="button" data-command="replace ${escapeHtml(ex?.name || "")}">Replace</button>
          <button type="button" data-command="next">Skip</button>
          <button type="button" data-command="easy">Easier</button>
          <button type="button" data-command="hard">Harder</button>
        </div>
      </div>
    </article>
  `;
}

function buildWeeklyPlanner(plan) {
  if (!Array.isArray(plan) || !plan.length) return "";
  const today = new Date().getDay();
  const dayMap = {0:"Sun",1:"Mon",2:"Tue",3:"Wed",4:"Thu",5:"Fri",6:"Sat"};
  return `
    <div class="weekly-planner-panel">
      <div class="panel-title-row"><span>Weekly Planner</span><small>Drag to visualize your split</small></div>
      <div class="weekly-day-track">
        ${plan.slice(0, 7).map((slot, idx) => {
          const label = slot.day || dayMap[idx] || `Day ${idx + 1}`;
          const active = slot.day_index === today || label.slice(0,3).toLowerCase() === dayMap[today].toLowerCase();
          const title = slot.rest ? "Recovery" : (slot.label || slot.muscle || "Workout");
          return `<div class="planner-day-card ${active ? "active" : ""} ${slot.rest ? "rest" : ""}" draggable="true">
            <strong>${escapeHtml(label)}</strong><span>${escapeHtml(title)}</span><small>${active ? "Today" : slot.rest ? "Restore" : "Planned"}</small>
          </div>`;
        }).join("")}
      </div>
    </div>
  `;
}

function buildCompletionDashboard(data, readyToLog) {
  const lines = extractInsightLines(data.reply, 3);
  return `
    <div class="session-status-grid">
      <div class="status-card primary"><span>Workout Complete</span><strong>${readyToLog ? "Ready" : "Feedback"}</strong><small>${readyToLog ? "Log the session" : "Tell the coach how it felt"}</small></div>
      <div class="status-card"><span>Calories</span><strong>${estimateCalories([], 45)}</strong><small>estimated burn</small></div>
      <div class="status-card"><span>Recovery</span><strong>Hydrate</strong><small>Protein plus fluids next</small></div>
    </div>
    <div class="coach-insight-strip">${lines.map((line) => `<div class="ai-insight-card"><span>AI</span>${escapeHtml(line)}</div>`).join("")}</div>
  `;
}

function buildLoggedDashboard(data) {
  return `
    <div class="session-status-grid">
      <div class="status-card primary"><span>Completion Badge</span><strong>Logged</strong><small>Workout saved</small></div>
      <div class="status-card"><span>Streak</span><strong>${escapeHtml(data.streak || 0)}</strong><small>days</small></div>
      <div class="status-card"><span>Duration</span><strong>${escapeHtml(data.duration || 0)}</strong><small>minutes</small></div>
      <div class="status-card"><span>Next Split</span><strong>${escapeHtml(data.next_session || "Rotated")}</strong><small>planner updated</small></div>
    </div>
    <div class="ai-insight-card wide"><span>REC</span>Rest, hydrate, and give the next session clean data.</div>
    ${buildWeeklyPlanner(data.weekly_plan)}
  `;
}

function buildNutritionDashboard(data) {
  const lines = extractInsightLines(data.reply, 6);
  const protein = lines.find((l) => /protein/i.test(l)) || "Protein Goal - 120-160g daily";
  const hydration = lines.find((l) => /water|hydr/i.test(l)) || "Hydration - 2.5L baseline";
  const recovery = lines.find((l) => /recover|omega|turmeric|ginger|meal/i.test(l)) || "Recovery Foods - Omega-3, turmeric, ginger";
  return `
    <div class="nutrition-card-grid">
      <div class="macro-card"><span>Protein Goal</span><strong>${escapeHtml(protein.replace(/^protein goal[:\s-]*/i, ""))}</strong></div>
      <div class="macro-card green"><span>Hydration</span><strong>${escapeHtml(hydration.replace(/^hydration[:\s-]*/i, ""))}</strong></div>
      <div class="macro-card orange"><span>Recovery Foods</span><strong>${escapeHtml(recovery.replace(/^recovery foods[:\s-]*/i, ""))}</strong></div>
    </div>
    <div class="coach-insight-strip">${lines.slice(0, 3).map((line) => `<div class="ai-insight-card"><span>NUT</span>${escapeHtml(line)}</div>`).join("")}</div>
  `;
}

function buildGreetingDashboard(data) {
  const name = currentUser?.name || "Athlete";
  const todayMuscle = data.today_muscle || "Full Body";
  const streak = data.streak || 0;
  const zone = data.zone || "green";
  const zoneEmoji = zone === "green" ? "✅" : zone === "yellow" ? "⚠️" : "🔴";
  const zoneLabel = zone === "green" ? "Fully recovered" : zone === "yellow" ? "Moderate recovery" : "Light day recommended";
  const modeLabel = (data.workout_mode || workoutMode) === "sport" ? "SPT" : (data.workout_mode || workoutMode) === "home" ? "HOM" : "GYM";
  const streakTxt = streak > 0 ? `🔥 ${streak} day streak` : "Start your streak!";

  // Build exercise preview chips (up to 3)
  const exChips = (data.exercises || []).slice(0, 3).map(ex => {
    const exName = ex.name || ex.exercise || "";
    return `<span class="ex-chip">${escapeHtml(exName)}</span>`;
  }).join("");

  return `
    <div class="coach-hero-card compact">
      <div class="coach-hero-copy">
        <div class="coach-kicker">FitCoach AI · Ready</div>
        <h3>Good to see you, ${escapeHtml(name)}!</h3>
        <p>💪 Today: <strong>${escapeHtml(todayMuscle)}</strong></p>
        <p>${zoneEmoji} Recovery: <strong>${zone.toUpperCase()}</strong> — ${zoneLabel}</p>
      </div>
      <div class="coach-hero-metrics">
        <div><strong>${streak}</strong><span>streak</span></div>
        <div><strong>${modeLabel}</strong><span>mode</span></div>
      </div>
    </div>
    ${exChips ? `<div class="coach-exercise-preview">Today's exercises: ${exChips}</div>` : ""}
    <div class="coach-insight-strip">
      <div class="ai-insight-card wide"><span>💪</span>${escapeHtml(streakTxt)} — ${escapeHtml(todayMuscle)} session queued</div>
    </div>
  `;
}

function buildInsightDashboard(data) {
  const lines = extractInsightLines(data.reply, 5);
  return `
    <div class="insight-dashboard">
      <div class="panel-title-row"><span>Your Coach</span><small>reply</small></div>
      <div class="coach-insight-strip vertical">
        ${lines.map((line, i) => `<div class="ai-insight-card ${i === 0 ? "wide" : ""}"><span>${i === 0 ? "💪" : "TIP"}</span>${escapeHtml(line)}</div>`).join("") || `<div class="ai-insight-card wide"><span>💪</span>${escapeHtml(data.reply || "Ready when you are.")}</div>`}
      </div>
    </div>
  `;
}

function wireCoachDashboard(panel) {
  panel.querySelectorAll("[data-command]").forEach((btn) => {
    btn.addEventListener("click", () => quickSend(btn.dataset.command));
  });
  panel.querySelectorAll("[data-toggle-section]").forEach((btn) => {
    btn.addEventListener("click", () => btn.closest(".coach-section")?.classList.toggle("collapsed"));
  });
  panel.querySelectorAll("[draggable='true']").forEach((card) => {
    card.addEventListener("dragstart", () => card.classList.add("dragging"));
    card.addEventListener("dragend", () => card.classList.remove("dragging"));
  });
}

function addCoachOptions(options) {
  if (!Array.isArray(options) || !options.length) return;
  const chatBox = document.getElementById("chat-box");
  const wrap = document.createElement("div");
  wrap.className = "coach-option-panel";
  options.forEach((opt) => {
    const btn = document.createElement("button");
    btn.className = "qa-btn focus-option";
    btn.type = "button";
    btn.textContent = cleanDisplayText(opt.label || opt.command || "Start");
    btn.onclick = () => quickSend(opt.command || opt.label);
    wrap.appendChild(btn);
  });
  chatBox.appendChild(wrap);
  wrap.scrollIntoView({behavior:"smooth",block:"nearest"});
}
function showTyping() {
  removeTyping();
  const t = document.createElement("div");
  t.className="message bot typing"; t.id="typing-indicator";
  t.innerHTML=`<div class="typing-dots"><span></span><span></span><span></span></div>`;
  document.getElementById("chat-box").appendChild(t);
}
function removeTyping() { document.getElementById("typing-indicator")?.remove(); }
function handleKey(e) { if(e.key==="Enter") sendMessage(); }
function quickSend(text) { document.getElementById("message").value=text; sendMessage(); }
function workoutAction(action) { document.getElementById("message").value=action; sendMessage(); }
function startWorkout() { document.getElementById("message").value="start"; sendMessage(); }

function syncGhostWorkout(data) {
  if (!data?.exercises?.length) return;
  const payload = {
    muscle_group: data.muscle_group,
    workout_mode: data.workout_mode,
    exercises: data.exercises,
    ghost_trainer: data.ghost_trainer || null,
    updated_at: new Date().toISOString(),
  };
  localStorage.setItem("fc_active_workout", JSON.stringify(payload));
  window.dispatchEvent(new CustomEvent("fitcoach:workout-loaded", { detail: payload }));
}

function sendMessage() {
  const input = document.getElementById("message");
  const text  = input.value.trim();
  if (!text) return;
  addMessage(text,"user");
  input.value = "";
  callServer(text);
}

async function callServer(message) {
  const inOnboarding = !document.getElementById("onboarding-overlay").classList.contains("hidden");
  if (!inOnboarding) showTyping();
  try {
    const res = await fetch(`${API}/api/chat`,{
      method:"POST",
      headers:{"Content-Type":"application/json","Authorization":`Bearer ${authToken}`},
      body: JSON.stringify({message, mode: workoutMode})
    });
    if (res.status===401){doLogout();return;}
    const data = await res.json();
    if (!inOnboarding) removeTyping();
    handleResponse(data);
  } catch {
    if (!inOnboarding) { removeTyping(); addMessage("⚠️ Connection issue. Is the server running?","bot"); }
  }
}

// ── RESPONSE HANDLER ──────────────────────────────────────────────────
function handleResponse(data) {
  // GENERAL ONBOARDING
  if (data.type==="onboarding") { showOnboardingStep(data); return; }

  if (data.type==="onboarding_complete") {
    hideOnboarding();
    currentUser = data.profile;
    onboardingGender = data.profile?.gender || "male";
    updateCoachHeader(data.profile?.name, data.profile?.gender);
    addMessage(data.reply,"bot");
    showQuickActions();
    return;
  }

  // ONBOARDING COMPLETE + start sport setup
  if (data.type==="onboarding_complete_sport") {
    hideOnboarding();
    currentUser = data.profile;
    onboardingGender = data.profile?.gender || "male";
    updateCoachHeader(data.profile?.name, data.profile?.gender);
    addMessage(data.reply,"bot");
    // Auto-start sport onboarding
    if (data.start_sport_onboard) {
      setTimeout(() => startSportOnboarding(), 600);
    }
    return;
  }

  // SPORT ONBOARDING — handled separately by sportOnboardingNext()
  // but if somehow triggered from chat, show overlay
  if (data.type==="sport_onboarding") { showSportOnboardingStep(data); return; }

  // SPORT MODE GUARD — backend tells us user needs sport onboarding first
  if (data.type==="sport_onboarding_prompt") {
    addMessage(data.reply, "bot");
    if (data.start_sport_onboard) {
      setTimeout(() => startSportOnboarding(), 600);
    }
    return;
  }

  if (data.type==="sport_onboarding_complete") {
    hideSportOnboarding();
    currentUser = {...(currentUser||{}), plays_sport:true, sport:data.sport, sport_profile:data.sport_profile};
    const sport = (data.sport||"").charAt(0).toUpperCase()+(data.sport||"").slice(1);
    addMessage(data.reply,"bot");
    showToast(`🏆 Sport Mode: ${sport} activated!`);
    setWorkoutMode("sport");
    updateProfileSportBadge();
    showQuickActions();
    return;
  }

  // Chat messages
  renderCoachResponse(data);
  if (data.options) addCoachOptions(data.options);
  const gender = currentUser?.gender || onboardingGender || "male";
  speakResponse(data, gender);

  switch(data.type) {
    case "daily_greeting":
      updateStreak(data.streak||0);
      showQuickActions();
      hideWorkoutUI();
      if (data.streak > 0) updateStreak(data.streak);
      break;
    case "workout_start":
      workoutActive=true; feedbackMode=false;
      syncGhostWorkout(data);
      showWorkoutProgress(data);
      showExerciseDemo(data.current_exercise, data.current_exercise_index, data.total_exercises, data.zone);
      hideQuickActions(); showWorkoutButtons(); hideFeedbackButtons();
      break;
    case "workout_next_set":
    case "workout_next_exercise":
      showWorkoutProgress(data);
      showExerciseDemo(data.current_exercise, data.current_exercise_index, data.total_exercises);
      startRestTimer(data.current_exercise?.rest);
      showWorkoutButtons(); hideFeedbackButtons();
      break;
    case "workout_all_done":
      workoutActive=false; feedbackMode=true;
      hideWorkoutUI(); showFeedbackButtons();
      break;
    case "feedback_received":
      hideFeedbackButtons(); showDoneButton();
      break;
    case "workout_logged":
      workoutActive=false; feedbackMode=false;
      hideWorkoutUI(); hideWorkoutButtons(); hideFeedbackButtons(); showQuickActions();
      launchConfetti();
      updateStreak(data.streak||0);
      showToast(`🎉 Workout ${data.total_workouts} done! ${data.duration} min`);
      if (data.new_badge) setTimeout(()=>showToast(`🏆 ${data.new_badge.badge_icon} ${data.new_badge.badge_name}`),2500);
      break;
    case "weight_logged":
      showToast(`✅ Weight: ${data.weight} kg logged`);
      break;
  }
}

// ── GENERAL ONBOARDING ────────────────────────────────────────────────
const GENERAL_FIELD_ORDER = ["name","dob","gender","height","weight","goal","level","workout_place","days_per_week","injuries","plays_sport"];
const GENERAL_QUESTIONS_MAP = {
  name:{reply:"Hey! 👋 What should I call you?",input_type:"text"},
  dob:{reply:"What's your date of birth?",input_type:"dob"},
  gender:{reply:"What's your gender?",input_type:"gender"},
  height:{reply:"What's your height?",input_type:"height"},
  weight:{reply:"What's your current weight?",input_type:"weight"},
  goal:{reply:"What's your primary fitness goal?",input_type:"goal"},
  level:{reply:"What's your fitness experience level?",input_type:"level"},
  workout_place:{reply:"Where do you prefer to work out?",input_type:"place"},
  days_per_week:{reply:"How many days per week can you train?",input_type:"days"},
  injuries:{reply:"Any injuries or pain I should know about?",input_type:"injuries"},
  plays_sport:{reply:"Do you play any sport competitively or recreationally?",input_type:"plays_sport"},
};

function showOnboardingStep(data) {
  document.getElementById("onboarding-overlay").classList.remove("hidden");
  onboardingField     = data.field;
  onboardingInputType = data.input_type;
  if (data.gender) onboardingGender = data.gender;

  const idx = GENERAL_FIELD_ORDER.indexOf(data.field);
  const total = GENERAL_FIELD_ORDER.length;
  document.getElementById("ob-progress-fill").style.width = ((idx/total)*100)+"%";
  document.getElementById("ob-step-label").textContent = `Step ${idx+1} of ${total}`;
  document.getElementById("ob-question").textContent = data.reply;
  document.getElementById("ob-error").classList.add("hidden");

  renderObInput("ob-input-area", data.input_type, data.gender || onboardingGender);
}

function renderObInput(areaId, inputType, gender) {
  const area = document.getElementById(areaId);
  area.innerHTML = "";

  switch(inputType) {
    case "text":
      area.innerHTML=`<input class="ob-text-input" id="ob-val" type="text" placeholder="Type your name…"/>`;
      setTimeout(()=>{
        const el=document.getElementById("ob-val");
        if(el){el.focus();el.addEventListener("keydown",e=>{if(e.key==="Enter")onboardingNext();});}
      },100);
      break;

    case "dob": {
      const months=["January","February","March","April","May","June","July","August","September","October","November","December"];
      const yr=new Date().getFullYear();
      area.innerHTML=`<div class="ob-dob-row">
        <select class="ob-select" id="ob-dob-day">${Array.from({length:31},(_,i)=>`<option value="${i+1}">${i+1}</option>`).join("")}</select>
        <select class="ob-select" id="ob-dob-month">${months.map((m,i)=>`<option value="${i+1}">${m}</option>`).join("")}</select>
        <select class="ob-select" id="ob-dob-year">${Array.from({length:80},(_,i)=>`<option value="${yr-i}">${yr-i}</option>`).join("")}</select>
      </div>
      <div id="ob-age-preview" style="color:var(--purpleLt);font-size:13px;text-align:center;margin-top:6px"></div>`;
      document.getElementById("ob-dob-year").value = yr-25;
      updateAgePreview();
      ["ob-dob-day","ob-dob-month","ob-dob-year"].forEach(id=>document.getElementById(id).onchange=updateAgePreview);
      break;
    }

    case "gender":
      area.innerHTML=`<div class="ob-options">
        <button class="ob-option" onclick="selectObOption(this,'male')">👨 Male</button>
        <button class="ob-option" onclick="selectObOption(this,'female')">👩 Female</button>
      </div>`;
      break;

    case "height":
      area.innerHTML=`<div class="ob-range-wrap">
        <div class="ob-range-label"><span>140 cm</span><span>210 cm</span></div>
        <input type="range" id="ob-val" min="140" max="210" value="170" oninput="document.getElementById('ob-range-val').textContent=this.value+' cm'"/>
        <div class="ob-range-value" id="ob-range-val">170 cm</div></div>`;
      break;

    case "weight":
      area.innerHTML=`<div class="ob-range-wrap">
        <div class="ob-range-label"><span>40 kg</span><span>150 kg</span></div>
        <input type="range" id="ob-val" min="40" max="150" value="70" oninput="document.getElementById('ob-range-val').textContent=this.value+' kg'"/>
        <div class="ob-range-value" id="ob-range-val">70 kg</div></div>`;
      break;

    case "goal": {
      const isFemale = (gender||"").toLowerCase()==="female";
      const goals = isFemale
        ? [["🏋️ Toned Body","toned body"],["🍑 Glute Growth","glute growth"],["✨ Lean Physique","lean physique"],["⏳ Hourglass","hourglass figure"]]
        : [["🔥 Fat Loss","fat loss"],["💪 Muscle Gain","muscle gain"],["🏆 Strength","strength"],["🏃 General Fitness","general fitness"]];
      area.innerHTML=`<div class="ob-options">${goals.map(([l,v])=>`<button class="ob-option" onclick="selectObOption(this,'${v}')">${l}</button>`).join("")}</div>`;
      break;
    }

    case "level":
      area.innerHTML=`<div class="ob-options">
        <button class="ob-option" onclick="selectObOption(this,'beginner')">🌱 Beginner</button>
        <button class="ob-option" onclick="selectObOption(this,'intermediate')">💪 Intermediate</button>
        <button class="ob-option" onclick="selectObOption(this,'advanced')">🔥 Advanced</button>
      </div>`;
      break;

    case "place":
      area.innerHTML=`<div class="ob-options">
        <button class="ob-option" onclick="selectObOption(this,'gym')">🏋️ Gym</button>
        <button class="ob-option" onclick="selectObOption(this,'home')">🏠 Home</button>
      </div>`;
      break;

    case "days":
      area.innerHTML=`<div class="ob-options">
        <button class="ob-option" onclick="selectObOption(this,'3')">3 days / week</button>
        <button class="ob-option" onclick="selectObOption(this,'4')">4 days / week</button>
        <button class="ob-option" onclick="selectObOption(this,'5')">5 days / week</button>
        <button class="ob-option" onclick="selectObOption(this,'6')">6 days / week</button>
      </div>`;
      break;

    case "injuries":
      area.innerHTML=`<div class="ob-options">
        <button class="ob-option" id="ob-inj-no"  onclick="selectInjury('no')">✅ No injuries</button>
        <button class="ob-option" id="ob-inj-yes" onclick="selectInjury('yes')">⚠️ Yes, I do</button>
      </div>
      <div id="ob-injury-detail" class="hidden" style="margin-top:10px">
        <input class="ob-text-input" id="ob-injury-text" placeholder="Describe briefly (e.g. left knee pain)"/>
      </div>`;
      break;

    case "plays_sport":
      area.innerHTML=`<div class="ob-options">
        <button class="ob-option" onclick="selectObOption(this,'yes')">🏆 Yes, I play a sport</button>
        <button class="ob-option" onclick="selectObOption(this,'no')">🏋️ No, gym only</button>
      </div>`;
      break;
  }
}

function updateAgePreview() {
  const d=parseInt(document.getElementById("ob-dob-day")?.value);
  const m=parseInt(document.getElementById("ob-dob-month")?.value);
  const y=parseInt(document.getElementById("ob-dob-year")?.value);
  if(d&&m&&y){
    const age=Math.floor((Date.now()-new Date(y,m-1,d).getTime())/(365.25*24*3600*1000));
    const el=document.getElementById("ob-age-preview");
    if(el) el.textContent=`Age: ${age} years old`;
  }
}

function selectObOption(btn, value) {
  btn.closest(".ob-options").querySelectorAll(".ob-option").forEach(b=>b.classList.remove("selected"));
  btn.classList.add("selected");
  btn.dataset.value = value;
}

function selectInjury(choice) {
  document.getElementById("ob-inj-no")?.classList.toggle("selected",  choice==="no");
  document.getElementById("ob-inj-yes")?.classList.toggle("selected", choice==="yes");
  document.getElementById("ob-injury-detail")?.classList.toggle("hidden", choice!=="yes");
}

function getObValue(inputType, areaId) {
  const area = areaId || "ob-input-area";
  switch(inputType) {
    case "text": return (document.getElementById("ob-val")?.value||"").trim();
    case "dob": {
      const d=document.getElementById("ob-dob-day")?.value;
      const m=document.getElementById("ob-dob-month")?.value;
      const y=document.getElementById("ob-dob-year")?.value;
      if(!d||!m||!y) return "";
      return `${y}-${String(m).padStart(2,"0")}-${String(d).padStart(2,"0")}`;
    }
    case "height": case "weight": return document.getElementById("ob-val")?.value||"";
    case "injuries": {
      const no  = document.getElementById("ob-inj-no")?.classList.contains("selected");
      const yes = document.getElementById("ob-inj-yes")?.classList.contains("selected");
      if(no)  return "none";
      if(yes) return (document.getElementById("ob-injury-text")?.value||"").trim()||"unspecified";
      return "";
    }
    default: {
      const sel = document.querySelector(`#${area} .ob-option.selected`);
      return sel?.dataset.value || "";
    }
  }
}

async function onboardingNext() {
  const value = getObValue(onboardingInputType, "ob-input-area");
  if (!value) {
    const e=document.getElementById("ob-error");
    e.textContent = onboardingInputType==="text" ? "Please type your name" : "Please make a selection";
    e.classList.remove("hidden"); return;
  }
  document.getElementById("ob-error").classList.add("hidden");
  if (onboardingField==="gender") onboardingGender = value;

  const btn=document.getElementById("ob-next-btn");
  btn.disabled=true; btn.textContent="…";
  try {
    const res=await fetch(`${API}/api/chat`,{
      method:"POST",
      headers:{"Content-Type":"application/json","Authorization":`Bearer ${authToken}`},
      body:JSON.stringify({message:value})
    });
    if(res.status===401){doLogout();return;}
    const data=await res.json();
    handleResponse(data);
  } catch {
    document.getElementById("ob-error").textContent="Connection error";
    document.getElementById("ob-error").classList.remove("hidden");
  } finally {
    btn.disabled=false; btn.textContent="Continue →";
  }
}

function hideOnboarding() { document.getElementById("onboarding-overlay").classList.add("hidden"); }

// ── SPORT ONBOARDING ──────────────────────────────────────────────────
let sportObState = {}; // local client-side state tracker

async function startSportOnboarding() {
  sportObState = {profile:{}, currentField:"sport_select", sport:null};
  document.getElementById("sport-onboarding-overlay").classList.remove("hidden");
  renderSportQuestion("sport_select");
}

function renderSportQuestion(field) {
  sportObField     = field;
  sportObInputType = SPORT_QUESTIONS[field]?.input_type || "text";
  const q = SPORT_QUESTIONS[field] || {reply:`Tell me about ${field}`};

  // Progress
  const sport = sportObState.sport;
  const order = SPORT_FIELD_ORDERS[sport] || SPORT_FIELD_ORDERS.default;
  const idx   = order.indexOf(field);
  const total = order.length;
  document.getElementById("sob-progress-fill").style.width = ((Math.max(0,idx)/total)*100)+"%";
  document.getElementById("sob-step-label").textContent = `Step ${idx+1} of ${total}`;
  document.getElementById("sob-question").textContent = q.reply;
  document.getElementById("sob-error").classList.add("hidden");

  renderSportInput(sportObInputType, sport);
}

function renderSportInput(inputType, sport) {
  const area = document.getElementById("sob-input-area");
  area.innerHTML = "";

  switch(inputType) {
    case "sport_select":
      area.innerHTML=`<div class="ob-options">
        <button class="ob-option" onclick="selectSobOption(this,'cricket')">🏏 Cricket</button>
        <button class="ob-option" onclick="selectSobOption(this,'football')">⚽ Football</button>
        <button class="ob-option" onclick="selectSobOption(this,'running')">🏃 Running</button>
      </div>`;
      break;
    case "cricket_role":
      area.innerHTML=`<div class="ob-options">
        <button class="ob-option" onclick="selectSobOption(this,'batsman')">🏏 Batsman</button>
        <button class="ob-option" onclick="selectSobOption(this,'bowler')">⚡ Bowler</button>
        <button class="ob-option" onclick="selectSobOption(this,'all-rounder')">🌟 All-rounder</button>
        <button class="ob-option" onclick="selectSobOption(this,'wicketkeeper')">🧤 Wicketkeeper</button>
      </div>`;
      break;
    case "bowling_type":
      area.innerHTML=`<div class="ob-options">
        <button class="ob-option" onclick="selectSobOption(this,'fast')">⚡ Fast</button>
        <button class="ob-option" onclick="selectSobOption(this,'medium pace')">🎯 Medium pace</button>
        <button class="ob-option" onclick="selectSobOption(this,'spin')">🌀 Spin</button>
      </div>`;
      break;
    case "match_frequency":
      area.innerHTML=`<div class="ob-options">
        <button class="ob-option" onclick="selectSobOption(this,'weekly')">📅 Weekly</button>
        <button class="ob-option" onclick="selectSobOption(this,'fortnightly')">📆 Fortnightly</button>
        <button class="ob-option" onclick="selectSobOption(this,'monthly')">🗓️ Monthly</button>
        <button class="ob-option" onclick="selectSobOption(this,'tournament')">🏆 Tournament season</button>
      </div>`;
      break;
    case "primary_focus":
      area.innerHTML=`<div class="ob-options">
        <button class="ob-option" onclick="selectSobOption(this,'strength')">💪 Strength</button>
        <button class="ob-option" onclick="selectSobOption(this,'speed')">⚡ Speed & Agility</button>
        <button class="ob-option" onclick="selectSobOption(this,'endurance')">🏃 Endurance</button>
        <button class="ob-option" onclick="selectSobOption(this,'injury prevention')">🛡️ Injury Prevention</button>
      </div>`;
      break;
    case "sport_injuries":
      area.innerHTML=`<div class="ob-options">
        <button class="ob-option" onclick="selectSobOption(this,'none')">✅ None</button>
        <button class="ob-option" onclick="selectSobOption(this,'shoulder')">💪 Shoulder</button>
        <button class="ob-option" onclick="selectSobOption(this,'knee')">🦵 Knee</button>
        <button class="ob-option" onclick="selectSobOption(this,'hamstring')">🏃 Hamstring</button>
        <button class="ob-option" onclick="selectSobOption(this,'back')">🔙 Lower back</button>
        <button class="ob-option" onclick="selectSobOption(this,'ankle')">🦶 Ankle</button>
      </div>`;
      break;
    case "football_position":
      area.innerHTML=`<div class="ob-options">
        <button class="ob-option" onclick="selectSobOption(this,'goalkeeper')">🥅 Goalkeeper</button>
        <button class="ob-option" onclick="selectSobOption(this,'defender')">🛡️ Defender</button>
        <button class="ob-option" onclick="selectSobOption(this,'midfielder')">🔄 Midfielder</button>
        <button class="ob-option" onclick="selectSobOption(this,'forward')">⚡ Forward</button>
      </div>`;
      break;
    case "distance_type":
      area.innerHTML=`<div class="ob-options">
        <button class="ob-option" onclick="selectSobOption(this,'sprint')">⚡ Sprint (100m–400m)</button>
        <button class="ob-option" onclick="selectSobOption(this,'5k')">🏃 5K</button>
        <button class="ob-option" onclick="selectSobOption(this,'10k')">🏃 10K</button>
        <button class="ob-option" onclick="selectSobOption(this,'half marathon')">🏅 Half Marathon</button>
        <button class="ob-option" onclick="selectSobOption(this,'marathon')">🎽 Marathon</button>
      </div>`;
      break;
    case "weekly_mileage":
      area.innerHTML=`<div class="ob-options">
        <button class="ob-option" onclick="selectSobOption(this,'less than 20km')">Under 20km</button>
        <button class="ob-option" onclick="selectSobOption(this,'20-40km')">20–40km</button>
        <button class="ob-option" onclick="selectSobOption(this,'40-60km')">40–60km</button>
        <button class="ob-option" onclick="selectSobOption(this,'60km+')">60km+</button>
      </div>`;
      break;
    default:
      area.innerHTML=`<input class="ob-text-input" id="sob-text-val" type="text" placeholder="Your answer…"/>`;
      setTimeout(()=>document.getElementById("sob-text-val")?.focus(),100);
  }
}

function selectSobOption(btn, value) {
  btn.closest(".ob-options").querySelectorAll(".ob-option").forEach(b=>b.classList.remove("selected"));
  btn.classList.add("selected");
  btn.dataset.value = value;
}

function getSobValue() {
  const sel = document.querySelector("#sob-input-area .ob-option.selected");
  if (sel) return sel.dataset.value;
  const txt = document.getElementById("sob-text-val");
  return (txt?.value||"").trim();
}

async function sportOnboardingNext() {
  const value = getSobValue();
  if (!value) {
    const e=document.getElementById("sob-error");
    e.textContent="Please make a selection"; e.classList.remove("hidden"); return;
  }
  document.getElementById("sob-error").classList.add("hidden");

  // Save to local state
  sportObState.profile[sportObField] = value;
  if (sportObField==="sport_select") { sportObState.sport=value; }

  // Skip bowling_type if not bowler/all-rounder
  if (sportObState.sport==="cricket" &&
      sportObField==="role" &&
      !["bowler","all-rounder"].includes(value.toLowerCase())) {
    sportObState.profile["bowling_type"] = "n/a";
  }

  const sport     = sportObState.sport;
  const order     = SPORT_FIELD_ORDERS[sport] || SPORT_FIELD_ORDERS.default;
  const nextField = order.find(f => !(f in sportObState.profile));

  if (!nextField) {
    // Done — send to server
    const btn=document.getElementById("sob-next-btn");
    btn.disabled=true; btn.textContent="Saving…";
    try {
      const res = await fetch(`${API}/api/sport-onboard`,{
        method:"POST",
        headers:{"Content-Type":"application/json","Authorization":`Bearer ${authToken}`},
        body: JSON.stringify({sport, profile: sportObState.profile})
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error||"Failed");
      hideSportOnboarding();
      currentUser = {...(currentUser||{}), plays_sport:true, sport:data.sport, sport_profile:data.sport_profile};
      addMessage(data.reply,"bot");
      showToast(`🏆 ${sport.charAt(0).toUpperCase()+sport.slice(1)} mode activated!`);
      setWorkoutMode("sport");
      updateProfileSportBadge();
      showQuickActions();
    } catch(err) {
      document.getElementById("sob-error").textContent = err.message||"Error saving. Try again.";
      document.getElementById("sob-error").classList.remove("hidden");
    } finally {
      const btn=document.getElementById("sob-next-btn");
      btn.disabled=false; btn.textContent="Continue →";
    }
    return;
  }

  renderSportQuestion(nextField);
}

// Simplified API endpoint for sport onboarding — batch save
// (matches the new /api/sport-onboard POST endpoint in app.py)

function hideSportOnboarding() { document.getElementById("sport-onboarding-overlay").classList.add("hidden"); }

function startSportOnboardingFromProfile() { startSportOnboarding(); }

function updateProfileSportBadge() {
  const sport = currentUser?.sport;
  const badge = document.getElementById("profile-sport-badge");
  const activateWrap = document.getElementById("activate-sport-wrap");
  if (sport && badge) {
    const icons = {cricket:"🏏",football:"⚽",running:"🏃"};
    badge.textContent = `${icons[sport]||"🏆"} ${sport.charAt(0).toUpperCase()+sport.slice(1)} Mode Active`;
    badge.classList.remove("hidden");
    activateWrap?.classList.add("hidden");
  } else if (activateWrap) {
    badge?.classList.add("hidden");
    activateWrap.classList.remove("hidden");
  }
}

// ── RECOVERY ──────────────────────────────────────────────────────────
function selectRecovery(key, value, optsId) {
  recoveryInputs[key] = value;
  document.getElementById(optsId)?.querySelectorAll(".ob-option").forEach(b=>{
    b.classList.toggle("selected", b.onclick?.toString().includes(`'${value}'`));
  });
  // visually select clicked button
  event.target.closest(".ob-option").classList.add("selected");
  // deselect siblings
  const parent = event.target.closest(".ob-options");
  parent?.querySelectorAll(".ob-option").forEach(b=>{
    if(b!==event.target.closest(".ob-option")) b.classList.remove("selected");
  });
  updateRecoveryCockpitPreview();
}

async function submitRecovery() {
  const r = recoveryInputs;
  if (!r.sleep||!r.squality||!r.fatigue||!r.soreness||!r.load) {
    document.getElementById("recovery-error").classList.remove("hidden"); return;
  }
  document.getElementById("recovery-error").classList.add("hidden");
  const btn=document.getElementById("recovery-submit-btn");
  btn.disabled=true; btn.querySelector("span").textContent="Calculating…";
  try {
    const data = await apiFetch("/api/recovery",{
      method:"POST",
      body:JSON.stringify({
        sleep_hours:parseFloat(r.sleep),
        sleep_quality:parseInt(r.squality),
        fatigue:parseInt(r.fatigue),
        soreness:parseInt(r.soreness),
        prev_load:parseInt(r.load)
      })
    });
    showRecoveryScore(data);
    loadRecoveryBanner();
    showToast(`📊 Recovery: ${data.score}/100 — ${data.zone.toUpperCase()}`);
  } catch { showToast("❌ Failed to save. Try again."); }
  finally { btn.disabled=false; btn.querySelector("span").textContent="Calculate Recovery Score"; }
}

function showRecoveryScore(data) {
  const card=document.getElementById("recovery-score-card");
  card.classList.remove("hidden");
  card.dataset.zone = data.zone || "green";
  card.style.setProperty("--recovery-score", data.score || 0);
  const dot  = document.getElementById("rs-zone-dot");
  const score= document.getElementById("rs-score");
  const lbl  = document.getElementById("rs-label");
  const msg  = document.getElementById("rs-message");
  dot.className   = `rs-zone-dot ${data.zone}`;
  score.className = `rs-score ${data.zone}`;
  score.textContent = data.score;
  lbl.textContent = {green:"🟢 Full Recovery",yellow:"🟡 Moderate",red:"🔴 Low Recovery"}[data.zone]||data.zone;
  msg.textContent = data.message;
  updateRecoveryCockpitScore(data);
}

function updateRecoveryCockpitPreview() {
  const sleepRead = document.getElementById("recovery-sleep-read");
  const trend = document.getElementById("recovery-trend");
  const aiNote = document.getElementById("recovery-ai-note");
  const bodyMap = document.getElementById("recovery-body-map");
  if (!sleepRead || !trend || !aiNote) return;
  const sleep = Number(recoveryInputs.sleep || 0);
  const squality = Number(recoveryInputs.squality || 0);
  const fatigue = Number(recoveryInputs.fatigue || 0);
  const soreness = Number(recoveryInputs.soreness || 0);
  sleepRead.textContent = sleep >= 8 && squality >= 4 ? "Deep" : sleep >= 6 ? "Manageable" : sleep ? "Restricted" : "Pending";
  trend.textContent = fatigue <= 2 && soreness <= 2 && sleep >= 7 ? "Rising" : fatigue >= 4 || soreness >= 4 ? "Suppressed" : "Stabilizing";
  bodyMap?.classList.toggle("fatigue-high", soreness >= 4 || fatigue >= 4);
  bodyMap?.classList.toggle("fatigue-mid", (soreness === 3 || fatigue === 3) && !(soreness >= 4 || fatigue >= 4));
  aiNote.textContent = fatigue >= 4 || soreness >= 4
    ? "Recovery load is elevated. A mobility, zone-2, or technique session will preserve progress without digging a deeper fatigue hole."
    : sleep >= 7 && squality >= 4
      ? "Signals look strong. You can handle a higher-quality session if warm-up readiness matches this check-in."
      : "Readiness is forming. Finish the check-in for a tighter intensity call and recovery recommendation.";
}

function updateRecoveryCockpitScore(data) {
  const score = Number(data?.score || 0);
  const zone = data?.zone || "green";
  const hydration = document.getElementById("recovery-hydration");
  const ns = document.getElementById("recovery-ns");
  const trend = document.getElementById("recovery-trend");
  const aiNote = document.getElementById("recovery-ai-note");
  const bodyMap = document.getElementById("recovery-body-map");
  if (hydration) hydration.textContent = score >= 75 ? "Optimal" : score >= 55 ? "Support" : "Prioritize";
  if (ns) ns.textContent = zone === "green" ? "Primed" : zone === "yellow" ? "Guarded" : "Downshift";
  if (trend) trend.textContent = zone === "green" ? "Rising" : zone === "yellow" ? "Stable" : "Suppressed";
  bodyMap?.classList.toggle("zone-green", zone === "green");
  bodyMap?.classList.toggle("zone-yellow", zone === "yellow");
  bodyMap?.classList.toggle("zone-red", zone === "red");
  if (aiNote) {
    aiNote.textContent = zone === "green"
      ? "Recovery systems are online. Strength, power, or performance work is appropriate if technique feels crisp."
      : zone === "yellow"
        ? "Keep the session productive but controlled. Cap volume, extend warm-up, and avoid chasing max intensity."
        : "Use today to restore. Mobility, breath work, walking, and easy movement will compound better than hard loading.";
  }
}

async function loadRecoveryLatest() {
  try {
    const data = await apiFetch("/api/recovery/latest");
    if (data.score) showRecoveryScore(data);
    const readiness = document.getElementById("coach-readiness-value");
    const ring = document.getElementById("coach-readiness-ring");
    const recoveryChip = document.getElementById("coach-recovery-chip");
    const fatigueChip = document.getElementById("coach-fatigue-chip");
    const recoveryStatus = document.getElementById("coach-recovery-status");
    if (readiness) readiness.textContent = data.score;
    if (ring) {
      ring.style.setProperty("--coach-ready", data.score);
      ring.dataset.zone = data.zone;
    }
    if (recoveryChip) recoveryChip.textContent = `Recovery: ${data.zone}`;
    if (fatigueChip) fatigueChip.textContent = data.zone === "green" ? "Fatigue: low" : data.zone === "yellow" ? "Fatigue: moderate" : "Fatigue: high";
    if (recoveryStatus) recoveryStatus.textContent = data.zone === "green" ? "Ready" : data.zone === "yellow" ? "Controlled" : "Restore";
  } catch {}
}

async function loadRecoveryBanner() {
  try {
    const data = await apiFetch("/api/recovery/latest");
    if (!data.zone) return;
    const banner = document.getElementById("recovery-banner");
    banner.classList.remove("hidden","yellow","red");
    if (data.zone==="yellow") banner.classList.add("yellow");
    if (data.zone==="red")    banner.classList.add("red");
    const icons = {green:"🟢",yellow:"🟡",red:"🔴"};
    const msgs  = {green:"Full recovery — go hard today!",yellow:"Moderate recovery — pace yourself",red:"Low recovery — mobility session today"};
    document.getElementById("recovery-banner-icon").textContent = icons[data.zone];
    document.getElementById("recovery-banner-text").textContent = `Recovery: ${data.score}/100 — ${msgs[data.zone]}`;
  } catch {}
}

// ── WORKOUT UI ────────────────────────────────────────────────────────
function showWorkoutProgress(data) {
  const bar=document.getElementById("workout-progress-bar");
  bar.classList.remove("hidden");
  document.querySelector(".chat-shell")?.classList.add("workout-live");
  const ei=data.current_exercise_index||0, tot=data.total_exercises||5;
  const sn=data.current_set||1, ts=data.current_exercise?.sets||3;
  document.getElementById("wpb-exercise").textContent=`Exercise ${ei+1}/${tot}`;
  document.getElementById("wpb-set").textContent=`Set ${sn}/${ts}`;
  const pct=((ei/tot)+(sn/(ts*tot)))*100;
  document.getElementById("wpb-fill").style.width=`${Math.min(pct,98)}%`;
}

function exerciseMotionType(exercise) {
  const hay = `${exercise?.name || ""} ${exercise?.muscle || ""} ${exercise?.category || ""}`.toLowerCase();
  if (hay.includes("curl") || hay.includes("bicep")) return "curl";
  if (hay.includes("squat") || hay.includes("lunge") || hay.includes("leg") || hay.includes("glute") || hay.includes("thrust")) return "squat";
  if (hay.includes("push-up") || hay.includes("pushup") || hay.includes("push up") || hay.includes("plank")) return "pushup";
  if (hay.includes("press") || hay.includes("shoulder") || hay.includes("overhead")) return "press";
  if (hay.includes("deadlift") || hay.includes("hinge") || hay.includes("romanian")) return "deadlift";
  if (hay.includes("jack") || hay.includes("high knee") || hay.includes("mountain") || hay.includes("run") || hay.includes("sprint") || hay.includes("shuffle") || hay.includes("agility") || hay.includes("drill")) return "cardio";
  return "squat";
}

function exerciseVizTip(type, exercise) {
  const tips = {
    curl: "Lock the elbow path and control the lowering phase.",
    squat: "Track knees over toes and own the bottom position.",
    pushup: "Keep ribs stacked and press the floor away.",
    press: "Brace the core before every overhead drive.",
    deadlift: "Hinge from the hips and keep the spine long.",
    cardio: "Stay light on the feet and keep rhythm consistent.",
  };
  const progression = Array.isArray(exercise?.progression) ? exercise.progression[0] : "";
  return progression || tips[type] || "Control the movement with clean intent.";
}

function exerciseMuscleTargets(type, exercise) {
  const hay = `${exercise?.name || ""} ${exercise?.muscle || ""}`.toLowerCase();
  if (type === "curl") return ["Biceps", "Forearms"];
  if (type === "press") return ["Shoulders", "Triceps", "Core"];
  if (type === "pushup") return hay.includes("plank") ? ["Core", "Shoulders"] : ["Chest", "Triceps", "Core"];
  if (type === "deadlift") return ["Hamstrings", "Glutes", "Back"];
  if (type === "cardio") return hay.includes("agility") || hay.includes("shuffle") ? ["Calves", "Glutes", "Agility"] : ["Calves", "Hamstrings", "Cardio"];
  return ["Quads", "Glutes", "Hamstrings"];
}

function exerciseMotionCue(type) {
  return {
    curl: "Elbow flexion path",
    squat: "Down / drive up",
    pushup: "Rigid body press",
    press: "Vertical power line",
    deadlift: "Hip hinge pattern",
    cardio: "Fast foot rhythm",
  }[type] || "Controlled motion";
}

function renderExerciseHologram(type, exercise, zone) {
  const muscle = escapeHtml(exercise?.muscle || "primary movers");
  const targets = exerciseMuscleTargets(type, exercise);
  return `
    <div class="holo-stage motion-${type} zone-${escapeHtml(zone || "green")}">
      <div class="holo-particles"><i></i><i></i><i></i><i></i><i></i></div>
      <div class="holo-ring ring-a"></div>
      <div class="holo-ring ring-b"></div>
      <svg class="holo-athlete" viewBox="0 0 220 180" aria-hidden="true">
        <defs>
          <filter id="holoGlow">
            <feGaussianBlur stdDeviation="2.2" result="blur"/>
            <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
          </filter>
          <linearGradient id="holoLine" x1="0" x2="1">
            <stop offset="0%" stop-color="#60a5fa"/>
            <stop offset="52%" stop-color="#a78bfa"/>
            <stop offset="100%" stop-color="#10b981"/>
          </linearGradient>
        </defs>
        <g class="athlete-body" filter="url(#holoGlow)">
          <circle class="joint head" cx="110" cy="33" r="10"/>
          <line class="bone torso" x1="110" y1="45" x2="110" y2="86"/>
          <g class="arms">
            <line class="bone upper-arm left" x1="110" y1="56" x2="82" y2="76"/>
            <line class="bone forearm left" x1="82" y1="76" x2="70" y2="103"/>
            <circle class="weight left" cx="70" cy="106" r="6"/>
            <line class="bone upper-arm right" x1="110" y1="56" x2="138" y2="76"/>
            <line class="bone forearm right" x1="138" y1="76" x2="150" y2="103"/>
            <circle class="weight right" cx="150" cy="106" r="6"/>
          </g>
          <g class="legs">
            <line class="bone thigh left" x1="110" y1="86" x2="86" y2="122"/>
            <line class="bone shin left" x1="86" y1="122" x2="72" y2="158"/>
            <line class="bone thigh right" x1="110" y1="86" x2="134" y2="122"/>
            <line class="bone shin right" x1="134" y1="122" x2="148" y2="158"/>
          </g>
          <ellipse class="muscle-glow muscle-arms" cx="110" cy="79" rx="54" ry="28"/>
          <ellipse class="muscle-glow muscle-legs" cx="110" cy="129" rx="58" ry="34"/>
          <ellipse class="muscle-glow muscle-core" cx="110" cy="76" rx="24" ry="34"/>
          <circle class="target-dot target-a" cx="82" cy="76" r="5"/>
          <circle class="target-dot target-b" cx="134" cy="122" r="5"/>
          <circle class="target-dot target-c" cx="110" cy="76" r="5"/>
        </g>
        <path class="motion-trail motion-arrow" d="M45 142 C76 102, 145 102, 176 142"/>
        <path class="motion-guide guide-up" d="M184 140 L184 72"/>
        <path class="motion-guide guide-down" d="M36 70 L36 138"/>
        <line class="depth-line" x1="48" y1="144" x2="172" y2="144"/>
      </svg>
      <div class="holo-scan"></div>
      <div class="motion-cue">${escapeHtml(exerciseMotionCue(type))}</div>
      <div class="target-stack">${targets.map((target) => `<span>${escapeHtml(target)}</span>`).join("")}</div>
      <div class="holo-caption"><strong>${muscle}</strong><span>muscle activation</span></div>
    </div>
  `;
}

function showExerciseDemo(exercise, idx, total, zone) {
  if (!exercise) return;
  const card=document.getElementById("exercise-demo-card");
  card.classList.remove("hidden");
  const type = exerciseMotionType(exercise);
  card.dataset.motion = type;
  document.getElementById("demo-name").textContent  = exercise.name;
  document.getElementById("demo-sets").textContent  = `${exercise.sets} sets`;
  document.getElementById("demo-reps").textContent  = exercise.reps+" reps";
  document.getElementById("demo-rest").textContent  = `⏱ ${exercise.rest}`;
  document.getElementById("demo-muscle").textContent= `💪 ${exercise.muscle||""}`;
  document.getElementById("demo-weight").textContent= `🏋️ ${exercise.weight_guide||""}`;
  // Zone badge if provided
  if (zone) {
    const z=document.getElementById("demo-muscle");
    const zIcons={green:"🟢",yellow:"🟡",red:"🔴"};
    z.textContent=`${zIcons[zone]||""} ${exercise.muscle||""}`;
  }
  document.getElementById("demo-rest").textContent = `Rest ${exercise.rest}`;
  document.getElementById("demo-muscle").textContent = zone ? `Recovery ${zone.toUpperCase()}: ${exercise.muscle||"full body"}` : `Targets: ${exercise.muscle||"full body"}`;
  document.getElementById("demo-weight").textContent = `AI tip: ${exerciseVizTip(type, exercise)}`;
  const wrap = card.querySelector(".demo-video-wrap");
  if (wrap) wrap.innerHTML = renderExerciseHologram(type, exercise, zone);
}

function hideWorkoutUI() {
  document.getElementById("workout-progress-bar").classList.add("hidden");
  document.getElementById("exercise-demo-card").classList.add("hidden");
  document.getElementById("rest-timer").classList.add("hidden");
  document.querySelector(".chat-shell")?.classList.remove("workout-live");
  clearInterval(restInterval);
}
function hideQuickActions() { document.getElementById("quick-actions").style.display="none"; }
function showQuickActions() {
  const qa=document.getElementById("quick-actions");
  qa.style.display="flex";
  // Update sport button if sport mode
  const hasSport = currentUser?.plays_sport && currentUser?.sport;
  const existSportBtn = document.getElementById("qa-sport-btn");
  if (hasSport && !existSportBtn) {
    const sport=currentUser.sport;
    const icons={cricket:"🏏",football:"⚽",running:"🏃"};
    const btn=document.createElement("button");
    btn.id="qa-sport-btn"; btn.className="qa-btn qa-sport";
    btn.onclick=()=>{ setWorkoutMode("sport"); startWorkout(); };
    btn.textContent=`${icons[sport]||"🏆"} ${sport.charAt(0).toUpperCase()+sport.slice(1)} Session`;
    qa.insertBefore(btn, qa.children[1]);
  }
}

function showWorkoutButtons() {
  const el=document.getElementById("workout-action-btns");
  el.classList.remove("hidden");
  el.innerHTML=`<button class="wab-btn wab-next" onclick="workoutAction('next')">✅ Next Set</button>
    <button class="wab-btn wab-done" onclick="workoutAction('done')">🏁 End Workout</button>`;
  document.getElementById("feedback-btns").classList.add("hidden");
}
function hideWorkoutButtons() { document.getElementById("workout-action-btns").classList.add("hidden"); }

function showFeedbackButtons() {
  document.getElementById("workout-action-btns").classList.add("hidden");
  const fb=document.getElementById("feedback-btns");
  fb.classList.remove("hidden");
  fb.innerHTML=`<p class="feedback-label">How did that feel?</p>
    <div style="display:flex;gap:10px;justify-content:center">
      <button class="fb-btn fb-easy" onclick="workoutAction('easy')">😄 Easy</button>
      <button class="fb-btn fb-hard" onclick="workoutAction('hard')">😤 Hard</button>
    </div>`;
}
function hideFeedbackButtons() { document.getElementById("feedback-btns").classList.add("hidden"); }
function showDoneButton() {
  const el=document.getElementById("workout-action-btns");
  el.classList.remove("hidden");
  el.innerHTML=`<button class="wab-btn wab-next" onclick="workoutAction('done')" style="background:var(--green)">🏁 Log Workout</button>`;
}

// ── REST TIMER ────────────────────────────────────────────────────────
function startRestTimer(restStr) {
  clearInterval(restInterval);
  if (!restStr) return;
  const secs=parseInt(restStr)||60;
  let rem=secs;
  const timer=document.getElementById("rest-timer");
  timer.classList.remove("hidden");
  updateRestDisplay(rem,secs);
  restInterval=setInterval(()=>{
    rem--;
    updateRestDisplay(rem,secs);
    if(rem<=0){
      clearInterval(restInterval);
      timer.classList.add("hidden");
      speak("Rest done. Let's go!",currentUser?.gender||onboardingGender);
    }
  },1000);
}
function updateRestDisplay(r,total) {
  document.getElementById("rt-count").textContent=r;
  document.getElementById("rt-fill").style.width=`${(r/total)*100}%`;
}
function skipTimer() { clearInterval(restInterval); document.getElementById("rest-timer").classList.add("hidden"); }

// ── VOICE ─────────────────────────────────────────────────────────────
function speak(text,gender) {
  if (!window.speechSynthesis) return;
  speechSynthesis.cancel();
  const utt=new SpeechSynthesisUtterance(text.replace(/[*_`#]/g,""));
  const voices=speechSynthesis.getVoices();
  if ((gender||"").toLowerCase()==="female") {
    const fv=voices.find(v=>v.name.includes("Samantha")||v.name.includes("Victoria")||v.lang==="en-US"&&v.name.toLowerCase().includes("f"));
    if(fv) utt.voice=fv;
  } else {
    const mv=voices.find(v=>v.lang==="en-US");
    if(mv) utt.voice=mv;
  }
  speechSynthesis.speak(utt);
}
function speakResponse(data,gender) {
  if (["workout_start","workout_next_set","workout_next_exercise"].includes(data.type))
    speak(data.reply.split("\n")[0].replace(/[*_]/g,""),gender);
}
function initVoiceInput() {
  const SR=window.SpeechRecognition||window.webkitSpeechRecognition;
  if(!SR){document.getElementById("voice-btn").style.display="none";return;}
  voiceRec=new SR();
  voiceRec.continuous=false; voiceRec.interimResults=false; voiceRec.lang="en-US";
  voiceRec.onresult=(e)=>{
    document.getElementById("message").value=e.results[0][0].transcript;
    stopListening(); setTimeout(()=>sendMessage(),300);
  };
  voiceRec.onend=()=>stopListening();
  voiceRec.onerror=()=>stopListening();
}
function toggleVoice() {
  if(isListening){voiceRec?.stop();stopListening();}
  else{try{voiceRec?.start();isListening=true;document.getElementById("voice-btn").classList.add("listening");document.getElementById("voice-btn").textContent="🔴";}catch{}}
}
function stopListening() {
  isListening=false;
  const btn=document.getElementById("voice-btn");
  btn.classList.remove("listening"); btn.textContent="🎤";
}

// ── CALORIES ──────────────────────────────────────────────────────────
function switchCalTab(tab) {
  document.getElementById("cal-tab-text").classList.toggle("active",tab==="text");
  document.getElementById("cal-tab-photo").classList.toggle("active",tab==="photo");
  document.getElementById("cal-text-section").classList.toggle("hidden",tab!=="text");
  document.getElementById("cal-photo-section").classList.toggle("hidden",tab!=="photo");
}
async function analyzeCalories() {
  const food=document.getElementById("cal-food-input").value.trim();
  if(!food) return showToast("⚠️ Describe what you ate");
  showCalLoading(true);
  try{
    const data=await apiFetch("/api/calories",{method:"POST",body:JSON.stringify({food})});
    showCalResult(data.nutrition || data.analysis);
  }catch{showToast("❌ Failed. Try again.");}
  finally{showCalLoading(false);}
}
function handleFoodPhoto(ev) {
  const file=ev.target.files[0]; if(!file)return;
  const r=new FileReader();
  r.onload=(e)=>{foodPhotoBase64=e.target.result;document.getElementById("food-photo-preview").src=foodPhotoBase64;document.getElementById("photo-preview-wrap").classList.remove("hidden");};
  r.readAsDataURL(file);
}
async function analyzePhotoCalories() {
  if(!foodPhotoBase64)return showToast("⚠️ Upload a photo first");
  showCalLoading(true);
  try{
    const data=await apiFetch("/api/calories",{method:"POST",body:JSON.stringify({food:"uploaded food image",image_data:foodPhotoBase64})});
    showCalResult(data.nutrition || data.analysis);
  }catch{showToast("❌ Failed.");}
  finally{showCalLoading(false);}
}
function showCalLoading(show){
  document.getElementById("cal-loading").classList.toggle("hidden",!show);
  if(show)document.getElementById("cal-result").classList.add("hidden");
}
function calPct(value,target){
  const n=Number(value)||0;
  const t=Number(target)||1;
  return Math.max(4,Math.min(100,Math.round((n/t)*100)));
}
function calBoolBadge(label,active){
  return `<div class="food-badge ${active?"active":"muted"}">${active?"OK":"--"} ${escapeHtml(label)}</div>`;
}
function macroRing(label,value,target,unit,cls){
  const pct=calPct(value,target);
  return `
    <div class="nutri-ring-card ${cls || ""}">
      <div class="nutri-ring" style="--pct:${pct}">
        <span>${escapeHtml(String(value))}</span>
      </div>
      <div>
        <strong>${escapeHtml(label)}</strong>
        <small>${escapeHtml(unit)} / target ${escapeHtml(String(target))}</small>
      </div>
    </div>`;
}
function nutrientBar(label,value,target,unit){
  const pct=calPct(value,target);
  return `
    <div class="nutrient-row">
      <div class="nutrient-row-top"><span>${escapeHtml(label)}</span><strong>${escapeHtml(String(value))}${escapeHtml(unit)}</strong></div>
      <div class="nutrient-track"><i style="width:${pct}%"></i></div>
    </div>`;
}
function showCalResult(result){
  const r=document.getElementById("cal-result");
  r.classList.remove("hidden");
  if(!result || typeof result==="string"){
    const text=String(result || "");
    document.getElementById("cal-result-body").innerHTML=text
      .replace(/\*\*(.*?)\*\*/g,"<strong>$1</strong>")
      .replace(/\*(.*?)\*/g,"<strong>$1</strong>")
      .replace(/\n/g,"<br>");
    return;
  }
  const m=result.macros || {};
  const t=result.macro_targets || {calories:600,protein:35,carbs:60,fats:22};
  const c=result.classification || {};
  const rec=result.recommendation || {};
  const score=Number(result.health_score || result.ai_food_score || 70);
  const items=(result.items || []).slice(0,4).map(item=>`
    <div class="detected-item">
      <span>${escapeHtml(item.name || "Food item")}</span>
      <small>${escapeHtml(item.portion || "Estimated")} - ${escapeHtml(String(item.calories || 0))} kcal</small>
    </div>`).join("");
  document.getElementById("cal-result-body").innerHTML=`
    <div class="nutrition-os">
      <section class="food-preview-card">
        <div class="scanner-frame">
          ${foodPhotoBase64 ? `<img src="${foodPhotoBase64}" alt="Food scan preview"/>` : `<div class="scanner-placeholder">AI</div>`}
          <span class="scan-line"></span>
        </div>
        <div class="food-preview-copy">
          <div class="eyebrow">Visual Nutrition Intelligence</div>
          <h3>${escapeHtml(result.detected_food || "Estimated Meal")}</h3>
          <div class="food-meta-row">
            <span>${escapeHtml(result.category || "Meal")}</span>
            <span>${escapeHtml(String(result.confidence || 78))}% confidence</span>
            <span>${escapeHtml(result.portion_size || "Estimated portion")}</span>
          </div>
          <div class="food-score-line">
            <div class="score-orb" style="--score:${score}"><strong>${score}</strong><span>AI score</span></div>
            <div>
              <strong>${escapeHtml(result.meal_quality || "Good")} meal quality</strong>
              <small>${escapeHtml(result.calorie_density || "Medium")} calorie density</small>
            </div>
          </div>
        </div>
      </section>

      <section class="macro-ring-grid">
        ${macroRing("Calories",m.calories || 0,t.calories || 600,"kcal","energy")}
        ${macroRing("Protein",m.protein || 0,t.protein || 35,"g","protein")}
        ${macroRing("Carbs",m.carbs || 0,t.carbs || 60,"g","carbs")}
        ${macroRing("Fats",m.fats || 0,t.fats || 22,"g","fats")}
      </section>

      <section class="nutrition-panel-grid">
        <div class="nutrition-widget">
          <div class="widget-title">Nutrient Detail</div>
          ${nutrientBar("Fiber",m.fiber || 0,10,"g")}
          ${nutrientBar("Sugar",m.sugar || 0,25,"g")}
          ${nutrientBar("Protein density",m.protein || 0,40,"g")}
          ${nutrientBar("Calorie load",m.calories || 0,t.calories || 600," kcal")}
        </div>
        <div class="nutrition-widget">
          <div class="widget-title">Goal Classification</div>
          <div class="food-badge-grid">
            ${calBoolBadge("Fat loss friendly",c.fat_loss_friendly)}
            ${calBoolBadge("Muscle gain",c.muscle_gain_friendly)}
            ${calBoolBadge("Lean physique",c.lean_physique_friendly)}
            ${calBoolBadge("Recovery food",c.recovery_food)}
            ${calBoolBadge("Endurance fuel",c.endurance_friendly)}
            ${calBoolBadge("High protein",c.high_protein)}
          </div>
        </div>
      </section>

      <section class="ai-reco-card">
        <div class="widget-title">AI Recommendation</div>
        <p>${escapeHtml(rec.summary || "Portion looks reasonable. Balance it around your training goal.")}</p>
        <div class="reco-grid">
          <div><span>Meal timing</span><strong>${escapeHtml(rec.timing || "Works best around your workout window.")}</strong></div>
          <div><span>Recovery</span><strong>${escapeHtml(rec.recovery || "Add lean protein for stronger recovery.")}</strong></div>
        </div>
      </section>
      <section class="nutrition-widget health-reco-card">
        <div class="widget-title">Health Recommendations</div>
        <div class="health-reco-grid">
          <div><span>Meal quality score</span><strong>${score}/100</strong></div>
          <div><span>Best goal fit</span><strong>${c.muscle_gain_friendly ? "Muscle gain" : c.fat_loss_friendly ? "Fat loss" : c.endurance_friendly ? "Endurance fuel" : "Balanced fitness"}</strong></div>
          <div><span>Next upgrade</span><strong>${(m.fiber || 0) < 5 ? "Add fiber and greens" : (m.protein || 0) < 20 ? "Add lean protein" : "Hydrate and time it well"}</strong></div>
        </div>
      </section>
      <section class="nutrition-widget suggested-meal-card">
        <div class="widget-title">Suggested Next Meal</div>
        <h3>${(m.protein || 0) < 25 ? "High-protein recovery plate" : "Micronutrient support plate"}</h3>
        <p>${(m.protein || 0) < 25 ? "Try chicken, paneer, tofu, eggs, or Greek yogurt with vegetables and a controlled carb portion." : "Your protein base looks solid. Add colorful vegetables, fruit, and water to round out recovery."}</p>
      </section>
      ${items ? `<section class="detected-stack"><div class="widget-title">Detected Items</div>${items}</section>` : ""}
    </div>`;
  document.getElementById("daily-calories-preview").textContent = `${m.calories || 0} kcal`;
  document.getElementById("daily-protein-preview").textContent = `${m.protein || 0}g`;
  document.getElementById("daily-carbs-preview").textContent = `${m.carbs || 0}g`;
  document.getElementById("daily-fats-preview").textContent = `${m.fats || 0}g`;
}

// ── PROGRESS ──────────────────────────────────────────────────────────
async function loadProgress() {
  try{
    const data=await apiFetch("/api/progress");
    document.getElementById("stat-weight-lost").textContent=data.total_weight_lost??"-";
    document.getElementById("stat-workouts").textContent=data.total_workouts??"-";
    document.getElementById("stat-streak").textContent=data.current_streak??"-";
    document.getElementById("stat-badges").textContent=data.badges?.length??"-";
    updateStreak(data.current_streak||0);
    renderWeightChart(data.weight);
    renderWeeklyChart(data.weekly_workouts);
    renderMuscleChart(data.muscle_distribution);
    renderHeatmap(data.heatmap);
    renderBadges(data.badges);
  }catch{}
}
function renderWeightChart(wd) {
  const c=document.getElementById("weightChart"); if(!c||!wd?.labels?.length)return;
  if(chartInst.weight)chartInst.weight.destroy();
  chartInst.weight=new Chart(c,{type:"line",data:{labels:wd.labels,datasets:[{label:"kg",data:wd.values,borderColor:"#a78bfa",backgroundColor:"rgba(124,58,237,.12)",tension:0.4,fill:true,pointRadius:4,pointBackgroundColor:"#a78bfa",pointBorderColor:"#0d0d1a",pointBorderWidth:2}]},options:chartOpts()});
}
function renderWeeklyChart(wd) {
  const c=document.getElementById("weeklyChart"); if(!c)return;
  if(chartInst.weekly)chartInst.weekly.destroy();
  chartInst.weekly=new Chart(c,{type:"bar",data:{labels:wd?.labels||[],datasets:[{label:"Workouts",data:wd?.values||[],backgroundColor:"rgba(16,185,129,.7)",borderColor:"#10b981",borderRadius:6}]},options:chartOpts(true)});
}
function renderMuscleChart(md) {
  const c=document.getElementById("muscleChart"); if(!c||!md?.length)return;
  if(chartInst.muscle)chartInst.muscle.destroy();
  const COLS=["#7c3aed","#10b981","#f59e0b","#3b82f6","#ef4444","#8b5cf6"];
  chartInst.muscle=new Chart(c,{type:"doughnut",data:{labels:md.map(m=>m.muscle),datasets:[{data:md.map(m=>m.count),backgroundColor:COLS,borderColor:"#12121e",borderWidth:2}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{position:"right",labels:{color:"#8b8ba8",font:{size:11},padding:10}}}}});
}
function renderHeatmap(hd) {
  const grid=document.getElementById("heatmap-grid"); if(!grid)return;
  grid.innerHTML="";
  const today=new Date();
  for(let i=89;i>=0;i--){
    const d=new Date(today); d.setDate(d.getDate()-i);
    const key=d.toISOString().split("T")[0];
    const cnt=hd?.[key]||0;
    const cell=document.createElement("div");
    cell.className=`heatmap-cell${cnt>0?` active-${Math.min(cnt,3)}`:""}`;
    cell.title=`${key}: ${cnt} workout${cnt!==1?"s":""}`;
    grid.appendChild(cell);
  }
}
function renderBadges(badges) {
  const c=document.getElementById("badges-container"); if(!c)return;
  if(!badges?.length){c.innerHTML=`<p class="no-badges">Complete workouts to earn badges! 🏆</p>`;return;}
  c.innerHTML=badges.map(b=>`<div class="badge-item"><span class="badge-icon">${b.badge_icon}</span><span class="badge-name">${b.badge_name}</span></div>`).join("");
}
function chartOpts(beginAtZero=false){
  return{responsive:true,maintainAspectRatio:false,
    plugins:{legend:{display:false}},
    scales:{
      x:{ticks:{color:"#64748b",font:{size:10},maxRotation:45},grid:{color:"rgba(255,255,255,.04)"}},
      y:{ticks:{color:"#64748b",font:{size:10}},grid:{color:"rgba(255,255,255,.04)"},beginAtZero}}};
}

// ── PROFILE ───────────────────────────────────────────────────────────
async function loadProfile() {
  try{
    const data=await apiFetch("/api/profile");
    document.getElementById("pf-name").value   =data.name||"";
    document.getElementById("pf-age").value    =data.age||"";
    document.getElementById("pf-gender").value =data.gender||"male";
    document.getElementById("pf-weight").value =data.weight||"";
    document.getElementById("pf-height").value =data.height||"";
    document.getElementById("pf-goal").value   =data.goal||"fat loss";
    document.getElementById("pf-level").value  =data.level||"beginner";
    document.getElementById("pf-place").value  =data.workout_place||"gym";
    document.getElementById("pf-days").value   =String(data.days_per_week||3);
    document.getElementById("pf-injuries").value=data.injuries||"";
    document.getElementById("profile-name-display").textContent=data.name||"Champion";
    document.getElementById("profile-goal-display").textContent=data.goal||"Fitness";
    document.getElementById("profile-avatar-display").textContent=data.gender?.toLowerCase()==="female"?"🏃‍♀️":"🏋️";
    currentUser=data;
    updateProfileCockpit(data);
    updateProfileSportBadge();
  }catch{}
}
function updateProfileCockpit(data) {
  const fields = ["name","age","gender","weight","height","goal","level","workout_place","days_per_week"];
  const complete = Math.round(fields.filter(k => data?.[k] !== undefined && data?.[k] !== null && data?.[k] !== "").length / fields.length * 100);
  const ring = document.getElementById("profile-completion-ring");
  const completeValue = document.getElementById("profile-completion-value");
  ring?.style.setProperty("--profile-complete", complete);
  if (completeValue) completeValue.textContent = `${complete}%`;
  const heightM = Number(data?.height || 0) / 100;
  const weight = Number(data?.weight || 0);
  const bmi = heightM && weight ? (weight / (heightM * heightM)).toFixed(1) : "--";
  const bmiEl = document.getElementById("profile-bmi");
  if (bmiEl) bmiEl.textContent = bmi;
  const days = Number(data?.days_per_week || 3);
  const daysEl = document.getElementById("profile-training-days");
  if (daysEl) daysEl.textContent = days;
  const goal = (data?.goal || "Fitness").toString();
  const level = (data?.level || "beginner").toString();
  const protocol = goal.includes("muscle") ? "Hypertrophy" : goal.includes("fat") ? "Cut Protocol" : goal.includes("strength") ? "Strength" : "Hybrid";
  const rank = level === "advanced" ? "Elite" : level === "intermediate" ? "Prime" : "Build";
  const protocolEl = document.getElementById("profile-protocol");
  const rankEl = document.getElementById("profile-rank");
  const readyEl = document.getElementById("profile-readiness");
  const consistency = document.getElementById("profile-consistency-bar");
  if (protocolEl) protocolEl.textContent = protocol;
  if (rankEl) rankEl.textContent = rank;
  if (readyEl) readyEl.textContent = days >= 5 ? "Green" : "Stable";
  consistency?.style.setProperty("--w", `${Math.min(94, 34 + days * 10)}%`);
  const insight = document.getElementById("profile-ai-insight");
  if (insight) {
    insight.textContent = `${rank} ${protocol.toLowerCase()} profile detected. Keep ${days} focused sessions per week and update recovery often so FitCoach can tune intensity around your ${goal.toLowerCase()} goal.`;
  }
}
async function saveProfile() {
  const body={
    name:document.getElementById("pf-name").value,
    age:parseInt(document.getElementById("pf-age").value),
    gender:document.getElementById("pf-gender").value,
    weight:parseFloat(document.getElementById("pf-weight").value),
    height:parseFloat(document.getElementById("pf-height").value),
    goal:document.getElementById("pf-goal").value,
    level:document.getElementById("pf-level").value,
    workout_place:document.getElementById("pf-place").value,
    days_per_week:parseInt(document.getElementById("pf-days").value),
    injuries:document.getElementById("pf-injuries").value
  };
  try{
    await apiFetch("/api/profile",{method:"PUT",body:JSON.stringify(body)});
    currentUser={...(currentUser||{}),...body};
    showToast("✅ Profile saved!");
    document.getElementById("profile-name-display").textContent=body.name;
    document.getElementById("profile-goal-display").textContent=body.goal;
    updateProfileCockpit(currentUser);
    document.getElementById("profile-avatar-display").textContent=body.gender==="female"?"🏃‍♀️":"🏋️";
  }catch{showToast("❌ Save failed.");}
}

// ── UI HELPERS ────────────────────────────────────────────────────────
function updateStreak(s){document.getElementById("streak-badge").textContent=`🔥 ${s}`;}
function updateCoachHeaader(name,gender){
  if(name) document.getElementById("coach-name").textContent=`Coach for ${name}`;
  if(gender?.toLowerCase()==="female") document.getElementById("coach-avatar").textContent="💃";
}
const updateCoachHeader = updateCoachHeaader;
function showToast(msg){
  const t=document.getElementById("toast");
  t.textContent=msg; t.classList.remove("hidden");
  clearTimeout(t._t);
  t._t=setTimeout(()=>t.classList.add("hidden"),3000);
}
function launchConfetti(){
  const o=document.getElementById("confetti-overlay");
  o.classList.remove("hidden"); o.innerHTML="";
  const C=["#7c3aed","#10b981","#f59e0b","#3b82f6","#ef4444","#f472b6"];
  for(let i=0;i<80;i++){
    const p=document.createElement("div");
    p.className="confetti-piece";
    p.style.cssText=`left:${Math.random()*100}%;background:${C[Math.floor(Math.random()*C.length)]};animation-duration:${1.5+Math.random()*2}s;animation-delay:${Math.random()*.5}s;transform:rotate(${Math.random()*360}deg);width:${6+Math.random()*8}px;height:${6+Math.random()*8}px;border-radius:${Math.random()>.5?"50%":"2px"}`;
    o.appendChild(p);
  }
  setTimeout(()=>{o.classList.add("hidden");o.innerHTML="";},3500);
}
document.addEventListener("click",()=>{if(window.speechSynthesis)speechSynthesis.resume();},{once:true});
