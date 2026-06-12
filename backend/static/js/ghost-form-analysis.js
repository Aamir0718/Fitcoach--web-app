import { angleDeg, LM } from "./ghost-pose.js";

export const TARGET_REPS = 12;

export function newRepState() {
  return {
    reps: 0,
    phase: "up",
    goodFrames: 0,
    totalFrames: 0,
    depthSamples: [],
    angleScores: [],
  };
}

export function analyze({ landmarks, exercise }) {
  if (!landmarks || landmarks.length < 29) return null;
  if (exercise === "squat") return analyzeSquat(landmarks);
  if (exercise === "pushup") return analyzePushup(landmarks);
  return analyzeBiceps(landmarks);
}

function analyzeSquat(lm) {
  const hip = lm[LM.LEFT_HIP];
  const rightHip = lm[LM.RIGHT_HIP];
  const knee = lm[LM.LEFT_KNEE];
  const rightKnee = lm[LM.RIGHT_KNEE];
  const ankle = lm[LM.LEFT_ANKLE];
  const rightAnkle = lm[LM.RIGHT_ANKLE];
  const shoulder = lm[LM.LEFT_SHOULDER];

  const kneeAngle = angleDeg(hip, knee, ankle);
  const rightKneeAngle = angleDeg(rightHip, rightKnee, rightAnkle);
  const hipAngle = angleDeg(shoulder, hip, knee);
  const torsoLean = angleDeg(shoulder, hip, knee);
  const cues = [];
  let good = true;
  const errors = [];

  if (torsoLean < 130) {
    cues.push("Straighten your back");
    good = false;
    errors.push("leaning_torso");
  }
  const kneeWidth = Math.abs(knee.x - rightKnee.x);
  const ankleWidth = Math.abs(ankle.x - rightAnkle.x);
  if (kneeWidth < ankleWidth * 0.68) {
    cues.push("Push knees out");
    good = false;
    errors.push("knee_collapse");
  }
  if (Math.abs(knee.x - ankle.x) > 0.08) {
    cues.push("Keep knees over toes");
    good = false;
    errors.push("knee_tracking");
  }
  if (kneeAngle > 150) {
    cues.push("Go lower");
    errors.push("shallow_squat");
  }

  const depthPct = clamp(((170 - kneeAngle) / 90) * 100, 0, 100);
  const phase = kneeAngle < 110 ? "down" : "up";
  const precision = scoreTargets([
    targetScore(kneeAngle, 90, 85),
    targetScore(rightKneeAngle, 90, 85),
    targetScore(hipAngle, 95, 80),
  ]);

  return {
    primaryAngle: kneeAngle,
    exercise: "squat",
    phase,
    good,
    cues,
    errors,
    depthPct,
    precision,
    angles: {
      leftKnee: kneeAngle,
      rightKnee: rightKneeAngle,
      leftHip: hipAngle,
      leftShoulder: angleDeg(lm[LM.LEFT_ELBOW], shoulder, hip),
    },
  };
}

function analyzePushup(lm) {
  const shoulder = lm[LM.LEFT_SHOULDER];
  const rightShoulder = lm[LM.RIGHT_SHOULDER];
  const elbow = lm[LM.LEFT_ELBOW];
  const rightElbow = lm[LM.RIGHT_ELBOW];
  const wrist = lm[LM.LEFT_WRIST];
  const rightWrist = lm[LM.RIGHT_WRIST];
  const hip = lm[LM.LEFT_HIP];
  const ankle = lm[LM.LEFT_ANKLE];

  const elbowAngle = angleDeg(shoulder, elbow, wrist);
  const rightElbowAngle = angleDeg(rightShoulder, rightElbow, rightWrist);
  const bodyLine = angleDeg(shoulder, hip, ankle);
  const shoulderAngle = angleDeg(elbow, shoulder, hip);
  const cues = [];
  let good = true;
  const errors = [];

  if (bodyLine < 160) {
    cues.push("Hips sagging - engage your core");
    good = false;
    errors.push("hips_sagging");
  }
  if (Math.abs(elbow.x - shoulder.x) > 0.16) {
    cues.push("Keep elbows tucked");
    good = false;
    errors.push("elbow_flare");
  }
  if (elbowAngle > 160) {
    cues.push("Lower your chest");
    errors.push("shallow_rep");
  }

  const depthPct = clamp(((170 - elbowAngle) / 90) * 100, 0, 100);
  const phase = elbowAngle < 100 ? "down" : "up";
  const precision = scoreTargets([
    targetScore(elbowAngle, 90, 85),
    targetScore(rightElbowAngle, 90, 85),
    targetScore(bodyLine, 175, 30),
  ]);

  return {
    primaryAngle: elbowAngle,
    exercise: "pushup",
    phase,
    good,
    cues,
    errors,
    depthPct,
    precision,
    angles: {
      leftElbow: elbowAngle,
      rightElbow: rightElbowAngle,
      leftShoulder: shoulderAngle,
      leftHip: bodyLine,
    },
  };
}

function analyzeBiceps(lm) {
  const shoulder = lm[LM.RIGHT_SHOULDER];
  const elbow = lm[LM.RIGHT_ELBOW];
  const wrist = lm[LM.RIGHT_WRIST];
  const hip = lm[LM.RIGHT_HIP];
  const elbowAngle = angleDeg(shoulder, elbow, wrist);
  const shoulderAngle = angleDeg(elbow, shoulder, hip);
  const cues = [];
  let good = true;
  const errors = [];

  if (elbow.x < shoulder.x - 0.06) {
    cues.push("Keep elbow tucked in");
    good = false;
    errors.push("swinging_arms");
  }
  if (shoulderAngle < 18 || shoulderAngle > 52) {
    cues.push("Stop swinging");
    good = false;
    errors.push("swinging_arms");
  }
  if (elbowAngle > 160) {
    cues.push("Curl all the way up");
    errors.push("incomplete_contraction");
  }
  if (elbowAngle < 50) cues.push("Squeeze at the top");

  const depthPct = clamp(((170 - elbowAngle) / 130) * 100, 0, 100);
  const phase = elbowAngle < 70 ? "down" : "up";
  const precision = scoreTargets([
    targetScore(elbowAngle, 55, 115),
    targetScore(shoulderAngle, 35, 35),
  ]);
  return {
    primaryAngle: elbowAngle,
    exercise: "biceps",
    phase,
    good,
    cues,
    errors,
    depthPct,
    precision,
    angles: {
      rightElbow: elbowAngle,
      rightShoulder: shoulderAngle,
      rightHip: angleDeg(shoulder, hip, lm[LM.RIGHT_KNEE]),
    },
  };
}

export function tick(state, fb) {
  const next = {
    ...state,
    totalFrames: state.totalFrames + 1,
    goodFrames: state.goodFrames + (fb.good ? 1 : 0),
    depthSamples: [...state.depthSamples.slice(-80), fb.depthPct],
    angleScores: [...state.angleScores.slice(-80), fb.precision ?? 100],
  };

  if (state.phase === "down" && fb.phase === "up") {
    next.reps = state.reps + 1;
  }
  next.phase = fb.phase;
  return next;
}

export function accuracy(state) {
  if (!state.totalFrames) return 100;
  return Math.round((state.goodFrames / state.totalFrames) * 100);
}

export function scoreForm({ state, feedback, stabilityScore }) {
  if (!feedback || !state.totalFrames) return 100;
  const posture = (state.goodFrames / state.totalFrames) * 100;
  const precision = average(state.angleScores, feedback.precision ?? 100);
  const range = rangeConsistency(state.depthSamples);
  return Math.round(clamp(
    posture * 0.35 + precision * 0.30 + stabilityScore * 0.20 + range * 0.15,
    0,
    100,
  ));
}

function rangeConsistency(samples) {
  if (!samples.length) return 100;
  const maxDepth = Math.max(...samples);
  const avgDepth = average(samples, 0);
  return clamp(maxDepth * 0.72 + avgDepth * 0.28, 0, 100);
}

function targetScore(value, target, tolerance) {
  return clamp(100 - (Math.abs(value - target) / tolerance) * 100, 0, 100);
}

function scoreTargets(values) {
  return Math.round(average(values, 100));
}

function average(values, fallback) {
  if (!values.length) return fallback;
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}
