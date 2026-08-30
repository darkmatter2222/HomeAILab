// 8:30–9:10 — THE SYNTHESIS
// Pull farther back: models, contexts, agents, hardware in one spatial
// system. THE STATEMENT: THERE IS NO BEST GPU. → THERE IS A BEST FIT.
// Then the three paths light in turn. THE MODEL DECIDES. START WITH THE
// MODEL.
import { motion } from "framer-motion";
import { SceneShell, Statement, EASE } from "../prims.jsx";
import { after, clamp01 } from "../clock.js";
import { SCENES } from "../timeline.js";

const SCENE = SCENES[11];

const PATHS = [
  { at: 20, label: "COMPUTE DOMINATES", gpu: "RTX 5090", note: "models fit on consumer hardware" },
  { at: 25, label: "CAPABILITY PER DOLLAR", gpu: "RTX 3090", note: "older hardware, extraordinary sense" },
  { at: 30, label: "CAPACITY DECIDES", gpu: "DGX SPARK", note: "workloads demand more memory" },
];

export default function Synthesis({ t }) {
  const lt = t - SCENE.from;
  const whole = after(lt, 1.5, 1.4);      // the whole system visible
  const noBest = after(lt, 9, 0.8);        // THERE IS NO BEST GPU
  const bestFit = after(lt, 14.5, 0.8);    // THERE IS A BEST FIT
  const decide = after(lt, 36, 1.0);       // THE MODEL DECIDES

  // which path is lit (by narration), none after the final statement
  const litIdx = PATHS.reduce((acc, p, i) => (lt >= p.at ? i : acc), -1);

  return (
    <SceneShell>
      {/* the spatial system: four strata */}
      <div style={{ position: "absolute", inset: 0, opacity: whole * 0.5 }}>
        {["MODELS", "CONTEXTS", "AGENTS", "HARDWARE"].map((s, i) => (
          <div key={s} style={{
            position: "absolute", left: "50%", top: `${18 + i * 18}%`,
            transform: "translate(-50%,-50%)",
            width: "64vw", height: 6,
            background: i === 3 ? "linear-gradient(90deg, transparent, rgba(118,185,0,0.35), transparent)" : "linear-gradient(90deg, transparent, rgba(255,255,255,0.18), transparent)",
            display: "flex", alignItems: "center", gap: 20,
            justifyContent: "center",
          }}>
            <div style={{ fontFamily: "var(--mono)", fontSize: 10.5, letterSpacing: "0.3em", color: "var(--ink-faint)" }}>{s}</div>
            {Array.from({ length: 5 }).map((_, k) => (
              <div key={k} style={{ width: 6, height: 6, borderRadius: "50%", background: i === 3 ? "rgba(118,185,0,0.5)" : "rgba(255,255,255,0.25)" }} />
            ))}
          </div>
        ))}
      </div>

      {/* the statement exchange */}
      <div style={{ position: "relative", height: 130, width: "100%", display: "grid", placeItems: "center" }}>
        <div style={{ position: "absolute", inset: 0, display: "grid", placeItems: "center", opacity: noBest * (1 - bestFit) }}>
          <Statement text="There is no best GPU." op={noBest} size="clamp(30px, 3.6vw, 54px)" />
        </div>
        <div style={{ position: "absolute", inset: 0, display: "grid", placeItems: "center", opacity: bestFit * (1 - decide * 0.6) }}>
          <Statement text="There is a best fit." op={bestFit} size="clamp(30px, 3.6vw, 54px)" mark={[null, "fit", null]} />
        </div>
        <div style={{ position: "absolute", inset: 0, display: "grid", placeItems: "center", opacity: decide }}>
          <Statement text="Start with the model." op={decide} size="clamp(32px, 4vw, 60px)" green />
        </div>
      </div>

      {/* the three paths light in turn */}
      <div style={{ position: "absolute", bottom: 130, left: 0, right: 0, display: "flex", justifyContent: "center", gap: 26 }}>
        {PATHS.map((p, i) => {
          const on = litIdx === i;
          return (
            <div key={p.gpu} style={{
              width: 230, padding: "14px 18px", borderRadius: 10,
              border: on ? "1px solid rgba(118,185,0,0.7)" : "1px solid rgba(255,255,255,0.14)",
              background: on ? "rgba(118,185,0,0.1)" : "rgba(255,255,255,0.03)",
              boxShadow: on ? "0 0 40px rgba(118,185,0,0.25)" : "none",
              transition: "all 0.6s",
            }}>
              <div style={{ fontFamily: "var(--mono)", fontSize: 11, letterSpacing: "0.2em", color: on ? "var(--green-bright)" : "var(--ink-faint)" }}>{p.label}</div>
              <div style={{ fontFamily: "var(--sans)", fontSize: 19, fontWeight: 700, color: on ? "var(--ink)" : "var(--ink-dim)", marginTop: 6 }}>{p.gpu}</div>
              <div style={{ fontFamily: "var(--mono)", fontSize: 10.5, letterSpacing: "0.1em", color: "var(--ink-faint)", marginTop: 4 }}>{p.note}</div>
            </div>
          );
        })}
      </div>
    </SceneShell>
  );
}
