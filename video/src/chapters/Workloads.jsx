// 0:30–1:35 — LOCAL AI IS NOT ONE WORKLOAD
// The model landscape resolves: one small model moves forward, activates,
// drops onto an abstract GPU (green path, immediate inference) — then a
// much larger dense model arrives with its memory footprint expanding.
// CAN IT RUN? pause. HOW FAST CAN IT RUN? pause. "Completely different questions."
import { motion } from "framer-motion";
import { SceneShell, Statement, ModelBlock, MemoryContainer, EASE } from "../prims.jsx";
import { after, clamp01 } from "../clock.js";
import { SCENES, sceneIndexAt } from "../timeline.js";

const SCENE = SCENES[1];

export default function Workloads({ t }) {
  const lt = t - SCENE.from;
  const landscape = after(lt, 0.5, 1.2);   // resolve the model field
  const small = after(lt, 4.5, 1.0);        // small model moves forward
  const smallRun = after(lt, 9.5, 0.8);     // data flows, drops onto GPU
  const large = after(lt, 14.5, 1.2);      // large model approaches
  const memExp = after(lt, 18.5, 1.4);      // its memory footprint expands
  const canRun = after(lt, 22, 0.6);        // CAN IT RUN?
  const howFast = after(lt, 25, 0.6);       // HOW FAST CAN IT RUN?
  const different = after(lt, 29, 0.8);     // breathing room

  // small model's GPU (abstract) — green success path
  const gpuOn = smallRun > 0.5;

  return (
    <SceneShell>
      {/* deep landscape backdrop */}
      <div style={{ position: "absolute", inset: 0, opacity: landscape * 0.5 }}>
        {Array.from({ length: 60 }).map((_, i) => (
          <div key={i} style={{
            position: "absolute", left: `${(i * 41) % 100}%`, top: `${(i * 29) % 100}%`,
            width: i % 8 === 0 ? 8 : 3.5, height: i % 8 === 0 ? 8 : 3.5,
            background: "rgba(255,255,255,0.18)", borderRadius: 1, opacity: 0.5,
          }} />
        ))}
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: 90, opacity: 0.25 + large * 0.75 }}>
        {/* small model, forward, active */}
        <div style={{ transform: `translateZ(${small * 60}px) scale(${0.9 + small * 0.15})`, transition: "none" }}>
          <ModelBlock size={0.7} active={smallRun > 0.4} label="SMALL · FAST" opacity={landscape} layers={5} />
          {gpuOn && (
            <div style={{ marginTop: 26, textAlign: "center" }}>
              <div style={{ width: 110, height: 64, margin: "0 auto", border: "1px solid rgba(118,185,0,0.55)", borderRadius: 8, background: "linear-gradient(160deg, rgba(118,185,0,0.12), rgba(10,13,22,0.9))", position: "relative", boxShadow: "0 0 34px rgba(118,185,0,0.25)" }}>
                <div style={{ position: "absolute", left: "50%", top: "50%", transform: "translate(-50%,-50%)", fontFamily: "var(--mono)", fontSize: 10, letterSpacing: "0.18em", color: "var(--ink-dim)" }}>GPU</div>
              </div>
              <div style={{ fontFamily: "var(--mono)", fontSize: 11, letterSpacing: "0.14em", color: "var(--green-bright)", marginTop: 8 }}>✓ immediate inference</div>
            </div>
          )}
        </div>

        {/* large dense model + expanding memory container */}
        <div style={{ opacity: large }}>
          <ModelBlock size={1.9} active={false} label="DENSE · LARGE" opacity={large} layers={9} />
          <div style={{ marginTop: 22, display: "flex", gap: 26, alignItems: "flex-start" }}>
            <MemoryContainer fill={memExp >= 1 ? 0.92 : 0.4 + memExp * 0.5} model={0.55 + memExp * 0.3} context={0} label="GPU MEMORY" tension={memExp > 0.8} delay={0} />
            <div style={{ display: "flex", flexDirection: "column", gap: 22 }}>
              <Statement text="CAN IT RUN?" op={canRun * (1 - howFast * 0.3)} size="clamp(20px, 2vw, 30px)" />
              <Statement text="HOW FAST CAN IT RUN?" mark={[null, "HOW FAST", null]} op={howFast} size="clamp(20px, 2vw, 30px)" />
            </div>
          </div>
        </div>
      </div>

      <div style={{ position: "absolute", bottom: 190, opacity: different }}>
        <Statement text="Completely different questions." op={different} size="clamp(22px, 2.2vw, 34px)" />
      </div>
    </SceneShell>
  );
}
