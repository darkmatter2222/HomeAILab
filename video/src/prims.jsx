// ═══════════════════════════════════════════════════════════════════════
// SPATIAL PRIMITIVES — the shared vocabulary of the dark canvas.
//
// Everything is a fixed-position block in the shared world; the camera
// (App.jsx) moves between vantages. Green means: active, selected,
// successful path, data moving, important number, current focus.
// Everything else is black / graphite / gray / white.
// ═══════════════════════════════════════════════════════════════════════
import { motion } from "framer-motion";

const G = "var(--green)";
const GB = "var(--green-bright)";

export const EASE = [0.22, 1, 0.36, 1];

// ── Text ────────────────────────────────────────────────────────────────
// Short declarative environment statements (never paragraphs). `mark` can
// be a plain string or [pre, markedGreen, post] to green one word.
export function Statement({ text, mark = "", size = "clamp(30px, 3.4vw, 52px)", sub = "", delay = 0, op = 1, green = false }) {
  const parts = Array.isArray(mark) ? mark : [mark, "", ""];
  return (
    <div style={{ textAlign: "center" }}>
      <motion.div
        initial={{ opacity: 0, y: 14, filter: "blur(5px)" }}
        animate={{ opacity: op, y: 0, filter: "blur(0px)" }}
        transition={{ delay, duration: 0.9, ease: EASE }}
        style={{
          fontFamily: "var(--sans)",
          fontSize: size,
          fontWeight: 750,
          letterSpacing: "0.01em",
          lineHeight: 1.12,
          color: green ? GB : "var(--ink)",
          textShadow: green ? "0 0 34px var(--green-glow)" : "0 2px 24px rgba(4,5,10,0.9)",
        }}
      >
        {parts[0]}
        {parts[1] && <span style={{ color: GB, textShadow: "0 0 26px var(--green-glow)" }}>{parts[1]}</span>}
        {parts[2]}
      </motion.div>
      {sub && (
        <motion.div
          initial={{ opacity: 0 }} animate={{ opacity: op }} transition={{ delay: delay + 0.5, duration: 0.7 }}
          style={{ fontFamily: "var(--mono)", fontSize: 13, letterSpacing: "0.22em", color: "var(--ink-faint)", marginTop: 14 }}
        >
          {sub}
        </motion.div>
      )}
    </div>
  );
}

// Fragmented dissolve: words drift apart and vanish (used when a question
// "fragments" into another question).
export function Fragment({ text, progress, delay = 0 }) {
  // progress 0..1 — 1 = fully fragmented
  const words = text.split(" ");
  return (
    <div style={{ position: "relative", fontSize: "clamp(30px, 3.4vw, 52px)", fontWeight: 750, letterSpacing: "0.02em", color: "var(--ink)", lineHeight: 1.15, textAlign: "center", whiteSpace: "pre-wrap" }}>
      {words.map((w, i) => (
        <motion.span
          key={i}
          animate={{
            opacity: progress >= 1 ? 0 : 1,
            y: progress >= 1 ? -10 - (i % 3) * 8 : 0,
            x: progress >= 1 ? (i % 2 ? 8 : -8) : 0,
            filter: progress >= 1 ? "blur(4px)" : "blur(0px)",
          }}
          transition={{ delay: delay + i * 0.05, duration: 0.8, ease: EASE }}
          style={{ display: "inline-block", marginRight: "0.28em" }}
        >
          {w}
        </motion.span>
      ))}
    </div>
  );
}

// ── Model blocks ────────────────────────────────────────────────────────
// A model is a stack of slabs (layers). size s: 0.5 small … 3.0 giant.
// MoE blocks carry an expert grid inside the shell.
export function ModelBlock({ size = 1, active = false, activeFrac = 0, label = "", opacity = 1, moe = false, layers = 6, delay = 0 }) {
  const w = 120 * size;
  const h = 120 * size;
  return (
    <div style={{ position: "relative", width: w, height: h, opacity, textAlign: "center" }}>
      <motion.div
        initial={{ opacity: 0, scale: 0.85 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ delay, duration: 0.9, ease: EASE }}
        style={{
          position: "absolute", inset: 0,
          borderRadius: 10,
          border: `1px solid ${active ? "rgba(118,185,0,0.65)" : "rgba(233,237,243,0.22)"}`,
          background: active
            ? "linear-gradient(160deg, rgba(118,185,0,0.16), rgba(118,185,0,0.04))"
            : "linear-gradient(160deg, rgba(255,255,255,0.07), rgba(255,255,255,0.02))",
          boxShadow: active ? "0 0 44px rgba(118,185,0,0.22), inset 0 0 26px rgba(118,185,0,0.08)" : "0 18px 50px rgba(0,0,0,0.5)",
          display: "flex", flexDirection: "column", gap: 5, padding: 8,
          backdropFilter: "blur(4px)",
        }}
      >
        {Array.from({ length: layers }).map((_, i) => {
          const on = moe ? (i / layers) < activeFrac : active;
          return (
            <div
              key={i}
              style={{
                flex: 1,
                borderRadius: 3,
                border: "1px solid rgba(255,255,255,0.08)",
                background: on ? "rgba(118,185,0,0.35)" : "rgba(255,255,255,0.05)",
                boxShadow: on ? "0 0 12px rgba(118,185,0,0.35)" : "none",
                transition: "background 0.5s, box-shadow 0.5s",
              }}
            />
          );
        })}
      </motion.div>
      {label && (
        <div style={{ position: "absolute", left: 0, right: 0, top: "100%", marginTop: 10, fontFamily: "var(--mono)", fontSize: 12, letterSpacing: "0.14em", color: active ? GB : "var(--ink-dim)" }}>
          {label}
        </div>
      )}
    </div>
  );
}

// ── GPU memory container ────────────────────────────────────────────────
// A vertical capacity vessel: fill % = what the GPU holds. fill 0..1.
export function MemoryContainer({ fill = 0.5, model = 0.4, context = 0, label = "GPU MEMORY", caption = "", tension = false, delay = 0 }) {
  const h = 240;
  const full = fill >= 0.98;
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 10 }}>
      <div style={{ position: "relative", height: h, width: 190, borderRadius: 12, border: "1px solid rgba(255,255,255,0.16)", background: "rgba(255,255,255,0.02)", overflow: "hidden" }}>
        {/* fill rises from the bottom: context (dark green) + model (bright) */}
        <motion.div
          initial={{ height: 0 }}
          animate={{ height: `${model * 100}%` }}
          transition={{ delay, duration: 1.4, ease: EASE }}
          style={{
            position: "absolute", bottom: 0, left: 0, right: 0,
            background: "linear-gradient(180deg, rgba(118,185,0,0.5), rgba(118,185,0,0.28))",
            boxShadow: "0 0 24px rgba(118,185,0,0.25)",
          }}
        >
          <div style={{ position: "absolute", top: 6, left: 12, fontFamily: "var(--mono)", fontSize: 10.5, letterSpacing: "0.14em", color: "var(--ink)" }}>MODEL</div>
        </motion.div>
        <motion.div
          initial={{ height: 0 }}
          animate={{ height: `${context * 100}%` }}
          transition={{ delay: delay + 0.3, duration: 1.4, ease: EASE }}
          style={{
            position: "absolute", bottom: `${model * 100}%`, left: 0, right: 0,
            background: "repeating-linear-gradient(180deg, rgba(118,185,0,0.2) 0 6px, rgba(118,185,0,0.1) 6px 12px)",
            borderTop: "1px solid rgba(145,199,51,0.5)",
          }}
        >
          {context > 0.05 && (
            <div style={{ position: "absolute", top: 6, left: 12, fontFamily: "var(--mono)", fontSize: 10.5, letterSpacing: "0.14em", color: "var(--ink-dim)" }}>CONTEXT</div>
          )}
        </motion.div>
        {/* tension marker when nearly full */}
        {tension && (
          <div style={{ position: "absolute", top: 4, right: 8, fontFamily: "var(--mono)", fontSize: 10.5, letterSpacing: "0.14em", color: full ? "var(--amber)" : GB }}>
            {full ? "FULL" : "LIMIT"}
          </div>
        )}
        {/* percent readout */}
        <div style={{ position: "absolute", bottom: 8, left: 0, right: 0, textAlign: "center", fontFamily: "var(--mono)", fontSize: 12, letterSpacing: "0.18em", color: "var(--ink-faint)" }}>
          {Math.round(fill * 100)}%
        </div>
      </div>
      <div style={{ fontFamily: "var(--mono)", fontSize: 12, letterSpacing: "0.2em", color: "var(--ink-dim)" }}>{label}</div>
      {caption && <div style={{ fontFamily: "var(--mono)", fontSize: 11.5, letterSpacing: "0.08em", color: "var(--ink-faint)" }}>{caption}</div>}
    </div>
  );
}

// ── Hardware unit ──────────────────────────────────────────────────────
// Abstract blocky GPU representation (not a product render).
export function HardwareUnit({ name, sub = "", accent = false, opacity = 1, delay = 0, width = 220, active = false }) {
  return (
    <div style={{ opacity, width }}>
      <motion.div
        initial={{ opacity: 0, y: 18 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay, duration: 1, ease: EASE }}
        style={{
          position: "relative",
          height: 128,
          borderRadius: 10,
          border: `1px solid ${accent ? "rgba(118,185,0,0.55)" : "rgba(255,255,255,0.18)"}`,
          background: accent
            ? "linear-gradient(160deg, rgba(118,185,0,0.14), rgba(10,13,22,0.9))"
            : "linear-gradient(160deg, rgba(255,255,255,0.08), rgba(10,13,22,0.9))",
          boxShadow: accent ? "0 0 48px rgba(118,185,0,0.28), 0 24px 60px rgba(0,0,0,0.55)" : "0 24px 60px rgba(0,0,0,0.55)",
          overflow: "hidden",
        }}
      >
        {/* pcie slots */}
        <div style={{ position: "absolute", left: 14, right: 14, top: 12, height: 6, display: "flex", gap: 6 }}>
          {Array.from({ length: 7 }).map((_, i) => (
            <div key={i} style={{ flex: 1, background: "rgba(255,255,255,0.09)", borderRadius: 2 }} />
          ))}
        </div>
        {/* die */}
        <div style={{ position: "absolute", left: "50%", top: 54, transform: "translate(-50%,-50%)", width: 64, height: 64, borderRadius: 6, border: "1px solid rgba(255,255,255,0.25)", background: "rgba(255,255,255,0.06)", display: "grid", placeItems: "center" }}>
          <div style={{ width: 34, height: 34, borderRadius: 4, background: active || accent ? "rgba(118,185,0,0.5)" : "rgba(255,255,255,0.12)", boxShadow: active ? "0 0 26px rgba(118,185,0,0.5)" : "none" }} />
        </div>
        {/* memory rows */}
        <div style={{ position: "absolute", left: 14, right: 14, bottom: 12, height: 18, display: "flex", gap: 4 }}>
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} style={{ flex: 1, background: "rgba(255,255,255,0.08)", borderRadius: 2 }} />
          ))}
        </div>
        {active && (
          <motion.div
            initial={{ opacity: 0 }} animate={{ opacity: [0.2, 0.55, 0.2] }} transition={{ duration: 2.2, repeat: Infinity }}
            style={{ position: "absolute", inset: 0, background: "radial-gradient(circle at 50% 50%, rgba(118,185,0,0.22), transparent 65%)" }}
          />
        )}
      </motion.div>
      <div style={{ textAlign: "center", marginTop: 14 }}>
        <div style={{ fontFamily: "var(--sans)", fontSize: 26, fontWeight: 750, color: accent ? GB : "var(--ink)", letterSpacing: "0.02em" }}>{name}</div>
        {sub && <div style={{ fontFamily: "var(--mono)", fontSize: 11.5, letterSpacing: "0.16em", color: "var(--ink-faint)", marginTop: 5 }}>{sub}</div>}
      </div>
    </div>
  );
}

// ── Data flow ──────────────────────────────────────────────────────────
// Dashed line with green packets travelling it. `speed` scales packet rate.
export function FlowLine({ x1, y1, x2, y2, active = true, speed = 1.6, delay = 0, color = "var(--green)" }) {
  const count = 3;
  return (
    <svg style={{ position: "absolute", inset: 0, width: "100%", height: "100%", pointerEvents: "none", overflow: "visible" }} viewBox="0 0 100 100" preserveAspectRatio="none">
      <line x1={x1} y1={y1} x2={x2} y2={y2} stroke="rgba(118,185,0,0.2)" strokeWidth={1.4} vectorEffect="non-scaling-stroke" />
      {active && Array.from({ length: count }).map((_, i) => (
        <circle key={i} r={2.6} fill={color} vectorEffect="non-scaling-stroke" style={{ filter: "drop-shadow(0 0 5px rgba(118,185,0,0.8))" }}>
          <animateMotion
            dur={`${(2.2 / speed).toFixed(2)}s`}
            begin={`${delay + (2.2 * i) / (speed * count)}s`}
            repeatCount="indefinite"
            path={`M ${x1} ${y1} L ${x2} ${y2}`}
            keyPoints="0;1" keyTimes="0;1" calcMode="linear"
          />
        </circle>
      ))}
    </svg>
  );
}

// Simple labeled connector used inside flex layouts (horizontal or vertical).
export function Connector({ dir = "h", label = "", active = false, opacity = 1, length = 70 }) {
  return (
    <div style={{ opacity, display: "flex", alignItems: "center", justifyContent: "center", gap: 8, ...(dir === "h" ? { width: length } : { height: length, flexDirection: "column" }) }}>
      <div style={{
        ...(dir === "h"
          ? { width: length, height: 1.5, background: active ? "linear-gradient(90deg, transparent, var(--green), transparent)" : "rgba(255,255,255,0.16)" }
          : { width: 1.5, height: length, background: active ? "linear-gradient(180deg, transparent, var(--green), transparent)" : "rgba(255,255,255,0.16)" }),
      }} />
      {label && <div style={{ fontFamily: "var(--mono)", fontSize: 10.5, letterSpacing: "0.14em", color: active ? GB : "var(--ink-faint)", whiteSpace: "nowrap" }}>{label}</div>}
      {dir === "h" && (
        <div style={{ width: 0, height: 0, borderStyle: "solid", ...(active ? { borderLeft: `8px solid ${GB}`, borderTop: "4px solid transparent", borderBottom: "4px solid transparent" } : { borderLeft: "8px solid var(--ink-faint)", borderTop: "4px solid transparent", borderBottom: "4px solid transparent" }) }} />
      )}
    </div>
  );
}

// ── Context ribbon ─────────────────────────────────────────────────────
// A growing context stream: token segments fill as context accumulates.
export function ContextRibbon({ fill = 0.4, label = "CONTEXT", delay = 0, segments = 24, caption = "" }) {
  return (
    <div style={{ width: 380 }}>
      <div style={{ display: "flex", gap: 3, height: 26, marginBottom: 10 }}>
        {Array.from({ length: segments }).map((_, i) => {
          const on = i / segments < fill;
          return (
            <motion.div
              key={i}
              initial={{ opacity: 0.15 }}
              animate={{ opacity: on ? 1 : 0.15, background: on ? "rgba(118,185,0,0.55)" : "rgba(255,255,255,0.08)", boxShadow: on ? "0 0 8px rgba(118,185,0,0.35)" : "none" }}
              transition={{ delay: delay + i * 0.03, duration: 0.35 }}
              style={{ flex: 1, borderRadius: 2, background: "rgba(255,255,255,0.08)" }}
            />
          );
        })}
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", fontFamily: "var(--mono)", fontSize: 11, letterSpacing: "0.14em", color: "var(--ink-dim)" }}>
        <span>{label}</span>
        {caption && <span style={{ color: GB }}>{caption}</span>}
      </div>
    </div>
  );
}

// ── Scene shell ────────────────────────────────────────────────────────
export function SceneShell({ children }) {
  return (
    <div style={{ width: "100%", height: "100%", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", position: "relative" }}>
      {children}
    </div>
  );
}
