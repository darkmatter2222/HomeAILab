import { motion } from "framer-motion";
import { Card, SceneShell, SceneTitle, Bar, Stat } from "../ui.jsx";

const POS = [
  { label: "draft pos 0", pct: 87 },
  { label: "draft pos 1", pct: 56 },
  { label: "draft pos 2", pct: 38 },
];

function ChainChip({ label, accent = false, delay, accept = null }) {
  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.85 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ delay, type: "spring", stiffness: 260 }}
      style={{
        fontFamily: "var(--mono)", fontSize: 12, padding: "7px 12px", borderRadius: 8,
        border: `1px solid ${accent ? "rgba(118,185,0,0.5)" : "rgba(152,161,179,0.4)"}`,
        background: accent ? "rgba(118,185,0,0.08)" : "rgba(152,161,179,0.08)",
        color: accent ? "var(--green-bright)" : "var(--ink-dim)",
        display: "flex", gap: 8, alignItems: "center",
      }}
    >
      {label}
      {accept != null && <span style={{ color: "var(--green)", fontSize: 11 }}>{accept}%</span>}
    </motion.div>
  );
}

export default function MTP({ num }) {
  return (
    <SceneShell>
      <SceneTitle num={num} kicker="MTP SPECULATIVE DECODE" title="The model drafts itself" />
      <div style={{ display: "grid", gridTemplateColumns: "1.2fr 1fr", gap: 16 }}>
        <div>
          <motion.div
            className="card"
            initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2, duration: 0.6 }}
            style={{ padding: "16px 18px" }}
          >
            <div style={{ fontFamily: "var(--mono)", fontSize: 13.5, color: "var(--ink-dim)", lineHeight: 1.85 }}>
              Qwen3.8 ships a <b style={{ color: "var(--green-bright)" }}>built-in multi-token-prediction head</b>. The model proposes the next
              3 tokens from its own weights — no separate drafter file, no extra GPU.
            </div>

            {/* draft chain */}
            <div style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 18, flexWrap: "wrap" }}>
              <ChainChip label="verify" delay={0.8} />
              {[0, 1, 2].map((i) => (
                <div key={i} style={{ display: "flex", gap: 8, alignItems: "center" }}>
                  <ChainChip label={`draft ${i + 1}`} accent delay={0.9 + i * 0.35} accept={POS[i].pct} />
                  {i < 2 && (
                    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}
                      transition={{ delay: 0.9 + i * 0.35 + 0.2 }}
                      style={{ fontFamily: "var(--mono)", fontSize: 11, color: "var(--ink-faint)" }}>→</motion.div>
                  )}
                </div>
              ))}
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 14, marginTop: 20 }}>
              {POS.map((p, i) => (
                <div key={i}><Bar pct={p.pct} label={p.label} value={`~${p.pct}%`} delay={1.1 + i * 0.4} height={8} /></div>
              ))}
            </div>
            <motion.div
              initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 2.6 }}
              style={{ fontFamily: "var(--mono)", fontSize: 11.5, color: "var(--ink-faint)", marginTop: 12 }}
            >
              acceptance decays down the chain · cumulative ~58–61% · higher on repetitive content
            </motion.div>
          </motion.div>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <Card title="Single-stream · Spark NVFP4" dim="200-tok decode-only · clean GPU" delay={0.4}>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14, textAlign: "center" }}>
              <Stat value={12.5} unit="tok/s · no-spec" delay={0.7} />
              <Stat value={19.5} unit="tok/s · MTP num_spec=3" label="1.56× single-stream win" delay={0.9} />
            </div>
            <motion.div
              initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 1.6 }}
              style={{ fontFamily: "var(--mono)", fontSize: 11, color: "var(--ink-faint)", textAlign: "center", marginTop: 8 }}
            >
              16-wide vs 1-wide is a ~2% wash → keep 16-wide (preserves ~165 aggregate) + MTP
            </motion.div>
          </Card>
          <Card title="The NVFP4 drafter fix" delay={1.2}>
            <div style={{ fontFamily: "var(--mono)", fontSize: 12, color: "var(--ink-dim)", lineHeight: 1.8 }}>
              The grafted MTP head ships <b style={{ color: "var(--amber)" }}>BF16 / full-width</b>, but vLLM builds the drafter’s
              <div style={{ color: "var(--green-bright)", margin: "6px 0", fontSize: 12.5 }}>
                Qwen3_5DecoderLayer from vllm_config.quant_config (NVFP4)
              </div>
              → loader crash. Patch: <b style={{ color: "var(--ink)" }}>shallow-copy vllm_config with quant_config=None</b>. SPEC_DECODE=on is now committed — the fastest single-stream config.
            </div>
          </Card>
        </div>
      </div>
    </SceneShell>
  );
}
