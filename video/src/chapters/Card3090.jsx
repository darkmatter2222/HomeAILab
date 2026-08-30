// 2:55–3:45 — THE 3090
// We discover the context viz exists above an RTX 3090. Older hardware,
// relatively inexpensive, still extremely relevant. The model landscape
// returns with a green zone the 3090 handles comfortably, a gray
// transitional zone, then a boundary. Model blocks flow toward it: some
// drop in effortlessly, some compress, one stops at the boundary.
import { motion } from "framer-motion";
import { SceneShell, Statement, HardwareUnit, MemoryContainer, EASE } from "../prims.jsx";
import { after, clamp01 } from "../clock.js";
import { SCENES } from "../timeline.js";

const SCENE = SCENES[4];

// incoming model blocks: comfortable → compressed → stopped at boundary
const INCOMING = [
  { label: "7B Q4", fit: 1, compress: 0 },
  { label: "13B Q5", fit: 1, compress: 0.5 },
  { label: "27B Q4", fit: 1, compress: 0.7 },
  { label: "70B Q4", fit: 0, compress: 1 },
];

export default function Card3090({ t }) {
  const lt = t - SCENE.from;
  const label = after(lt, 1.5, 0.8);
  const rotate = clamp01((lt - 5) / 1.6);
  const zones = after(lt, 14, 1.2);
  const boundary = after(lt, 17, 1.0);
  const flow = clamp01((lt - 20) / 12); // blocks flow in over 20..32s
  const stopLine = after(lt, 25, 1.0);

  return (
    <SceneShell>
      {/* zone map: green comfortable, gray transitional, boundary */}
      <div style={{ position: "absolute", top: 70, left: "50%", transform: "translateX(-50%)", width: "min(880px, 74vw)", opacity: zones, display: "flex", alignItems: "stretch" }}>
        <div style={{ width: "52%", height: 44, borderRadius: "8px 0 0 8px", background: "linear-gradient(90deg, rgba(118,185,0,0.22), rgba(118,185,0,0.08))", border: "1px solid rgba(118,185,0,0.4)", borderRight: 0, display: "flex", alignItems: "center", padding: "0 18px", fontFamily: "var(--mono)", fontSize: 11.5, letterSpacing: "0.18em", color: "var(--green-bright)" }}>
          COMFORTABLE
        </div>
        <div style={{ width: "30%", height: 44, background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.14)", borderRight: 0, display: "flex", alignItems: "center", justifyContent: "center", fontFamily: "var(--mono)", fontSize: 11.5, letterSpacing: "0.18em", color: "var(--ink-faint)" }}>
          COMPRESS · QUANTIZE
        </div>
        <div style={{ width: "18%", height: 44, background: "rgba(255,255,255,0.02)", display: "flex", alignItems: "center", justifyContent: "center", fontFamily: "var(--mono)", fontSize: 11.5, letterSpacing: "0.18em", color: "var(--ink-faint)", opacity: 0.9 }}>
          OUT
        </div>
        {/* boundary line */}
        <motion.div
          initial={{ opacity: 0 }} animate={{ opacity: boundary }}
          style={{ position: "absolute", left: "82%", top: -14, bottom: -14, width: 1.5, background: "linear-gradient(180deg, transparent, var(--green), transparent)", boxShadow: "0 0 14px var(--green-glow)" }}
        />
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: 70 }}>
        {/* the 3090 — rotates slightly and stops */}
        <motion.div
          initial={{ rotateY: 0 }}
          animate={{ rotateY: rotate * 14 }}
          transition={{ duration: 0.1, ease: "linear" }}
          style={{ perspective: 900 }}
        >
          <HardwareUnit name="RTX 3090" sub="OLDER · CHEAPER · STILL RELEVANT" accent delay={0} width={240} active={flow > 0.3} />
        </motion.div>

        <MemoryContainer
          fill={0.4 + flow * 0.45}
          model={0.45}
          context={flow * 0.35}
          label="24 GB"
          caption="how far before you need something newer?"
          tension={flow > 0.75}
        />

        {/* incoming model blocks */}
        <div style={{ display: "flex", flexDirection: "column", gap: 22 }}>
          {INCOMING.map((m, i) => {
            const appear = flow > i / INCOMING.length;
            const stopped = !m.fit && flow > (i + 1) / INCOMING.length;
            return (
              <motion.div
                key={m.label}
                initial={{ opacity: 0, x: 60 }}
                animate={{ opacity: appear ? 1 : 0, x: appear ? (stopped ? 40 : 0) : 60 }}
                transition={{ duration: 0.9, ease: EASE }}
                style={{ display: "flex", alignItems: "center", gap: 12 }}
              >
                <div style={{
                  width: 46, height: 38, borderRadius: 6,
                  border: `1px solid ${stopped ? "rgba(255,255,255,0.2)" : "rgba(118,185,0,0.5)"}`,
                  background: stopped ? "rgba(255,255,255,0.05)" : "rgba(118,185,0,0.16)",
                  opacity: 1 - m.compress * 0.5,
                }} />
                <div>
                  <div style={{ fontFamily: "var(--mono)", fontSize: 12.5, letterSpacing: "0.1em", color: stopped ? "var(--ink-dim)" : "var(--ink)" }}>{m.label}</div>
                  <div style={{ fontFamily: "var(--mono)", fontSize: 10.5, letterSpacing: "0.12em", color: stopped ? "var(--ink-faint)" : m.compress > 0 ? "var(--ink-dim)" : "var(--green-bright)" }}>
                    {stopped ? "STOPS AT THE BOUNDARY" : m.compress > 0 ? "quantized to fit" : "drops in effortlessly"}
                  </div>
                </div>
              </motion.div>
            );
          })}
        </div>
      </div>

      <div style={{ position: "absolute", bottom: 195, opacity: boundary }}>
        <Statement text="How far can you get before you need something newer?" op={boundary} size="clamp(22px, 2.3vw, 34px)" />
      </div>
    </SceneShell>
  );
}
