import { motion } from "framer-motion";
import { Card, KV, SceneShell, SceneTitle } from "../ui.jsx";

const JOBS = [
  { job: "vllm-dgxspark", target: "host.docker.internal:8006 (ds4 shim fronts it)", device: "Spark GB10" },
  { job: "vllm-5090", target: "192.168.86.37:8006", device: "RTX 5090" },
  { job: "llamacpp-3090", target: "192.168.86.48:8006", device: "RTX 3090" },
  { job: "node", target: "host.docker.internal:9100", device: "Spark host" },
  { job: "dcgm", target: "host.docker.internal:9400", device: "GPU row" },
  { job: "qwen38-router", target: "192.168.86.48:8010 · /router/metrics", device: "ingress" },
];

function Sparkline({ seed = 0, color = "var(--green)", delay = 0.5 }) {
  const pts = Array.from({ length: 26 }, (_, i) => {
    const x = (i / 25) * 220;
    const y = 42 - (Math.sin(i * 0.7 + seed) * 13 + Math.sin(i * 0.23 + seed * 2) * 8 + 16);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
  return (
    <div style={{ background: "rgba(255,255,255,0.03)", borderRadius: 8, padding: "8px 10px" }}>
      <svg viewBox="0 0 220 48" style={{ width: "100%", height: 48 }}>
        <motion.polyline
          points={pts} fill="none" stroke={color} strokeWidth="1.6"
          initial={{ pathLength: 0, opacity: 0 }} animate={{ pathLength: 1, opacity: 1 }}
          transition={{ delay, duration: 1.4, ease: "easeOut" }}
        />
      </svg>
    </div>
  );
}

export default function Monitoring({ num }) {
  return (
    <SceneShell>
      <SceneTitle num={num} kicker="OBSERVABILITY" title="Grafana sees every GPU" />
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1.3fr", gap: 16 }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <Card title="Prometheus scrape jobs" dim="Spark :9090 · 5 s · POST /-/reload" delay={0.1}>
            <div style={{ display: "flex", flexDirection: "column", gap: 7 }}>
              {JOBS.map((j, i) => (
                <motion.div
                  key={j.job}
                  initial={{ opacity: 0, x: -12 }} animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: 0.3 + i * 0.24, duration: 0.4 }}
                  style={{ fontFamily: "var(--mono)", fontSize: 12, display: "grid", gridTemplateColumns: "128px 1fr 84px", gap: 10, color: "var(--ink-dim)" }}
                >
                  <span style={{ color: "var(--green-bright)" }}>{j.job}</span>
                  <span>{j.target}</span>
                  <span style={{ color: "var(--ink-faint)", textAlign: "right" }}>{j.device}</span>
                </motion.div>
              ))}
            </div>
          </Card>
          <motion.div
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 2.2 }}
            style={{ fontFamily: "var(--mono)", fontSize: 11.5, color: "var(--ink-faint)", lineHeight: 1.8 }}
          >
            gotcha — Grafana 13 Unified Storage: dashboards live in the SQLite <span style={{ color: "var(--green-bright)" }}>resource</span> table,
            not the legacy table; the classic PUT 404s. Edits must sync <b>resource</b> + <b>resource_history</b> together, then restart Grafana.
          </motion.div>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
          <Card title="TIME TO FIRST TOKEN" dim="P50 / P95 / P99 · per device" delay={0.4}>
            <Sparkline seed={2} delay={0.8} />
            <div style={{ fontFamily: "var(--mono)", fontSize: 10.5, color: "var(--ink-faint)", marginTop: 8, lineHeight: 1.6 }}>
              time_to_first_token_seconds_bucket · MODEL TTFT P95 COMPARISON
            </div>
          </Card>
          <Card title="PREFIX CACHE HIT RATE" dim={'device =~ "RTX|DGX Spark"'} delay={0.6}>
            <Sparkline seed={5} color="var(--cyan)" delay={1.0} />
            <div style={{ fontFamily: "var(--mono)", fontSize: 10.5, color: "var(--ink-faint)", marginTop: 8, lineHeight: 1.6 }}>
              prefix_cache_hits_total / queries · sticky sessions keep the prefix on one GPU
            </div>
          </Card>
          <Card title="SPEC DECODE ACCEPTANCE" dim="by draft position" delay={0.8}>
            <Sparkline seed={9} color="var(--amber)" delay={1.2} />
            <div style={{ fontFamily: "var(--mono)", fontSize: 10.5, color: "var(--ink-faint)", marginTop: 8, lineHeight: 1.6 }}>
              spec_decode_num_accepted_tokens_per_pos_total · ~87 → 56 → 38%
            </div>
          </Card>
          <Card title="END-TO-END LATENCY + QUEUE" dim="P50 / P95 / P99" delay={1.0}>
            <Sparkline seed={13} delay={1.4} />
            <div style={{ fontFamily: "var(--mono)", fontSize: 10.5, color: "var(--ink-faint)", marginTop: 8, lineHeight: 1.6 }}>
              inter-token latency (TPOT) · model queue pressure · KV cache used
            </div>
          </Card>
          <motion.div
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 1.9 }}
            style={{ gridColumn: "1 / -1", fontFamily: "var(--mono)", fontSize: 12, color: "var(--ink-dim)", lineHeight: 1.7, padding: "0 4px" }}
          >
            dashboard <b style={{ color: "var(--green-bright)" }}>adrsc9f</b> (uid) · v8 “Throughput Without Contention” + NVIDIA Refined Theme + <b>device</b>
            filter (RTX|DGX Spark) + DCGM row + fleet-uptime. Proxied at <b>http://192.168.86.48/grafana</b>.
          </motion.div>
        </div>
      </div>
    </SceneShell>
  );
}
