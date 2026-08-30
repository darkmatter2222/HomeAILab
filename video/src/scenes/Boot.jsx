import { motion } from "framer-motion";
import { SceneShell, ArchitectureDiagram } from "../ui.jsx";

// Claude Code is the client; the router is the single entry point.
const LINES = [
  ["$ claude-cluster.bat", "cmd"],
  ["ANTHROPIC_BASE_URL  http://192.168.86.48:8010", "var(--ink-dim)"],
  ["AUTH                <router key>  ·  model qwen3.8", "var(--ink-dim)"],
  ["context             262,144 tokens  ·  thinking OFF", "var(--ink-dim)"],
  ["compact window      245,760  (16K headroom)  ·  max output 8,192", "var(--ink-dim)"],
  ["probing /router/status …", "var(--ink-dim)"],
  ["5090 ✓ 3090 ✓  Spark ✓   ·   capacity 19", "var(--green-bright)"],
];

// The world opens here: the full fleet topology, then we dolly toward the door.
export default function Boot({ num }) {
  return (
    <SceneShell>
      {/* open on the architecture diagram — the whole world, at a glance */}
      <div style={{ flex: 1, minHeight: 0, width: "100%", display: "flex", flexDirection: "column" }}>
        <div style={{ fontFamily: "var(--mono)", fontSize: 12, letterSpacing: "0.32em", color: "var(--green)", marginBottom: 10, marginTop: 4 }}>
          {String(num).padStart(2, "0")} · CLIENT → CLUSTER
        </div>
        <div style={{ flex: 1, minHeight: 0 }}>
          <ArchitectureDiagram compact animate={true} />
        </div>
      </div>

      {/* the terminal types in as we zoom toward the door */}
      <div style={{ fontFamily: "var(--mono)", fontSize: 15, lineHeight: 1.95, width: "min(680px, 72vw)", marginTop: 14 }}>
        {LINES.map((l, i) => (
          <motion.div
            key={i}
            initial={{ opacity: 0, x: -10 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: 0.9 + i * 0.7, duration: 0.4 }}
            style={{ color: l[1] === "cmd" ? "var(--ink)" : l[1], display: "flex", gap: 12 }}
          >
            <span style={{ color: "var(--green)", minWidth: 26 }}>{i === 0 ? "$" : "·"}</span>
            <span>{l[0]}</span>
          </motion.div>
        ))}
        <motion.div
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.9 + LINES.length * 0.7 }}
          style={{ fontFamily: "var(--mono)", fontSize: 13, color: "var(--ink-dim)", display: "flex", gap: 12, marginTop: 6 }}
        >
          <span style={{ color: "var(--green)", minWidth: 26 }}>✓</span>
          <span>all Claude roles (Fable/Opus/Sonnet/Haiku + subagents) → one local model</span>
        </motion.div>
      </div>
    </SceneShell>
  );
}
