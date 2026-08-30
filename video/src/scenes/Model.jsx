import { motion } from "framer-motion";
import { Card, KV, Stat, SceneShell, SceneTitle, Bar } from "../ui.jsx";

export default function Model({ num }) {
  return (
    <SceneShell>
      <SceneTitle num={num} kicker="THE WEIGHTS" title="One model · two paths" />
      <div style={{ display: "grid", gridTemplateColumns: "1.25fr 1fr 1fr", gap: 16 }}>
        <Card title="Qwen3.8-27B · Uncensored" dim="abliterated · Heretic LoRA merge" delay={0.1}>
          <KV
            rows={[
              ["class", "27B hybrid linear + full attention"],
              ["layers", "64 total · only 16 full-attention", "g"],
              ["linear layers", "48 · near-O(1) per token", "g"],
              ["perplexity", "7.181  (f16 ≈ 7.156)", "g"],
              ["context cap", "262,144 tokens (verified)", "g"],
              ["abliteration", "refusal dirs removed (Heretic)"],
            ]}
          />
        </Card>

        <Card title="Path A · Q4_K_M · GGUF" dim="→ llama.cpp · RTX 3090" delay={0.25}>
          <KV
            rows={[
              ["file", "Qwen3.8-27B-Uncensored-Q4_K_M.gguf"],
              ["size", "16.8 GiB · MTP head built-in"],
              ["runs on", "RTX 3090 · 24 GB", "g"],
              ["KV dtype", "q4_0 (max that fits 24 GB)"],
              ["VRAM @ 32K", "≈ 20 GiB · ~4 GiB headroom", "g"],
              ["speed", "~60 tok/s decode · prefill 1.15–1.3k", "g"],
            ]}
          />
        </Card>

        <Card title="Path B · NVFP4 · ModelOpt" dim="→ vLLM · 5090 + GB10" delay={0.4}>
          <KV
            rows={[
              ["model", "Qwen3.8-27B-Uncensored-NVFP4-ModelOpt"],
              ["size", "19 GiB NVFP4 · +811 MB MTP graft"],
              ["runs on", "RTX 5090 · DGX Spark GB10", "g"],
              ["KV dtype", "fp8 · GB10 FP4 tensor cores"],
              ["served by", "vLLM (OpenAI + Anthropic)"],
              ["5090", "cap 2 · full 262K/stream · spec OFF", "d"],
              ["Spark", "cap 16 · mem 0.85 · MTP ON", "d"],
            ]}
          />
        </Card>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 16, marginTop: 16 }}>
        <Card delay={0.55}><Stat value={262144} unit="TOKENS" label="context ceiling (verified)" delay={0.7} /></Card>
        <Card delay={0.65}><Stat value={4.0} unit="GiB" label="KV @ 262K · q4_0 (fp8 OOMs)" delay={0.8} /></Card>
        <Card delay={0.75}><Stat value={7.181} unit="PPL" label="near-f16 after abliteration" delay={0.9} suffix="." /></Card>
        <Card delay={0.85}><Stat value={16} unit="OF 64 LAYERS" label="full-attention (48 linear)" delay={1.0} /></Card>
      </div>

      <div style={{ marginTop: 18, maxWidth: 880 }}>
        <Bar label="why 262K fits on 24 GB — KV budget @ 262K (q4_0)" pct={17} value="4.0 / 24 GiB" delay={1.1} />
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 1.6 }}
          style={{ fontFamily: "var(--mono)", fontSize: 12.5, color: "var(--ink-faint)", marginTop: 12, lineHeight: 1.75 }}
        >
          16 layers × GQA 4 kv-heads × 256 head-dim × 262,144 × 2 × 0.5 B ≈ 4.0 GiB. The 48 linear layers barely grow with context,
          so a 254,290-token prompt fits and prefills clean on the 3090.
        </motion.div>
      </div>
    </SceneShell>
  );
}
