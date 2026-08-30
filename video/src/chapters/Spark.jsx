// 4:35–5:25 — DGX SPARK
// Space over speed. Memory volume expands outward; a giant model descends
// into it and fits. The 5090 appears in the background: the same model
// doesn't fit there, Spark stays active. It changes which models are
// available at all. Then the trade: slower data movement.
import { motion } from "framer-motion";
import { SceneShell, Statement, HardwareUnit, EASE } from "../prims.jsx";
import { after, clamp01 } from "../clock.js";
import { SCENES } from "../timeline.js";

const SCENE = SCENES[6];

export default function Spark({ t }) {
  const lt = t - SCENE.from;
  const label = after(lt, 1.5, 0.8);
  const space = after(lt, 5, 1.4);        // memory volume expands outward
  const descend = clamp01((lt - 9) / 4);   // giant model descends
  const fits = after(lt, 13, 0.8);        // it fits
  const compare = after(lt, 17.5, 1.2);    // 5090 appears: doesn't fit
  const available = after(lt, 24, 1.0);    // "which models are available at all"
  const trade = after(lt, 29, 1.2);        // the slower trade

  return (
    <SceneShell>
      <div style={{ display: "flex", alignItems: "center", gap: 90 }}>
        {/* the Spark: a spacious vessel */}
        <div style={{ position: "relative" }}>
          <HardwareUnit name="DGX SPARK" sub="SPACE · NOT SPEED" accent delay={0} width={270} active={fits} />
          {/* expanding memory volume rings */}
          {[1, 2, 3].map((r) => (
            <motion.div
              key={r}
              initial={{ opacity: 0, scale: 0.7 }}
              animate={{ opacity: space / r, scale: 1 }}
              transition={{ duration: 1.2, ease: EASE, delay: r * 0.25 }}
              style={{
                position: "absolute", left: "50%", top: "55%",
                width: 320 + r * 90, height: 190 + r * 60,
                transform: "translate(-50%,-50%)",
                borderRadius: 18,
                border: "1px solid rgba(118,185,0,0.28)",
                boxShadow: "0 0 40px rgba(118,185,0,0.08) inset",
                pointerEvents: "none",
              }}
            />
          ))}
          <div style={{ position: "absolute", top: "55%", left: "50%", transform: "translate(-50%,-50%)", fontFamily: "var(--mono)", fontSize: 12, letterSpacing: "0.22em", color: "var(--green-bright)", opacity: space }}>
            122 GiB UNIFIED
          </div>
        </div>

        {/* giant model descending in */}
        <motion.div
          initial={{ opacity: 0, y: -70 }}
          animate={{ opacity: descend > 0.1 ? 1 : 0, y: descend >= 1 ? 40 : -70 }}
          transition={{ duration: 2, ease: EASE }}
          style={{ textAlign: "center" }}
        >
          <div style={{
            width: 190, height: 190, borderRadius: 12,
            border: "1px solid rgba(255,255,255,0.35)",
            background: "linear-gradient(160deg, rgba(255,255,255,0.1), rgba(255,255,255,0.03))",
            display: "grid", placeItems: "center",
            boxShadow: fits ? "0 0 50px rgba(118,185,0,0.3)" : "0 30px 80px rgba(0,0,0,0.5)",
            transition: "box-shadow 0.8s",
          }}>
            <div style={{ width: 120, height: 120, borderRadius: 8, border: "1px solid rgba(255,255,255,0.2)", background: "rgba(255,255,255,0.06)", display: "grid", placeItems: "center", fontFamily: "var(--mono)", fontSize: 12, letterSpacing: "0.2em", color: "var(--ink-dim)" }}>
              GIANT
            </div>
          </div>
          <div style={{ fontFamily: "var(--mono)", fontSize: 11.5, letterSpacing: "0.2em", color: fits ? "var(--green-bright)" : "var(--ink-faint)", marginTop: 12 }}>
            {descend >= 1 ? (fits ? "✓ IT FITS" : "DESCENDING") : "DESCENDING"}
          </div>
        </motion.div>

        {/* the 5090 in the background: same model, doesn't fit */}
        <div style={{ opacity: compare, display: "flex", flexDirection: "column", gap: 14 }}>
          <div style={{
            width: 210, height: 96, borderRadius: 8,
            border: "1px solid rgba(255,255,255,0.2)",
            background: "rgba(255,255,255,0.04)",
            display: "flex", alignItems: "center", justifyContent: "center",
            fontFamily: "var(--mono)", fontSize: 12, letterSpacing: "0.18em", color: "var(--ink-dim)",
          }}>
            5090 · 32 GB — SAME MODEL
          </div>
          <div style={{ fontFamily: "var(--mono)", fontSize: 11, letterSpacing: "0.16em", color: "var(--ink-faint)" }}>
            DOESN'T FIT
          </div>
        </div>
      </div>

      {/* the trade: slower flow comparison */}
      <div style={{ position: "absolute", bottom: 250, display: "flex", gap: 40, opacity: trade }}>
        {[{ n: "5090", speed: "fast", w: 150, active: true }, { n: "SPARK", speed: "slower", w: 150, active: false }].map((r) => (
          <div key={r.n} style={{ textAlign: "center" }}>
            <div style={{ position: "relative", height: 26, width: r.w }}>
              <div style={{ position: "absolute", inset: 0, background: "rgba(255,255,255,0.06)", borderRadius: 3 }} />
              <div style={{
                position: "absolute", left: 0, top: 0, bottom: 0, width: r.active ? "78%" : "34%",
                background: r.active ? "linear-gradient(90deg, rgba(118,185,0,0.5), rgba(118,185,0,0.15))" : "rgba(255,255,255,0.16)",
                borderRadius: 3,
              }} />
            </div>
            <div style={{ fontFamily: "var(--mono)", fontSize: 10.5, letterSpacing: "0.18em", color: r.active ? "var(--green-bright)" : "var(--ink-faint)", marginTop: 8 }}>
              {r.n} DATA · {r.speed}
            </div>
          </div>
        ))}
      </div>

      <div style={{ position: "absolute", bottom: 195 }}>
        <Statement text="It changes which models are available to you at all." op={available} size="clamp(22px, 2.4vw, 36px)" />
        <div style={{ height: 14 }} />
        <Statement text="A different trade." op={trade} size="clamp(16px, 1.8vw, 24px)" />
      </div>
    </SceneShell>
  );
}
