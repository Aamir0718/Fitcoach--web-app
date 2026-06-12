import { getPoseLandmarker, POSE_EDGES, LM } from "./ghost-pose.js";
import { analyze, tick, scoreForm, TARGET_REPS, newRepState } from "./ghost-form-analysis.js";

const EXERCISE_BRIEFS = {
  squat: "Feet shoulder-width. Hips back, chest tall. Drive through the heels.",
  pushup: "Hands under shoulders. Lock the core. Keep elbows near 45 degrees from the torso.",
  biceps: "Elbows pinned. Slow eccentric. Squeeze the peak without swinging.",
};

const DEMO_COPY = {
  squat: "Match the ghost outline: hips back, knees tracking, chest tall.",
  pushup: "Keep one clean line from shoulders to ankles and lower under control.",
  biceps: "Pin the upper arm and curl without letting the shoulder swing forward.",
};

const MUSCLE_ACTIVATION = {
  squat: [
    ["Quads", 92],
    ["Glutes", 84],
    ["Hamstrings", 62],
    ["Core", 48],
  ],
  pushup: [
    ["Chest", 88],
    ["Triceps", 74],
    ["Shoulders", 58],
    ["Core", 52],
  ],
  biceps: [
    ["Biceps", 94],
    ["Forearms", 61],
    ["Shoulders", 26],
    ["Core", 18],
  ],
};

const SCORE_STATES = [
  { min: 82, key: "good", color: "rgb(16, 185, 129)", glow: "rgba(16, 185, 129, .42)" },
  { min: 62, key: "warn", color: "rgb(245, 158, 11)", glow: "rgba(245, 158, 11, .42)" },
  { min: 0, key: "poor", color: "rgb(239, 68, 68)", glow: "rgba(239, 68, 68, .42)" },
];

const state = {
  exercise: "squat",
  activeWorkout: null,
  exerciseMeta: new Map(),
  targetReps: TARGET_REPS,
  status: "idle",
  reps: 0,
  acc: 100,
  displayAcc: 100,
  elapsed: 0,
  feedback: null,
  rafId: null,
  timerId: null,
  lastVideoTime: -1,
  repState: newRepState(),
  previousAngles: null,
  stabilityScore: 100,
  completedPulse: false,
  renderedExercise: null,
  initialized: false,
};

const els = {};

function cacheEls() {
  els.video = document.getElementById("ghost-video");
  els.canvas = document.getElementById("ghost-canvas");
  els.overlay = document.getElementById("ghost-idle-overlay");
  els.overlayTitle = document.getElementById("ghost-overlay-title");
  els.overlayCopy = document.getElementById("ghost-overlay-copy");
  els.startBtn = document.getElementById("ghost-start-btn");
  els.stopBtn = document.getElementById("ghost-stop-btn");
  els.statusPill = document.getElementById("ghost-status-pill");
  els.reps = document.getElementById("ghost-reps");
  els.accuracy = document.getElementById("ghost-accuracy");
  els.accuracyLabel = document.getElementById("ghost-accuracy-label");
  els.timer = document.getElementById("ghost-timer");
  els.depthFill = document.getElementById("ghost-depth-fill");
  els.angle = document.getElementById("ghost-angle");
  els.brief = document.getElementById("ghost-brief");
  els.liveCue = document.getElementById("ghost-live-cue");
  els.exerciseSelector = document.getElementById("ghost-exercise-selector");
  els.accuracyCard = document.getElementById("ghost-accuracy-card");
  els.repRing = document.getElementById("ghost-rep-ring");
  els.targetReps = document.getElementById("ghost-target-reps");
  els.muscleList = document.getElementById("ghost-muscle-list");
  els.demoFigure = document.getElementById("ghost-demo-figure");
  els.demoCopy = document.getElementById("ghost-demo-copy");
}

function init() {
  if (state.initialized) return;
  cacheEls();
  if (!els.video || !els.canvas) return;

  els.startBtn?.addEventListener("click", start);
  els.stopBtn?.addEventListener("click", stop);
  els.exerciseSelector?.addEventListener("click", (event) => {
    const btn = event.target.closest("[data-exercise]");
    if (!btn) return;
    setExercise(btn.dataset.exercise, btn.dataset.exerciseName);
  });

  state.initialized = true;
  loadActiveWorkout();
  render();
}

function setExercise(exercise, exerciseName = null) {
  state.exercise = exercise;
  const meta = state.exerciseMeta.get(exerciseName) || state.exerciseMeta.get(exercise) || null;
  state.targetReps = meta?.posture_config?.rep_target || meta?.rep_target || TARGET_REPS;
  state.repState = newRepState();
  state.reps = 0;
  state.acc = 100;
  state.displayAcc = 100;
  state.feedback = null;
  state.previousAngles = null;
  state.stabilityScore = 100;
  document.querySelectorAll(".ghost-exercise-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.exercise === exercise && (!exerciseName || btn.dataset.exerciseName === exerciseName));
  });
  render();
}

function formKeyForExercise(exercise) {
  const configured = exercise?.posture_config?.form_key || exercise?.form_key;
  if (configured) return configured;
  const name = (exercise?.name || "").toLowerCase();
  if (name.includes("push") || name.includes("plank") || name.includes("press")) return "pushup";
  if (name.includes("curl") || name.includes("row") || name.includes("pull") || name.includes("rotation")) return "biceps";
  return "squat";
}

function loadActiveWorkout(payload = null) {
  let workout = payload;
  if (!workout) {
    try {
      workout = JSON.parse(localStorage.getItem("fc_active_workout") || "null");
    } catch {
      workout = null;
    }
  }
  if (!workout?.exercises?.length || !els.exerciseSelector) return;

  state.activeWorkout = workout;
  state.exerciseMeta = new Map();
  els.exerciseSelector.innerHTML = workout.exercises.map((exercise, index) => {
    const formKey = formKeyForExercise(exercise);
    const target = exercise?.posture_config?.rep_target || TARGET_REPS;
    state.exerciseMeta.set(exercise.name, { ...exercise, rep_target: target });
    return `
      <button class="ghost-exercise-btn ${index === 0 ? "active" : ""}" type="button" data-exercise="${formKey}" data-exercise-name="${escapeAttr(exercise.name)}">
        <span>${index + 1}. ${exercise.name}</span><small>${exercise.sets || 3} x ${exercise.reps || target}</small>
      </button>
    `;
  }).join("");

  const first = workout.exercises[0];
  setExercise(formKeyForExercise(first), first.name);
}

function escapeAttr(value) {
  return String(value || "").replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");
}

async function start() {
  init();
  setStatus("loading");
  try {
    const landmarker = await getPoseLandmarker();
    const stream = await navigator.mediaDevices.getUserMedia({
      video: { width: 1280, height: 720, facingMode: "user" },
      audio: false,
    });

    els.video.srcObject = stream;
    await new Promise((resolve) => {
      els.video.onloadedmetadata = () => els.video.play().then(resolve);
    });

    els.canvas.width = els.video.videoWidth;
    els.canvas.height = els.video.videoHeight;
    state.repState = newRepState();
    state.reps = 0;
    state.acc = 100;
    state.displayAcc = 100;
    state.feedback = null;
    state.previousAngles = null;
    state.stabilityScore = 100;
    state.lastVideoTime = -1;
    setStatus("running");
    startTimer();
    loop(landmarker);
  } catch (err) {
    console.error(err);
    setStatus("error");
    els.overlayCopy.textContent = err instanceof Error
      ? err.message
      : "Could not start the camera. Check browser permissions.";
  }
}

function stop() {
  if (state.rafId) cancelAnimationFrame(state.rafId);
  state.rafId = null;
  clearInterval(state.timerId);
  state.timerId = null;

  const stream = els.video?.srcObject;
  stream?.getTracks?.().forEach((track) => track.stop());
  if (els.video) els.video.srcObject = null;

  const ctx = els.canvas?.getContext("2d");
  ctx?.clearRect(0, 0, els.canvas.width, els.canvas.height);
  setStatus("idle");
}

function loop(landmarker) {
  if (!els.video || !els.canvas || state.status !== "running") return;
  const ctx = els.canvas.getContext("2d");
  const now = performance.now();

  if (els.video.currentTime !== state.lastVideoTime) {
    state.lastVideoTime = els.video.currentTime;
    const result = landmarker.detectForVideo(els.video, now);

    ctx.save();
    ctx.clearRect(0, 0, els.canvas.width, els.canvas.height);
    ctx.translate(els.canvas.width, 0);
    ctx.scale(-1, 1);

    const landmarks = result.landmarks?.[0] ?? [];
    if (landmarks.length) {
      const feedback = analyze({ landmarks, exercise: state.exercise });
      if (feedback) {
        const next = tick(state.repState, feedback);
        const previousReps = state.repState.reps;
        state.repState = next;
        state.reps = next.reps;
        state.feedback = feedback;
        state.stabilityScore = calculateStability(feedback.angles);
        state.acc = scoreForm({
          state: next,
          feedback,
          stabilityScore: state.stabilityScore,
        });
        if (state.reps > previousReps) pulseRepCompletion();
        drawCoachingOverlay(ctx, landmarks, els.canvas.width, els.canvas.height, feedback);
      }
    } else {
      state.feedback = null;
    }
    ctx.restore();
    if (state.feedback) {
      drawAngleLabels(ctx, landmarks, state.feedback.angles, els.canvas.width, els.canvas.height, getScoreState(state.acc));
    }
    render();
  }

  state.rafId = requestAnimationFrame(() => loop(landmarker));
}

function drawCoachingOverlay(ctx, landmarks, width, height, feedback) {
  const scoreState = getScoreState(state.acc);
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  drawGhostSkeleton(ctx, landmarks, width, height);
  drawSkeleton(ctx, landmarks, width, height, scoreState);
}

function drawSkeleton(ctx, landmarks, width, height, scoreState) {
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  ctx.shadowColor = scoreState.glow;
  ctx.shadowBlur = 22;
  ctx.lineWidth = 9;
  ctx.strokeStyle = scoreState.glow;
  drawEdges(ctx, landmarks, width, height, 4, 4, true);

  ctx.shadowBlur = 12;
  ctx.lineWidth = 4;
  ctx.strokeStyle = scoreState.color;
  drawEdges(ctx, landmarks, width, height, 0, 0, true);

  ctx.fillStyle = scoreState.color;
  ctx.shadowBlur = 16;
  for (let i = 11; i <= 28; i += 1) {
    const point = landmarks[i];
    if (!point) continue;
    ctx.beginPath();
    ctx.arc(point.x * width, point.y * height, 5.5, 0, Math.PI * 2);
    ctx.fill();
    ctx.beginPath();
    ctx.arc(point.x * width, point.y * height, 10, 0, Math.PI * 2);
    ctx.strokeStyle = "rgba(255,255,255,.16)";
    ctx.lineWidth = 1;
    ctx.stroke();
  }
}

function drawEdges(ctx, landmarks, width, height, offsetX, offsetY, animated = false) {
  if (animated) {
    const dashOffset = -(performance.now() / 80) % 22;
    ctx.setLineDash([16, 6]);
    ctx.lineDashOffset = dashOffset;
  }
  for (const [a, b] of POSE_EDGES) {
    const start = landmarks[a];
    const end = landmarks[b];
    if (!start || !end) continue;
    ctx.beginPath();
    ctx.moveTo(start.x * width + offsetX, start.y * height + offsetY);
    ctx.lineTo(end.x * width + offsetX, end.y * height + offsetY);
    ctx.stroke();
  }
  ctx.setLineDash([]);
}

function drawGhostSkeleton(ctx, landmarks, width, height) {
  const ghost = getIdealGhost(landmarks, width, height, state.exercise);
  if (!ghost.length) return;

  ctx.save();
  ctx.globalAlpha = 0.58;
  ctx.shadowColor = "rgba(167, 139, 250, .55)";
  ctx.shadowBlur = 22;
  ctx.strokeStyle = "rgba(216, 204, 255, .5)";
  ctx.lineWidth = 3;
  ctx.setLineDash([10, 12]);

  for (const [start, end] of ghost) {
    ctx.beginPath();
    ctx.moveTo(start.x, start.y);
    ctx.lineTo(end.x, end.y);
    ctx.stroke();
  }
  ctx.setLineDash([]);
  ctx.fillStyle = "rgba(216, 204, 255, .44)";
  for (const point of ghost.flat()) {
    ctx.beginPath();
    ctx.arc(point.x, point.y, 4, 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.restore();
}

function drawAngleLabels(ctx, landmarks, angles, width, height, scoreState) {
  if (!angles) return;
  const labels = angleLabelAnchors(landmarks, angles);
  ctx.save();
  ctx.font = "700 12px DM Sans, sans-serif";
  ctx.textBaseline = "middle";
  ctx.shadowColor = scoreState.glow;
  ctx.shadowBlur = 12;

  for (const label of labels) {
    if (!label.point || !Number.isFinite(label.value)) continue;
    const x = (1 - label.point.x) * width + label.dx;
    const y = label.point.y * height + label.dy;
    const text = `${label.name} ${Math.round(label.value)}°`;
    const metrics = ctx.measureText(text);
    const boxW = metrics.width + 18;
    const boxH = 25;
    roundRect(ctx, x - boxW / 2, y - boxH / 2, boxW, boxH, 12);
    ctx.fillStyle = "rgba(7, 7, 15, .72)";
    ctx.fill();
    ctx.strokeStyle = scoreState.color;
    ctx.lineWidth = 1;
    ctx.stroke();
    ctx.fillStyle = scoreState.color;
    ctx.fillText(text, x - metrics.width / 2, y + 1);
  }
  ctx.restore();
}

function angleLabelAnchors(landmarks, angles) {
  return [
    { name: "ELBOW", value: angles.leftElbow, point: landmarks[LM.LEFT_ELBOW], dx: -38, dy: -22 },
    { name: "ELBOW", value: angles.rightElbow, point: landmarks[LM.RIGHT_ELBOW], dx: 38, dy: -22 },
    { name: "KNEE", value: angles.leftKnee, point: landmarks[LM.LEFT_KNEE], dx: -34, dy: 24 },
    { name: "KNEE", value: angles.rightKnee, point: landmarks[LM.RIGHT_KNEE], dx: 34, dy: 24 },
    { name: "HIP", value: angles.leftHip, point: landmarks[LM.LEFT_HIP], dx: -34, dy: -24 },
    { name: "HIP", value: angles.rightHip, point: landmarks[LM.RIGHT_HIP], dx: 34, dy: -24 },
    { name: "SHLD", value: angles.leftShoulder, point: landmarks[LM.LEFT_SHOULDER], dx: -38, dy: -24 },
    { name: "SHLD", value: angles.rightShoulder, point: landmarks[LM.RIGHT_SHOULDER], dx: 38, dy: -24 },
  ].filter((label) => Number.isFinite(label.value));
}

function getIdealGhost(landmarks, width, height, exercise) {
  const leftShoulder = landmarks[LM.LEFT_SHOULDER];
  const rightShoulder = landmarks[LM.RIGHT_SHOULDER];
  const leftHip = landmarks[LM.LEFT_HIP];
  const rightHip = landmarks[LM.RIGHT_HIP];
  if (!leftShoulder || !rightShoulder || !leftHip || !rightHip) return [];

  const centerX = ((leftHip.x + rightHip.x) / 2) * width;
  const hipY = ((leftHip.y + rightHip.y) / 2) * height;
  const shoulderY = ((leftShoulder.y + rightShoulder.y) / 2) * height;
  const body = Math.max(90, Math.abs(hipY - shoulderY));
  const spread = Math.max(60, Math.abs(leftShoulder.x - rightShoulder.x) * width);

  const p = {};
  if (exercise === "squat") {
    p.ls = { x: centerX - spread * .55, y: hipY - body * 1.15 };
    p.rs = { x: centerX + spread * .55, y: hipY - body * 1.15 };
    p.lh = { x: centerX - spread * .42, y: hipY };
    p.rh = { x: centerX + spread * .42, y: hipY };
    p.lk = { x: centerX - spread * .62, y: hipY + body * .62 };
    p.rk = { x: centerX + spread * .62, y: hipY + body * .62 };
    p.la = { x: centerX - spread * .72, y: hipY + body * 1.22 };
    p.ra = { x: centerX + spread * .72, y: hipY + body * 1.22 };
    p.le = { x: p.ls.x - spread * .18, y: p.ls.y + body * .34 };
    p.re = { x: p.rs.x + spread * .18, y: p.rs.y + body * .34 };
    p.lw = { x: p.le.x, y: p.le.y + body * .42 };
    p.rw = { x: p.re.x, y: p.re.y + body * .42 };
  } else if (exercise === "pushup") {
    const y = hipY + body * .25;
    p.ls = { x: centerX - spread * .55, y };
    p.rs = { x: centerX + spread * .55, y };
    p.lh = { x: centerX - spread * .25, y: y + body * .08 };
    p.rh = { x: centerX + spread * .25, y: y + body * .08 };
    p.lk = { x: centerX - spread * .05, y: y + body * .14 };
    p.rk = { x: centerX + spread * .05, y: y + body * .14 };
    p.la = { x: centerX + spread * .88, y: y + body * .2 };
    p.ra = { x: centerX + spread * 1.02, y: y + body * .2 };
    p.le = { x: p.ls.x - spread * .2, y: y + body * .38 };
    p.re = { x: p.rs.x + spread * .2, y: y + body * .38 };
    p.lw = { x: p.le.x - spread * .08, y: y + body * .74 };
    p.rw = { x: p.re.x + spread * .08, y: y + body * .74 };
  } else {
    p.rs = { x: centerX + spread * .45, y: shoulderY };
    p.rh = { x: centerX + spread * .35, y: hipY };
    p.rk = { x: centerX + spread * .35, y: hipY + body * .9 };
    p.ra = { x: centerX + spread * .35, y: hipY + body * 1.65 };
    p.re = { x: p.rs.x + spread * .02, y: shoulderY + body * .55 };
    p.rw = { x: p.re.x + spread * .22, y: shoulderY + body * .12 };
    p.ls = { x: centerX - spread * .45, y: shoulderY };
    p.lh = { x: centerX - spread * .35, y: hipY };
    p.le = { x: p.ls.x - spread * .04, y: shoulderY + body * .55 };
    p.lw = { x: p.le.x - spread * .04, y: shoulderY + body * 1.03 };
    p.lk = { x: p.lh.x, y: hipY + body * .9 };
    p.la = { x: p.lh.x, y: hipY + body * 1.65 };
  }

  return [
    [p.ls, p.rs], [p.ls, p.le], [p.le, p.lw], [p.rs, p.re], [p.re, p.rw],
    [p.ls, p.lh], [p.rs, p.rh], [p.lh, p.rh],
    [p.lh, p.lk], [p.lk, p.la], [p.rh, p.rk], [p.rk, p.ra],
  ];
}

function roundRect(ctx, x, y, width, height, radius) {
  ctx.beginPath();
  ctx.moveTo(x + radius, y);
  ctx.arcTo(x + width, y, x + width, y + height, radius);
  ctx.arcTo(x + width, y + height, x, y + height, radius);
  ctx.arcTo(x, y + height, x, y, radius);
  ctx.arcTo(x, y, x + width, y, radius);
  ctx.closePath();
}

function startTimer() {
  clearInterval(state.timerId);
  const startedAt = Date.now();
  state.elapsed = 0;
  state.timerId = setInterval(() => {
    state.elapsed = Math.floor((Date.now() - startedAt) / 1000);
    renderTimer();
  }, 1000);
  renderTimer();
}

function setStatus(status) {
  state.status = status;
  render();
}

function render() {
  if (!state.initialized) return;
  const running = state.status === "running";
  const loading = state.status === "loading";
  const error = state.status === "error";

  els.overlay?.classList.toggle("hidden", running);
  els.stopBtn?.classList.toggle("hidden", !running);
  els.liveCue?.classList.toggle("hidden", !running);
  els.startBtn.disabled = loading;

  els.overlayTitle.textContent = loading ? "Loading the model..." : error ? "Camera unavailable" : "Step into frame";
  if (!error) {
    els.overlayCopy.textContent = "Choose an exercise, stand far enough for full-body visibility, then allow camera access.";
  }
  els.startBtn.textContent = loading ? "Preparing..." : "Begin Session";
  els.statusPill.innerHTML = `<span></span> ${running ? "Live tracking" : loading ? "Preparing camera" : error ? "Camera blocked" : "Camera idle"}`;
  els.statusPill.classList.toggle("running", running);
  els.statusPill.classList.toggle("error", error);

  state.displayAcc += (state.acc - state.displayAcc) * 0.22;
  const displayAcc = Math.round(state.displayAcc);
  const scoreState = getScoreState(displayAcc);

  els.reps.textContent = String(state.reps);
  els.targetReps.textContent = state.targetReps;
  els.repRing.style.setProperty("--rep-progress", Math.min(state.reps / state.targetReps, 1));
  els.repRing.classList.toggle("complete", state.reps >= state.targetReps);
  els.accuracy.textContent = `${displayAcc}%`;
  els.accuracyLabel.textContent = accuracyLabel(displayAcc);
  els.accuracyCard.dataset.state = scoreState.key;
  els.depthFill.style.width = `${state.feedback?.depthPct ?? 0}%`;
  els.angle.textContent = state.feedback ? `${Math.round(state.feedback.primaryAngle)}°` : "--°";
  els.brief.textContent = EXERCISE_BRIEFS[state.exercise];
  if (state.renderedExercise !== state.exercise) {
    renderMuscleActivation();
    renderDemoGuide();
    state.renderedExercise = state.exercise;
  }

  const cue = state.feedback?.cues?.[0] || "Good posture";
  els.liveCue.textContent = cue;
  els.liveCue.classList.toggle("good", Boolean(state.feedback && !state.feedback.cues.length));
  els.liveCue.dataset.state = scoreState.key;
  renderTimer();
}

function renderTimer() {
  if (!els.timer) return;
  const mins = Math.floor(state.elapsed / 60);
  const secs = state.elapsed % 60;
  els.timer.textContent = `${String(mins).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
}

function accuracyLabel(value) {
  if (value >= 90) return "Textbook execution";
  if (value >= 75) return "Solid, small tweaks";
  if (value >= 60) return "Watch your form";
  return "Slow down, reset";
}

function calculateStability(angles) {
  if (!angles) return 100;
  if (!state.previousAngles) {
    state.previousAngles = { ...angles };
    return 100;
  }
  const keys = Object.keys(angles).filter((key) => Number.isFinite(angles[key]) && Number.isFinite(state.previousAngles[key]));
  const delta = keys.reduce((sum, key) => sum + Math.abs(angles[key] - state.previousAngles[key]), 0) / Math.max(keys.length, 1);
  state.previousAngles = { ...angles };
  return Math.max(35, Math.min(100, 100 - delta * 4.5));
}

function getScoreState(value) {
  return SCORE_STATES.find((item) => value >= item.min) || SCORE_STATES[SCORE_STATES.length - 1];
}

function pulseRepCompletion() {
  els.repRing?.classList.add("pulse");
  window.setTimeout(() => els.repRing?.classList.remove("pulse"), 520);
}

function renderMuscleActivation() {
  if (!els.muscleList) return;
  const rows = MUSCLE_ACTIVATION[state.exercise] || [];
  els.muscleList.innerHTML = rows.map(([name, value]) => `
    <div class="ghost-muscle-row">
      <span>${name}</span>
      <div class="ghost-muscle-track"><div style="--activation:${value}%"></div></div>
      <small>${value}%</small>
    </div>
  `).join("");
}

function renderDemoGuide() {
  if (!els.demoFigure) return;
  els.demoFigure.dataset.exercise = state.exercise;
  els.demoCopy.textContent = DEMO_COPY[state.exercise];
  els.demoFigure.innerHTML = demoSvg(state.exercise);
}

function demoSvg(exercise) {
  const paths = {
    squat: `
      <polyline points="58,20 50,48 34,72 26,104" />
      <polyline points="62,20 76,48 92,72 100,104" />
      <line x1="58" y1="20" x2="62" y2="20" />
      <line x1="50" y1="48" x2="76" y2="48" />
      <line x1="58" y1="20" x2="38" y2="58" />
      <line x1="62" y1="20" x2="84" y2="58" />
    `,
    pushup: `
      <polyline points="18,62 44,58 74,62 108,66" />
      <line x1="36" y1="58" x2="28" y2="92" />
      <line x1="50" y1="58" x2="56" y2="92" />
      <line x1="74" y1="62" x2="84" y2="82" />
      <line x1="108" y1="66" x2="116" y2="82" />
    `,
    biceps: `
      <line x1="60" y1="20" x2="58" y2="52" />
      <line x1="58" y1="52" x2="58" y2="104" />
      <line x1="60" y1="24" x2="88" y2="58" />
      <line x1="88" y1="58" x2="74" y2="34" />
      <line x1="60" y1="24" x2="34" y2="58" />
      <line x1="34" y1="58" x2="34" y2="92" />
    `,
  };
  return `<svg viewBox="0 0 128 118" role="img" aria-label="${exercise} form guide">
    <g>${paths[exercise]}</g>
  </svg>`;
}

window.fitCoachGhostTrainer = { init, start, stop };

document.addEventListener("DOMContentLoaded", init);
window.addEventListener("fitcoach:workout-loaded", (event) => loadActiveWorkout(event.detail));
window.addEventListener("storage", (event) => {
  if (event.key === "fc_active_workout") loadActiveWorkout();
});
window.addEventListener("beforeunload", stop);
