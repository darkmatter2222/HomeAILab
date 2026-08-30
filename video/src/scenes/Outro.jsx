import { motion } from "framer-motion";

const FACTS = [
  "3 hosts · 3 GPUs · 1 signature",
  "total capacity 19 · 5090:2 + 3090:1 + Spark:16",
  "262,144-token context · 254K prompt verified",
  "TTFT 0.10 s (Spark) · 0.2 s (3090) · prefix-cache tracked",
  "Portainer deploys · Grafana watches everything",
];

export default function Outro({ num }) {
  return (
    <div style={{ textAlign: "center", width: "100%", height: "100%", display: "flex", flexDirection: "column", justifyContent: "center" }}>
      <motion.div
        initial={{ opacity: 0, scale: 0.9, filter: "blur(12px)" }}
        animate={{ opacity: 1, scale: 1, filter: "blur(0px)" }}
        transition={{ duration: 1.1, ease: [0.16, 1, 0.3, 1] }}
        style={{
          fontFamily: "var(--mono)",
          fontSize: "clamp(38px, 6.6vw, 80px)",
          fontWeight: 800,
          letterSpacing: "0.02em",
          color: "var(--green-bright)",
          textShadow: "0 0 60px rgba(118,185,0,0.4)",
          willChange: "transform, opacity",
        }}
      >
        QWEN3.8 FLEET
      </motion.div>
      <motion.div
        initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.7, duration: 0.8, ease: [0.22, 1, 0.36, 1] }}
        style={{ fontFamily: "var(--sans)", fontSize: 18, color: "var(--ink-dim)", marginTop: 12, letterSpacing: "0.06em" }}
      >
        three GPUs · one model · one contract
      </motion.div>
      <div style={{ display: "flex", gap: 18, justifyContent: "center", marginTop: 40, flexWrap: "wrap" }}>
        {FACTS.map((f, i) => (
          <motion.div
            key={i}
            initial={{ opacity: 0, y: 14, scale: 0.97 }} animate={{ opacity: 1, y: 0, scale: 1 }}
            transition={{ delay: 1.2 + i * 0.3, duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
            className="card"
            style={{ padding: "12px 20px", fontFamily: "var(--mono)", fontSize: 13, color: "var(--ink-dim)", border: "1px solid var(--panel-line)" }}
          >
            <span style={{ color: "var(--green-bright)" }}>▸ </span>{f}
          </motion.div>
        ))}
      </div>
      <motion.div
        initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 3.2, duration: 1 }}
        style={{ marginTop: 48, fontFamily: "var(--mono)", fontSize: 12, color: "var(--ink-faint)", letterSpacing: "0.2em" }}
      >
        modeloptimizer · 2026
      </motion.div>
    </div>
  );
}
