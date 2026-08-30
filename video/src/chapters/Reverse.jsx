// 6:55–7:30 — REVERSE IT
// Everything freezes. The camera turns around: hardware moves to the top,
// each machine projects an envelope into the model landscape. The recurring
// phrase: WHAT IS MY PRACTICAL MODEL ENVELOPE?
import { motion } from "framer-motion";
import { SceneShell, Statement, EASE } from "../prims.jsx";
import { after, clamp01 } from "../clock.js";
import { SCENES } from "../timeline.js";

const SCENE = SCENES[9];

const MACHINES = [
  { id: "3090", name: "RTX 3090", env: 0.32 },
  { id: "5090", name: "RTX 5090", env: 0.52 },
  { id: "SPARK", name: "DGX SPARK", env: 0.85 },
];

export default function Reverse({ t }) {
  const lt = t - SCENE.from;
  const freeze = after(lt, 1.5, 0.8);
  const turn = clamp01((lt - 5) / 2.5);        // the turnaround
  const envelopes = clamp01((lt - 9) / 12);    // cones project 9..21s
  const phrase = after(lt, 25, 1.0);

  return (
    <SceneShell>
      {/* hardware now at the top */}
      <div style={{ position: "absolute", top: 70, left: 0, right: 0, display: "flex", justifyContent: "center", gap: 140, opacity: 0.3 + turn * 0.7 }}>
        {MACHINES.map((m, i) => (
          <div key={m.id} style={{ textAlign: "center", opacity: 1 - i * 0.06 }}>
            <div style={{
              width: 110, height: 56, margin: "0 auto", borderRadius: 8,
              border: "1px solid rgba(255,255,255,0.3)",
              background: "linear-gradient(160deg, rgba(255,255,255,0.1), rgba(255,255,255,0.02))",
            }} />
            <div style={{ fontFamily: "var(--mono)", fontSize: 11.5, letterSpacing: "0.2em", color: "var(--ink-dim)", marginTop: 12 }}>{m.name}</div>
          </div>
        ))}
      </div>

      {/* envelopes projecting down into the landscape */}
      <div style={{ position: "absolute", top: 210, left: 0, right: 0, display: "flex", justifyContent: "center", gap: 140, height: 260 }}>
        {MACHINES.map((m) => (
          <div key={m.id} style={{ position: "relative", width: 220, height: 260 }}>
            {/* the landscape strip this machine can reach */}
            <div style={{ position: "absolute", inset: 0, borderRadius: 12, background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.1)" }} />
            {/* envelope: a cone of reach, taller for the Spark */}
            <motion.div
              initial={{ opacity: 0, scaleY: 0 }}
              animate={{ opacity: envelopes, scaleY: 1 }}
              transition={{ duration: 1.4, ease: EASE, delay: MACHINES.indexOf(m) * 0.4 }}
              style={{
                position: "absolute", top: 0, left: "50%", transformOrigin: "top center",
                width: 200, height: `${m.env * 100}%`,
                transform: "translateX(-50%)",
                clipPath: `polygon(50% 0, 100% ${Math.min(100, m.env * 130)}%, 0 ${Math.min(100, m.env * 130)}%)`,
                background: "linear-gradient(180deg, rgba(118,185,0,0.3), rgba(118,185,0,0.04))",
              }}
            />
            {/* model blocks inside the envelope */}
            {Array.from({ length: 5 }).map((_, bi) => {
              const inEnv = bi / 5 < m.env;
              return (
                <motion.div
                  key={bi}
                  initial={{ opacity: 0 }}
                  animate={{ opacity: envelopes * (inEnv ? 0.9 : 0.15) }}
                  transition={{ delay: 0.3 + MACHINES.indexOf(m) * 0.4 + bi * 0.1 }}
                  style={{
                    position: "absolute",
                    left: `${18 + bi * 14}%`,
                    top: `${(bi * 21) % 80}%`,
                    width: inEnv ? 16 : 12, height: inEnv ? 16 : 12,
                    background: inEnv ? "rgba(118,185,0,0.55)" : "rgba(255,255,255,0.15)",
                    borderRadius: 3,
                    border: inEnv ? "none" : "1px dashed rgba(255,255,255,0.25)",
                  }}
                />
              );
            })}
            <div style={{ position: "absolute", bottom: -26, left: 0, right: 0, textAlign: "center", fontFamily: "var(--mono)", fontSize: 11, letterSpacing: "0.18em", color: "var(--ink-faint)" }}>
              {m.name} ENVELOPE
            </div>
          </div>
        ))}
      </div>

      <div style={{ position: "absolute", bottom: 195, opacity: phrase }}>
        <Statement
          text="What is my practical model envelope?"
          op={phrase}
          size="clamp(26px, 2.8vw, 44px)"
          green
        />
        <div style={{ fontFamily: "var(--mono)", fontSize: 11.5, letterSpacing: "0.26em", color: "var(--ink-faint)", marginTop: 14, opacity: phrase }}>
          THE RECURRING QUESTION
        </div>
      </div>
    </SceneShell>
  );
}
