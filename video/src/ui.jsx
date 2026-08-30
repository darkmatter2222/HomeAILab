import { useRef, useEffect, useState } from "react";
import { motion, animate } from "framer-motion";

export function Card({ title, dim, children, delay = 0, className = "" }) {
  return (
    <motion.div
      className={`card ${className}`}
      initial={{ opacity: 0, y: 26, scale: 0.96, filter: "blur(6px)" }}
      animate={{ opacity: 1, y: 0, scale: 1, filter: "blur(0px)" }}
      transition={{ delay, duration: 0.8, ease: [0.22, 1, 0.36, 1] }}
      style={{ willChange: "transform, opacity" }}
    >
      {title && (
        <div className="hd">
          <span>{title}</span>
          {dim && <span className="dim">{dim}</span>}
        </div>
      )}
      <div className="bd">{children}</div>
    </motion.div>
  );
}

export function KV({ rows }) {
  return (
    <div className="kv">
      {rows.map((r, i) =>
        i % 2 === 0 ? (
          <span key={r[0]} className="k">{r[1]}</span>
        ) : (
          <span key={r[0]} className={`v ${r[2] || ""}`}>{r[1]}</span>
        )
      )}
    </div>
  );
}

export function Stat({ value, unit, label, delay = 0.2, suffix = "" }) {
  const [display, setDisplay] = useState("0");
  useEffect(() => {
    const controls = animate(0, value, {
      duration: 1.6,
      ease: [0.22, 1, 0.36, 1],
      delay,
      onUpdate: (v) => setDisplay(fmtNum(v)),
    });
    return () => controls.stop();
  }, [value]);
  return (
    <div className="big-stat">
      <div className="num">{display}{suffix}</div>
      <div className="unit">{unit}</div>
      {label && (
        <div style={{ marginTop: 10, color: "var(--ink-dim)", fontFamily: "var(--mono)", fontSize: 12.5, letterSpacing: "0.1em" }}>
          {label}
        </div>
      )}
    </div>
  );
}

function fmtNum(v) {
  if (v >= 100) return Math.round(v).toString();
  return v.toFixed(1);
}

export function SceneShell({ children, className = "" }) {
  // full-bleed: consume the whole window edge-to-edge (the camera world pans
  // this; the teleprompter owns the bottom strip).
  return (
    <div className={className} style={{ width: "100%", height: "100%", display: "flex", flexDirection: "column", position: "relative" }}>
      {children}
    </div>
  );
}

// NVIDIA house pattern: line-mask reveal (parent clips, inner slides up) +
// a thin green hairline sweep under the title (their signature accent).
// scene number is injected by the App (which knows the index), so the kicker
// reads "SCENE 03 · FLEET TOPOLOGY" instead of a hard-coded scene number.
export function SceneTitle({ num, kicker, title, delay = 0 }) {
  const full = `${String(num).padStart(2, "0")} · ${kicker}`;
  return (
    <div style={{ marginBottom: 26 }}>
      <motion.div
        initial={{ opacity: 0, x: -14 }}
        animate={{ opacity: 1, x: 0 }}
        transition={{ delay, duration: 0.6, ease: [0.33, 1, 0.68, 1] }}
        style={{ fontFamily: "var(--mono)", fontSize: 12, letterSpacing: "0.32em", color: "var(--green)", marginBottom: 10 }}
      >
        {full}
      </motion.div>
      {/* line-mask reveal for the headline */}
      <div style={{ overflow: "hidden" }}>
        <motion.h1
          initial={{ y: "105%" }}
          animate={{ y: "0%" }}
          transition={{ delay: delay + 0.12, duration: 0.9, ease: [0.16, 1, 0.3, 1] }}
          style={{ fontSize: "clamp(28px, 2.1vw, 38px)", fontWeight: 800, letterSpacing: "-0.01em", lineHeight: 1.1, willChange: "transform" }}
        >
          {title}
        </motion.h1>
      </div>
      {/* NVIDIA signature hairline sweep */}
      <motion.div
        initial={{ scaleX: 0, opacity: 0 }}
        animate={{ scaleX: 1, opacity: 1 }}
        transition={{ delay: delay + 0.55, duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
        style={{
          height: 2, width: 220, marginTop: 10, transformOrigin: "left center",
          background: "linear-gradient(90deg, var(--green), var(--green-bright) 40%, transparent)",
          boxShadow: "0 0 14px var(--green-glow)",
        }}
      />
    </div>
  );
}

// ── The fleet architecture diagram ──────────────────────────────────────
// Client → router → three GPUs (+ the monitoring plane). Shared geometry so
// the same world can be opened on (BOOT), navigated to (TOPOLOGY), and
// zoomed into/out of by the camera. `compact` drops the labels/footnotes for
// the small embed; `animate` false is used by the static opening diagram.
const DIAG = {
  W: 1180, H: 560,
  P: {
    client: { x: 96, y: 180 },
    router: { x: 380, y: 250 },
    databrick: { x: 760, y: 120 },
    redpc: { x: 1050, y: 120 },
    spark: { x: 760, y: 400 },
    prom: { x: 1050, y: 400 },
  },
};

export function ArchitectureDiagram({ compact = false, animate = true }) {
  const P = DIAG.P;
  const link = (a, b) => `M ${a.x} ${a.y} L ${b.x} ${b.y}`;
  const t = (d, extra = 0) => (animate ? { delay: d + extra, duration: 0.7, ease: [0.22, 1, 0.36, 1] } : {});

  return (
    <div style={{ position: "relative", width: "100%", aspectRatio: `${DIAG.W}/${DIAG.H}` }}>
      <svg viewBox={`0 0 ${DIAG.W} ${DIAG.H}`} style={{ position: "absolute", inset: 0, width: "100%", height: "100%" }} preserveAspectRatio="xMidYMid meet">
        {[[P.client, P.router], [P.router, P.databrick], [P.router, P.spark], [P.router, P.redpc], [P.redpc, P.prom], [P.spark, P.prom]].map(([a, b], i) => (
          <motion.line
            key={i} x1={a.x} y1={a.y} x2={b.x} y2={b.y}
            stroke="rgba(118,185,0,0.26)" strokeWidth="1.5"
            {...(animate
              ? { initial: { pathLength: 0, opacity: 0 }, animate: { pathLength: 1, opacity: 1 }, transition: { delay: 0.9 + i * 0.28, duration: 0.8 } }
              : { initial: { pathLength: 1, opacity: 1 } })}
          />
        ))}
      </svg>

      {/* client */}
      <motion.div
        initial={animate ? { opacity: 0, x: -16 } : {}} animate={{ opacity: 1, x: 0 }} transition={t(0.3)}
        className="card"
        style={{ position: "absolute", left: P.client.x - 120, top: P.client.y - 44, width: 240, borderRadius: 12 }}
      >
        <div style={{ padding: "14px 16px", fontFamily: "var(--mono)" }}>
          <div style={{ fontSize: 16, fontWeight: 700 }}>Claude Code</div>
          <div style={{ fontSize: 11.5, color: "var(--ink-faint)", marginTop: 4, lineHeight: 1.7 }}>
            claude-cluster.bat<br />base url :8010 · key qwen38…
          </div>
        </div>
      </motion.div>

      {/* router — the door */}
      <motion.div
        initial={animate ? { opacity: 0, scale: 0.9 } : {}} animate={{ opacity: 1, scale: 1 }} transition={t(0.55)}
        className="card"
        style={{ position: "absolute", left: P.router.x - 150, top: P.router.y - 74, width: 300, borderRadius: 12, border: "1px solid rgba(118,185,0,0.5)" }}
      >
        <div style={{ padding: 16, fontFamily: "var(--mono)" }}>
          <div style={{ fontSize: 12, color: "var(--green)", letterSpacing: "0.2em" }}>INGRESS · qwen38-gpu-router</div>
          <div style={{ fontSize: 15, fontWeight: 600, margin: "8px 0 6px", color: "var(--ink)" }}>
            FastAPI · port <b style={{ color: "var(--green-bright)" }}>8010</b>
          </div>
          <div style={{ fontSize: 11.5, color: "var(--ink-dim)", lineHeight: 1.8 }}>
            OpenAI + Anthropic · 262K<br />strict priority · sticky sessions<br />UI dashboard <b style={{ color: "var(--green-bright)" }}>qwen38-router-ui :8090</b>
          </div>
        </div>
      </motion.div>

      {[
        { p: P.databrick, name: "Databrick", ip: "192.168.86.48 · Portainer ep 3", sub: "Portainer server · router + UI live here", gpu: "RTX 3090 · 24 GB", note: "llama.cpp :8006 (cap 1) · Q4_K_M · 32K · MTP", d: 1.2 },
        { p: P.spark, name: "DGX Spark", ip: "192.168.86.39 · GB10 · Portainer ep 4", sub: "aarch64 Blackwell · 122 GiB unified · also runs Grafana+Prometheus", gpu: "NVIDIA GB10 · FP4 tensor cores", note: "vLLM NVFP4 :8006 (cap 16) · MTP on · TTFT ~0.10 s", d: 1.5 },
        { p: P.redpc, name: "RedPCv2", ip: "192.168.86.37 · RTX 5090 · Portainer ep 5", sub: "Windows + WSL2 Docker · untouched by router internals", gpu: "RTX 5090", note: "vLLM v0.27.1 :8006 (cap 2) · NVFP4 · spec OFF", d: 1.8 },
      ].map((h) => (
        <motion.div
          key={h.name}
          initial={animate ? { opacity: 0, scale: 0.94 } : {}} animate={{ opacity: 1, scale: 1 }}
          transition={t(h.d)}
          className="card"
          style={{ position: "absolute", left: h.p.x - 140, top: h.p.y - 62, width: 280, borderRadius: 12 }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", padding: "12px 16px", borderBottom: "1px solid var(--panel-line)", fontFamily: "var(--mono)" }}>
            <div>
              <div style={{ fontSize: 16.5, fontWeight: 700, color: "var(--ink)" }}>{h.name}</div>
              <div style={{ fontSize: 11, color: "var(--ink-faint)", letterSpacing: "0.06em", marginTop: 2 }}>{h.ip}</div>
            </div>
            <span className="pulse" style={{ width: 12, height: 12, borderRadius: "50%", background: "var(--green)", alignSelf: "center", boxShadow: "0 0 12px var(--green-glow)" }} />
          </div>
          <div style={{ padding: "12px 16px", fontFamily: "var(--mono)", fontSize: 12, lineHeight: 1.85, color: "var(--ink-dim)" }}>
            {h.sub}
            <div style={{ color: "var(--green-bright)", fontWeight: 600, marginTop: 4 }}>{h.gpu}</div>
            <div style={{ color: "var(--ink-faint)", fontSize: 11 }}>{h.note}</div>
          </div>
        </motion.div>
      ))}

      {!compact && (
        <motion.div
          initial={animate ? { opacity: 0, scale: 0.94 } : {}} animate={{ opacity: 1, scale: 1 }} transition={t(2.1)}
          className="card"
          style={{ position: "absolute", left: P.prom.x - 140, top: P.prom.y - 62, width: 280, borderRadius: 12 }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", padding: "12px 16px", borderBottom: "1px solid var(--panel-line)", fontFamily: "var(--mono)" }}>
            <div>
              <div style={{ fontSize: 16.5, fontWeight: 700, color: "var(--ink)" }}>Monitoring plane</div>
              <div style={{ fontSize: 11, color: "var(--ink-faint)", letterSpacing: "0.06em", marginTop: 2 }}>Grafana :3000 · Prometheus :9090</div>
            </div>
          </div>
          <div style={{ padding: "12px 16px", fontFamily: "var(--mono)", fontSize: 12, lineHeight: 1.85, color: "var(--ink-dim)" }}>
            scrapes all 3 engines + router · 5 s interval
            <div style={{ color: "var(--green-bright)", fontWeight: 600, marginTop: 4 }}>vllm:* · DCGM · node · qwen38-router</div>
            <div style={{ color: "var(--ink-faint)", fontSize: 11 }}>fleet dashboard adrsc9f · proxied at :48/grafana</div>
          </div>
        </motion.div>
      )}

      {/* live token streams */}
      <svg viewBox={`0 0 ${DIAG.W} ${DIAG.H}`} style={{ position: "absolute", inset: 0, width: "100%", height: "100%", pointerEvents: "none" }} preserveAspectRatio="xMidYMid meet">
        {animate && (
          <>
            <TokenStream d={link(P.client, P.router)} duration={2} delay={2.6} />
            <TokenStream d={link(P.router, P.redpc)} duration={1.8} delay={2.8} />
            <TokenStream d={link(P.router, P.spark)} duration={1.9} delay={3.0} />
            <TokenStream d={link(P.router, P.databrick)} duration={1.8} delay={3.2} />
            <TokenStream d={link(P.redpc, P.prom)} duration={3} delay={3.6} color="var(--cyan)" />
            <TokenStream d={link(P.spark, P.prom)} duration={2.6} delay={3.8} color="var(--cyan)" />
          </>
        )}
      </svg>
    </div>
  );
}

// ── Token stream: glowing dashes travelling an SVG path (SMIL) ──────
export function TokenStream({ d, duration, delay = 0, color = "var(--green)", count = 3 }) {
  // Packets fade in at the path start and out at the end (opacity 0→1→1→0
  // over the first/last 10%) so tokens don't pop on/off — the "no-pop" fix.
  return (
    <>
      <path d={d} stroke="rgba(118,185,0,0.14)" strokeWidth="1.5" fill="none" />
      {Array.from({ length: count }).map((_, i) => (
        <g key={i}>
          <circle r="3.2" fill={color} style={{ filter: "drop-shadow(0 0 6px rgba(118,185,0,0.9))" }}>
            <animateMotion
              dur={`${duration}s`}
              begin={`${delay + (duration * i) / count}s`}
              repeatCount="indefinite"
              keyPoints="0;1"
              keyTimes="0;1"
              calcMode="linear"
              path={d}
            />
            <animate
              attributeName="opacity"
              values="0;1;1;0"
              keyTimes="0;0.1;0.9;1"
              dur={`${duration}s`}
              begin={`${delay + (duration * i) / count}s`}
              repeatCount="indefinite"
            />
          </circle>
        </g>
      ))}
    </>
  );
}

export function Bar({ pct, delay = 0.3, label, value, height = 10 }) {
  return (
    <div style={{ marginBottom: 14 }}>
      {label && (
        <div style={{ display: "flex", justifyContent: "space-between", fontFamily: "var(--mono)", fontSize: 12, color: "var(--ink-dim)", marginBottom: 6 }}>
          <span>{label}</span>
          {value && <span style={{ color: "var(--green-bright)" }}>{value}</span>}
        </div>
      )}
      <div style={{ height, background: "rgba(255,255,255,0.06)", borderRadius: 5, overflow: "hidden" }}>
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${pct}%` }}
          transition={{ delay, duration: 1.1, ease: [0.22, 1, 0.36, 1] }}
          style={{
            height: "100%",
            borderRadius: 5,
            background: "linear-gradient(90deg, var(--green-dim), var(--green))",
            boxShadow: "0 0 16px rgba(118,185,0,0.5)",
          }}
        />
      </div>
    </div>
  );
}

export function SectionNote({ children, delay = 0 }) {
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ delay, duration: 0.8 }}
      style={{ fontFamily: "var(--mono)", fontSize: 12.5, color: "var(--ink-faint)", letterSpacing: "0.04em", lineHeight: 1.7 }}
    >
      {children}
    </motion.div>
  );
}
