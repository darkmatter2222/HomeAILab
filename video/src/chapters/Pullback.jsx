// 5:25–6:10 — THE GREAT PULLBACK
// Pulling back, we discover the three machines sit under a giant floating
// decision map. At its center: WHAT DO YOU WANT TO RUN? Branches unfold
// slowly; green paths where there's a good match, gray where there are
// tradeoffs. No giant red Xs.
import { motion } from "framer-motion";
import { SceneShell, Statement, HardwareUnit, EASE } from "../prims.jsx";
import { after, clamp01 } from "../clock.js";
import { SCENES } from "../timeline.js";

const SCENES2 = SCENES;

const BRANCHES = [
  { label: "FAST LOCAL ASSISTANT", matches: ["5090"] },
  { label: "CODING", matches: ["3090", "5090"] },
  { label: "LARGE DENSE MODELS", matches: ["SPARK"] },
  { label: "GIANT MoE", matches: ["SPARK"] },
  { label: "LONG CONTEXT", matches: ["SPARK"] },
  { label: "MULTIPLE AGENTS", matches: ["5090", "SPARK"] },
];

const MACHINES = [
  { id: "3090", x: -24 },
  { id: "5090", x: 0 },
  { id: "SPARK", x: 24 },
];

export default function Pullback({ t }) {
  const lt = t - SCENES2[7].from;
  const pull = after(lt, 1.5, 1.6);       // the pull-back reveal
  const center = after(lt, 5, 0.8);       // the central question
  const branches = clamp01((lt - 8) / 22); // slow unfold 8..30s
  const paths = after(lt, 20, 1.4);       // match paths light
  const start = after(lt, 30, 1.0);       // "start with the workload"

  // branch row positions (y %) and each machine's y
  const branchY = (i) => 22 + i * 10.5;
  const machineY = (id) => {
    const i = MACHINES.findIndex((m) => m.id === id);
    return 22 + i * 22;
  };

  return (
    <SceneShell>
      {/* the floating map */}
      <div style={{ position: "relative", width: "min(1180px, 84vw)", height: 560, opacity: pull }}>
        {/* center node */}
        <div style={{ position: "absolute", left: "50%", top: "50%", transform: "translate(-50%,-50%)", textAlign: "center", zIndex: 3 }}>
          <div style={{
            padding: "16px 30px", borderRadius: 12,
            border: "1px solid rgba(118,185,0,0.6)",
            background: "rgba(118,185,0,0.08)",
            boxShadow: "0 0 50px rgba(118,185,0,0.25)",
          }}>
            <div style={{ fontFamily: "var(--sans)", fontSize: 26, fontWeight: 750, color: "var(--green-bright)", letterSpacing: "0.02em" }}>
              WHAT DO YOU WANT TO RUN?
            </div>
            <div style={{ fontFamily: "var(--mono)", fontSize: 10.5, letterSpacing: "0.24em", color: "var(--ink-dim)", marginTop: 6 }}>
              START WITH THE WORKLOAD
            </div>
          </div>
        </div>

        {/* branch nodes */}
        {BRANCHES.map((b, i) => {
          const on = branches > (i + 1) / BRANCHES.length;
          return (
            <motion.div
              key={b.label}
              initial={{ opacity: 0, x: 40 }}
              animate={{ opacity: on ? 1 : 0.15, x: on ? 0 : 40 }}
              transition={{ duration: 0.9, ease: EASE }}
              style={{
                position: "absolute", left: "8%", top: `${branchY(i)}%`,
                width: 230, padding: "12px 16px",
                border: "1px solid rgba(255,255,255,0.18)",
                borderRadius: 8,
                background: "rgba(255,255,255,0.04)",
                fontFamily: "var(--mono)", fontSize: 12.5, letterSpacing: "0.12em",
                color: on ? "var(--ink)" : "var(--ink-faint)",
              }}
            >
              {b.label}
            </motion.div>
          );
        })}

        {/* machines on the right */}
        {MACHINES.map((m) => (
          <motion.div
            key={m.id}
            initial={{ opacity: 0, x: -30 }}
            animate={{ opacity: pull, x: 0 }}
            transition={{ duration: 1, ease: EASE }}
            style={{
              position: "absolute", right: "4%", top: `${machineY(m.id)}%`,
              padding: "14px 22px", borderRadius: 8,
              border: "1px solid rgba(118,185,0,0.5)",
              background: "rgba(118,185,0,0.07)",
              fontFamily: "var(--sans)", fontSize: 17, fontWeight: 700, color: "var(--ink)",
            }}
          >
            {m.id === "SPARK" ? "DGX SPARK" : `RTX ${m.id}`}
          </motion.div>
        ))}

        {/* paths: SVG curves from each branch to matching machines */}
        <svg style={{ position: "absolute", inset: 0, width: "100%", height: "100%", pointerEvents: "none" }} viewBox="0 0 100 100" preserveAspectRatio="none">
          {BRANCHES.map((b, i) => {
            const by = branchY(i) / 100 * 100;
            const x1 = 30; // right edge of branch node
            const x2 = 88; // machine left edge
            return MACHINES.map((m) => {
              const match = b.matches.includes(m.id);
              const my = machineY(m.id) / 100 * 100;
              const visible = paths > 0.3 && b.matches.length;
              if (!match) {
                // gray tradeoff path only for the first few (avoid hairball)
                if (i > 2 || m.id !== "3090") return null;
                return (
                  <motion.path
                    key={`${i}-${m.id}-g`}
                    initial={{ pathLength: 0, opacity: 0 }}
                    animate={{ pathLength: 1, opacity: paths * 0.3 }}
                    transition={{ duration: 1, ease: EASE }}
                    d={`M ${x1} ${by} C ${(x1 + x2) / 2} ${by}, ${(x1 + x2) / 2} ${my}, ${x2} ${my}`}
                    fill="none"
                    stroke="rgba(255,255,255,0.5)"
                    strokeWidth={1}
                    strokeDasharray="3 4"
                    vectorEffect="non-scaling-stroke"
                  />
                );
              }
              return (
                <motion.path
                  key={`${i}-${m.id}`}
                  initial={{ pathLength: 0, opacity: 0 }}
                  animate={{ pathLength: 1, opacity: paths }}
                  transition={{ duration: 1.1, ease: EASE, delay: (i % 3) * 0.15 }}
                  d={`M ${x1} ${by} C ${(x1 + x2) / 2} ${by}, ${(x1 + x2) / 2} ${my}, ${x2} ${my}`}
                  fill="none"
                  stroke="rgba(118,185,0,0.7)"
                  strokeWidth={1.6}
                  vectorEffect="non-scaling-stroke"
                  style={{ filter: "drop-shadow(0 0 4px rgba(118,185,0,0.5))" }}
                />
              );
            });
          })}
        </svg>
      </div>

      <div style={{ position: "absolute", bottom: 195, opacity: start }}>
        <Statement text="Start with the workload." op={start} size="clamp(26px, 2.8vw, 42px)" />
      </div>
    </SceneShell>
  );
}
