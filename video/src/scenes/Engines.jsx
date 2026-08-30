import { motion } from "framer-motion";
import { Card, KV, SceneShell, SceneTitle, Bar } from "../ui.jsx";

export default function Engines({ num }) {
  return (
    <SceneShell>
      <SceneTitle num={num} kicker="ENGINES + SPEED" title="Two engines, one signature" />
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1.1fr", gap: 16 }}>
        <Card title="vLLM" dim="throughput · OpenAI + Anthropic" delay={0.1}>
          <KV
            rows={[
              ["5090", "vllm-openai v0.27.1 · NVFP4"],
              ["Spark GB10", "vllm-arm64-cu13-0.25.1", "g"],
              ["quant", "modelopt_fp4 · fp8 KV"],
              ["attention", "FLASHINFER backend"],
              ["prefix caching", "on (Grafana-tracked)", "g"],
              ["5090", "cap 2 · spec OFF (MTP ckpt incompat)", "d"],
              ["Spark", "cap 16 · mem 0.85 · MTP ON", "g"],
              ["TTFT", "Spark ~0.10 s", "g"],
            ]}
          />
        </Card>

        <Card title="llama.cpp" dim="context king · 24 GB" delay={0.3}>
          <KV
            rows={[
              ["build", "server-cuda12 (ghcr.io/ggml-org)"],
              ["model", "Q4_K_M fused · MTP inline"],
              ["ctx now", "32,768 (shed 262K for speed)", "g"],
              ["batch / ubatch", "4096 / 512 · cont-batching"],
              ["load", "mmap · flash-attn on"],
              ["power", "3090 ~350 W · 1590 MHz"],
              ["TTFT", "~0.2 s (warm/cached)", "g"],
            ]}
          />
        </Card>

        <Card title="Head-to-head" dim="measured · median runs" delay={0.5}>
          <div style={{ display: "flex", flexDirection: "column", gap: 16, marginTop: 4 }}>
            <div>
              <div style={{ fontFamily: "var(--mono)", fontSize: 11.5, color: "var(--ink-faint)", marginBottom: 8 }}>3090 decode (tok/s)</div>
              <Bar label="no-spec baseline" pct={68} value="40.6" delay={0.9} />
              <Bar label="MTP n_max=3 (deployed)" pct={100} value="~60 · 1.47×" delay={1.2} />
            </div>
            <div>
              <div style={{ fontFamily: "var(--mono)", fontSize: 11.5, color: "var(--ink-faint)", marginBottom: 8 }}>Spark NVFP4 aggregate @262K (tok/s)</div>
              <div style={{ display: "flex", gap: 10, alignItems: "flex-end", height: 60 }}>
                {[{ c: 8, v: 94, h: 45 }, { c: 12, v: 131, h: 60 }, { c: 16, v: 165, h: 90 }].map((b, i) => (
                  <div key={b.c} style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: 6 }}>
                    <div style={{ height: b.h / 2, width: "70%", background: "linear-gradient(90deg,var(--green-dim),var(--green))", borderRadius: 4, boxShadow: "0 0 12px rgba(118,185,0,0.5)", display: "flex", alignItems: "center", justifyContent: "center", fontFamily: "var(--mono)", fontSize: 10, color: "#04050a", fontWeight: 700 }}>
                      {b.v}
                    </div>
                    <div style={{ fontFamily: "var(--mono)", fontSize: 10, color: "var(--ink-faint)" }}>c{b.c}</div>
                  </div>
                ))}
              </div>
              <div style={{ fontFamily: "var(--mono)", fontSize: 10.5, color: "var(--ink-faint)", marginTop: 6 }}>concurrency sweep → ~165 @16 (deployed, linear scaling)</div>
            </div>
            <motion.div
              initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 2.4 }}
              style={{ fontFamily: "var(--mono)", fontSize: 11.5, color: "var(--ink-faint)", lineHeight: 1.75 }}
            >
              3090 prefill 1.15–1.3k tok/s — linear layers keep long-context cost low.
            </motion.div>
          </div>
        </Card>
      </div>
    </SceneShell>
  );
}
