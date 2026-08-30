// 9:50–10:00 — OPEN LOOP INTO VIDEO TWO
// Everything fades except the 3090. A modern model appears behind it — too
// large-looking for the old GPU. The model begins loading, the 3090
// activates. FINAL VISUAL: HOW FAR CAN A 3090 GO? Cut to black.
import { motion } from "framer-motion";
import { SceneShell, Statement, EASE } from "../prims.jsx";
import { after, clamp01 } from "../clock.js";
import { SCENES } from "../timeline.js";

const SCENE = SCENES[14];

export default function OpenLoop({ t }) {
  const lt = t - SCENE.from;
  const focus = after(lt, 0.5, 0.8);   // everything except the 3090 fades
  const model = after(lt, 2.5, 0.9);    // the modern model appears
  const loading = clamp01((lt - 4) / 3); // model begins loading
  const final = after(lt, 6.5, 0.8);    // the final question
  const black = after(lt, 9.3, 0.6);    // cut to black

  return (
    <div style={{ position: "relative", width: "100%", height: "100%", display: "flex", alignItems: "center", justifyContent: "center" }}>
      <div style={{ opacity: focus * (1 - black), display: "flex", flexDirection: "column", alignItems: "center", gap: 36 }}>
        {/* the modern model, too large for the old card */}
        <motion.div
          initial={{ opacity: 0, scale: 0.8 }}
          animate={{ opacity: model, scale: 1 }}
          transition={{ duration: 1, ease: EASE }}
          style={{ textAlign: "center" }}
        >
          <div style={{
            width: 170, height: 150, borderRadius: 12,
            border: "1px solid rgba(255,255,255,0.35)",
            background: "linear-gradient(160deg, rgba(255,255,255,0.1), rgba(255,255,255,0.03))",
            display: "grid", placeItems: "center",
            boxShadow: "0 30px 80px rgba(0,0,0,0.55)",
          }}>
            <div style={{ fontFamily: "var(--mono)", fontSize: 11.5, letterSpacing: "0.18em", color: "var(--ink-dim)" }}>
              MODERN MODEL
            </div>
            <div style={{ fontFamily: "var(--mono)", fontSize: 10, letterSpacing: "0.14em", color: "var(--ink-faint)", marginTop: 6 }}>
              TOO LARGE?
            </div>
          </div>
          {/* loading bar */}
          <div style={{ width: 170, height: 5, background: "rgba(255,255,255,0.08)", borderRadius: 3, marginTop: 14, overflow: "hidden" }}>
            <div style={{
              width: `${loading * 100}%`, height: "100%",
              background: "linear-gradient(90deg, var(--green-dim), var(--green))",
              boxShadow: "0 0 12px var(--green-glow)",
            }} />
          </div>
        </motion.div>

        {/* the 3090, activating */}
        <div style={{ textAlign: "center" }}>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            style={{
              width: 200, height: 100, borderRadius: 10,
              border: "1px solid rgba(118,185,0,0.6)",
              background: "linear-gradient(160deg, rgba(118,185,0,0.14), rgba(10,13,22,0.9))",
              boxShadow: loading > 0.3 ? "0 0 50px rgba(118,185,0,0.3)" : "0 20px 60px rgba(0,0,0,0.55)",
              transition: "box-shadow 0.8s",
            }}
          />
          <div style={{ fontFamily: "var(--mono)", fontSize: 12, letterSpacing: "0.24em", color: "var(--ink-dim)", marginTop: 12 }}>
            RTX 3090
          </div>
        </div>
      </div>

      {/* the final question + cut to black */}
      <div style={{ position: "absolute", inset: 0, display: "grid", placeItems: "center", opacity: final * (1 - black) }}>
        <Statement text="How far can a 3090 go?" op={final} size="clamp(34px, 4.4vw, 66px)" green />
      </div>
      <div style={{ position: "absolute", inset: 0, background: "var(--bg)", opacity: black }} />
    </div>
  );
}
