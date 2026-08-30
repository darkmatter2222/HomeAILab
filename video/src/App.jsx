import { useEffect, useRef, useState, useCallback } from "react";
import { SCENES, TOTAL, sceneIndexAt, fmtClock } from "./timeline.js";
import Hook from "./chapters/Hook.jsx";
import Workloads from "./chapters/Workloads.jsx";
import MixtureOfExperts from "./chapters/MixtureOfExperts.jsx";
import Context from "./chapters/Context.jsx";
import Card3090 from "./chapters/Card3090.jsx";
import Card5090 from "./chapters/Card5090.jsx";
import Spark from "./chapters/Spark.jsx";
import Pullback from "./chapters/Pullback.jsx";
import Framework from "./chapters/Framework.jsx";
import Reverse from "./chapters/Reverse.jsx";
import RealWorld from "./chapters/RealWorld.jsx";
import Synthesis from "./chapters/Synthesis.jsx";
import Owners from "./chapters/Owners.jsx";
import Series from "./chapters/Series.jsx";
import OpenLoop from "./chapters/OpenLoop.jsx";

const COMP = {
  hook: Hook,
  workloads: Workloads,
  moe: MixtureOfExperts,
  context: Context,
  h3090: Card3090,
  h5090: Card5090,
  spark: Spark,
  pullback: Pullback,
  framework: Framework,
  reverse: Reverse,
  realworld: RealWorld,
  synthesis: Synthesis,
  owners: Owners,
  series: Series,
  openloop: OpenLoop,
};

// ── The continuous camera ──────────────────────────────────────────────
// Every chapter is a fixed vantage in one shared dark world. Between
// chapters the camera *travels* (2.4 s, slow-out) rather than cutting,
// with a slight dimensional tilt mid-flight. Once settled, a very slow
// drift keeps the world breathing — restrained, never frantic.
const TRANS = 2.4;

function easeInOutQuint(p) {
  return p < 0.5 ? 16 * p ** 5 : 1 - Math.pow(-2 * p + 2, 5) / 2;
}
const clamp01 = (v) => Math.min(1, Math.max(0, v));

function camAt(q, a, b) {
  const e = easeInOutQuint(q);
  const z = a.z + (b.z - a.z) * e;
  const x = a.x + (b.x - a.x) * e;
  const y = a.y + (b.y - a.y) * e;
  const roll = a.roll + (b.roll - a.roll) * e;
  const pitch = (a.pitch ?? 0) + ((b.pitch ?? 0) - (a.pitch ?? 0)) * e;
  const rotX = Math.sin(q * Math.PI) * (b.z - a.z) * 38; // dimensional tilt
  return { z, x, y, roll, pitch, rotX };
}

function idle(t, b) {
  const s = 1 + 0.008 * Math.sin(t * 0.3);
  return {
    x: b.x + Math.sin(t * 0.15) * 1.2,
    y: b.y + Math.cos(t * 0.12) * 0.9,
    z: b.z * s,
    roll: b.roll + Math.sin(t * 0.1) * 0.1,
    pitch: (b.pitch ?? 0) + Math.sin(t * 0.18) * 0.4,
    rotX: 0,
  };
}

// ── Cinematic transcript (the spoken narration, bottom center) ─────────
// Never a scrolling teleprompter: one short phrase is current (full
// opacity, fixed zone), the previous phrase drifts up and fades, the next
// is not yet visible. [[terms]] render green — never whole sentences.
function parseMarks(text) {
  const out = [];
  const re = /\[\[(.+?)\]\]/g;
  let last = 0;
  let m;
  while ((m = re.exec(text))) {
    if (m.index > last) out.push({ t: text.slice(last, m.index), g: false });
    out.push({ t: m[1], g: true });
    last = m.index + m[0].length;
  }
  if (last < text.length) out.push({ t: text.slice(last), g: false });
  return out;
}

function renderPhrase(text) {
  return parseMarks(text).map((p, i) =>
    p.g ? (
      <span key={i} style={{ color: "var(--green-bright)", textShadow: "0 0 18px var(--green-glow)" }}>{p.t}</span>
    ) : (
      <span key={i}>{p.t}</span>
    )
  );
}

function Caption({ cues, t, sceneFrom }) {
  const n = cues.length;
  const start = cues[0].at;
  // active index: the cue spoken at time t
  let i = 0;
  for (let k = 0; k < n; k++) {
    if (t >= sceneFrom + cues[k].at) i = k;
  }
  const inCue = t - (sceneFrom + cues[i].at);
  const nextAt = i < n - 1 ? cues[i + 1].at : start + 99;
  const dur = Math.max(0.001, nextAt - cues[i].at);
  const p = clamp01(inCue / dur);
  // current line: fade in over 0.4 s, fade out over the last 0.3 s
  const curOp = Math.min(clamp01(inCue / 0.4), 1 - clamp01((inCue - (dur - 0.3)) / 0.3));
  // previous line: drifts upward and fades during the first ~0.9 s
  const prevOp = i > 0 ? clamp01((dur - inCue) / (dur * 0.55 + 0.4)) : 0;
  const prev = i > 0 ? cues[i - 1].text : null;

  return (
    <div
      style={{
        position: "absolute", left: 0, right: 0, bottom: 64,
        display: "flex", flexDirection: "column", alignItems: "center",
        pointerEvents: "none", zIndex: 45,
        maskImage: "linear-gradient(180deg, transparent 0%, black 40%, black 100%)",
        WebkitMaskImage: "linear-gradient(180deg, transparent 0%, black 40%, black 100%)",
        height: 120, justifyContent: "flex-end",
      }}
    >
      {prev !== null && (
        <div
          style={{
            position: "absolute", bottom: 52,
            fontFamily: "var(--sans)",
            fontSize: "clamp(15px, 1.55vw, 21px)",
            fontWeight: 450, letterSpacing: "0.01em", textAlign: "center",
            maxWidth: "72vw", color: "var(--ink-dim)",
            opacity: prevOp * 0.55,
            transform: `translateY(${-(1 - prevOp) * 34}px)`,
            textShadow: "0 2px 16px rgba(4,5,10,0.95)",
            filter: `blur(${((1 - prevOp) * 2.2).toFixed(2)}px)`,
          }}
        >
          {renderPhrase(prev)}
        </div>
      )}
      <div
        style={{
          fontFamily: "var(--sans)",
          fontSize: "clamp(17px, 1.8vw, 25px)",
          fontWeight: 500, letterSpacing: "0.005em", textAlign: "center",
          maxWidth: "72vw", color: "var(--ink)",
          opacity: curOp,
          transform: `translateY(${(1 - curOp) * 10}px)`,
          textShadow: "0 2px 20px rgba(4,5,10,0.95)",
          lineHeight: 1.4,
        }}
      >
        {renderPhrase(cues[i].text)}
      </div>
    </div>
  );
}

// ── The far world: engineering grid + minimal dust ─────────────────────
function DepthField({ cam }) {
  const far = `translate3d(${cam.x * 0.4}px, ${cam.y * 0.4 + cam.rotX * 0.35}px, 0) scale(${1.02 + (1 - cam.z) * 0.22}) rotate(${cam.roll * 0.5}deg) rotateX(${cam.rotX * 0.5}deg)`;
  const near = `translate3d(${cam.x * 1.5}px, ${cam.y * 1.5 + cam.rotX * 1.1}px, 0) scale(${1.04 + (1 - cam.z) * 0.8})`;
  return (
    <>
      <div
        style={{
          position: "absolute", inset: "-12%",
          background:
            "linear-gradient(rgba(118,185,0,0.045) 1px, transparent 1px), linear-gradient(90deg, rgba(118,185,0,0.045) 1px, transparent 1px)",
          backgroundSize: "54px 54px",
          transform: far,
          maskImage: "radial-gradient(ellipse 78% 68% at 50% 44%, black 22%, transparent 86%)",
          WebkitMaskImage: "radial-gradient(ellipse 78% 68% at 50% 44%, black 22%, transparent 86%)",
          filter: `blur(${Math.max(0, cam.rotX * 0.05)}px)`,
          opacity: 0.9 - Math.abs(cam.z - 1.4) * 0.18,
        }}
      />
      <div style={{ position: "absolute", inset: 0, transform: near, pointerEvents: "none" }}>
        {[[18, 22, 4], [82, 18, 5], [74, 80, 3.5], [12, 78, 5], [50, 12, 3.5], [90, 55, 4]].map(([x, y, s], i) => (
          <div key={i} style={{
            position: "absolute", left: `${x}%`, top: `${y}%`, width: s, height: s, borderRadius: "50%",
            background: "rgba(118,185,0,0.22)", boxShadow: "0 0 10px rgba(118,185,0,0.25)",
          }} />
        ))}
      </div>
    </>
  );
}

export default function App() {
  const [t, setT] = useState(0);
  const [started, setStarted] = useState(false);
  const [offset, setOffset] = useState(0);
  const startRef = useRef(0);
  const rafRef = useRef(null);

  // deep-link: ?seek=N or #N — jump straight to second N (verification / dev)
  useEffect(() => {
    const m = (location.search.match(/[?&]seek=(\d+(\.\d+)?)/) || location.hash.match(/#(\d+(\.\d+)?)/) || [])[1];
    if (m) { setOffset(parseFloat(m)); setStarted(true); }
  }, []);

  useEffect(() => {
    if (!started) return;
    startRef.current = performance.now() - offset * 1000;
    const tick = (now) => {
      const elapsed = (now - startRef.current) / 1000;
      setT(Math.min(elapsed, TOTAL + 1));
      if (elapsed < TOTAL + 1) rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(rafRef.current);
  }, [started, offset]);

  const idx = sceneIndexAt(t);
  const scene = SCENES[idx];
  const ActiveComp = COMP[scene.id];

  // camera: mid-flight during the first TRANS of a chapter, then idle
  const inWin = clamp01((t - scene.from) / TRANS);
  const prev = idx > 0 ? SCENES[idx - 1] : null;
  const cam = (t - scene.from < TRANS && idx > 0)
    ? camAt(inWin, prev.cam, scene.cam)
    : idle(t, scene.cam);

  // the world rides the camera as one rigid body
  const content = `perspective(1500px) translate3d(${cam.x}px, ${cam.y}px, 0) rotateX(${(scene.cam.pitch ?? 0) + cam.rotX * 0.4}deg) rotateZ(${cam.roll}deg) scale(${cam.z})`;

  const progress = Math.min(1, t / TOTAL);
  const clean = typeof location !== "undefined" && /[?&]clean(=1)?$/.test(location.search);

  const restart = useCallback(() => {
    setStarted(false);
    setT(0);
    setTimeout(() => setStarted(true), 50);
  }, []);

  useEffect(() => {
    const onKey = (e) => {
      if (e.key === "r" || e.key === "R") restart();
      if (!started && (e.key === " " || e.key === "Enter")) { e.preventDefault(); setStarted(true); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [started, restart]);

  // outgoing chapter recedes slightly during the flight
  const PrevComp = prev ? COMP[prev.id] : null;
  const tOut = 1 - inWin;
  const outgoing = (idx > 0 && tOut > 0 && prev)
    ? {
        style: {
          opacity: easeInOutQuint(tOut) * 0.6,
          transform: `perspective(1500px) translate3d(${cam.x}px, ${cam.y}px, ${tOut * 220}px) scale(${1 + (1 - tOut) * 0.1}) rotateZ(${prev.cam.roll}deg)`,
          filter: `blur(${((1 - tOut) * 5).toFixed(2)}px)`,
        },
      }
    : null;

  return (
    <>
      <div className="scene-root" style={{ perspective: "1500px", transformStyle: "preserve-3d" }}>
        {started ? (
          <>
            <DepthField cam={cam} />
            {outgoing && PrevComp && (
              <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center", overflow: "hidden", ...outgoing.style }}>
                <div className="scene-clip" style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center", overflow: "hidden" }}>
                  <PrevComp t={t} />
                </div>
              </div>
            )}
            <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center", overflow: "hidden", transform: content, transformStyle: "preserve-3d" }}>
              <div className="scene-clip" style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center", overflow: "hidden" }}>
                <ActiveComp t={t} />
              </div>
            </div>
            {/* the spoken narration — cinematic transcript */}
            <Caption cues={scene.cues} t={t} sceneFrom={scene.from} />
          </>
        ) : (
          <div style={{ textAlign: "center", fontFamily: "var(--mono)" }}>
            <div style={{ fontSize: 15, color: "var(--green-bright)", letterSpacing: "0.3em", marginBottom: 18 }}>
              THE MODEL QUESTION · 10-MINUTE SPATIAL PRESENTATION
            </div>
            <div style={{ color: "var(--ink-dim)", fontSize: 14 }}>
              press <b style={{ color: "var(--ink)" }}>Space</b> or click to start · R restarts
            </div>
          </div>
        )}
      </div>

      {/* HUD frame */}
      <div className="hud">
        <div className="corner tl" /><div className="corner tr" />
        <div className="corner bl" /><div className="corner br" />
      </div>

      {/* chapter label */}
      <div className="scene-label">
        <div className="tick" />
        <div className="t mono">
          <b>{scene.name}</b> · {fmtClock(t)} / 10:00
        </div>
      </div>

      {/* progress */}
      <div className="progress-hairline">
        <div style={{ width: `${progress * 100}%` }} />
      </div>

      {/* dev controls (hidden during capture via ?clean) */}
      {!clean && (
        <div style={{ position: "fixed", right: 34, bottom: 150, zIndex: 70, display: "flex", gap: 8, alignItems: "center", fontFamily: "var(--mono)", fontSize: 11, color: "var(--ink-faint)" }}>
          <button
            onClick={restart}
            style={{ background: "rgba(118,185,0,0.1)", border: "1px solid rgba(118,185,0,0.35)", color: "var(--green-bright)", borderRadius: 6, padding: "6px 12px", fontFamily: "var(--mono)", fontSize: 11, cursor: "pointer" }}
          >
            ⟳ restart
          </button>
        </div>
      )}
    </>
  );
}
