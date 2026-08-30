// 9:10–9:35 — EXISTING OWNERS
// ALREADY OWN THE HARDWARE? Don't upgrade because of a faster benchmark.
// Find the practical limit of what you own: MODEL SIZE, CONTEXT,
// QUANTIZATION, LATENCY, CONCURRENCY. Upgrade when your workload crosses
// that line. Not before.
import { motion } from "framer-motion";
import { SceneShell, Statement, EASE } from "../prims.jsx";
import { after, clamp01 } from "../clock.js";
import { SCENES } from "../timeline.js";

const SCENE = SCENES[12];

const LIMITS = ["MODEL SIZE", "CONTEXT", "QUANTIZATION", "LATENCY", "CONCURRENCY"];

export default function Owners({ t }) {
  const lt = t - SCENE.from;
  const title = after(lt, 1.5, 0.8);
  const silhouettes = after(lt, 5, 1.0);
  const limits = clamp01((lt - 9) / 10);   // one by one 9..19s
  const cross = after(lt, 20, 1.0);

  return (
    <SceneShell>
      <div style={{ opacity: title }}>
        <Statement text="Already own the hardware?" op={title} size="clamp(26px, 2.8vw, 44px)" />
      </div>

      {/* machine silhouettes */}
      <div style={{ display: "flex", gap: 70, marginTop: 40, opacity: silhouettes }}>
        {["3090", "5090", "SPARK"].map((n, i) => (
          <div key={n} style={{ textAlign: "center" }}>
            <div style={{
              width: 130, height: 66, borderRadius: 8,
              border: "1px solid rgba(255,255,255,0.22)",
              background: "linear-gradient(160deg, rgba(255,255,255,0.07), rgba(255,255,255,0.02))",
              boxShadow: "0 20px 50px rgba(0,0,0,0.5)",
            }} />
            <div style={{ fontFamily: "var(--mono)", fontSize: 11, letterSpacing: "0.2em", color: "var(--ink-faint)", marginTop: 10 }}>
              {n === "SPARK" ? "DGX SPARK" : `RTX ${n}`}
            </div>
          </div>
        ))}
      </div>

      {/* the practical limits, one by one */}
      <div style={{ display: "flex", gap: 14, marginTop: 54 }}>
        {LIMITS.map((l, i) => {
          const on = limits > (i + 1) / LIMITS.length;
          return (
            <div key={l} style={{
              padding: "12px 18px", borderRadius: 8,
              border: on ? "1px solid rgba(118,185,0,0.6)" : "1px solid rgba(255,255,255,0.12)",
              background: on ? "rgba(118,185,0,0.1)" : "rgba(255,255,255,0.03)",
              fontFamily: "var(--mono)", fontSize: 12, letterSpacing: "0.16em",
              color: on ? "var(--green-bright)" : "var(--ink-faint)",
              transition: "all 0.5s",
            }}>
              {l}
            </div>
          );
        })}
      </div>

      <div style={{ position: "absolute", bottom: 200, opacity: cross }}>
        <Statement text="Upgrade when your workload crosses that line." op={cross} size="clamp(20px, 2.4vw, 34px)" />
        <div style={{ fontFamily: "var(--mono)", fontSize: 12, letterSpacing: "0.3em", color: "var(--ink-faint)", marginTop: 12 }}>
          NOT BEFORE
        </div>
      </div>
    </SceneShell>
  );
}
