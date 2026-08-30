// 1:35–2:20 — MIXTURE OF EXPERTS
// Push through the shell of a giant model. Inside: expert blocks in a dark
// architectural volume. Data comes in, the router branches, selected experts
// light green, the rest stay dark. Pull back to the giant whole.
import { motion } from "framer-motion";
import { SceneShell, Statement, FlowLine, EASE } from "../prims.jsx";
import { after, clamp01 } from "../clock.js";
import { SCENES } from "../timeline.js";

const SCENE = SCENES[2];

// 5x4 expert grid, 48 experts; 16 active at a time
const GRID = 20; // total experts (visual subset of a real MoE)
const ACTIVE = 7;

export default function MixtureOfExperts({ t }) {
  const lt = t - SCENE.from;
  const inside = after(lt, 2, 1.2);        // pushed through the shell
  const data = after(lt, 5.5, 0.8);         // data arrives at the router
  const route = after(lt, 7.5, 0.8);        // router branches
  const activate = after(lt, 9.5, 1.0);     // selected experts light
  const pullback = after(lt, 15, 1.4);      // pull back to the giant whole
  const stop = after(lt, 25, 1.0);          // "stop scaling together"

  // deterministic active set (rotation so it feels alive but calm)
  const activeSet = new Set(
    Array.from({ length: GRID }).map((_, i) => (i * 3) % GRID)
  ).size >= 0 ? Array.from({ length: GRID }, (_, i) => (i * 3) % GRID).filter((v, i, a) => a.indexOf(v) === i && i < ACTIVE) : [];

  const experts = Array.from({ length: GRID }, (_, i) => i);

  return (
    <SceneShell>
      {/* the giant shell we're inside */}
      <div style={{
        position: "absolute", inset: "-8% -4%",
        border: "1px solid rgba(255,255,255,0.14)",
        borderRadius: 26,
        boxShadow: "inset 0 0 120px rgba(0,0,0,0.6)",
        opacity: 0.35 + pullback * 0.3,
      }} />

      <div style={{ display: "flex", alignItems: "center", gap: 60, opacity: inside }}>
        {/* data in → router */}
        <div style={{ position: "relative", width: 190, height: 340 }}>
          <FlowLine x1={8} y1={50} x2={82} y2={50} active={data > 0.5} speed={2} />
          <div style={{ position: "absolute", left: 14, top: 38, fontFamily: "var(--mono)", fontSize: 11, letterSpacing: "0.16em", color: "var(--ink-dim)" }}>DATA IN</div>
          {/* router node */}
          <motion.div
            initial={{ opacity: 0, scale: 0.7 }} animate={{ opacity: route, scale: 1 }} transition={{ duration: 0.7, ease: EASE }}
            style={{
              position: "absolute", left: 74, top: 44, width: 42, height: 42,
              borderRadius: "50%",
              border: "1px solid rgba(118,185,0,0.7)",
              background: "rgba(118,185,0,0.12)",
              boxShadow: "0 0 30px rgba(118,185,0,0.4)",
              display: "grid", placeItems: "center",
              fontFamily: "var(--mono)", fontSize: 9.5, letterSpacing: "0.1em", color: "var(--green-bright)",
            }}
          >
            ROUTE
          </motion.div>
          {/* branch lines to the expert volume */}
          {experts.slice(0, 5).map((i, k) => (
            <FlowLine key={k} x1={88} y1={50} x2={100} y2={12 + k * 19} active={route > 0.6} speed={1.6} />
          ))}
        </div>

        {/* the expert volume */}
        <motion.div
          initial={{ opacity: 0 }} animate={{ opacity: inside }} transition={{ duration: 1 }}
          style={{
            display: "grid",
            gridTemplateColumns: `repeat(5, 1fr)`,
            gap: 10,
            padding: 26,
            border: "1px solid rgba(255,255,255,0.12)",
            borderRadius: 14,
            background: "rgba(255,255,255,0.02)",
            boxShadow: "0 30px 80px rgba(0,0,0,0.5)",
          }}
        >
          {experts.map((i) => {
            const on = activeSet.includes(i) && activate > 0.5;
            return (
              <motion.div
                key={i}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: (i % GRID) * 0.02 }}
                style={{
                  width: 64, height: 52,
                  borderRadius: 6,
                  border: on ? "1px solid rgba(118,185,0,0.7)" : "1px solid rgba(255,255,255,0.1)",
                  background: on ? "rgba(118,185,0,0.4)" : "rgba(255,255,255,0.04)",
                  boxShadow: on ? "0 0 22px rgba(118,185,0,0.45)" : "none",
                  transition: "background 0.6s, box-shadow 0.6s, border 0.6s",
                }}
              />
            );
          })}
        </motion.div>
      </div>

      <div style={{ position: "absolute", bottom: 200, textAlign: "center" }}>
        <Statement text="Enormous in memory. Only part active." op={pullback} size="clamp(22px, 2.3vw, 36px)" />
        <Statement text="Compute and memory stop scaling together." op={stop * 0.9} size="clamp(18px, 1.9vw, 28px)" green={stop > 0.8} delay={stop > 0.4 ? 0.2 : 0} />
      </div>

      {/* active count readout */}
      <div style={{ position: "absolute", top: 90, right: 60, fontFamily: "var(--mono)", fontSize: 13, letterSpacing: "0.18em", color: "var(--green-bright)", opacity: activate }}>
        {ACTIVE} / {GRID} EXPERTS ACTIVE
      </div>
    </SceneShell>
  );
}
