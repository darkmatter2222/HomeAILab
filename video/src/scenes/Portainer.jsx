import { motion } from "framer-motion";
import { Card, KV, SceneShell, SceneTitle } from "../ui.jsx";

const STEPS = [
  { t: 0.4, a: "POST /auth  →  { \"jwt\": \"eyJhbGci…\" }", d: "user agenticharness · role admin · Bearer on every call" },
  { t: 1.9, a: "GET /api/endpoints  →  3 · 4 · 5", d: "Databrick (local socket) · DGX Spark · RedPCv2-5090" },
  { t: 3.5, a: "POST /api/stacks/create/standalone/string?endpointId=N", d: "body { Name, EntryPoint, StackFileContent, Prune:true }" },
  { t: 5.1, a: "→ creates + deploys in a single call", d: "Status:1 · ProjectPath /data/compose/<id> · redeploys keep the name" },
];

const STACKS = [
  { stack: "qwen38-27b-3090", ep: 3, img: "llama.cpp server-cuda12", ok: "redeploy #26" },
  { stack: "qwen38-gpu-router", ep: 3, img: "FastAPI ingress :8010", ok: "name kept" },
  { stack: "qwen38-router-ui", ep: 3, img: "python:3.11-slim :8090", ok: "basic auth" },
  { stack: "qwen38-27b-dgxsparx", ep: 4, img: "vLLM arm64-cu13-0.25.1 · NVFP4", ok: "live" },
];

export default function Portainer({ num }) {
  return (
    <SceneShell>
      <SceneTitle num={num} kicker="CONTROL PLANE" title="Portainer deploys everything" />
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1.25fr", gap: 16 }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {STEPS.map((s, i) => (
            <motion.div
              key={i}
              className="card"
              initial={{ opacity: 0, x: -24 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: s.t, duration: 0.55, ease: [0.22, 1, 0.36, 1] }}
              style={{ display: "flex", gap: 14, alignItems: "center" }}
            >
              <div style={{ fontFamily: "var(--mono)", fontSize: 13, color: "var(--green-bright)", minWidth: 26, textAlign: "center", fontWeight: 700 }}>{i + 1}</div>
              <div style={{ fontFamily: "var(--mono)", fontSize: 13.5, lineHeight: 1.55 }}>
                <div style={{ color: "var(--ink)" }}>{s.a}</div>
                <div style={{ color: "var(--ink-faint)", fontSize: 11.5, marginTop: 3 }}>{s.d}</div>
              </div>
            </motion.div>
          ))}
          <motion.div
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 6.4 }}
            style={{ fontFamily: "var(--mono)", fontSize: 12, color: "var(--ink-faint)", lineHeight: 1.7 }}
          >
            gotcha: the create route is <span style={{ color: "var(--green-bright)" }}>standalone</span> (not “compose”) — a numeric type id fails with
            “Invalid value for query parameter”.
          </motion.div>
        </div>

        <Card title="Live stacks · delete + recreate" dim="keeps the name" delay={0.3}>
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {STACKS.map((s, i) => (
              <motion.div
                key={s.stack}
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 1.2 + i * 0.45 }}
                style={{
                  display: "grid", gridTemplateColumns: "200px 54px 1fr", gap: 12,
                  fontFamily: "var(--mono)", fontSize: 12.5, padding: "10px 12px",
                  border: "1px solid rgba(118,185,0,0.12)", borderRadius: 8, background: "rgba(118,185,0,0.04)", alignItems: "center",
                }}
              >
                <span style={{ color: "var(--green-bright)", fontWeight: 600 }}>{s.stack}</span>
                <span style={{ color: "var(--ink-dim)" }}>ep {s.ep}</span>
                <span style={{ color: "var(--ink-faint)", display: "flex", justifyContent: "space-between" }}>
                  <span>{s.img}</span>
                  <motion.span
                    initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 1.5 + i * 0.45 + 0.4 }}
                    style={{ color: "var(--green)", display: "inline-flex", alignItems: "center", gap: 8 }}
                  >
                    <span style={{ width: 8, height: 8, borderRadius: "50%", background: "var(--green)", boxShadow: "0 0 10px var(--green-glow)" }} />
                    {s.ok}
                  </motion.span>
                </span>
              </motion.div>
            ))}
          </div>
          <motion.div
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 3.8 }}
            style={{ marginTop: 14, fontFamily: "var(--mono)", fontSize: 12, color: "var(--ink-faint)", lineHeight: 1.8 }}
          >
            $-escaping: every shell <span style={{ color: "var(--ink-dim)" }}>$</span> in a compose command becomes <b style={{ color: "var(--green-bright)" }}>$$</b> (HF_TOKEN stays single-$).<br />
            25 MiB/s download cap on every fetch — steady-state restarts download nothing.
          </motion.div>
        </Card>
      </div>
    </SceneShell>
  );
}
