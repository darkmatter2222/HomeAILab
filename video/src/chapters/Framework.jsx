// 6:10–6:55 — THE DECISION FRAMEWORK
// One branch at a time. Fast workloads → compute. Larger models → memory.
// Giant models → capacity. Long context → context ribbon. Multiple agents
// → parallel request paths. Then pull back: all branches visible — the
// conceptual climax.
import { motion } from "framer-motion";
import { SceneShell, Statement, ContextRibbon, EASE } from "../prims.jsx";
import { after, clamp01 } from "../clock.js";
import { SCENES } from "../timeline.js";

const SCENE = SCENES[8];

const STEPS = [
  { key: "resp", at: 0, label: "RESPONSIVENESS", metric: "COMPUTE" },
  { key: "size", at: 6, label: "MODEL SIZE", metric: "MEMORY" },
  { key: "giant", at: 12, label: "GIANT MODELS", metric: "CAPACITY" },
  { key: "ctx", at: 17, label: "LONG CONTEXT", metric: "CONTEXT" },
  { key: "agents", at: 23, label: "MULTIPLE AGENTS", metric: "THROUGHPUT" },
];

export default function Framework({ t }) {
  const lt = t - SCENE.from;
  const pullbackAll = after(lt, 29, 1.2); // all branches visible

  // which step is active (0..4), none when pulled back
  const activeIdx = STEPS.reduce((acc, s, i) => (lt >= s.at ? i : acc), -1);
  const showAll = lt >= 29;

  return (
    <SceneShell>
      {/* left: branch list, sequential lighting */}
      <div style={{ display: "flex", flexDirection: "column", gap: 14, width: 320 }}>
        {STEPS.map((s, i) => {
          const on = showAll || activeIdx === i;
          const past = !showAll && activeIdx > i;
          return (
            <motion.div
              key={s.key}
              initial={{ opacity: 0, x: -24 }}
              animate={{ opacity: showAll ? 0.85 : on ? 1 : past ? 0.4 : 0.15, x: 0 }}
              transition={{ duration: 0.7, ease: EASE }}
              style={{
                padding: "12px 18px", borderRadius: 8,
                border: on ? "1px solid rgba(118,185,0,0.6)" : "1px solid rgba(255,255,255,0.14)",
                background: on ? "rgba(118,185,0,0.08)" : "rgba(255,255,255,0.03)",
                fontFamily: "var(--mono)", fontSize: 13, letterSpacing: "0.16em",
                color: on ? "var(--ink)" : "var(--ink-faint)",
                display: "flex", justifyContent: "space-between", alignItems: "center", gap: 16,
              }}
            >
              {s.label}
              {on && <span style={{ color: "var(--green-bright)", fontSize: 11.5, letterSpacing: "0.14em" }}>{s.metric}</span>}
            </motion.div>
          );
        })}
      </div>

      <div style={{ width: 60 }} />

      {/* right: the metric that becomes prominent */}
      <div style={{ width: 420, display: "flex", flexDirection: "column", gap: 30 }}>
        {STEPS.map((s, i) => {
          const on = showAll || activeIdx === i;
          if (!on && !pastVisible(lt, s, i)) return null;
          return (
            <div key={s.key} style={{ opacity: showAll ? 0.5 : on ? 1 : 0.3 }}>
              {s.key === "resp" && <MetricBar label="COMPUTE" pct={showAll ? 0.7 : 0.92} />}
              {s.key === "size" && <MetricBar label="MEMORY" pct={showAll ? 0.7 : 0.78} />}
              {s.key === "giant" && <MetricBar label="CAPACITY" pct={showAll ? 0.7 : 0.95} amber={!showAll} />}
              {s.key === "ctx" && <ContextRibbon fill={showAll ? 0.5 : 0.9} label="CONTEXT" caption={showAll ? "" : "grows with the workload"} />}
              {s.key === "agents" && (
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                  {[0, 1, 2, 3].map((a) => (
                    <motion.div
                      key={a}
                      animate={on && !showAll ? { opacity: [0.4, 1, 0.4] } : {}}
                      transition={{ duration: 1.6, repeat: Infinity, delay: a * 0.3 }}
                      style={{
                        padding: "10px 14px", borderRadius: 6,
                        border: "1px solid rgba(118,185,0,0.45)",
                        background: "rgba(118,185,0,0.08)",
                        fontFamily: "var(--mono)", fontSize: 11, letterSpacing: "0.14em", color: "var(--green-bright)",
                      }}
                    >
                      AGENT {a + 1}
                    </motion.div>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {showAll && (
        <div style={{ position: "absolute", bottom: 195 }}>
          <Statement text="All dimensions, one system." op={pullbackAll} size="clamp(24px, 2.6vw, 40px)" />
        </div>
      )}
    </SceneShell>
  );
}

function pastVisible(lt, s, i) {
  // previous steps stay faintly visible while the next is active
  const next = STEPS[i + 1];
  return i < STEPS.length - 1 && next && lt >= next.at && lt < 29;
}

function MetricBar({ label, pct, amber = false }) {
  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", fontFamily: "var(--mono)", fontSize: 12, letterSpacing: "0.18em", color: "var(--ink-dim)", marginBottom: 8 }}>
        <span>{label}</span>
        <span style={{ color: amber ? "var(--amber)" : "var(--green-bright)" }}>{Math.round(pct * 100)}%</span>
      </div>
      <div style={{ height: 10, borderRadius: 5, background: "rgba(255,255,255,0.06)", overflow: "hidden" }}>
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${pct * 100}%` }}
          transition={{ duration: 1, ease: EASE }}
          style={{
            height: "100%", borderRadius: 5,
            background: amber ? "linear-gradient(90deg, rgba(255,178,77,0.5), rgba(255,178,77,0.2))" : "linear-gradient(90deg, rgba(118,185,0,0.6), rgba(118,185,0,0.2))",
          }}
        />
      </div>
    </div>
  );
}
