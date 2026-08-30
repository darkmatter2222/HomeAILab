import { useEffect, useMemo, useState } from "react";
import { motion, AnimatePresence, useReducedMotion } from "framer-motion";
import "./App.css";

/* ================= THEME (NVIDIA design language) ================= */
const GREEN = "#76B900";
const GREEN_DARK = "#568000";
const INK = "#1A1A1A";
const BG = "#0A0F0A";
const CARD = "rgba(20,28,18,0.55)";
const LINE = "rgba(118,185,0,0.22)";
const TEXT = "#EAF2E2";
const DIM = "#93a38a";
const CYAN = "#5FD4E0";

/* ================= FLEET DATA (from CLAUDE.md) ================= */
const BACKENDS = [
  {
    id: "5090", rank: 1, host: "RedPCv2", ip: "192.168.86.37",
    gpu: "RTX 5090 (Blackwell)", vram: "32 GB", engine: "vLLM 0.27.1",
    engineShort: "vLLM", model: "Qwen3.8-27B-Uncensored NVFP4",
    quant: "same NVFP4 weights", cap: 2,
    stats: ["cap 2 (router cap)", "full 262K per stream", "OpenAI + Anthropic API", "untouched reference"],
  },
  {
    id: "3090", rank: 2, host: "Databrick", ip: "192.168.86.48",
    gpu: "RTX 3090 (Ampere)", vram: "24 GB", engine: "llama.cpp cuda12",
    engineShort: "llama.cpp", model: "Qwen3.8-27B-Uncensored Q4_K_M GGUF",
    quant: "fused MTP head in GGUF", cap: 1,
    stats: ["~60 tok/s decode", "prefill 1.15–1.3k tok/s", "TTFT ~0.2 s", "254k-token prompt verified"],
  },
  {
    id: "spark", rank: 3, host: "DGX Spark", ip: "192.168.86.39",
    gpu: "GB10 (Blackwell)", vram: "122 GiB", engine: "vLLM 0.25.1",
    engineShort: "vLLM", model: "Qwen3.8-27B-Uncensored NVFP4",
    quant: "NVFP4 ModelOpt + MTP graft", cap: 16,
    stats: ["165 tok/s @16 wide", "19.9 tok/s single-stream +MTP", "TTFT ~0.10 s", "262K ctx, fp8 KV"],
  },
  {
    id: "5090", rank: 2, host: "RedPCv2", ip: "192.168.86.37",
    gpu: "RTX 5090 (Blackwell)", vram: "32 GB", engine: "vLLM 0.27.1",
    engineShort: "vLLM", model: "Qwen3.8-27B-Uncensored NVFP4",
    quant: "same NVFP4 weights", cap: 2,
    stats: ["cap 2 (router cap)", "full 262K per stream", "OpenAI + Anthropic API", "untouched reference"],
  },
  {
    id: "3090", rank: 1, host: "Databrick", ip: "192.168.86.48",
    gpu: "RTX 3090 (Ampere)", vram: "24 GB", engine: "llama.cpp cuda12",
    engineShort: "llama.cpp", model: "Qwen3.8-27B-Uncensored Q4_K_M GGUF",
    quant: "fused MTP head in GGUF", cap: 1,
    stats: ["~60 tok/s decode", "prefill 1.15–1.3k tok/s", "TTFT ~0.2 s", "254k-token prompt verified"],
  },
];

const TICKS = 198; // 3 min at 60fps
const TICK_MS = 1000 / 60;

/* ---------- small building blocks ---------- */
function CountUp({ to, dur = 1200, decimals = 0, suffix = "" }) {
  const [v, setV] = useState(0);
  useEffect(() => {
    let raf; const t0 = performance.now();
    const step = (t) => {
      const p = Math.min(1, (t - t0) / dur);
      const e = 1 - Math.pow(1 - p, 3);
      setV(to * e);
      if (p < 1) raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [to, dur]);
  return <span className="countup">{v.toFixed(decimals)}{suffix}</span>;
}

function StatTile({ label, value, sub }) {
  return (
    <div className="tile">
      <div className="tile-val">{value}</div>
      <div className="tile-label">{label}</div>
      {sub && <div className="tile-sub">{sub}</div>}
    </div>
  );
}

/* ---------- animated data packets traveling on an SVG path ---------- */
function Packets({ pathId, count = 3, dur = 2.4, active }) {
  if (!active) return null;
  return (
    <>
      {Array.from({ length: count }).map((_, i) => (
        <circle key={i} r="3.2" className="pkt">
          <animateMotion dur={`${dur}s`} begin={`${i * (dur / count)}s`} repeatCount="indefinite"
            keyPoints="0;1" keyTimes="0;1" calcMode="linear" path={`url(#${pathId})`} />
          <set attributeName="opacity" to="1" dur="0.1s" begin={`${i * (dur / count)}s`} />
        </circle>
      ))}
    </>
  );
}

/* ================= SCENES ================= */

function SceneTitle({ kicker, title, sub }) {
  return (
    <div className="scene-title">
      <motion.div initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6 }} className="kicker">
        {kicker}
      </motion.div>
      <motion.h2 initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.7, delay: 0.1 }} className="scene-h2">
        {title}
      </motion.h2>
      {sub && <motion.p initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.35, duration: 0.6 }} className="scene-sub">{sub}</motion.p>}
    </div>
  );
}

function S01Opening() {
  const words = ["QWEN3.8-27B", "GPU FLEET"];
  return (
    <div className="scene s01">
      <div className="grid-fx" />
      {words.map((w, i) => (
        <motion.div key={w} className="opening-line"
          initial={{ opacity: 0, scale: 0.94, filter: "blur(12px)" }}
          animate={{ opacity: 1, scale: 1, filter: "blur(0px)" }}
          transition={{ duration: 1.1, delay: 0.5 + i * 0.9, ease: [0.16, 1, 0.3, 1] }}>
          {w}
        </motion.div>
      ))}
      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 2.8, duration: 1 }} className="opening-sub">
        Three GPUs · One signature · 262,144-token context
      </motion.div>
    </div>
  );
}

function S02Topology() {
  return (
    <div className="scene s02">
      <SceneTitle kicker="NETWORK TOPOLOGY" title="Three machines, one network, one model"
        sub="Hosted entirely on Portainer stacks — the YAMLs are the source of truth." />
      <svg viewBox="0 0 900 420" className="topo-svg">
        <defs>
          <path id="p-client" d="M105 210 L 330 210" />
          <path id="p-router-5090" d="M560 210 C 680 120, 700 95, 770 88" />
          <path id="p-router-3090" d="M560 210 L 770 210" />
          <path id="p-router-spark" d="M560 210 C 680 300, 700 325, 770 332" />
        </defs>
        {/* links */}
        <g className="topo-line"><path d="M105 210 L 330 210" /><Packets pathId="p-client" count={3} dur={2.2} active /></g>
        <g className="topo-line"><path d="M560 210 C 680 120, 700 95, 770 88" /><Packets pathId="p-router-5090" count={3} dur={2.2} active /></g>
        <g className="topo-line"><path d="M560 210 L 770 210" /><Packets pathId="p-router-3090" count={3} dur={2.2} active /></g>
        <g className="topo-line"><path d="M560 210 C 680 300, 700 325, 770 332" /><Packets pathId="p-router-spark" count={4} dur={2.2} active /></g>

        {/* client */}
        <motion.g initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3, duration: 0.7 }}>
          <rect x="18" y="158" width="190" height="104" rx="14" className="node-rect" />
          <text x="113" y="196" className="node-title" textAnchor="middle">Claude Code</text>
          <text x="113" y="220" className="node-sub" textAnchor="middle">claude-cluster.bat</text>
          <text x="113" y="240" className="node-sub" textAnchor="middle">ANTHROPIC_BASE_URL → :8010</text>
        </motion.g>

        {/* router */}
        <motion.g initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }} transition={{ delay: 0.7, duration: 0.8, ease: "backOut" }}>
          <circle cx="445" cy="210" r="62" className="router-glow" />
          <circle cx="445" cy="210" r="52" className="router-ring" />
          <text x="445" y="200" className="node-title" textAnchor="middle">GPU Router</text>
          <text x="445" y="222" className="node-sub" textAnchor="middle">FastAPI · :8010</text>
          <text x="445" y="240" className="node-sub" textAnchor="middle">strict priority</text>
        </motion.g>

        {/* backends */}
        {BACKENDS.map((b, i) => {
          const y = i === 0 ? 88 : i === 1 ? 210 : 332;
          return (
            <motion.g key={b.id} initial={{ opacity: 0, x: 24 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 1.1 + i * 0.25, duration: 0.7 }}>
              <rect x="768" y={y - 56} width="118" height="112" rx="12"
                className={`node-rect ${b.id === "5090" ? "gpu5090" : b.id === "3090" ? "gpu3090" : "gpu"}`} />
              <text x="827" y={y - 28} className="node-title" textAnchor="middle">{b.host}</text>
              <text x="827" y={y - 8} className="node-sub" textAnchor="middle">{b.gpu}</text>
              <text x="827" y={y + 12} className="node-sub" textAnchor="middle">{b.engineShort}</text>
              <text x="827" y={y + 34} className="node-cap" textAnchor="middle">cap {b.cap}</text>
            </motion.g>
          );
        })}
      </svg>
    </div>
  );
}

function S03Priority() {
  const steps = [
    { b: BACKENDS[0], note: "vLLM /metrics running+waiting + router in-flight" },
    { b: BACKENDS[1], note: "llama.cpp /slots is_processing" },
    { b: BACKENDS[2], note: "vLLM NVFP4, cap 16" },
  ];
  return (
    <div className="scene s03">
      <SceneTitle kicker="ROUTING LOGIC" title="Dynamic, strict-priority dispatch"
        sub="A backend is usable only when cap − busy − inflight ≥ 1 and healthy. 500 at full capacity, then recovers." />
      <div className="prio-list">
        {steps.map((s, i) => (
          <motion.div key={i} className="prio-row"
            initial={{ opacity: 0, x: -30 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.4 + i * 0.8, duration: 0.7 }}>
            <div className="prio-rank">{["①", "②", "③"][i]}</div>
            <div className="prio-host">{s.b.host} · {s.b.gpu}</div>
            <div className="prio-meta">{s.b.engine} · {s.note}</div>
            <div className="prio-flag">{["FIRST", "SECOND", "SPILL"][i]}</div>
          </motion.div>
        ))}
        <motion.div className="prio-note" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 3, duration: 0.6 }}>
          Sticky sessions pin a conversation to its GPU · vLLM 0.27.1 gauges stay 0 mid-generation, so the router's own in-flight count is authoritative
        </motion.div>
      </div>
    </div>
  );
}

function S04Specs() {
  return (
    <div className="scene s04">
      <SceneTitle kicker="BACKEND SPECS" title="Three engines, one model, one 262K signature"
        sub="Every backend serves the same Qwen3.8-27B abliterated ('Uncensored') weights at max_model_len 262,144." />
      <div className="card-grid">
        {BACKENDS.map((b, i) => (
          <motion.div key={b.id} className={`card ${b.id === "5090" ? "gpu5090" : b.id === "3090" ? "gpu3090" : "gpu"}`}
            initial={{ opacity: 0, y: 24 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3 + i * 0.5, duration: 0.8 }}>
            <div className="card-head">
              <span className="card-host">{b.host}</span>
              <span className="card-ip">{b.ip}</span>
            </div>
            <div className="card-gpu">{b.gpu} · {b.vram}</div>
            <div className="card-engine">{b.engine}</div>
            <div className="card-model">{b.model}</div>
            <div className="card-quant">{b.quant}</div>
            <div className="tile-row">
              {b.stats.map((s) => (
                <StatTile key={s} label="" value={s} />
              ))}
            </div>
          </motion.div>
        ))}
      </div>
    </div>
  );
}

function S05Metrics() {
  const rows = [
    ["TTFT", "0.10 s", "Spark single-stream"],
    ["TTFT", "0.20 s", "3090"],
    ["Aggregate", "165 tok/s", "Spark @ 16-wide"],
    ["Decode", "60 tok/s", "3090 w/ MTP spec decode (1.47×)"],
    ["Single-stream", "19.9 tok/s", "Spark MTP, max_num_seqs=1 (60.6% accept)"],
    ["Prefix cache", "live", "Grafana: vLLM GPU prefix-cache hit rate per backend"],
  ];
  return (
    <div className="scene s05">
      <SceneTitle kicker="THE NUMBERS" title="Speeds, latency, and the MTP win" />
      <div className="metric-grid">
        {rows.map(([k, v, sub], i) => (
          <motion.div key={i} className="metric-row"
            initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3 + i * 0.45, duration: 0.6 }}>
            <div className="metric-key">{k}</div>
            <div className="metric-val">{v}</div>
            <div className="metric-sub">{sub}</div>
          </motion.div>
        ))}
      </div>
      <motion.div className="spark-bar" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 3.2, duration: 0.5 }}>
        Concurrency sweep @262K: 8-wide → 94 · 12-wide → 131 · 16-wide → <span className="green">~165 tok/s</span> (linear scaling)
      </motion.div>
    </div>
  );
}

function S06Portainer() {
  const steps = [
    ["YAML is truth", "Stacks authored in repo, maintained in the Portainer UI — no other deploy path."],
    ["Auth", "POST /auth → JWT for user <portainer user>"],
    ["Deploy", "POST /api/stacks/create/standalone/string?endpointId=N — create + deploy in one call"],
    ["Teardown", "DELETE /api/stacks/&lt;id&gt;?endpointId=N, then re-create by name"],
    ["Hosts", "Databrick ep 3 (3090, router, UI) · DGX Spark ep 4 · RedPCv2 ep 5 (untouched)"],
  ];
  return (
    <div className="scene s06">
      <SceneTitle kicker="DEPLOYMENT" title="Everything ships through Portainer" />
      <div className="portainer-steps">
        {steps.map(([t, d], i) => (
          <motion.div key={i} className="pn-step"
            initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} transition={{ delay: 0.3 + i * 0.55, duration: 0.6 }}>
            <div className="pn-num">{String(i + 1).padStart(2, "0")}</div>
            <div className="pn-text"><div className="pn-title">{t}</div><div className="pn-desc">{d}</div></div>
          </motion.div>
        ))}
      </div>
    </div>
  );
}

function S07Grafana() {
  return (
    <div className="scene s07">
      <SceneTitle kicker="OBSERVABILITY" title="Prometheus + Grafana 13 on the Spark"
        sub="Dashboards with a per-device filter dimension — TTFT, prefix-cache hit rate, GPU telemetry." />
      <div className="grafana-panel">
        {[
          { label: "TTFT (p95)", color: GREEN, pts: "0,80 40,84 80,70 120,76 160,40 200,46 240,28 280,34" },
          { label: "Prefix-cache hit", color: CYAN, pts: "0,110 40,96 80,100 120,70 160,74 200,52 240,58 280,38" },
          { label: "GPU util", color: "#9BE300", pts: "0,140 40,120 80,128 120,110 160,116 200,96 240,100 280,84" },
        ].map((s, i) => (
          <motion.div key={s.label} className="g-series" initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.5 + i * 0.4, duration: 0.6 }}>
            <div className="g-label"><span className="dot" style={{ background: s.color }} />{s.label}</div>
            <svg viewBox="0 0 300 160" className="g-svg">
              <polyline points={s.pts} fill="none" stroke={s.color} strokeWidth="2.5" strokeLinecap="round"
                style={{ strokeDasharray: 320, strokeDashoffset: 320, animation: "dash 2s ease forwards", animationDelay: `${0.6 + i * 0.4}s` }} />
              {s.pts.split(" ").map((p, j) => {
                const [x, y] = p.split(",").map(Number);
                return <circle key={j} cx={x} cy={y} r="2.5" fill={s.color} style={{ opacity: 0, animation: `fadein 0.3s ${1 + i * 0.4 + j * 0.15}s forwards` }} />;
              })}
            </svg>
          </motion.div>
        ))}
      </div>
    </div>
  );
}

function S08Finale() {
  return (
    <div className="scene s08">
      <div className="finale">
        <motion.div className="finale-ring" />
        <motion.h1 initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }} transition={{ duration: 1, ease: [0.16, 1, 0.3, 1] }}>
          One signature. Three GPUs. <span className="green">262K.</span>
        </motion.h1>
        <motion.p initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 1.1, duration: 0.8 }} className="finale-sub">
          Qwen3.8-27B-Uncensored · NVFP4 + GGUF + MTP · vLLM &amp; llama.cpp · Portainer · Grafana
        </motion.p>
        <div className="finale-tiles">
          {[["19", "total capacity", "5090:2 + 3090:1 + Spark:16"], ["262,144", "context tokens", "verified to 254k prompt"], ["3", "engines, one API", "OpenAI + Anthropic at :8010"], ["165", "tok/s aggregate", "Spark @ 16-wide, linear"]].map(([v, l, s], i) => (
            <motion.div key={i} className="ftile" initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 1.6 + i * 0.3, duration: 0.6 }}>
              <div className="ftile-val"><CountUp to={Number(v.replace(/[^\d.]/g, ""))} decimals={0} /></div>
              <div className="ftile-label">{l}</div>
              <div className="ftile-sub">{s}</div>
            </motion.div>
          ))}
        </div>
      </div>
    </div>
  );
}

/* ================= SEQUENCER ================= */
const SCENES = [
  { id: "opening", dur: 8, C: S01Opening },
  { id: "topology", dur: 14, C: S02Topology },
  { id: "priority", dur: 10, C: S03Priority },
  { id: "specs", dur: 14, C: S04Specs },
  { id: "metrics", dur: 12, C: S05Metrics },
  { id: "portainer", dur: 12, C: S06Portainer },
  { id: "grafana", dur: 10, C: S07Grafana },
  { id: "finale", dur: 8, C: S08Finale },
];

export default function App() {
  const [tick, setTick] = useState(0);
  const [playing, setPlaying] = useState(true);
  const reduced = useReducedMotion();
  useEffect(() => {
    if (!playing) return;
    const id = setInterval(() => setTick((t) => (t + 1) % TICKS), TICK_MS);
    return () => clearInterval(id);
  }, [playing]);

  const sceneIndex = useMemo(() => {
    let acc = 0;
    for (let i = 0; i < SCENES.length; i++) {
      acc += SCENES[i].dur;
      if (tick < acc * 60) return i;
    }
    return SCENES.length - 1;
  }, [tick]);

  const scene = SCENES[sceneIndex];
  const totalSec = SCENES.reduce((a, s) => a + s.dur, 0);
  const elapsed = Math.floor((tick / 60) % totalSec);

  return (
    <div className="stage">
      <div className="bg-glow" />
      <AnimatePresence mode="wait">
        <motion.div key={scene.id} className="scene-wrap"
          initial={{ opacity: 0, filter: "blur(8px)" }}
          animate={{ opacity: 1, filter: "blur(0px)" }}
          exit={{ opacity: 0, filter: "blur(8px)" }}
          transition={{ duration: reduced ? 0.15 : 0.55, ease: [0.22, 1, 0.36, 1] }}>
          <scene.C />
        </motion.div>
      </AnimatePresence>

      {/* HUD */}
      <div className="hud">
        <div className="hud-brand">QWEN3.8 FLEET</div>
        <div className="hud-progress">
          <div className="hud-progress-fill" style={{ width: `${(elapsed / totalSec) * 100}%` }} />
        </div>
        <div className="hud-right">
          <span className="hud-scene">{scene.id}</span>
          <button className="hud-btn" onClick={() => setPlaying((p) => !p)}>{playing ? "❚❚" : "▶"}</button>
          <button className="hud-btn" onClick={() => setTick(0)}>⟲</button>
          <span className="hud-time">{String(Math.floor(elapsed / 60)).padStart(2, "0")}:{String(elapsed % 60).padStart(2, "0")} / 03:00</span>
        </div>
      </div>
    </div>
  );
}
