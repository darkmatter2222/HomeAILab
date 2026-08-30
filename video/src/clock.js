// ── Timeline helpers shared by the master clock and every chapter ──────
// Chapters carry a `cues` array (see timeline.js). Within a chapter, the
// first ~1.2 s is the camera flight-in, so beats are scheduled on the
// chapter-relative clock with that headroom. `beatAt` returns 0..1 progress
// for each cue; a cue at progress p is visible during [p, next p).

export const clamp01 = (v) => Math.min(1, Math.max(0, v));

export function cueProgresses(t, cues) {
  const n = cues.length;
  if (!n) return [];
  if (n === 1) return [t < cues[0].at ? 0 : 1];
  const first = cues[0].at;
  const last = cues[n - 1].at;
  const span = Math.max(0.001, last - first);
  return cues.map((c) => clamp01((t - c.at) / span));
}

// smooth fade for the window [p, next)
export function cueFade(p, next) {
  const fadeIn = clamp01(p * 3);
  const fadeOut = next === undefined ? 1 : p > 0.92 ? clamp01((1 - p) / 0.08) : 1;
  return Math.min(fadeIn, fadeOut);
}

// hold a value after a timestamp (with a short ramp)
export function after(t, at, ramp = 0.8) {
  return clamp01((t - at) / ramp);
}
