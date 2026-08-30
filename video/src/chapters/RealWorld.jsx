// 7:30–8:30 — REAL WORLD USE
// Leave abstraction: a Claude Code window as a floating plane in the dark
// environment. Model server, GPU, repo/context, tool calls. The full loop:
// prompt in, context flows, GPU processes, response returns, tool call
// leaves, files return, more inference. Then the three abstract parallel
// questions: wait time (TTFT), context, model envelope, concurrency.
import { motion } from "framer-motion";
import { SceneShell, Statement, EASE } from "../prims.jsx";
import { after, clamp01 } from "../clock.js";
import { SCENES } from "../timeline.js";

const SCENE = SCENES[10];

export default function RealWorld({ t }) {
  const lt = t - SCENE.from;
  const plane = after(lt, 1.5, 1.2);
  const loop = clamp01((lt - 5) / 8);       // the agentic loop animating
  const doWork = after(lt, 16, 0.9);        // "I buy it to do work"
  const q = clamp01((lt - 20) / 26);        // the four questions 20..46s
  const active = [
    { at: 20, label: "HOW LONG DO I WAIT?", sub: "TTFT · time to first token" },
    { at: 27, label: "CAN I KEEP THE CONTEXT I NEED?", sub: "CONTEXT WINDOW" },
    { at: 33, label: "CAN I RUN THE MODEL I WANT?", sub: "MODEL ENVELOPE" },
    { at: 39, label: "WHEN ANOTHER AGENT SHOWS UP?", sub: "CONCURRENCY" },
  ];
  const activeIdx = active.reduce((acc, a, i) => (lt >= a.at ? i : acc), -1);
  const showAll = lt >= 46;

  // loop steps
  const LOOP = ["prompt", "context", "GPU", "response", "tool", "files", "inference"];

  return (
    <SceneShell>
      <div style={{ display: "flex", alignItems: "center", gap: 70, opacity: plane }}>
        {/* the floating Claude Code plane */}
        <motion.div
          initial={{ opacity: 0, y: 24 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 1, ease: EASE }}
          style={{
            width: 380, borderRadius: 12,
            border: "1px solid rgba(255,255,255,0.2)",
            background: "rgba(12,15,24,0.92)",
            boxShadow: "0 40px 100px rgba(0,0,0,0.6)",
            fontFamily: "var(--mono)",
            overflow: "hidden",
            transform: "perspective(1200px) rotateX(4deg)",
          }}
        >
          <div style={{ padding: "10px 14px", borderBottom: "1px solid rgba(255,255,255,0.1)", display: "flex", gap: 6, alignItems: "center" }}>
            {["#ff5f57", "#febc2e", "#28c840"].map((c) => (
              <div key={c} style={{ width: 9, height: 9, borderRadius: "50%", background: c, opacity: 0.7 }} />
            ))}
            <span style={{ marginLeft: 10, fontSize: 11.5, color: "var(--ink-faint)" }}>claude code</span>
          </div>
          <div style={{ padding: "14px 16px", fontSize: 12.5, lineHeight: 2, color: "var(--ink-dim)" }}>
            <div><span style={{ color: "var(--green-bright)" }}>›</span> fix the KV cache eviction bug</div>
            <div style={{ opacity: 0.55 }}>reading src/kv.rs …</div>
            <div style={{ opacity: loop > 0.3 ? 1 : 0.25 }}>editing src/kv.rs ✓</div>
            <div style={{ opacity: loop > 0.55 ? 1 : 0.25 }}>tool: cargo test …</div>
            <div style={{ opacity: loop > 0.8 ? 1 : 0.2, color: "var(--green-bright)" }}>3 passed · done</div>
          </div>
        </motion.div>

        <div style={{ display: "flex", flexDirection: "column", gap: 40 }}>
          {/* the loop, animated sequentially */}
          <div>
            <div style={{ fontFamily: "var(--mono)", fontSize: 11, letterSpacing: "0.22em", color: "var(--ink-faint)", marginBottom: 12 }}>THE LOOP</div>
            <div style={{ display: "flex", gap: 4, alignItems: "center", flexWrap: "wrap", maxWidth: 420 }}>
              {LOOP.map((s, i) => {
                const on = loop > (i + 1) / LOOP.length;
                return (
                  <div key={s} style={{ display: "flex", alignItems: "center", gap: 4 }}>
                    <div style={{
                      padding: "7px 11px", borderRadius: 6,
                      border: `1px solid ${on ? "rgba(118,185,0,0.6)" : "rgba(255,255,255,0.14)"}`,
                      background: on ? "rgba(118,185,0,0.12)" : "rgba(255,255,255,0.03)",
                      fontFamily: "var(--mono)", fontSize: 11.5, letterSpacing: "0.12em",
                      color: on ? "var(--green-bright)" : "var(--ink-faint)",
                      transition: "all 0.4s",
                    }}>
                      {s}
                    </div>
                    {i < LOOP.length - 1 && <div style={{ width: 12, height: 1.5, background: on ? "var(--green)" : "rgba(255,255,255,0.12)", opacity: 0.7 }} />}
                  </div>
                );
              })}
            </div>
          </div>

          <div style={{ opacity: doWork }}>
            <Statement text="I buy it to do work." op={doWork} size="clamp(20px, 2.2vw, 32px)" />
          </div>

          {/* the four practical questions */}
          <div style={{ display: "flex", flexDirection: "column", gap: 10, width: 380 }}>
            {active.map((a, i) => {
              const on = showAll || activeIdx === i;
              const past = !showAll && activeIdx > i;
              return (
                <div
                  key={a.label}
                  style={{
                    padding: "10px 14px", borderRadius: 8,
                    border: on ? "1px solid rgba(118,185,0,0.55)" : "1px solid rgba(255,255,255,0.12)",
                    background: on ? "rgba(118,185,0,0.07)" : "rgba(255,255,255,0.03)",
                    opacity: on ? 1 : past ? 0.5 : 0.25,
                    transition: "all 0.5s",
                  }}
                >
                  <div style={{ fontFamily: "var(--mono)", fontSize: 13, letterSpacing: "0.1em", color: on ? "var(--ink)" : "var(--ink-dim)" }}>{a.label}</div>
                  <div style={{ fontFamily: "var(--mono)", fontSize: 10.5, letterSpacing: "0.18em", color: on ? "var(--green-bright)" : "var(--ink-faint)", marginTop: 3 }}>{a.sub}</div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </SceneShell>
  );
}
