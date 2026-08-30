// 0:00–0:30 — THE HOOK
// Darkness → three points of green light → three machines → the question
// fragments into "WHAT DO YOU WANT TO RUN?" → the model landscape materializes
// behind them → travel through the machines and turn: hardware on one side,
// models on the other. Arrow reverses → "WHAT CAN YOU ACTUALLY RUN?"
import { motion } from "framer-motion";
import { SceneShell, Statement, Fragment, ModelBlock, EASE } from "../prims.jsx";
import { cueProgresses, cueFade, after, clamp01 } from "../clock.js";
import { SCENES, sceneIndexAt } from "../timeline.js";

const SCENE = SCENES[0];

export default function Hook({ t }) {
  const lt = t - SCENE.from;
  const cues = SCENE.cues;
  const p = cueProgresses(lt, cues);

  // beats
  const points = after(lt, 1.5, 1.2);       // three green points in darkness
  const machines = after(lt, 6.0, 1.4);      // resolve into hardware
  const dimOthers = after(lt, 12.5, 0.9);    // everything dims except machines
  const q1 = after(lt, 13.5, 0.7);           // WHICH GPU?
  const frag1 = clamp01((lt - 16.5) / 1.2);  // fragment
  const q2 = after(lt, 18, 0.7);             // WHAT DO YOU WANT TO RUN?
  const landscape = after(lt, 21.5, 1.4);    // model landscape behind
  const reversed = after(lt, 24.5, 1.0);     // world reverses; envelope question

  // three machine marks (abstract, minimal)
  const marks = [
    { name: "RTX 3090", x: -26, s: 0.8 },
    { name: "RTX 5090", x: 0, s: 1 },
    { name: "DGX SPARK", x: 26, s: 1.15 },
  ];

  return (
    <SceneShell>
      {/* far model landscape — hundreds of tiny blocks deep behind */}
      <div style={{ position: "absolute", inset: 0, opacity: landscape * 0.9 }}>
        {Array.from({ length: 120 }).map((_, i) => {
          const x = (i * 37) % 100;
          const y = 8 + ((i * 53) % 84);
          const big = i % 9 === 0;
          return (
            <motion.div
              key={i}
              initial={{ opacity: 0, scale: 0.4 }}
              animate={{ opacity: 0.14 + (i % 7) * 0.03, scale: 1 }}
              transition={{ delay: (i % 12) * 0.05, duration: 0.6 }}
              style={{
                position: "absolute", left: `${x}%`, top: `${y}%`,
                width: big ? 9 : 4, height: big ? 9 : 4,
                background: i % 17 === 0 ? "rgba(118,185,0,0.5)" : "rgba(255,255,255,0.35)",
                borderRadius: 1,
              }}
            />
          );
        })}
        {/* landscape labels — the categories that materialize */}
        {["MoE", "Long-context", "Agents", "Vision", "Coding", "Dense"].map((l, i) => (
          <motion.div
            key={l}
            initial={{ opacity: 0 }}
            animate={{ opacity: landscape }}
            transition={{ delay: 0.3 + i * 0.12 }}
            style={{
              position: "absolute", left: `${12 + i * 15}%`, top: `${74 + (i % 3) * 8}%`,
              fontFamily: "var(--mono)", fontSize: 11, letterSpacing: "0.2em", color: "var(--ink-faint)",
            }}
          >
            {l}
          </motion.div>
        ))}
      </div>

      {/* the three machines (reverse side swaps their role) */}
      <div style={{ position: "absolute", left: 0, right: 0, top: "38%", transform: "translateY(-50%)", display: "flex", justifyContent: "center", gap: 54, opacity: 1 - (reversed * 0.25) }}>
        {marks.map((m, i) => (
          <div key={m.name} style={{ textAlign: "center", width: 150 }}>
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: points * (1 - machines * 0.55) }}
              style={{
                width: 14 * m.s, height: 14 * m.s, margin: "0 auto",
                borderRadius: "50%",
                background: "rgba(118,185,0,0.9)",
                boxShadow: "0 0 30px rgba(118,185,0,0.8), 0 0 90px rgba(118,185,0,0.4)",
              }}
            />
            <motion.div
              animate={{ opacity: machines, y: machines ? 0 : 12 }}
              transition={{ duration: 0.8, ease: EASE }}
              style={{
                marginTop: 26,
                width: 92 * m.s, height: 64 * m.s, margin: "26px auto 0",
                border: "1px solid rgba(255,255,255,0.28)",
                borderRadius: 8,
                background: "linear-gradient(160deg, rgba(255,255,255,0.1), rgba(255,255,255,0.02))",
                position: "relative",
              }}
            >
              <div style={{ position: "absolute", left: "50%", top: "50%", transform: "translate(-50%,-50%)", width: 22 * m.s, height: 22 * m.s, borderRadius: 3, background: "rgba(255,255,255,0.16)" }} />
            </motion.div>
            <motion.div animate={{ opacity: machines }} style={{ fontFamily: "var(--mono)", fontSize: 12.5, letterSpacing: "0.18em", color: "var(--ink-dim)", marginTop: 12 }}>
              {m.name}
            </motion.div>
          </div>
        ))}
      </div>

      {/* the question sequence */}
      <div style={{ position: "absolute", left: 0, right: 0, top: "68%", textAlign: "center" }}>
        <div style={{ position: "relative", height: 90 }}>
          <div style={{ position: "absolute", inset: 0, opacity: q1 * (1 - frag1) }}>
            <Fragment text="WHICH GPU?" progress={frag1} />
          </div>
          <div style={{ position: "absolute", inset: 0, opacity: q2 * (1 - reversed * 0.6) }}>
            <Statement text="WHAT DO YOU" mark={[null, "WANT TO RUN?", null]} op={q2} />
          </div>
          <div style={{ position: "absolute", inset: 0, opacity: reversed }}>
            <Statement text="WHAT CAN YOU" mark={[null, "ACTUALLY RUN?", null]} op={reversed} size="clamp(28px, 3vw, 46px)" />
          </div>
        </div>
      </div>

      {/* reversed envelope hint: machines project onto the landscape */}
      <div style={{ position: "absolute", left: 0, right: 0, bottom: 200, opacity: reversed * 0.8, display: "flex", justifyContent: "center", gap: 54 }}>
        {["3090", "5090", "SPARK"].map((n, i) => (
          <div key={n} style={{ textAlign: "center" }}>
            <div style={{ width: 0, height: 0, margin: "0 auto", borderLeft: "30px solid transparent", borderRight: "30px solid transparent", borderBottom: `54px solid ${i === 1 ? "rgba(118,185,0,0.16)" : "rgba(255,255,255,0.06)"}` }} />
            <div style={{ fontFamily: "var(--mono)", fontSize: 10.5, letterSpacing: "0.2em", color: "var(--ink-faint)", marginTop: 6 }}>{n}</div>
          </div>
        ))}
      </div>
    </SceneShell>
  );
}
