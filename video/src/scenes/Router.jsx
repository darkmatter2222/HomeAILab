import { motion } from "framer-motion";
import { useState, useEffect } from "react";
import { SceneShell, SceneTitle, Card, KV, TokenStream } from "../ui.jsx";

const LANES = [
  { gpu: "RTX 5090 · RedPCv2", ip: "192.168.86.37:8006", engine: "vLLM 0.27.1 · NVFP4 · spec OFF", cap: 2, prio: 1, color: "var(--green)" },
  { gpu: "RTX 3090 · Databrick", ip: "host.docker.internal:8006", engine: "llama.cpp · Q4_K_M · MTP", cap: 1, prio: 2, color: "var(--cyan)" },
  { gpu: "DGX Spark GB10", ip: "192.168.86.39:8006", engine: "vLLM 0.25.1 · NVFP4 · MTP ON", cap: 16, prio: 3, color: "var(--amber)" },
];

// Which lane each of the 7 simulated requests lands on.
const SCRIPT = [0, 1, 2, 2, 2, 0, "full"];

function LaneBar({ gpu, ip, engine, cap, prio, color, load, delay, hot }) {
  return (
    <motion.div
      className="card"
      initial={{ opacity: 0, x: 40 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay, duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
      style={{ position: "relative", overflow: "hidden", border: hot ? "1px solid rgba(255,84,112,0.4)" : "1px solid var(--panel-line)" }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "4px 2px" }}>
        <div style={{ fontFamily: "var(--mono)" }}>
          <div style={{ fontSize: 15, fontWeight: 700 }}>{gpu}</div>
          <div style={{ fontSize: 11, color: "var(--ink-faint)", marginTop: 2 }}>{ip} · {engine}</div>
        </div>
        <div style={{ fontFamily: "var(--mono)", fontSize: 12, textAlign: "right" }}>
          <span style={{ color: "var(--ink-faint)" }}>P{prio} · cap </span>
          <span style={{ color: "var(--green-bright)" }}>{cap}</span>
          <span style={{ color: "var(--ink-dim)" }}> · busy {load}/{cap}</span>
        </div>
      </div>
      <div style={{ height: 8, background: "rgba(255,255,255,0.06)", borderRadius: 4, margin: "10px 0 2px", overflow: "hidden" }}>
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${(load / cap) * 100}%` }}
          transition={{ duration: 0.7, ease: "easeOut" }}
          style={{ height: "100%", background: color, boxShadow: `0 0 12px ${color}` }}
        />
      </div>
    </motion.div>
  );
}

export default function Router({ num }) {
  const [stage, setStage] = useState(0);
  useEffect(() => {
    const ids = [];
    [1, 2, 3, 4, 5, 6, 7, 8].forEach((n, i) => {
      ids.push(setTimeout(() => setStage(n), i * 1300 + 1100));
    });
    return () => ids.forEach(clearTimeout);
  }, []);

  const loads = [0, 0, 0];
  SCRIPT.slice(0, Math.min(stage, SCRIPT.length)).forEach((s) => { if (typeof s === "number") loads[s] += 1; });

  return (
    <SceneShell>
      <SceneTitle num={num} kicker="GPU ROUTER" title="Strict-priority ingress" />
      <div style={{ display: "grid", gridTemplateColumns: "1.55fr 1fr", gap: 18 }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <motion.div
            initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2, duration: 0.6 }}
            className="card"
            style={{ display: "flex", alignItems: "center", gap: 14, padding: "14px 16px" }}
          >
            <div style={{ fontFamily: "var(--mono)", fontSize: 13.5 }}>
              <div style={{ color: "var(--ink)" }}>Claude Code  →  router :8010</div>
              <div style={{ fontSize: 11, color: "var(--ink-faint)", marginTop: 2 }}>ANTHROPIC_BASE_URL=http://192.168.86.48:8010 · key qwen38-router-7f3a9c2e</div>
            </div>
            {/* live request stream */}
            <svg viewBox="0 0 220 40" style={{ flex: 1, height: 40, minWidth: 120 }}>
              <path d="M 8 20 L 200 20" stroke="rgba(118,185,0,0.14)" strokeWidth="1.5" fill="none" />
              <TokenStream d="M 8 20 L 200 20" duration={1.6} delay={0.8} count={2} />
            </svg>
          </motion.div>

          {LANES.map((l, i) => (
            <LaneBar key={i} {...l} load={loads[i]} delay={0.5 + i * 0.35} hot={stage >= 8 && l.cap - loads[i] <= 0} />
          ))}

          <motion.div
            className="card"
            initial={{ opacity: 0 }} animate={{ opacity: stage >= 8 ? 1 : 0 }}
            transition={{ delay: 8.4 }}
            style={{ display: "flex", alignItems: "center", gap: 12, padding: "12px 16px" }}
          >
            <motion.div
              initial={{ scale: 0.85, opacity: 0 }} animate={{ scale: 1, opacity: 1 }}
              transition={{ delay: 8.4, type: "spring", stiffness: 300 }}
              style={{ fontFamily: "var(--mono)", fontSize: 13, display: "flex", alignItems: "center", gap: 10 }}
            >
              <span style={{ background: "rgba(255,84,112,0.12)", border: "1px solid rgba(255,84,112,0.4)", padding: "4px 10px", borderRadius: 6, color: "var(--danger)" }}>
                500 · capacity_exhausted
              </span>
              <span style={{ color: "var(--ink-dim)" }}>
                total in-flight = total capacity (19) → “try again”.
                <span style={{ color: "var(--ink-faint)", fontSize: 11 }}> (was 503 — 500 reads as a retry, not a fault)</span>
              </span>
            </motion.div>
          </motion.div>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <Card title="Per-request algorithm" delay={0.4}>
            <KV
              rows={[
                ["probe", "every 2 s · vLLM /metrics + llama /slots"],
                ["authoritative", "router in-flight count", "g"],
                ["gate", "cap − busy − in-flight ≥ 1"],
                ["route", "P1 5090 → P2 3090 → P3 Spark", "g"],
                ["500 only", "when ALL backends at live max"],
                ["sticky", "session pins its GPU (KV/prefix)"],
                ["total cap", "19 (2 + 1 + 16)", "g"],
              ]}
            />
          </Card>
          <Card title="Unified contract" dim="one signature" delay={1.0}>
            <div style={{ fontFamily: "var(--mono)", fontSize: 12.5, color: "var(--ink-dim)", lineHeight: 1.85 }}>
              vLLM and llama.cpp expose <b style={{ color: "var(--ink)" }}>different</b> /v1/models shapes. The router answers it itself —
              <div style={{ marginTop: 8, color: "var(--green-bright)", fontSize: 12 }}>
                qwen3.8 · owned_by vllm · max_model_len 262144
              </div>
              so every client sees <b style={{ color: "var(--ink)" }}>one</b> contract no matter which GPU answers.
              Auth is case-insensitive (401 on a missing key).
            </div>
          </Card>
        </div>
      </div>
    </SceneShell>
  );
}
