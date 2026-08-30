// 9:35–9:50 — DEFINE THE SERIES
// The environment reforms into the three machines. Model families wait in
// the darkness. RUN IT. MEASURE IT. FIND THE LIMIT.
import { motion } from "framer-motion";
import { SceneShell, Statement, EASE } from "../prims.jsx";
import { after, clamp01 } from "../clock.js";
import { SCENES } from "../timeline.js";

const SCENE = SCENES[13];

const BEATS = [
  { at: 1.5, label: "Different models", icon: "M" },
  { at: 4, label: "Different inference engines", icon: "E" },
  { at: 6.5, label: "Different context sizes", icon: "C" },
  { at: 9, label: "Real agentic workloads", icon: "A" },
];

export default function Series({ t }) {
  const lt = t - SCENE.from;
  const machines = after(lt, 1.5, 1.0);
  const models = clamp01((lt - 2) / 6);
  const motto = after(lt, 10, 1.0);

  return (
    <SceneShell>
      {/* the three machines, reformed */}
      <div style={{ display: "flex", gap: 56, opacity: machines }}>
        {["3090", "5090", "SPARK"].map((n, i) => (
          <div key={n} style={{ textAlign: "center" }}>
            <div style={{
              width: 120, height: 60, borderRadius: 8,
              border: "1px solid rgba(255,255,255,0.25)",
              background: "linear-gradient(160deg, rgba(255,255,255,0.09), rgba(255,255,255,0.02))",
              boxShadow: "0 18px 46px rgba(0,0,0,0.5)",
            }} />
            <div style={{ fontFamily: "var(--mono)", fontSize: 11, letterSpacing: "0.2em", color: "var(--ink-dim)", marginTop: 10 }}>
              {n === "SPARK" ? "DGX SPARK" : `RTX ${n}`}
            </div>
          </div>
        ))}
      </div>

      {/* model families moving forward in the darkness */}
      <div style={{ display: "flex", gap: 18, marginTop: 44, alignItems: "flex-end" }}>
        {Array.from({ length: 14 }).map((_, i) => {
          const on = models > i / 14;
          return (
            <motion.div
              key={i}
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: on ? 0.7 : 0.1, y: 0 }}
              transition={{ delay: i * 0.08, duration: 0.5 }}
              style={{
                width: 26 + (i % 4) * 10, height: 40 + (i % 3) * 22,
                borderRadius: 6,
                border: "1px solid rgba(255,255,255,0.2)",
                background: "rgba(255,255,255,0.05)",
              }}
            />
          );
        })}
      </div>

      {/* the beats */}
      <div style={{ display: "flex", gap: 26, marginTop: 40 }}>
        {BEATS.map((b) => (
          <div key={b.label} style={{ textAlign: "center", opacity: after(lt, b.at, 0.7) }}>
            <div style={{
              width: 44, height: 44, margin: "0 auto", borderRadius: "50%",
              border: "1px solid rgba(118,185,0,0.5)",
              background: "rgba(118,185,0,0.08)",
              display: "grid", placeItems: "center",
              fontFamily: "var(--mono)", fontSize: 15, color: "var(--green-bright)",
            }}>
              {b.icon}
            </div>
            <div style={{ fontFamily: "var(--mono)", fontSize: 11, letterSpacing: "0.14em", color: "var(--ink-dim)", marginTop: 10, maxWidth: 120 }}>
              {b.label}
            </div>
          </div>
        ))}
      </div>

      <div style={{ position: "absolute", bottom: 195, opacity: motto }}>
        <Statement text="Run it. Measure it. Find the limit." op={motto} size="clamp(28px, 3.2vw, 48px)" green />
      </div>
    </SceneShell>
  );
}
