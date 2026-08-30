// 3:45–4:35 — THE 5090
// A different problem. When the workload fits, raw compute is incredibly
// valuable: a tight agentic loop — model → GPU → response → agent → tool →
// model — with faster, denser data movement. Then the wall: a larger model
// approaches the memory container and doesn't fit. The green compute network
// stays powerful but idle.
import { motion } from "framer-motion";
import { SceneShell, Statement, HardwareUnit, MemoryContainer, FlowLine, EASE } from "../prims.jsx";
import { after, clamp01 } from "../clock.js";
import { SCENES } from "../timeline.js";

const SCENE = SCENES[5];

const LOOP = ["model", "GPU", "response", "agent", "tool"];

export default function Card5090({ t }) {
  const lt = t - SCENE.from;
  const intro = after(lt, 1.5, 1.0);
  const loopOn = after(lt, 6, 1.0);       // the tight agentic loop ignites
  const wall = after(lt, 16, 1.0);        // "but there's still a wall"
  const big = after(lt, 19, 1.2);         // large model approaches
  const idle = after(lt, 24, 1.2);        // compute network, powerful but idle
  const hold = after(lt, 28, 1.0);        // hold the visual

  return (
    <SceneShell>
      <div style={{ display: "flex", alignItems: "center", gap: 80 }}>
        {/* the 5090 + the tight loop */}
        <div style={{ opacity: intro }}>
          <HardwareUnit name="RTX 5090" sub="RAW COMPUTE · WHEN IT FITS" accent delay={0} width={250} active={loopOn > 0.5 && !idle} />
          <div style={{ marginTop: 30, display: "flex", alignItems: "center", gap: 4, opacity: loopOn }}>
            {LOOP.map((s, i) => (
              <div key={s} style={{ display: "flex", alignItems: "center", gap: 4 }}>
                <motion.div
                  animate={loopOn > 0.6 ? { opacity: [0.5, 1, 0.5], boxShadow: ["0 0 0px rgba(118,185,0,0)", "0 0 18px rgba(118,185,0,0.5)", "0 0 0px rgba(118,185,0,0)"] } : {}}
                  transition={{ duration: 1.4, repeat: Infinity, delay: i * 0.28 }}
                  style={{
                    padding: "8px 12px", borderRadius: 6,
                    border: "1px solid rgba(118,185,0,0.45)",
                    background: "rgba(118,185,0,0.1)",
                    fontFamily: "var(--mono)", fontSize: 11.5, letterSpacing: "0.14em", color: "var(--green-bright)",
                  }}
                >
                  {s}
                </motion.div>
                {i < LOOP.length - 1 && (
                  <div style={{ width: 18, height: 1.5, background: "linear-gradient(90deg, transparent, var(--green))" }} />
                )}
              </div>
            ))}
            {/* close the loop back */}
            <div style={{ width: 18, height: 1.5, background: "linear-gradient(90deg, transparent, var(--green))" }} />
          </div>
          <div style={{ fontFamily: "var(--mono)", fontSize: 11, letterSpacing: "0.16em", color: "var(--ink-faint)", marginTop: 10, opacity: loopOn }}>
            TIGHT LOOP · DENSE DATA MOVEMENT
          </div>
        </div>

        {/* the wall: memory container + a model that doesn't fit */}
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 20, opacity: wall }}>
          <div style={{ position: "relative" }}>
            <MemoryContainer
              fill={big > 0.5 ? 0.85 : 0.55}
              model={big > 0.5 ? 0.8 : 0.5}
              context={0}
              label="32 GB"
              tension={big > 0.5}
            />
            {/* oversized model approaching */}
            <motion.div
              initial={{ opacity: 0, y: -30 }}
              animate={{ opacity: big, y: 0 }}
              transition={{ duration: 1.2, ease: EASE }}
              style={{
                position: "absolute", top: -46, left: "50%", transform: "translateX(-50%)",
                width: 230, height: 96, borderRadius: 10,
                border: "1px solid rgba(255,255,255,0.3)",
                background: "rgba(255,255,255,0.06)",
                display: "flex", alignItems: "center", justifyContent: "center",
                fontFamily: "var(--mono)", fontSize: 11.5, letterSpacing: "0.18em", color: "var(--ink-dim)",
                boxShadow: "0 0 0 8px rgba(4,5,10,0.5)",
              }}
            >
              DOESN'T FIT
            </motion.div>
          </div>
          {/* idle compute network */}
          <div style={{ width: 240, height: 70, position: "relative", opacity: idle }}>
            <FlowLine x1={5} y1={50} x2={95} y2={50} active={false} />
            {Array.from({ length: 7 }).map((_, i) => (
              <div key={i} style={{
                position: "absolute", left: `${8 + i * 13}%`, top: "50%",
                width: 8, height: 8, borderRadius: 2, transform: "translateY(-50%)",
                background: "rgba(118,185,0,0.5)",
                boxShadow: "0 0 14px rgba(118,185,0,0.4)",
                opacity: 0.35 + idle * 0.3,
              }} />
            ))}
            <div style={{ position: "absolute", left: 0, right: 0, bottom: -22, textAlign: "center", fontFamily: "var(--mono)", fontSize: 10.5, letterSpacing: "0.2em", color: "var(--ink-faint)" }}>
              COMPUTE · POWERFUL · IDLE
            </div>
          </div>
        </div>
      </div>

      <div style={{ position: "absolute", bottom: 195, opacity: hold }}>
        <Statement text="All that compute doesn't help if the workload can't fit." op={hold} size="clamp(24px, 2.5vw, 38px)" />
      </div>
    </SceneShell>
  );
}
